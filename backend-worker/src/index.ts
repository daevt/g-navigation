export interface Env {
  VIETMAP_API_KEY?: string;
  CLIENT_TOKEN?: string;
  DEFAULT_VEHICLE?: string;
  ALLOW_OSM_FALLBACK?: string;
}

export interface RouteStep {
  maneuverType: string;
  text: string;
  roadName: string;
  distanceMeters: number;
  durationSeconds: number;
  location: [number, number];
  interval: [number, number];
}

export interface NormalizedRouteResponse {
  routeId: string;
  provider: "vietmap" | "osm-fallback";
  vehicle: string;
  distanceMeters: number;
  durationSeconds: number;
  points: [number, number][];
  steps: RouteStep[];
}

export interface CompactRoadSegment {
  /** Tên đường (rỗng nếu không tên) */
  n: string;
  /** Cấp đường: 1 = trục chính, 2 = đường phố, 3 = đường nội bộ/hẻm */
  c: 1 | 2 | 3;
  /** Danh sách tọa độ [lat, lng] đã rút gọn */
  p: [number, number][];
}

const CORS_HEADERS: Record<string, string> = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
  "Access-Control-Allow-Headers": "Content-Type, Authorization, X-Client-Token",
};

export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    if (request.method === "OPTIONS") {
      return new Response(null, { status: 204, headers: CORS_HEADERS });
    }

    // Kiểm tra CLIENT_TOKEN nếu người dùng có đặt mật khẩu bảo vệ Worker cá nhân
    if (env.CLIENT_TOKEN) {
      const token =
        request.headers.get("X-Client-Token") ||
        new URL(request.url).searchParams.get("token");
      if (token !== env.CLIENT_TOKEN) {
        return jsonResponse({ error: "Unauthorized: Invalid X-Client-Token" }, 401);
      }
    }

    const url = new URL(request.url);
    const path = url.pathname;

    try {
      if (path === "/" || path === "/health") {
        return jsonResponse({
          ok: true,
          service: "g-navigation-worker",
          vietmapConfigured: Boolean(env.VIETMAP_API_KEY),
          osmFallbackEnabled: env.ALLOW_OSM_FALLBACK !== "false",
          timestamp: new Date().toISOString(),
        });
      }

      if (path === "/api/route") {
        return await handleRouteRequest(url, env);
      }

      if (path === "/api/roads") {
        return await handleRoadsRequest(request, url, ctx);
      }

      if (path === "/api/search") {
        return await handleSearchRequest(url, env);
      }

      return jsonResponse({ error: "Not found", path }, 404);
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : String(err);
      return jsonResponse({ error: message }, 500);
    }
  },
};

/**
 * Xử lý tìm đường xe máy qua VIETMAP Route API (ưu tiên) hoặc OSRM fallback
 * Query: ?origin=10.776889,106.700806&dest=10.7825,106.6952&vehicle=motorcycle
 */
async function handleRouteRequest(url: URL, env: Env): Promise<Response> {
  const originStr = url.searchParams.get("origin");
  const destStr = url.searchParams.get("dest");
  const vehicle = url.searchParams.get("vehicle") || env.DEFAULT_VEHICLE || "motorcycle";

  if (!originStr || !destStr) {
    return jsonResponse(
      { error: "Thiếu tham số origin hoặc dest (ví dụ: ?origin=10.7768,106.7008&dest=10.7825,106.6952)" },
      400
    );
  }

  const origin = parseLatLng(originStr);
  const dest = parseLatLng(destStr);
  if (!origin || !dest) {
    return jsonResponse({ error: "Tọa độ origin hoặc dest không hợp lệ" }, 400);
  }

  if (env.VIETMAP_API_KEY && env.VIETMAP_API_KEY !== "YOUR_VIETMAP_API_KEY") {
    try {
      const route = await fetchVietmapRoute(origin, dest, vehicle, env.VIETMAP_API_KEY);
      return jsonResponse(route);
    } catch (vietmapErr) {
      if (env.ALLOW_OSM_FALLBACK === "false") {
        throw vietmapErr;
      }
      // Nếu lỗi hạn mức hoặc key chưa kích hoạt, chuyển sang OSM fallback nếu cho phép
    }
  }

  if (env.ALLOW_OSM_FALLBACK !== "false") {
    const fallbackRoute = await fetchOsmFallbackRoute(origin, dest, vehicle);
    return jsonResponse(fallbackRoute);
  }

  return jsonResponse(
    { error: "Chưa cấu hình VIETMAP_API_KEY và ALLOW_OSM_FALLBACK đang tắt." },
    503
  );
}

