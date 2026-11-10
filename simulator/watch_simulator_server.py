#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
G Navigation — Máy ảo iPhone (iOS App) + Trạm P2P kết nối trực tiếp với DevEco Studio Watch Emulator
- Cổng: http://localhost:8787/iphone
- Tương tác trực tiếp 100% thời gian thực với máy ảo đồng hồ HarmonyOS (DevEco Emulator 127.0.0.1:5555)
  và điện thoại iPhone thật qua mạng Wi-Fi LAN.
"""

import json
import math
import os
import socket
import threading
import time
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORT = 8787


def load_vietmap_api_key() -> str:
    env_key = os.environ.get("VIETMAP_API_KEY", "").strip()
    if env_key:
        return env_key
    for candidate in (".env", "../.env", "backend-worker/.dev.vars"):
        if os.path.exists(candidate):
            try:
                with open(candidate, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line.startswith("VIETMAP_API_KEY="):
                            return line.split("=", 1)[1].strip().strip('"').strip("'")
            except Exception:
                pass
    return ""


VIETMAP_API_KEY = load_vietmap_api_key()


def get_lan_ip() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


STATE_LOCK = threading.Lock()
ROAD_TILE_CACHE: dict[str, list[dict]] = {}

WATCH_HUB = {
    "lastPacketTs": time.time(),
    "mode": "LIVE_P2P",
    "bluetoothEnabled": True,
    "state": {
        "t": "S",
        "seq": 1,
        "ts": int(time.time()),
        "lat": 10.775840,
        "lng": 106.700420,
        "hdg": 42,
        "spd": 32,
        "mType": "TURN_RIGHT",
        "mDist": 85,
        "road": "Nguyễn Huệ",
        "eta": "14:25",
        "rem": 1250,
        "vib": 0,
        "reroute": False,
    },
    "routeId": "init_q1",
    "routePoints": [
        [10.774500, 106.698900],
        [10.775150, 106.699650],
        [10.775840, 106.700420],
        [10.776480, 106.701120],
        [10.775800, 106.701950],
        [10.775100, 106.702800],
        [10.774450, 106.703600],
    ],
    "routeChunks": {},
    "roadsTile": "init_tile",
    "roads": [
        {
            "n": "Lê Lợi",
            "c": 1,
            "p": [
                [10.773800, 106.698100],
                [10.775150, 106.699650],
                [10.776480, 106.701120],
                [10.777600, 106.702400],
            ],
        },
        {
            "n": "Nguyễn Huệ",
            "c": 1,
            "p": [
                [10.777400, 106.700100],
                [10.776480, 106.701120],
                [10.775100, 106.702800],
                [10.773600, 106.704600],
            ],
        },
        {
            "n": "Pasteur",
            "c": 2,
            "p": [
                [10.776900, 106.698200],
                [10.775500, 106.699800],
                [10.774000, 106.701500],
            ],
        },
        {
            "n": "Nam Kỳ Khởi Nghĩa",
            "c": 1,
            "p": [
                [10.776100, 106.697400],
                [10.774700, 106.699000],
                [10.773200, 106.700700],
            ],
        },
        {
            "n": "Đồng Khởi",
            "c": 2,
            "p": [
                [10.778200, 106.701800],
                [10.776600, 106.703500],
                [10.775000, 106.705200],
            ],
        },
    ],
    "roadChunks": {},
    "steps": [],
    "packetsReceived": 1,
    "recentLogs": [],
}


def add_log(msg: str) -> None:
    ts = time.strftime("%H:%M:%S")
    WATCH_HUB["recentLogs"].insert(0, f"[{ts}] {msg}")
    if len(WATCH_HUB["recentLogs"]) > 60:
        WATCH_HUB["recentLogs"].pop()


def process_p2p_packet(pkt: dict) -> None:
    with STATE_LOCK:
        if not WATCH_HUB["bluetoothEnabled"]:
            add_log("Đã chặn gói P2P do Bluetooth đang tắt (Kiểm thử Mốc 4)")
            return

        pkt_type = pkt.get("t", "")
        if not pkt_type:
            return
        WATCH_HUB["lastPacketTs"] = time.time()
        WATCH_HUB["packetsReceived"] += 1
        WATCH_HUB["mode"] = "LIVE_P2P"

        if pkt_type == "H":
            add_log("iOS -> Watch [H] Heartbeat giữ kết nối")
            return

        if pkt_type == "S":
            WATCH_HUB["state"] = {
                "t": "S",
                "seq": int(pkt.get("seq", WATCH_HUB["state"]["seq"] + 1)),
                "ts": int(pkt.get("ts", time.time())),
                "lat": float(pkt.get("lat", WATCH_HUB["state"]["lat"])),
                "lng": float(pkt.get("lng", WATCH_HUB["state"]["lng"])),
                "hdg": int(pkt.get("hdg", WATCH_HUB["state"]["hdg"])),
                "spd": int(pkt.get("spd", 0)),
                "mType": str(pkt.get("mType", "STRAIGHT")),
                "mDist": int(pkt.get("mDist", 0)),
                "road": str(pkt.get("road", "")),
                "eta": str(pkt.get("eta", "--:--")),
                "rem": int(pkt.get("rem", 0)),
                "vib": int(pkt.get("vib", 0)),
                "reroute": bool(pkt.get("reroute", False)),
            }
            add_log(
                f"iOS -> Watch [S#{WATCH_HUB['state']['seq']}] {WATCH_HUB['state']['mType']} "
                f"{WATCH_HUB['state']['mDist']}m · {WATCH_HUB['state']['road']}"
            )
            return

        if pkt_type == "R":
            r_id = str(pkt.get("id", "rt"))
            idx = int(pkt.get("idx", 0))
            tot = int(pkt.get("tot", 1))
            pts = pkt.get("pts", [])
            if r_id != WATCH_HUB["routeId"]:
                WATCH_HUB["routeId"] = r_id
                WATCH_HUB["routeChunks"] = {}
            WATCH_HUB["routeChunks"][idx] = pts
            merged = []
            for c in range(tot):
                part = WATCH_HUB["routeChunks"].get(c, [])
                merged.extend(part)
            if len(merged) >= 2:
                WATCH_HUB["routePoints"] = merged
            add_log(f"iOS -> Watch [R] Gói tuyến đường {idx + 1}/{tot} ({len(pts)} tọa độ)")
            return

        if pkt_type == "M":
            tile = str(pkt.get("tile", "tile"))
            idx = int(pkt.get("idx", 0))
            tot = int(pkt.get("tot", 1))
            rds = pkt.get("rds", [])
            if tile != WATCH_HUB["roadsTile"]:
                WATCH_HUB["roadsTile"] = tile
                WATCH_HUB["roadChunks"] = {}
            WATCH_HUB["roadChunks"][idx] = rds
            merged_roads = []
            for c in range(tot):
                part = WATCH_HUB["roadChunks"].get(c, [])
                merged_roads.extend(part)
            if merged_roads:
                WATCH_HUB["roads"] = merged_roads
            add_log(f"iOS -> Watch [M] Gói đường nền {idx + 1}/{tot} ({len(rds)} đường)")


def fetch_overpass_roads(lat: float, lng: float, radius: int = 340) -> tuple[str, list[dict]]:
    tile_lat = round(lat * 333)
    tile_lng = round(lng * 333)
    tile_id = f"{tile_lat}_{tile_lng}"
    if tile_id in ROAD_TILE_CACHE:
        return tile_id, ROAD_TILE_CACHE[tile_id]

    c_lat = tile_lat / 333.0
    c_lng = tile_lng / 333.0
    query = (
        f'[out:json][timeout:8];'
        f'(way["highway"~"^(trunk|primary|secondary|tertiary|residential|unclassified|service)$"]'
        f'(around:{radius},{c_lat:.6f},{c_lng:.6f}););out geom;'
    )
    try:
        req = urllib.request.Request(
            "https://overpass-api.de/api/interpreter",
            data=f"data={urllib.parse.quote(query)}".encode("utf-8"),
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "User-Agent": "GNavigation-iOS-Sim/1.0",
            },
        )
        with urllib.request.urlopen(req, timeout=9) as resp:
            osm = json.loads(resp.read().decode("utf-8"))
        roads = []
        for el in osm.get("elements", []):
            geom = el.get("geometry") or []
            if len(geom) < 2:
                continue
            hw = str((el.get("tags") or {}).get("highway", ""))
            r_class = 1 if hw in ("trunk", "primary") else (2 if hw in ("secondary", "tertiary") else 3)
            name = str((el.get("tags") or {}).get("name", "")).strip()[:32]
            pts = [[round(g["lat"], 6), round(g["lon"], 6)] for g in geom]
            # Rút gọn điểm nếu quá dày
            if len(pts) > 8:
                step = max(1, len(pts) // 6)
                pts = pts[::step] + ([pts[-1]] if pts[-1] != pts[::step][-1] else [])
            roads.append({"n": name, "c": r_class, "p": pts})
            if len(roads) >= 42:
                break
        if roads:
            ROAD_TILE_CACHE[tile_id] = roads
            return tile_id, roads
    except Exception as e:
        add_log(f"Overpass fallback: {e}")

    with STATE_LOCK:
        return tile_id, WATCH_HUB["roads"]


def decode_polyline5(encoded: str) -> list[list[float]]:
    index = 0
    lat = 0
    lng = 0
    coords: list[list[float]] = []
    length = len(encoded)
    while index < length:
        shift = 0
        result = 0
        while True:
            b = ord(encoded[index]) - 63
            index += 1
            result |= (b & 0x1F) << shift
            shift += 5
            if b < 0x20:
                break
        dlat = ~(result >> 1) if (result & 1) else (result >> 1)
        lat += dlat

        shift = 0
        result = 0
        while True:
            b = ord(encoded[index]) - 63
            index += 1
            result |= (b & 0x1F) << shift
            shift += 5
            if b < 0x20:
                break
        dlng = ~(result >> 1) if (result & 1) else (result >> 1)
        lng += dlng

        coords.append([round(lat / 1e5, 6), round(lng / 1e5, 6)])
    return coords


def map_vietmap_sign(sign: int) -> str:
    return {
        -3: "SHARP_LEFT",
        -2: "TURN_LEFT",
        -1: "SLIGHT_LEFT",
        0: "STRAIGHT",
        1: "SLIGHT_RIGHT",
        2: "TURN_RIGHT",
        3: "SHARP_RIGHT",
        4: "ARRIVE",
        5: "ARRIVE",
        6: "ROUNDABOUT",
        -98: "UTURN",
        7: "UTURN",
        8: "UTURN",
    }.get(sign, "STRAIGHT")


def fetch_osrm_route(origin_lat: float, origin_lng: float, dest_lat: float, dest_lng: float) -> dict:
    # Ưu tiên gọi VIETMAP Route v1.1/v4 với vehicle=motorcycle nếu đã có VIETMAP_API_KEY
    if VIETMAP_API_KEY:
        try:
            vm_url = (
                f"https://maps.vietmap.vn/api/route?api-version=1.1"
                f"&apikey={urllib.parse.quote(VIETMAP_API_KEY)}"
                f"&point={origin_lat:.6f},{origin_lng:.6f}"
                f"&point={dest_lat:.6f},{dest_lng:.6f}"
                f"&vehicle=motorcycle&points_encoded=true"
            )
            req = urllib.request.Request(vm_url, headers={"User-Agent": "GNavigation-iOS-Sim/1.0"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                vm_data = json.loads(resp.read().decode("utf-8"))
            path = (vm_data.get("paths") or [None])[0]
            if path:
                pts = (
                    decode_polyline5(path["points"])
                    if isinstance(path.get("points"), str)
                    else [[round(c[1], 6), round(c[0], 6)] for c in path.get("points", {}).get("coordinates", [])]
                )
                steps = []
                for inst in path.get("instructions") or []:
                    interval = inst.get("interval") or [0, 0]
                    idx0 = min(max(0, int(interval[0])), max(0, len(pts) - 1))
                    pt = pts[idx0] if pts else [origin_lat, origin_lng]
                    road = str(inst.get("street_name") or inst.get("text") or "Đường phía trước").strip()[:34]
                    steps.append(
                        {
                            "maneuverType": map_vietmap_sign(int(inst.get("sign") or 0)),
                            "text": str(inst.get("text") or road),
                            "roadName": road,
                            "distanceMeters": int(round(float(inst.get("distance") or 0))),
                            "durationSeconds": int(round(float(inst.get("time") or 0) / 1000.0)),
                            "location": pt,
                            "interval": [int(interval[0]), int(interval[1])],
                        }
                    )
                add_log(
                    f"VIETMAP Route (motorcycle): {int(round(path.get('distance', 0)))}m, {len(steps)} chỉ dẫn"
                )
                return {
                    "routeId": f"vm_{int(time.time())}",
                    "provider": "vietmap",
                    "vehicle": "motorcycle",
                    "distanceMeters": int(round(float(path.get("distance") or 0))),
                    "durationSeconds": int(round(float(path.get("time") or 0) / 1000.0)),
                    "points": pts,
                    "steps": steps,
                }
        except Exception as e:
            add_log(f"VIETMAP Route lỗi ({e}), chuyển sang OSRM fallback...")

    coords = f"{origin_lng:.6f},{origin_lat:.6f};{dest_lng:.6f},{dest_lat:.6f}"
    url = f"https://router.project-osrm.org/route/v1/driving/{coords}?overview=full&geometries=geojson&steps=true"
    req = urllib.request.Request(url, headers={"User-Agent": "GNavigation-iOS-Sim/1.0"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    route = data["routes"][0]
    raw_coords = route["geometry"]["coordinates"]
    pts = [[round(c[1], 6), round(c[0], 6)] for c in raw_coords]
    steps = []
    for s in route.get("legs", [{}])[0].get("steps", []):
        man = s.get("maneuver", {})
        loc = man.get("location", [origin_lng, origin_lat])
        m_type = map_osrm_maneuver(man.get("type"), man.get("modifier"))
        road = (s.get("name") or "Đường phía trước").strip()
        steps.append(
            {
                "maneuverType": m_type,
                "text": road,
                "roadName": road,
                "distanceMeters": int(round(s.get("distance", 0))),
                "durationSeconds": int(round(s.get("duration", 0))),
                "location": [round(loc[1], 6), round(loc[0], 6)],
                "interval": [0, 0],
            }
        )

    result = {
        "routeId": f"rt_{int(time.time())}",
        "provider": "vietmap-osm",
        "vehicle": "motorcycle",
        "distanceMeters": int(round(route.get("distance", 0))),
        "durationSeconds": int(round(route.get("duration", 0))),
        "points": pts,
        "steps": steps,
    }
    return result


def map_osrm_maneuver(m_type: str | None, modifier: str | None) -> str:
    if m_type == "arrive":
        return "ARRIVE"
    if m_type in ("roundabout", "rotary"):
        return "ROUNDABOUT"
    mapping = {
        "uturn": "UTURN",
        "sharp left": "SHARP_LEFT",
        "left": "TURN_LEFT",
        "slight left": "SLIGHT_LEFT",
        "sharp right": "SHARP_RIGHT",
        "right": "TURN_RIGHT",
        "slight right": "SLIGHT_RIGHT",
    }
    return mapping.get(modifier or "", "STRAIGHT")


IPHONE_SIMULATOR_HTML = r"""<!DOCTYPE html>
<html lang="vi">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no" />
<title>G Navigation — iPhone 15 Pro Simulator (iOS)</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<style>
  :root {
    --ios-bg: #000000;
    --ios-card: #1c1c1e;
    --ios-card2: #2c2c2e;
    --ios-blue: #0a84ff;
    --ios-green: #30d158;
    --ios-orange: #ff9f0a;
    --ios-red: #ff453a;
    --ios-cyan: #64d2ff;
    --ios-text: #ffffff;
    --ios-sub: #8e8e93;
  }
  * { box-sizing: border-box; user-select: none; }
  body {
    margin: 0;
    background: #05070a;
    color: var(--ios-text);
    font-family: -apple-system, BlinkMacSystemFont, "SF Pro Display", "Segoe UI", sans-serif;
    height: 100vh;
    display: flex;
    flex-direction: column;
    overflow: hidden;
  }
  /* Thanh trạng thái iPhone + Dynamic Island */
  .ios-statusbar {
    height: 44px;
    padding: 0 22px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    font-size: 13px;
    font-weight: 600;
    background: #000;
    position: relative;
    flex-shrink: 0;
    z-index: 20;
  }
  .dynamic-island {
    width: 112px;
    height: 26px;
    background: #111;
    border-radius: 16px;
    border: 1px solid #222;
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 6px;
    font-size: 10px;
    color: var(--ios-green);
  }
  .island-dot {
    width: 7px;
    height: 7px;
    border-radius: 50%;
    background: var(--ios-green);
    animation: pulse 1.4s infinite;
  }
  @keyframes pulse {
    0%, 100% { opacity: 1; }
    50% { opacity: 0.35; }
  }
  /* Nội dung các Tab */
  .tab-container {
    flex: 1;
    position: relative;
    overflow: hidden;
    display: flex;
    flex-direction: column;
  }
  .tab-pane {
    display: none;
    flex-direction: column;
    height: 100%;
    width: 100%;
    overflow-y: auto;
  }
  .tab-pane.active {
    display: flex;
  }
  /* Tab 1: Bản đồ thật + Tìm kiếm + Điều hướng */
  .top-search-bar {
    padding: 10px 12px;
    background: rgba(28, 28, 30, 0.95);
    border-bottom: 1px solid #2c2c2e;
    z-index: 10;
  }
  .search-row {
    display: flex;
    gap: 6px;
  }
  .search-row input {
    flex: 1;
    background: #2c2c2e;
    border: none;
    color: #fff;
    padding: 9px 12px;
    border-radius: 10px;
    font-size: 13px;
    outline: none;
  }
  .ios-btn {
    background: var(--ios-blue);
    color: #fff;
    border: none;
    border-radius: 10px;
    padding: 8px 12px;
    font-size: 13px;
    font-weight: 600;
    cursor: pointer;
  }
  .ios-btn.green { background: var(--ios-green); color: #021a08; }
  .ios-btn.orange { background: var(--ios-orange); color: #1f1100; }
  .ios-btn.red { background: var(--ios-red); }
  .ios-btn.gray { background: var(--ios-card2); }
  .search-results {
    max-height: 150px;
    overflow-y: auto;
    margin-top: 6px;
    background: #252528;
    border-radius: 10px;
    display: none;
  }
  .search-item {
    padding: 8px 10px;
    border-bottom: 1px solid #333;
    cursor: pointer;
    font-size: 12px;
  }
  .search-item:hover { background: #3a3a3c; }
  #iosMap {
    flex: 1;
    width: 100%;
    min-height: 260px;
    z-index: 1;
  }
  /* Bảng điều khiển lái xe nổi dưới bản đồ */
  .nav-sheet {
    background: var(--ios-card);
    border-top: 1px solid #2c2c2e;
    padding: 10px 14px;
    z-index: 10;
  }
  .turn-preview {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 8px;
  }
  .turn-title {
    font-size: 16px;
    font-weight: 700;
    color: var(--ios-green);
  }
  .turn-sub {
    font-size: 12px;
    color: var(--ios-sub);
  }
  .quick-routes {
    display: flex;
    gap: 6px;
    overflow-x: auto;
    padding-bottom: 6px;
  }
  .chip {
    background: #2c2c2e;
    color: #e5e5ea;
    border: 1px solid #3a3a3c;
    border-radius: 999px;
    padding: 5px 10px;
    font-size: 11px;
    white-space: nowrap;
    cursor: pointer;
  }
  .chip:hover { border-color: var(--ios-blue); color: #fff; }
  /* Tab 2 & Tab 3 Cards */
  .ios-section {
    background: var(--ios-card);
    border-radius: 14px;
    padding: 14px;
    margin: 10px 12px 0 12px;
  }
  .ios-section h3 {
    margin: 0 0 8px 0;
    font-size: 14px;
    color: var(--ios-cyan);
  }
  .ios-section p {
    margin: 0 0 10px 0;
    font-size: 12px;
    color: var(--ios-sub);
    line-height: 1.4;
  }
  .mono-box {
    background: #000;
    padding: 8px 10px;
    border-radius: 8px;
    font-family: monospace;
    font-size: 12px;
    color: var(--ios-green);
    margin-bottom: 8px;
  }
  .log-list {
    background: #09090b;
    border-radius: 10px;
    padding: 8px;
    height: 220px;
    overflow-y: auto;
    font-family: monospace;
    font-size: 11px;
    color: #d1d1d6;
  }
  /* Thanh TabBar chuẩn iOS */
  .ios-tabbar {
    height: 58px;
    background: rgba(22, 22, 24, 0.98);
    border-top: 1px solid #2c2c2e;
    display: flex;
    justify-content: space-around;
    align-items: center;
    flex-shrink: 0;
    z-index: 20;
  }
  .tab-btn {
    background: none;
    border: none;
    color: var(--ios-sub);
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 3px;
    font-size: 10px;
    font-weight: 600;
    cursor: pointer;
  }
  .tab-btn.active { color: var(--ios-blue); }
  .tab-btn span.icon { font-size: 18px; }
  /* Màn hình khóa iPhone (iOS Lock Screen Overlay cho Mốc 2 & Mốc 4) */
  .lockscreen-overlay {
    position: absolute;
    inset: 0;
    background: linear-gradient(180deg, rgba(8,15,26,0.96), rgba(3,5,9,0.98));
    z-index: 100;
    display: none;
    flex-direction: column;
    align-items: center;
    justify-content: space-between;
    padding: 55px 24px 36px 24px;
    text-align: center;
  }
  .lockscreen-overlay.locked {
    display: flex;
  }
  .lock-clock {
    font-size: 64px;
    font-weight: 200;
    letter-spacing: -1px;
    margin-top: 10px;
  }
  .lock-date {
    font-size: 15px;
    color: #aeaeb2;
  }
  .lock-widget {
    width: 100%;
    background: rgba(28, 28, 30, 0.85);
    border: 1px solid #3a3a3c;
    border-radius: 18px;
    padding: 14px;
    text-align: left;
  }
</style>
</head>
<body>

<!-- Thanh trạng thái iPhone -->
<div class="ios-statusbar">
  <span id="iosClock">14:20</span>
  <div class="dynamic-island">
    <span class="island-dot" id="islandDot"></span>
    <span id="islandText">P2P Fit 4 Pro</span>
  </div>
  <span>5G 🔋98%</span>
</div>

<div class="tab-container">
  <!-- TAB 1: Dẫn đường & Bản đồ thật -->
  <div class="tab-pane active" id="tab-nav">
    <div class="top-search-bar">
      <div class="search-row">
        <input type="text" id="searchInput" placeholder="Tìm điểm đến tại VN (VD: Hồ Gươm, Chợ Bến Thành)..." onkeydown="if(event.key==='Enter')searchPlace()" />
        <button class="ios-btn" onclick="searchPlace()">Tìm</button>
      </div>
      <div class="search-results" id="searchResults"></div>
    </div>

    <!-- Bản đồ tương tác thật (Click để chọn đích hoặc Kéo xe máy để đi lệch tuyến!) -->
    <div id="iosMap"></div>

    <div class="nav-sheet">
      <div class="quick-routes">
        <span class="chip" onclick="startRealRoute(10.7721,106.6983, 10.7769,106.7032)">🛵 Bến Thành → Nhà hát TP</span>
        <span class="chip" onclick="startRealRoute(10.7769,106.7032, 10.7770,106.6953)">🛵 Nhà hát TP → Dinh Độc Lập</span>
        <span class="chip" onclick="startRealRoute(21.0285,105.8542, 21.0368,105.8347)">🛵 Hồ Gươm → Lăng Bác (Hà Nội)</span>
      </div>

      <div class="turn-preview">
        <div>
          <div class="turn-title" id="iosTurnDist">85 m · Rẽ phải</div>
          <div class="turn-sub" id="iosTurnRoad">Đường tiếp theo: Nguyễn Huệ</div>
        </div>
        <div style="text-align:right">
          <div style="font-size:15px;font-weight:700;color:var(--ios-cyan)" id="iosSpeed">32 km/h</div>
          <div class="turn-sub" id="iosEta">Còn 1.2 km</div>
        </div>
      </div>

      <div style="display:flex;gap:8px;">
        <button class="ios-btn green" style="flex:1" id="driveBtn" onclick="toggleDrive()">▶ Chạy xe GPS thật</button>
        <button class="ios-btn gray" onclick="stepOnce()">⏭ +1 Bước</button>
        <button class="ios-btn orange" onclick="lockIphoneScreen()" title="Khóa màn hình iPhone (Mốc 2 & 4)">🔒 Khóa iPhone</button>
      </div>
      <div style="font-size:11px;color:var(--ios-sub);margin-top:6px;">
        💡 <strong>Mẹo tương tác thật</strong>: Nhấp chuột bất kỳ lên bản đồ để đổi điểm đến, hoặc <strong>nắm kéo chấm xanh xe máy</strong> chệch khỏi vạch đường > 45m để thấy đồng hồ DevEco tự rung báo lệch tuyến và tính lại đường!
      </div>
    </div>
  </div>

  <!-- TAB 2: Kiểm thử Mốc 2 & Mốc 4 (Wear Engine P2P & Bluetooth) -->
  <div class="tab-pane" id="tab-m2">
    <div class="ios-section">
      <h3>1. Định danh iOS & Kết nối DevEco Watch Emulator</h3>
      <p>Máy ảo iPhone này đang phát trực tiếp từng gói tin P2P (<code>S</code>, <code>R</code>, <code>M</code>, <code>H</code>) sang ứng dụng <code>com.gnavigation.watch</code> đang chạy trên <strong>DevEco Studio Wearable Emulator</strong> của bạn.</p>
      <div class="mono-box">
        Bundle ID: com.gnavigation.ios<br/>
        Peer Watch: com.gnavigation.watch (Connected)<br/>
        Đã truyền: <span id="m2PktCount">0</span> gói P2P
      </div>
    </div>

    <div class="ios-section">
      <h3>2. Kiểm thử Mốc 2 (Chỉ dẫn mẫu & Khóa màn hình)</h3>
      <p>Gửi gói tin mẫu hoặc khóa màn hình iPhone trong khi xe đang chạy để kiểm tra đồng hồ DevEco Emulator vẫn nhận dữ liệu nền:</p>
      <div style="display:flex;flex-direction:column;gap:8px;">
        <button class="ios-btn green" onclick="sendSampleM2()">📨 Gửi chỉ dẫn mẫu + Cụm đường giả ngay</button>
        <button class="ios-btn orange" onclick="startDriveAndLock()">🔒 Bật chạy xe nền & Khóa màn hình iPhone ngay</button>
      </div>
    </div>

    <div class="ios-section">
      <h3>3. Kiểm thử Mốc 4 (Ngắt & Nối lại Bluetooth P2P)</h3>
      <p>Khi tắt Bluetooth quá 12 giây, đồng hồ DevEco sẽ tự động ẩn chỉ dẫn cũ và báo <em>"⚠ Mất dữ liệu từ iPhone"</em>. Khi bật lại Bluetooth, iPhone lập tức đồng bộ lại tuyến đường:</p>
      <button class="ios-btn red" id="btToggleBtn" style="width:100%" onclick="toggleBluetooth()">🔌 Tắt Bluetooth tới đồng hồ (Test mất kết nối)</button>
    </div>
  </div>

  <!-- TAB 3: Cấu hình & Nhật ký P2P -->
  <div class="tab-pane" id="tab-logs">
    <div class="ios-section">
      <h3>Cầu nối P2P thời gian thực (iOS ↔ HarmonyOS Emulator)</h3>
      <p>Mọi thao tác trên máy ảo iPhone này (hoặc từ iPhone thật qua <code>http://__LAN_IP__:8787</code>) đều được ghi lại bên dưới:</p>
      <div class="log-list" id="iosLogList"></div>
    </div>
  </div>

  <!-- Lớp phủ Màn hình khóa iPhone (Lock Screen) -->
  <div class="lockscreen-overlay" id="lockOverlay">
    <div>
      <div style="font-size:13px;color:var(--ios-green);font-weight:600">🔒 ĐANG KHÓA MÀN HÌNH IPHONE</div>
      <div class="lock-clock" id="lockClock">14:20</div>
      <div class="lock-date">Thứ Ba, 10 tháng 11</div>
    </div>

    <div class="lock-widget">
      <div style="font-size:11px;color:var(--ios-cyan);font-weight:700;margin-bottom:4px;">G NAVIGATION · ĐANG PHÁT P2P NỀN SANG ĐỒNG HỒ</div>
      <div style="font-size:16px;font-weight:700" id="lockNavTitle">Đang gửi GPS sang Fit 4 Pro...</div>
      <div style="font-size:12px;color:#aeaeb2;margin-top:3px" id="lockNavSub">Quan sát đồng hồ DevEco Emulator bên cạnh vẫn tự xoay bản đồ và đếm ngược khoảng cách!</div>
    </div>

    <button class="ios-btn" style="width:80%;padding:12px;border-radius:999px;font-size:15px" onclick="unlockIphoneScreen()">🔓 Mở khóa màn hình iPhone</button>
  </div>
</div>

<!-- Thanh điều hướng dưới cùng của iPhone -->
<div class="ios-tabbar">
  <button class="tab-btn active" id="btn-tab-nav" onclick="switchTab('nav')">
    <span class="icon">🧭</span>
    <span>Dẫn đường</span>
  </button>
  <button class="tab-btn" id="btn-tab-m2" onclick="switchTab('m2')">
    <span class="icon">⌚</span>
    <span>Kiểm thử Mốc 2 & 4</span>
  </button>
  <button class="tab-btn" id="btn-tab-logs" onclick="switchTab('logs')">
    <span class="icon">📡</span>
    <span>Nhật ký P2P</span>
  </button>
</div>

<script>
let map, riderMarker, destMarker, routeLine;
let currentRoute = [];
let currentSteps = [];
let routeIdx = 0;
let seqCounter = 10;
let driveTimer = null;
let btConnected = true;
let loadedTileKey = "";

function switchTab(name) {
  ['nav', 'm2', 'logs'].forEach(t => {
    document.getElementById('tab-' + t).classList.toggle('active', t === name);
    document.getElementById('btn-tab-' + t).classList.toggle('active', t === name);
  });
  if (name === 'nav' && map) {
    setTimeout(() => map.invalidateSize(), 100);
  }
}

function initMap() {
  map = L.map('iosMap', { zoomControl: false }).setView([10.77584, 106.70042], 16);
  L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
    maxZoom: 19,
    attribution: '&copy; OpenStreetMap'
  }).addTo(map);

  const riderIcon = L.divIcon({
    html: '<div style="width:22px;height:22px;border-radius:50%;background:#00e5ff;border:3px solid #fff;box-shadow:0 0 12px #00e5ff;"></div>',
    iconSize: [22, 22],
    iconAnchor: [11, 11]
  });

  riderMarker = L.marker([10.77584, 106.70042], { icon: riderIcon, draggable: true }).addTo(map);
  riderMarker.bindTooltip("Kéo tôi đi chệch đường để test Reroute!", { direction: "top" });

  // Khi người dùng nắm kéo xe máy trên bản đồ iPhone
  riderMarker.on('dragend', async function(e) {
    const pos = riderMarker.getLatLng();
    await handleManualRiderMove(pos.lat, pos.lng);
  });

  // Khi người dùng click bất kỳ lên bản đồ iPhone -> Đặt điểm đến mới và dẫn đường thật!
  map.on('click', async function(e) {
    const start = riderMarker.getLatLng();
    await startRealRoute(start.lat, start.lng, e.latlng.lat, e.latlng.lng);
  });

  // Tải sẵn tuyến đường ban đầu
  startRealRoute(10.7721, 106.6983, 10.7769, 106.7032);
}

async function sendP2P(packets) {
  await fetch('/api/p2p', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(packets)
  });
}

async function syncNearbyRoadsToWatch(lat, lng, force = false) {
  const tKey = `${Math.round(lat * 333)}_${Math.round(lng * 333)}`;
  if (!force && tKey === loadedTileKey) return;
  loadedTileKey = tKey;
  try {
    const res = await fetch(`/api/roads?lat=${lat}&lng=${lng}&radius=340`);
    const data = await res.json();
    if (data.roads && data.roads.length > 0) {
      // Chia thành các gói M giống hệt P2PPacketChunker.makeRoadChunks trên Swift
      const chunkSize = 6;
      const chunks = [];
      for (let i = 0; i < data.roads.length; i += chunkSize) {
        chunks.push(data.roads.slice(i, i + chunkSize));
      }
      const pkts = chunks.map((rds, idx) => ({
        t: 'M',
        tile: data.tile || tKey,
        idx: idx,
        tot: chunks.length,
        rds: rds
      }));
      await sendP2P(pkts);
    }
  } catch (e) {}
}

async function startRealRoute(oLat, oLng, dLat, dLng, isReroute = false) {
  try {
    riderMarker.setLatLng([oLat, oLng]);
    if (destMarker) map.removeLayer(destMarker);
    destMarker = L.marker([dLat, dLng]).addTo(map);

    const res = await fetch(`/api/route?origin=${oLat},${oLng}&dest=${dLat},${dLng}&vehicle=motorcycle`);
    const route = await res.json();
    if (!route.points || route.points.length < 2) return;

    currentRoute = route.points;
    currentSteps = route.steps || [];
    routeIdx = 0;

    if (routeLine) map.removeLayer(routeLine);
    routeLine = L.polyline(currentRoute, { color: '#30d158', weight: 6 }).addTo(map);
    if (!isReroute) {
      map.fitBounds(routeLine.getBounds(), { padding: [30, 30] });
    }

    // 1. Chia nhỏ tuyến đường thành các gói R gửi sang đồng hồ DevEco Emulator
    const maxPts = 22;
    const rChunks = [];
    for (let i = 0; i < currentRoute.length; i += maxPts) {
      const slice = currentRoute.slice(i, i + maxPts);
      if (i > 0 && rChunks.length > 0) {
        slice.unshift(rChunks[rChunks.length - 1][rChunks[rChunks.length - 1].length - 1]);
      }
      rChunks.push(slice);
    }
    const rPkts = rChunks.map((pts, idx) => ({
      t: 'R',
      id: route.routeId,
      idx: idx,
      tot: rChunks.length,
      pts: pts
    }));
    await sendP2P(rPkts);

    // 2. Tải mạng lưới đường phố xung quanh từ OpenStreetMap Overpass gửi sang đồng hồ
    await syncNearbyRoadsToWatch(oLat, oLng, true);

    // 3. Gửi gói trạng thái S đầu tiên
    await emitPositionAtIndex(0);
  } catch (e) {
    console.error(e);
  }
}

function haversineMeters(lat1, lon1, lat2, lon2) {
  const R = 6371000;
  const dLat = (lat2 - lat1) * Math.PI / 180;
  const dLon = (lon2 - lon1) * Math.PI / 180;
  const a = Math.sin(dLat/2)**2 + Math.cos(lat1*Math.PI/180)*Math.cos(lat2*Math.PI/180)*Math.sin(dLon/2)**2;
  return 2 * R * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
}

async function handleManualRiderMove(lat, lng) {
  if (currentRoute.length < 2) return;
  let minD = 999999;
  let closestIdx = 0;
  for (let i = 0; i < currentRoute.length; i++) {
    const d = haversineMeters(lat, lng, currentRoute[i][0], currentRoute[i][1]);
    if (d < minD) {
      minD = d;
      closestIdx = i;
    }
  }

  // Nếu kéo xe máy lệch khỏi tuyến > 42m -> Phát lệnh rung cảnh báo lệch tuyến (vib=3, reroute=true) lên đồng hồ rồi tự tính lại tuyến!
  if (minD > 42 && destMarker) {
    seqCounter += 1;
    document.getElementById('iosTurnDist').innerText = '⚠ Lệch tuyến (' + Math.round(minD) + 'm)';
    document.getElementById('iosTurnRoad').innerText = 'Đang tính lại đường mới...';

    await sendP2P({
      t: 'S',
      seq: seqCounter,
      ts: Math.floor(Date.now() / 1000),
      lat: lat,
      lng: lng,
      hdg: 0,
      spd: 28,
      mType: 'UTURN',
      mDist: Math.round(minD),
      road: 'Đang tính lại đường...',
      eta: '--:--',
      rem: 1000,
      vib: 3,
      reroute: true
    });

    setTimeout(async () => {
      const dest = destMarker.getLatLng();
      await startRealRoute(lat, lng, dest.lat, dest.lng, true);
    }, 1600);
  } else {
    routeIdx = closestIdx;
    await emitPositionAtIndex(routeIdx);
  }
}

async function emitPositionAtIndex(idx) {
  if (currentRoute.length < 2) return;
  const safeIdx = Math.min(idx, currentRoute.length - 1);
  const curr = currentRoute[safeIdx];
  const next = currentRoute[Math.min(safeIdx + 1, currentRoute.length - 1)];

  riderMarker.setLatLng([curr[0], curr[1]]);

  const dy = next[0] - curr[0];
  const dx = next[1] - curr[1];
  const hdg = (dy === 0 && dx === 0) ? 0 : Math.round((Math.atan2(dx, dy) * 180 / Math.PI + 360) % 360);

  // Tìm bước rẽ tiếp theo
  let nextStep = currentSteps.find(s => haversineMeters(curr[0], curr[1], s.location[0], s.location[1]) > 15) || currentSteps[currentSteps.length - 1];
  let mDist = nextStep ? Math.round(haversineMeters(curr[0], curr[1], nextStep.location[0], nextStep.location[1])) : 50;
  let mType = nextStep ? nextStep.maneuverType : 'STRAIGHT';
  let road = nextStep ? nextStep.roadName : 'Đường phía trước';

  if (safeIdx >= currentRoute.length - 1) {
    mType = 'ARRIVE';
    mDist = 0;
    road = 'Đã tới điểm đích';
  }

  let rem = 0;
  for (let i = safeIdx; i < currentRoute.length - 1; i++) {
    rem += haversineMeters(currentRoute[i][0], currentRoute[i][1], currentRoute[i+1][0], currentRoute[i+1][1]);
  }
  rem = Math.round(rem);

  const vib = mDist <= 35 && mDist > 10 ? 2 : (mDist <= 105 && mDist >= 75 ? 1 : 0);
  const spd = safeIdx >= currentRoute.length - 1 ? 0 : (32 + (safeIdx % 4) * 3);

  seqCounter += 1;
  const pkt = {
    t: 'S',
    seq: seqCounter,
    ts: Math.floor(Date.now() / 1000),
    lat: curr[0],
    lng: curr[1],
    hdg: hdg,
    spd: spd,
    mType: mType,
    mDist: mDist,
    road: road,
    eta: '14:28',
    rem: rem,
    vib: vib,
    reroute: false
  };

  document.getElementById('iosTurnDist').innerText = `${mDist} m · ${mType}`;
  document.getElementById('iosTurnRoad').innerText = `Đường kế: ${road}`;
  document.getElementById('iosSpeed').innerText = `${spd} km/h`;
  document.getElementById('iosEta').innerText = `Còn ${rem >= 1000 ? (rem/1000).toFixed(1) + ' km' : rem + ' m'}`;
  document.getElementById('lockNavTitle').innerText = `${mDist}m → ${road} (${spd} km/h)`;

  await sendP2P(pkt);
  await syncNearbyRoadsToWatch(curr[0], curr[1], false);
}

async function stepOnce() {
  if (currentRoute.length < 2) return;
  routeIdx = (routeIdx + 1) % currentRoute.length;
  await emitPositionAtIndex(routeIdx);
}

function toggleDrive() {
  const btn = document.getElementById('driveBtn');
  if (driveTimer) {
    clearInterval(driveTimer);
    driveTimer = null;
    btn.innerText = '▶ Chạy xe GPS thật';
    btn.className = 'ios-btn green';
  } else {
    stepOnce();
    driveTimer = setInterval(stepOnce, 1300);
    btn.innerText = '⏸ Đang lái xe (Bấm để dừng)';
    btn.className = 'ios-btn red';
  }
}

async function searchPlace() {
  const q = document.getElementById('searchInput').value.trim();
  if (!q) return;
  const res = await fetch('/api/search?q=' + encodeURIComponent(q));
  const data = await res.json();
  const box = document.getElementById('searchResults');
  if (!data.results || data.results.length === 0) {
    box.style.display = 'none';
    return;
  }
  box.style.display = 'block';
  box.innerHTML = data.results.map(r => `
    <div class="search-item" onclick="selectSearchResult(${r.lat}, ${r.lng}, '${r.name.replace(/'/g, "")}')">
      <strong>${r.name}</strong><br/>
      <span style="color:#8e8e93">${r.address}</span>
    </div>
  `).join('');
}

async function selectSearchResult(lat, lng, name) {
  document.getElementById('searchResults').style.display = 'none';
  document.getElementById('searchInput').value = name;
  const start = riderMarker.getLatLng();
  await startRealRoute(start.lat, start.lng, lat, lng);
}

function lockIphoneScreen() {
  document.getElementById('lockOverlay').classList.add('locked');
}

function unlockIphoneScreen() {
  document.getElementById('lockOverlay').classList.remove('locked');
}

function startDriveAndLock() {
  if (!driveTimer) toggleDrive();
  lockIphoneScreen();
}

async function sendSampleM2() {
  await emitPositionAtIndex(routeIdx);
}

async function toggleBluetooth() {
  btConnected = !btConnected;
  await fetch('/api/bluetooth', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ enabled: btConnected })
  });
  const btn = document.getElementById('btToggleBtn');
  const dot = document.getElementById('islandDot');
  const txt = document.getElementById('islandText');
  if (btConnected) {
    btn.innerText = '🔌 Tắt Bluetooth tới đồng hồ (Test mất kết nối)';
    btn.className = 'ios-btn red';
    dot.style.background = '#30d158';
    txt.innerText = 'P2P Fit 4 Pro';
    // Tự động đồng bộ lại toàn bộ tuyến đường ngay khi nối lại Bluetooth!
    await emitPositionAtIndex(routeIdx);
  } else {
    btn.innerText = '🔗 Bật lại Bluetooth (Tự động SYNC lại đồng hồ)';
    btn.className = 'ios-btn green';
    dot.style.background = '#ff453a';
    txt.innerText = 'Đã ngắt BT';
  }
}