async function fetchVietmapRoute(
  origin: [number, number],
  dest: [number, number],
  vehicle: string,
  apiKey: string
): Promise<NormalizedRouteResponse> {
  // VIETMAP Route API hỗ trợ vehicle=motorcycle và points_encoded=true
  const endpoint = new URL("https://maps.vietmap.vn/api/route");
  endpoint.searchParams.set("api-version", "1.1");
  endpoint.searchParams.set("apikey", apiKey);
  endpoint.searchParams.append("point", `${origin[0]},${origin[1]}`);
  endpoint.searchParams.append("point", `${dest[0]},${dest[1]}`);
  endpoint.searchParams.set("vehicle", vehicle);
  endpoint.searchParams.set("points_encoded", "true");

  const res = await fetch(endpoint.toString(), {
    headers: { Accept: "application/json" },
  });

  if (!res.ok) {
    const body = await res.text();
    throw new Error(`VIETMAP Route error (${res.status}): ${body.slice(0, 200)}`);
  }

  const data: any = await res.json();
  const path = data?.paths?.[0];
  if (!path) {
    throw new Error("VIETMAP không trả về tuyến đường hợp lệ.");
  }

  const rawPoints: [number, number][] =
    typeof path.points === "string"
      ? decodePolyline(path.points, 5)
      : Array.isArray(path.points?.coordinates)
      ? path.points.coordinates.map((c: [number, number]) => [round6(c[1]), round6(c[0])])
      : [];

  const instructions: any[] = Array.isArray(path.instructions) ? path.instructions : [];
  const steps: RouteStep[] = instructions.map((inst) => {
    const interval: [number, number] = Array.isArray(inst.interval)
      ? [Number(inst.interval[0]) || 0, Number(inst.interval[1]) || 0]
      : [0, 0];
    const pt = rawPoints[interval[0]] || origin;
    const roadName = sanitizeRoadName(inst.street_name || inst.text || "");
    return {
      maneuverType: mapVietmapSignToManeuver(Number(inst.sign || 0)),
      text: String(inst.text || roadName || "Đi thẳng"),
      roadName: roadName || extractRoadFromInstruction(String(inst.text || "")),
      distanceMeters: Math.round(Number(inst.distance || 0)),
      durationSeconds: Math.round(Number(inst.time || 0) / 1000),
      location: pt,
      interval,
    };
  });

  return {
    routeId: `vm_${Date.now().toString(36)}`,
    provider: "vietmap",
    vehicle,
    distanceMeters: Math.round(Number(path.distance || 0)),
    durationSeconds: Math.round(Number(path.time || 0) / 1000),
    points: simplifyPolyline(rawPoints, 0.00003),
    steps,
  };
}

async function fetchOsmFallbackRoute(
  origin: [number, number],
  dest: [number, number],
  vehicle: string
): Promise<NormalizedRouteResponse> {
  // Dùng OSRM công cộng cho giai đoạn thử nghiệm 0 đồng khi chưa gắn VIETMAP_API_KEY
  const coords = `${origin[1]},${origin[0]};${dest[1]},${dest[0]}`;
  const osrmUrl = `https://router.project-osrm.org/route/v1/driving/${coords}?overview=full&geometries=polyline&steps=true`;

  const res = await fetch(osrmUrl, {
    headers: { "User-Agent": "GNavigation-Worker/1.0" },
  });
  if (!res.ok) {
    throw new Error(`OSRM fallback error (${res.status})`);
  }

  const data: any = await res.json();
  const route = data?.routes?.[0];
  if (!route) {
    throw new Error("Không tìm thấy đường đi từ OSRM fallback.");
  }

  const points = decodePolyline(route.geometry, 5);
  const rawSteps: any[] = route.legs?.[0]?.steps || [];

  const steps: RouteStep[] = rawSteps.map((s) => {
    const loc = s.maneuver?.location
      ? ([round6(s.maneuver.location[1]), round6(s.maneuver.location[0])] as [number, number])
      : origin;
    const mType = mapOsrmManeuver(s.maneuver?.type, s.maneuver?.modifier);
    const roadName = sanitizeRoadName(s.name || s.ref || "Đường phía trước");
    return {
      maneuverType: mType,
      text: buildVietnameseInstruction(mType, roadName),
      roadName,
      distanceMeters: Math.round(Number(s.distance || 0)),
      durationSeconds: Math.round(Number(s.duration || 0)),
      location: loc,
      interval: [0, 0],
    };
  });

  return {
    routeId: `osm_${Date.now().toString(36)}`,
    provider: "osm-fallback",
    vehicle,
    distanceMeters: Math.round(Number(route.distance || 0)),
    durationSeconds: Math.round(Number(route.duration || 0)),
    points: simplifyPolyline(points, 0.00003),
    steps,
  };
}

/**
 * Trích xuất các đoạn đường xung quanh vị trí xe máy để đồng hồ tự vẽ bằng Canvas.
 * Có lưu bộ nhớ đệm (Cache) theo ô lưới ~300m trên Cloudflare Edge.
 */
async function handleRoadsRequest(
  request: Request,
  url: URL,
  ctx: ExecutionContext
): Promise<Response> {
  const lat = Number(url.searchParams.get("lat"));
  const lng = Number(url.searchParams.get("lng"));
  const radius = Math.min(600, Math.max(150, Number(url.searchParams.get("radius") || 320)));

  if (!Number.isFinite(lat) || !Number.isFinite(lng)) {
    return jsonResponse({ error: "Tham số lat và lng là bắt buộc" }, 400);
  }

  // Quy tròn về lưới ~300m (0.003 độ) để tối ưu cache
  const tileLat = Math.round(lat * 333);
  const tileLng = Math.round(lng * 333);
  const tileId = `${tileLat}_${tileLng}`;

  const cacheUrl = new URL(request.url);
  cacheUrl.search = `?tile=${tileId}&r=${radius}`;
  const cacheKey = new Request(cacheUrl.toString(), { method: "GET" });
  const cache = caches.default;

  const cached = await cache.match(cacheKey);
  if (cached) {
    return cached;
  }

  const centerLat = tileLat / 333;
  const centerLng = tileLng / 333;

  const overpassQuery = `[out:json][timeout:10];(way["highway"~"^(trunk|primary|secondary|tertiary|residential|unclassified|service)$"](around:${radius},${centerLat.toFixed(6)},${centerLng.toFixed(6)}););out geom;`;

  const overpassRes = await fetch("https://overpass-api.de/api/interpreter", {
    method: "POST",
    headers: {
      "Content-Type": "application/x-www-form-urlencoded",
      "User-Agent": "GNavigation-Worker/1.0",
    },
    body: `data=${encodeURIComponent(overpassQuery)}`,
  });

  if (!overpassRes.ok) {
    return jsonResponse({ tile: tileId, roads: [] });
  }

  const osmData: any = await overpassRes.json();
  const elements: any[] = Array.isArray(osmData?.elements) ? osmData.elements : [];

  const roads: CompactRoadSegment[] = [];
  for (const el of elements) {
    if (el.type !== "way" || !Array.isArray(el.geometry) || el.geometry.length < 2) {
      continue;
    }
    const hw = String(el.tags?.highway || "");
    const roadClass: 1 | 2 | 3 =
      hw === "trunk" || hw === "primary"
        ? 1
        : hw === "secondary" || hw === "tertiary"
        ? 2
        : 3;

    const rawPts: [number, number][] = el.geometry.map((g: { lat: number; lon: number }) => [
      round6(g.lat),
      round6(g.lon),
    ]);
    const simplified = simplifyPolyline(rawPts, 0.00004);
    if (simplified.length < 2) continue;

    roads.push({
      n: sanitizeRoadName(el.tags?.name || ""),
      c: roadClass,
      p: simplified,
    });

    // Giới hạn tối đa 45 đoạn đường quanh xe để nhẹ băng thông P2P sang đồng hồ
    if (roads.length >= 45) break;
  }

  const response = jsonResponse(
    {
      tile: tileId,
      center: [round6(centerLat), round6(centerLng)],
      roads,
    },
    200,
    {
      "Cache-Control": "public, max-age=86400",
    }
  );

  ctx.waitUntil(cache.put(cacheKey, response.clone()));
  return response;
}

/**
 * Tìm kiếm địa điểm qua VIETMAP Search v3 hoặc Nominatim fallback
 */