async function refreshLogs() {
  try {
    const res = await fetch('/api/state');
    const data = await res.json();
    document.getElementById('m2PktCount').innerText = data.packetsReceived || 0;
    document.getElementById('iosLogList').innerHTML = (data.recentLogs || []).map(l => `<div>${l}</div>`).join('');
  } catch (e) {}
  const now = new Date();
  const hm = now.toTimeString().slice(0, 5);
  document.getElementById('iosClock').innerText = hm;
  document.getElementById('lockClock').innerText = hm;
}

window.addEventListener('DOMContentLoaded', () => {
  initMap();
  setInterval(refreshLogs, 1000);
});
</script>
</body>
</html>
"""


class WatchSimulatorHandler(BaseHTTPRequestHandler):
    def log_message(self, fmt: str, *args) -> None:
        return

    def _send_json(self, obj: object, status: int = 200) -> None:
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, X-Client-Token")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self) -> None:
        self._send_json({"ok": True}, 200)

    def do_GET(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        qs = urllib.parse.parse_qs(parsed.query)

        if path in ("/", "/iphone", "/watch"):
            lan_ip = get_lan_ip()
            html = IPHONE_SIMULATOR_HTML.replace("__LAN_IP__", lan_ip).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(html)))
            self.end_headers()
            self.wfile.write(html)
            return

        if path == "/api/state":
            with STATE_LOCK:
                snapshot = dict(WATCH_HUB)
                snapshot["ageSeconds"] = round(time.time() - WATCH_HUB["lastPacketTs"], 1)
            self._send_json(snapshot)
            return

        if path == "/api/route":
            origin_str = (qs.get("origin") or ["10.775840,106.700420"])[0]
            dest_str = (qs.get("dest") or ["10.776900,106.703200"])[0]
            try:
                o_lat, o_lng = [float(x) for x in origin_str.split(",")]
                d_lat, d_lng = [float(x) for x in dest_str.split(",")]
                route = fetch_osrm_route(o_lat, o_lng, d_lat, d_lng)
                self._send_json(route)
            except Exception as e:
                self._send_json({"error": str(e)}, 500)
            return

        if path == "/api/roads":
            lat = float((qs.get("lat") or ["10.775840"])[0])
            lng = float((qs.get("lng") or ["106.700420"])[0])
            radius = int((qs.get("radius") or ["340"])[0])
            tile_id, roads = fetch_overpass_roads(lat, lng, radius)
            self._send_json({"tile": tile_id, "roads": roads})
            return

        if path == "/api/search":
            q = (qs.get("q") or [""])[0].strip()
            if not q:
                self._send_json({"results": []})
                return
            if VIETMAP_API_KEY:
                try:
                    vm_s_url = (
                        f"https://maps.vietmap.vn/api/search?api-version=1.1"
                        f"&apikey={urllib.parse.quote(VIETMAP_API_KEY)}"
                        f"&text={urllib.parse.quote(q)}"
                    )
                    req = urllib.request.Request(vm_s_url, headers={"User-Agent": "GNavigation-iOS-Sim/1.0"})
                    with urllib.request.urlopen(req, timeout=8) as resp:
                        vm_body = json.loads(resp.read().decode("utf-8"))
                    feats = (vm_body.get("data") or {}).get("features") or []
                    results = []
                    for f in feats[:6]:
                        coords = (f.get("geometry") or {}).get("coordinates") or []
                        props = f.get("properties") or {}
                        if len(coords) >= 2:
                            results.append(
                                {
                                    "name": str(props.get("name") or props.get("label") or q),
                                    "address": str(props.get("label") or props.get("region") or ""),
                                    "lat": float(coords[1]),
                                    "lng": float(coords[0]),
                                }
                            )
                    if results:
                        add_log(f"VIETMAP Search: '{q}' ({len(results)} kết quả)")
                        self._send_json({"provider": "vietmap", "results": results})
                        return
                except Exception as e:
                    add_log(f"VIETMAP Search fallback: {e}")

            try:
                nom_url = (
                    "https://nominatim.openstreetmap.org/search?format=json&countrycodes=vn&limit=5&q="
                    + urllib.parse.quote(q)
                )
                req = urllib.request.Request(nom_url, headers={"User-Agent": "GNavigation-iOS-Sim/1.0"})
                with urllib.request.urlopen(req, timeout=8) as resp:
                    items = json.loads(resp.read().decode("utf-8"))
                results = [
                    {
                        "name": str(it.get("display_name", q)).split(",")[0],
                        "address": str(it.get("display_name", "")),
                        "lat": float(it["lat"]),
                        "lng": float(it["lon"]),
                    }
                    for it in items
                ]
                add_log(f"iOS tìm kiếm: '{q}' ({len(results)} kết quả)")
                self._send_json({"provider": "nominatim", "results": results})
            except Exception as e:
                self._send_json({"results": [], "error": str(e)})
            return

        self._send_json({"ok": True, "service": "g-navigation-ios-simulator"})

    def do_POST(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length) if length > 0 else b"{}"
        try:
            payload = json.loads(raw.decode("utf-8"))
        except Exception:
            payload = {}

        if parsed.path == "/api/bluetooth":
            with STATE_LOCK:
                enabled = bool(payload.get("enabled", True))
                WATCH_HUB["bluetoothEnabled"] = enabled
                if enabled:
                    WATCH_HUB["lastPacketTs"] = time.time()
                    add_log("Bluetooth P2P ĐÃ KẾT NỐI LẠI -> Đồng bộ sang đồng hồ DevEco!")
                else:
                    # Đẩy lùi lastPacketTs để sau vài giây đồng hồ phát hiện mất kết nối (Mốc 4)
                    WATCH_HUB["lastPacketTs"] = time.time() - 13.0
                    add_log("Bluetooth P2P ĐÃ NGẮT -> Đồng hồ sẽ ẩn chỉ dẫn cũ!")
            self._send_json({"ok": True})
            return

        if parsed.path == "/api/p2p":
            if isinstance(payload, list):
                for pkt in payload:
                    if isinstance(pkt, dict):
                        process_p2p_packet(pkt)
            elif isinstance(payload, dict):
                process_p2p_packet(payload)
            self._send_json({"ok": True})
            return

        self._send_json({"error": "Not found"}, 404)


if __name__ == "__main__":
    lan_ip = get_lan_ip()
    server = ThreadingHTTPServer(("0.0.0.0", PORT), WatchSimulatorHandler)
    print(f"============================================================")
    print(f" G Navigation iOS Simulator đang chạy tại: http://localhost:{PORT}/iphone")
    print(f"============================================================")
    server.serve_forever()