async function handleSearchRequest(url: URL, env: Env): Promise<Response> {
  const q = (url.searchParams.get("q") || "").trim();
  const lat = url.searchParams.get("lat") || "10.776889";
  const lng = url.searchParams.get("lng") || "106.700806";

  if (!q) {
    return jsonResponse({ results: [] });
  }

  if (env.VIETMAP_API_KEY && env.VIETMAP_API_KEY !== "YOUR_VIETMAP_API_KEY") {
    try {
      const searchUrl = new URL("https://maps.vietmap.vn/api/search/v3");
      searchUrl.searchParams.set("apikey", env.VIETMAP_API_KEY);
      searchUrl.searchParams.set("text", q);
      searchUrl.searchParams.set("focus", `${lat},${lng}`);

      const res = await fetch(searchUrl.toString());
      if (res.ok) {
        const items: any[] = await res.json();
        const topItems = items.slice(0, 6);
        const results = await Promise.all(
          topItems.map(async (item) => {
            if (item.lat && item.lng) {
              return {
                name: item.name || item.display || q,
                address: item.address || item.display || "",
                lat: Number(item.lat),
                lng: Number(item.lng),
              };
            }
            if (item.ref_id) {
              const placeUrl = `https://maps.vietmap.vn/api/place/v3?apikey=${encodeURIComponent(
                env.VIETMAP_API_KEY!
              )}&refid=${encodeURIComponent(item.ref_id)}`;
              const pRes = await fetch(placeUrl);
              if (pRes.ok) {
                const pData: any = await pRes.json();
                return {
                  name: item.name || pData.name || q,
                  address: item.address || pData.address || "",
                  lat: Number(pData.lat),
                  lng: Number(pData.lng),
                };
              }
            }
            return null;
          })
        );
        return jsonResponse({
          provider: "vietmap",
          results: results.filter((r) => r && Number.isFinite(r.lat) && Number.isFinite(r.lng)),
        });
      }
    } catch {
      // Chuyển sang Nominatim fallback bên dưới
    }
  }

  const nomUrl = `https://nominatim.openstreetmap.org/search?format=json&countrycodes=vn&limit=6&q=${encodeURIComponent(
    q
  )}`;
  const nomRes = await fetch(nomUrl, {
    headers: { "User-Agent": "GNavigation-Worker/1.0" },
  });
  const nomItems: any[] = nomRes.ok ? await nomRes.json() : [];

  return jsonResponse({
    provider: "osm-fallback",
    results: nomItems.map((item) => ({
      name: String(item.display_name || q).split(",")[0],
      address: String(item.display_name || ""),
      lat: Number(item.lat),
      lng: Number(item.lon),
    })),
  });
}

// --- Các hàm tiện ích xử lý hình học & chuẩn hóa ---

function parseLatLng(raw: string): [number, number] | null {
  const parts = raw.split(",").map((s) => Number(s.trim()));
  if (parts.length !== 2 || !Number.isFinite(parts[0]) || !Number.isFinite(parts[1])) {
    return null;
  }
  return [parts[0], parts[1]];
}

function mapVietmapSignToManeuver(sign: number): string {
  switch (sign) {
    case -3:
      return "SHARP_LEFT";
    case -2:
      return "TURN_LEFT";
    case -1:
      return "SLIGHT_LEFT";
    case 0:
      return "STRAIGHT";
    case 1:
      return "SLIGHT_RIGHT";
    case 2:
      return "TURN_RIGHT";
    case 3:
      return "SHARP_RIGHT";
    case 4:
    case 5:
      return "ARRIVE";
    case 6:
      return "ROUNDABOUT";
    case -98:
    case 7:
    case 8:
      return "UTURN";
    default:
      return "STRAIGHT";
  }
}

function mapOsrmManeuver(type?: string, modifier?: string): string {
  if (type === "arrive") return "ARRIVE";
  if (type === "roundabout" || type === "rotary") return "ROUNDABOUT";
  if (modifier === "uturn") return "UTURN";
  if (modifier === "sharp left") return "SHARP_LEFT";
  if (modifier === "left") return "TURN_LEFT";
  if (modifier === "slight left") return "SLIGHT_LEFT";
  if (modifier === "sharp right") return "SHARP_RIGHT";
  if (modifier === "right") return "TURN_RIGHT";
  if (modifier === "slight right") return "SLIGHT_RIGHT";
  return "STRAIGHT";
}

function buildVietnameseInstruction(maneuverType: string, road: string): string {
  const target = road ? ` vào ${road}` : "";
  switch (maneuverType) {
    case "TURN_LEFT":
      return `Rẽ trái${target}`;
    case "TURN_RIGHT":
      return `Rẽ phải${target}`;
    case "SLIGHT_LEFT":
      return `Chếch sang trái${target}`;
    case "SLIGHT_RIGHT":
      return `Chếch sang phải${target}`;
    case "SHARP_LEFT":
      return `Rẽ ngoặt trái${target}`;
    case "SHARP_RIGHT":
      return `Rẽ ngoặt phải${target}`;
    case "UTURN":
      return `Quay đầu${target}`;
    case "ROUNDABOUT":
      return `Vào vòng xuyến${target}`;
    case "ARRIVE":
      return "Đã đến điểm đích";
    default:
      return `Đi thẳng${target}`;
  }
}

function sanitizeRoadName(name: string): string {
  return name.trim().slice(0, 34);
}

function extractRoadFromInstruction(text: string): string {
  const match = text.match(/(?:vào|trên|đường|phố)\s+([^,.]+)/i);
  return match ? sanitizeRoadName(match[1]) : sanitizeRoadName(text);
}

function decodePolyline(encoded: string, precision = 5): [number, number][] {
  const factor = Math.pow(10, precision);
  let index = 0;
  let lat = 0;
  let lng = 0;
  const coordinates: [number, number][] = [];

  while (index < encoded.length) {
    let shift = 0;
    let result = 0;
    let byte: number;
    do {
      byte = encoded.charCodeAt(index++) - 63;
      result |= (byte & 0x1f) << shift;
      shift += 5;
    } while (byte >= 0x20);
    const deltaLat = result & 1 ? ~(result >> 1) : result >> 1;
    lat += deltaLat;

    shift = 0;
    result = 0;
    do {
      byte = encoded.charCodeAt(index++) - 63;
      result |= (byte & 0x1f) << shift;
      shift += 5;
    } while (byte >= 0x20);
    const deltaLng = result & 1 ? ~(result >> 1) : result >> 1;
    lng += deltaLng;

    coordinates.push([round6(lat / factor), round6(lng / factor)]);
  }
  return coordinates;
}

/**
 * Rút gọn polyline theo khoảng cách vuông góc Ramer-Douglas-Peucker
 * giúp giảm số điểm gửi qua Wear Engine P2P mà vẫn giữ đúng hình dáng đường.
 */
function simplifyPolyline(pts: [number, number][], epsilon: number): [number, number][] {
  if (pts.length <= 2) return pts;
  let maxDist = 0;
  let index = 0;
  const start = pts[0];
  const end = pts[pts.length - 1];

  for (let i = 1; i < pts.length - 1; i++) {
    const d = perpendicularDistance(pts[i], start, end);
    if (d > maxDist) {
      index = i;
      maxDist = d;
    }
  }

  if (maxDist > epsilon) {
    const left = simplifyPolyline(pts.slice(0, index + 1), epsilon);
    const right = simplifyPolyline(pts.slice(index), epsilon);
    return left.slice(0, left.length - 1).concat(right);
  }
  return [start, end];
}

function perpendicularDistance(
  pt: [number, number],
  lineStart: [number, number],
  lineEnd: [number, number]
): number {
  const dx = lineEnd[1] - lineStart[1];
  const dy = lineEnd[0] - lineStart[0];
  const mag = Math.hypot(dx, dy);
  if (mag === 0) {
    return Math.hypot(pt[1] - lineStart[1], pt[0] - lineStart[0]);
  }
  const u =
    ((pt[1] - lineStart[1]) * dx + (pt[0] - lineStart[0]) * dy) / (mag * mag);
  const clampedU = Math.max(0, Math.min(1, u));
  const projX = lineStart[1] + clampedU * dx;
  const projY = lineStart[0] + clampedU * dy;
  return Math.hypot(pt[1] - projX, pt[0] - projY);
}

function round6(val: number): number {
  return Math.round(val * 1e6) / 1e6;
}

function jsonResponse(
  body: unknown,
  status = 200,
  extraHeaders: Record<string, string> = {}
): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: {
      "Content-Type": "application/json; charset=utf-8",
      ...CORS_HEADERS,
      ...extraHeaders,
    },
  });
}
