#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
G Navigation — Hệ thống Máy ảo kép (iPhone 15 Pro iOS + Huawei Watch Fit 4 Pro 408x480)
đồng thời truyền trực tiếp sang DevEco Studio HarmonyOS Emulator (127.0.0.1:5555).
Đã tích hợp VIETMAP Route API (vehicle=motorcycle) & VIETMAP Search API qua file .env.
"""

import json
import math
import os
import socket
import subprocess
import threading
import time
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORT = 8787

# Bộ nhớ đệm cảm biến vị trí gốc của Windows (System.Device.Location.GeoCoordinateWatcher)
WINDOWS_GPS_CACHE = {
    "lat": 21.001021,
    "lng": 105.856575,
    "acc": 45,
    "updatedAt": 0.0,
}


def refresh_windows_native_gps() -> dict:
    """Đọc trực tiếp cảm biến vị trí Wi-Fi/GPS gốc của Windows 11 (GeoCoordinateWatcher)"""
    now = time.time()
    if now - WINDOWS_GPS_CACHE["updatedAt"] < 15.0:
        return WINDOWS_GPS_CACHE
    try:
        ps_cmd = (
            "Add-Type -AssemblyName System.Device; "
            "$w = New-Object System.Device.Location.GeoCoordinateWatcher([System.Device.Location.GeoPositionAccuracy]::High); "
            "$w.Start(); "
            "for($i=0;$i -lt 8;$i++){ if($w.Status -eq 'Ready' -and -not $w.Position.Location.IsUnknown){break}; Start-Sleep -Milliseconds 300 }; "
            "$loc = $w.Position.Location; "
            "if(-not $loc.IsUnknown){ Write-Output \"$($loc.Latitude),$($loc.Longitude),$($loc.HorizontalAccuracy)\" }; "
            "$w.Stop()"
        )
        out = subprocess.check_output(
            ["powershell", "-NoProfile", "-Command", ps_cmd],
            timeout=5,
            stderr=subprocess.DEVNULL,
        ).decode("utf-8").strip()
        if "," in out:
            parts = out.split(",")
            lat = float(parts[0])
            lng = float(parts[1])
            acc = int(round(float(parts[2]))) if len(parts) > 2 else 50
            if -90 <= lat <= 90 and -180 <= lng <= 180:
                WINDOWS_GPS_CACHE["lat"] = round(lat, 6)
                WINDOWS_GPS_CACHE["lng"] = round(lng, 6)
                WINDOWS_GPS_CACHE["acc"] = max(10, acc)
                WINDOWS_GPS_CACHE["updatedAt"] = now
    except Exception:
        pass
    return WINDOWS_GPS_CACHE


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
    "vietmapEnabled": bool(VIETMAP_API_KEY),
    "state": {
        "t": "S",
        "seq": 1,
        "ts": int(time.time()),
        "lat": 21.001021,
        "lng": 105.856575,
        "hdg": 0,
        "spd": 0,
        "mType": "STRAIGHT",
        "mDist": 65,
        "road": "Thanh Nhàn",
        "eta": "15:05",
        "rem": 1450,
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


def build_roads_from_steps_and_corridor(pts: list[list[float]], steps: list[dict]) -> list[dict]:
    """Tạo ngay lập tức mạng lưới đường phố & đường cắt ngang dọc theo lộ trình VIETMAP"""
    roads: list[dict] = []
    if len(pts) >= 2:
        roads.append({"n": "", "c": 1, "p": pts})

    # Tạo các nhánh đường giao cắt tại mỗi nút rẽ của VIETMAP để đồng hồ luôn thấy ngã tư & tên đường
    for st in steps:
        loc = st.get("location") or []
        if len(loc) < 2:
            continue
        lat, lng = float(loc[0]), float(loc[1])
        name = str(st.get("roadName") or "").strip()
        # Tạo đường cắt ngang qua giao lộ
        roads.append(
            {
                "n": name,
                "c": 1,
                "p": [
                    [round(lat - 0.0009, 6), round(lng - 0.0009, 6)],
                    [round(lat, 6), round(lng, 6)],
                    [round(lat + 0.0009, 6), round(lng + 0.0009, 6)],
                ],
            }
        )
        roads.append(
            {
                "n": "",
                "c": 2,
                "p": [
                    [round(lat - 0.0008, 6), round(lng + 0.0008, 6)],
                    [round(lat, 6), round(lng, 6)],
                    [round(lat + 0.0008, 6), round(lng - 0.0008, 6)],
                ],
            }
        )
    return roads


def fetch_overpass_roads(lat: float, lng: float, radius: int = 340) -> tuple[str, list[dict]]:
    tile_lat = round(lat * 333)
    tile_lng = round(lng * 333)
    tile_id = f"{tile_lat}_{tile_lng}"
    if tile_id in ROAD_TILE_CACHE:
        return tile_id, ROAD_TILE_CACHE[tile_id]

    c_lat = tile_lat / 333.0
    c_lng = tile_lng / 333.0
    query = (
        f'[out:json][timeout:4];'
        f'(way["highway"~"^(trunk|primary|secondary|tertiary|residential|unclassified|service)$"]'
        f'(around:{radius},{c_lat:.6f},{c_lng:.6f}););out geom;'
    )
    for endpoint in (
        "https://overpass.private.coffee/api/interpreter",
        "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
        "https://overpass-api.de/api/interpreter",
    ):
        try:
            req = urllib.request.Request(
                endpoint,
                data=f"data={urllib.parse.quote(query)}".encode("utf-8"),
                headers={
                    "Content-Type": "application/x-www-form-urlencoded",
                    "User-Agent": "GNavigation-iOS-Sim/1.0",
                },
            )
            with urllib.request.urlopen(req, timeout=4) as resp:
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
                if len(pts) > 8:
                    step = max(1, len(pts) // 6)
                    pts = pts[::step] + ([pts[-1]] if pts[-1] != pts[::step][-1] else [])
                roads.append({"n": name, "c": r_class, "p": pts})
                if len(roads) >= 48:
                    break
            if roads:
                ROAD_TILE_CACHE[tile_id] = roads
                return tile_id, roads
        except Exception:
            continue

    with STATE_LOCK:
        fallback = build_roads_from_steps_and_corridor(
            WATCH_HUB.get("routePoints", []), WATCH_HUB.get("steps", [])
        )
        return tile_id, (fallback if fallback else WATCH_HUB["roads"])


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
                    f"✅ VIETMAP Route (motorcycle): {int(round(path.get('distance', 0)))}m, {len(steps)} bước rẽ"
                )
                with STATE_LOCK:
                    WATCH_HUB["steps"] = steps
                    WATCH_HUB["routePoints"] = pts
                    WATCH_HUB["roads"] = build_roads_from_steps_and_corridor(pts, steps)
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

    return {
        "routeId": f"rt_{int(time.time())}",
        "provider": "osm-fallback",
        "vehicle": "motorcycle",
        "distanceMeters": int(round(route.get("distance", 0))),
        "durationSeconds": int(round(route.get("duration", 0))),
        "points": pts,
        "steps": steps,
    }


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


DUAL_SIMULATOR_HTML = r"""<!DOCTYPE html>
<html lang="vi">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>G Navigation — Cặp Máy Ảo iPhone 15 Pro (iOS) ↔ Huawei Watch Fit 4 Pro</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<style>
  :root {
    --ios-card: #1c1c1e;
    --ios-card2: #2c2c2e;
    --ios-blue: #0a84ff;
    --ios-green: #30d158;
    --ios-orange: #ff9f0a;
    --ios-red: #ff453a;
    --ios-cyan: #64d2ff;
    --ios-sub: #8e8e93;
  }
  * { box-sizing: border-box; user-select: none; }
  body {
    margin: 0;
    background: radial-gradient(circle at 30% 20%, #102030 0%, #05080c 75%);
    color: #fff;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    min-height: 100vh;
    display: flex;
    flex-direction: column;
  }
  .top-header {
    padding: 10px 24px;
    background: rgba(12, 18, 28, 0.9);
    border-bottom: 1px solid #1e2d42;
    display: flex;
    justify-content: space-between;
    align-items: center;
    flex-wrap: wrap;
    gap: 10px;
  }
  .top-header h1 {
    margin: 0;
    font-size: 16px;
    display: flex;
    align-items: center;
    gap: 10px;
  }
  .vm-badge {
    background: rgba(48, 209, 88, 0.16);
    color: #30d158;
    border: 1px solid #30d158;
    padding: 3px 10px;
    border-radius: 999px;
    font-size: 11px;
    font-weight: 700;
  }
  .workspace {
    display: flex;
    justify-content: center;
    align-items: flex-start;
    gap: 36px;
    padding: 20px;
    flex-wrap: wrap;
    flex: 1;
  }
  /* KHUNG MÁY ẢO IPHONE 15 PRO */
  .iphone-chassis {
    width: 392px;
    height: 770px;
    background: #000;
    border-radius: 48px;
    padding: 12px;
    border: 4px solid #363b44;
    box-shadow: 0 24px 60px rgba(0,0,0,0.8);
    display: flex;
    flex-direction: column;
    position: relative;
    overflow: hidden;
  }
  .iphone-screen {
    flex: 1;
    background: #000;
    border-radius: 38px;
    overflow: hidden;
    display: flex;
    flex-direction: column;
    position: relative;
  }
  .ios-statusbar {
    height: 40px;
    padding: 0 18px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    font-size: 12px;
    font-weight: 600;
    background: #000;
    flex-shrink: 0;
  }
  .dynamic-island {
    width: 116px;
    height: 24px;
    background: #111;
    border-radius: 14px;
    border: 1px solid #262629;
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 5px;
    font-size: 10px;
    color: var(--ios-green);
  }
  .island-dot {
    width: 7px;
    height: 7px;
    border-radius: 50%;
    background: var(--ios-green);
  }
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
  .tab-pane.active { display: flex; }
  .top-search-bar {
    padding: 8px 10px;
    background: #1c1c1e;
    border-bottom: 1px solid #2c2c2e;
    z-index: 10;
  }
  .search-row { display: flex; gap: 6px; }
  .search-row input {
    flex: 1;
    background: #2c2c2e;
    border: none;
    color: #fff;
    padding: 8px 10px;
    border-radius: 10px;
    font-size: 12px;
    outline: none;
  }
  .ios-btn {
    background: var(--ios-blue);
    color: #fff;
    border: none;
    border-radius: 10px;
    padding: 8px 11px;
    font-size: 12px;
    font-weight: 600;
    cursor: pointer;
  }
  .ios-btn.green { background: var(--ios-green); color: #021a08; }
  .ios-btn.orange { background: var(--ios-orange); color: #1f1100; }
  .ios-btn.red { background: var(--ios-red); }
  .ios-btn.gray { background: var(--ios-card2); }
  .search-results {
    max-height: 140px;
    overflow-y: auto;
    margin-top: 6px;
    background: #252528;
    border-radius: 10px;
    display: none;
  }
  .search-item {
    padding: 7px 10px;
    border-bottom: 1px solid #333;
    cursor: pointer;
    font-size: 11px;
  }
  .search-item:hover { background: #3a3a3c; }
  #iosMap { flex: 1; width: 100%; min-height: 220px; z-index: 1; background: #0d1520; position: relative; }
  /* Chuyển gạch bản đồ OpenStreetMap chuẩn sang giao diện Dark Navigation sắc nét, không bao giờ đòi API Key */
  #iosMap .leaflet-tile-pane {
    filter: invert(92%) hue-rotate(185deg) brightness(95%) contrast(92%);
  }
  .my-location-fab {
    position: absolute;
    right: 12px;
    bottom: 12px;
    z-index: 500;
    width: 38px;
    height: 38px;
    border-radius: 19px;
    background: rgba(28, 28, 30, 0.92);
    border: 1px solid #3a3a3c;
    color: #0a84ff;
    font-size: 18px;
    display: flex;
    align-items: center;
    justify-content: center;
    cursor: pointer;
    box-shadow: 0 4px 12px rgba(0,0,0,0.5);
  }
  .my-location-fab:hover {
    background: #2c2c2e;
    color: #64d2ff;
  }
  .nav-sheet {
    background: var(--ios-card);
    border-top: 1px solid #2c2c2e;
    padding: 10px 12px;
    z-index: 10;
  }
  .quick-routes {
    display: flex;
    gap: 5px;
    overflow-x: auto;
    padding-bottom: 6px;
  }
  .chip {
    background: #2c2c2e;
    color: #e5e5ea;
    border: 1px solid #3a3a3c;
    border-radius: 999px;
    padding: 4px 9px;
    font-size: 10px;
    white-space: nowrap;
    cursor: pointer;
  }
  .chip:hover { border-color: var(--ios-blue); }
  .turn-preview {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 8px;
  }
  .turn-title { font-size: 15px; font-weight: 700; color: var(--ios-green); }
  .turn-sub { font-size: 11px; color: var(--ios-sub); }
  .ios-section {
    background: var(--ios-card);
    border-radius: 14px;
    padding: 12px;
    margin: 10px 10px 0 10px;
  }
  .ios-section h3 { margin: 0 0 6px 0; font-size: 13px; color: var(--ios-cyan); }
  .ios-section p { margin: 0 0 8px 0; font-size: 11px; color: var(--ios-sub); line-height: 1.4; }
  .mono-box {
    background: #000;
    padding: 8px;
    border-radius: 8px;
    font-family: monospace;
    font-size: 11px;
    color: var(--ios-green);
  }
  .ios-tabbar {
    height: 54px;
    background: #161618;
    border-top: 1px solid #2c2c2e;
    display: flex;
    justify-content: space-around;
    align-items: center;
    flex-shrink: 0;
  }
  .tab-btn {
    background: none;
    border: none;
    color: var(--ios-sub);
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 2px;
    font-size: 10px;
    font-weight: 600;
    cursor: pointer;
  }
  .tab-btn.active { color: var(--ios-blue); }
  .lockscreen-overlay {
    position: absolute;
    inset: 0;
    background: linear-gradient(180deg, rgba(8,15,26,0.96), rgba(3,5,9,0.98));
    z-index: 100;
    display: none;
    flex-direction: column;
    align-items: center;
    justify-content: space-between;
    padding: 50px 20px 30px 20px;
    text-align: center;
  }
  .lockscreen-overlay.locked { display: flex; }

  /* CỘT PHẢI: ĐỒNG HỒ HUAWEI WATCH FIT 4 PRO (408x480 CHỮ NHẬT BO GÓC) + LOG */
  .watch-panel {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 14px;
    width: 420px;
  }
  .watch-case {
    position: relative;
    width: 336px;
    height: 396px;
    background: linear-gradient(145deg, #3c4654, #1c222b);
    border-radius: 66px;
    padding: 15px;
    box-shadow:
      0 24px 60px rgba(0,0,0,0.75),
      inset 0 2px 4px rgba(255,255,255,0.25);
    display: flex;
    align-items: center;
    justify-content: center;
  }
  .watch-case.vibrating {
    animation: vibrateAnim 0.14s linear infinite;
    box-shadow: 0 0 36px rgba(0, 230, 118, 0.75);
  }
  @keyframes vibrateAnim {
    0%, 100% { transform: translate(0, 0); }
    25% { transform: translate(-3px, 1px); }
    75% { transform: translate(3px, -1px); }
  }
  .watch-crown {
    position: absolute;
    right: -12px;
    top: 84px;
    width: 12px;
    height: 46px;
    background: linear-gradient(180deg, #525d6e, #252c37);
    border-radius: 0 8px 8px 0;
    border-left: 3px solid #e53935;
  }
  .watch-side-btn {
    position: absolute;
    right: -8px;
    top: 224px;
    width: 8px;
    height: 50px;
    background: #343d4b;
    border-radius: 0 5px 5px 0;
  }
  .watch-screen {
    position: relative;
    width: 100%;
    height: 100%;
    background: #0A0E14;
    border-radius: 52px;
    overflow: hidden;
    border: 2px solid #05070a;
  }
  #watchMapBg {
    position: absolute;
    width: 520px;
    height: 520px;
    left: 50%;
    top: 67%;
    margin-left: -260px;
    margin-top: -260px;
    pointer-events: none;
    z-index: 0;
    opacity: 0.72;
  }
  #watchMapBg .leaflet-tile-pane {
    filter: invert(93%) hue-rotate(185deg) brightness(88%) contrast(95%);
  }
  #watchCanvas { position: relative; width: 100%; height: 100%; display: block; z-index: 2; }
  .w-turn-banner {
    z-index: 5;
    position: absolute;
    top: 14px;
    left: 50%;
    transform: translateX(-50%);
    width: 86%;
    background: rgba(16, 27, 40, 0.9);
    border: 1px solid #26384c;
    border-radius: 20px;
    padding: 8px 10px;
    display: flex;
    align-items: center;
    gap: 9px;
  }
  .w-icon-box {
    width: 40px;
    height: 40px;
    border-radius: 12px;
    background: #00b0ff;
    display: flex;
    align-items: center;
    justify-content: center;
    flex-shrink: 0;
  }
  .w-bottom-bar {
    position: absolute;
    bottom: 12px;
    left: 50%;
    transform: translateX(-50%);
    width: 82%;
    background: rgba(16, 27, 40, 0.9);
    border: 1px solid #243447;
    border-radius: 22px;
    padding: 6px 12px;
    display: flex;
    align-items: center;
    justify-content: space-between;
  }
  .log-card {
    width: 100%;
    background: #101824;
    border: 1px solid #1e2d42;
    border-radius: 16px;
    padding: 12px;
  }
  .log-box {
    background: #070a0f;
    border-radius: 10px;
    padding: 8px;
    height: 185px;
    overflow-y: auto;
    font-family: monospace;
    font-size: 11px;
    color: #b0bec5;
  }
</style>
</head>
<body>

<div class="top-header">
  <h1>
    <span>📱 Máy ảo iPhone 15 Pro (iOS) ↔ ⌚ Máy ảo Huawei Watch Fit 4 Pro (408×480)</span>
    <span class="vm-badge">✓ Đã kích hoạt VIETMAP Route (Motorcycle) & Search API</span>
  </h1>
  <div style="font-size:12px;color:#90a4ae;">
    Đã truyền: <strong id="hdrPktCount" style="color:#30d158">1</strong> gói P2P · Đồng bộ trực tiếp với cả DevEco Emulator
  </div>
</div>

<div class="workspace">
  <!-- BÊN TRÁI: MÁY ẢO IPHONE 15 PRO -->
  <div class="iphone-chassis">
    <div class="iphone-screen">
      <div class="ios-statusbar">
        <span id="iosClock">14:35</span>
        <div class="dynamic-island">
          <span class="island-dot" id="islandDot"></span>
          <span id="islandText">P2P Fit 4 Pro</span>
        </div>
        <span>5G 🔋98%</span>
      </div>

      <div class="tab-container">
        <!-- TAB 1: Bản đồ VIETMAP & Điều hướng -->
        <div class="tab-pane active" id="tab-nav">
          <div class="top-search-bar">
            <div class="search-row">
              <input type="text" id="searchInput" placeholder="Tìm qua VIETMAP (VD: Chợ Bến Thành, Hồ Gươm)..." onkeydown="if(event.key==='Enter')searchPlace()" />
              <button class="ios-btn" onclick="searchPlace()">Tìm</button>
            </div>
            <div class="search-results" id="searchResults"></div>
          </div>

          <div id="iosMap">
            <button class="my-location-fab" onclick=" event.stopPropagation(); locateRealGPS(true);" title="Về vị trí hiện tại của tôi">🎯</button>
          </div>

          <div class="nav-sheet">
            <div style="font-size:11px;color:#64d2ff;font-weight:600;margin-bottom:5px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;" id="currentAddressLine">
              📍 Vị trí hiện tại: Đang lấy từ cảm biến Windows GPS...
            </div>
            <div class="quick-routes">
              <span class="chip" onclick="startRealRoute(realGpsLat,realGpsLng, 21.0045,105.8431)">🧭 Chỉ đường → ĐH Bách Khoa HN</span>
              <span class="chip" onclick="startRealRoute(realGpsLat,realGpsLng, 21.0285,105.8542)">🧭 Chỉ đường → Hồ Gươm</span>
              <span class="chip" onclick="startRealRoute(realGpsLat,realGpsLng, 20.9958,105.8675)">🧭 Chỉ đường → Times City</span>
              <span class="chip" onclick="startRealRoute(realGpsLat,realGpsLng, 21.0368,105.8347)">🧭 Chỉ đường → Lăng Bác</span>
            </div>

            <div class="turn-preview">
              <div>
                <div class="turn-title" id="iosTurnDist">Sẵn sàng chỉ đường</div>
                <div class="turn-sub" id="iosTurnRoad">Chọn điểm đến hoặc bấm Chỉ đường bên dưới</div>
              </div>
              <div style="text-align:right">
                <div style="font-size:14px;font-weight:700;color:var(--ios-cyan)" id="iosSpeed">0 km/h</div>
                <div class="turn-sub" id="iosEta">GPS: Hà Nội</div>
              </div>
            </div>

            <div style="display:flex;gap:5px;">
              <button class="ios-btn green" style="flex:1" id="driveBtn" onclick="toggleDrive()">🧭 Bắt đầu chỉ đường (Chạy xe)</button>
              <button class="ios-btn gray" onclick="stepOnce()" title="Nhích 1 bước dọc lộ trình">⏭ +1 Bước</button>
              <button class="ios-btn" onclick="locateRealGPS(true)" title="Lấy lại GPS hiện tại">📍 GPS</button>
              <button class="ios-btn orange" onclick="lockIphoneScreen()" title="Khóa màn hình iPhone">🔒</button>
            </div>
            <div style="font-size:10px;color:var(--ios-sub);margin-top:5px;" id="gpsStatusLine">
              🛰️ Đã kết nối cảm biến vị trí gốc của Windows. Nhấp lên bản đồ để chọn đích hoặc bấm <strong>Bắt đầu chỉ đường</strong>!
            </div>
          </div>
        </div>

        <!-- TAB 2: Kiểm thử Mốc 2 & Mốc 4 -->
        <div class="tab-pane" id="tab-m2">
          <div class="ios-section">
            <h3>1. Kết nối Wear Engine P2P & VIETMAP</h3>
            <div class="mono-box">
              Bundle ID: com.gnavigation.ios<br/>
              Peer Watch: com.gnavigation.watch<br/>
              Routing Engine: VIETMAP Route v1.1 (vehicle=motorcycle)
            </div>
          </div>
          <div class="ios-section">
            <h3>2. Kiểm thử Mốc 2 (Khóa màn hình iPhone)</h3>
            <p>Bấm nút dưới để xe tự chạy trên nền khi màn hình iPhone đang khóa, kiểm tra đồng hồ bên phải vẫn cập nhật liên tục:</p>
            <button class="ios-btn orange" style="width:100%" onclick="startDriveAndLock()">🔒 Chạy nền & Khóa màn hình iPhone</button>
          </div>
          <div class="ios-section">
            <h3>3. Kiểm thử Mốc 4 (Ngắt & Nối lại Bluetooth)</h3>
            <p>Ngắt Bluetooth để kiểm tra đồng hồ tự ẩn chỉ dẫn cũ, sau đó bật lại để tự động SYNC tuyến đường:</p>
            <button class="ios-btn red" id="btToggleBtn" style="width:100%" onclick="toggleBluetooth()">🔌 Tắt Bluetooth tới đồng hồ</button>
          </div>
        </div>

        <!-- Lớp phủ khóa màn hình iPhone -->
        <div class="lockscreen-overlay" id="lockOverlay">
          <div>
            <div style="font-size:12px;color:var(--ios-green);font-weight:700">🔒 MÀN HÌNH IPHONE ĐANG KHÓA</div>
            <div style="font-size:58px;font-weight:200;margin-top:8px" id="lockClock">14:35</div>
            <div style="font-size:14px;color:#aeaeb2">Đang truyền P2P nền sang Fit 4 Pro</div>
          </div>
          <div style="width:100%;background:#1c1c1e;border:1px solid #3a3a3c;border-radius:16px;padding:12px;text-align:left">
            <div style="font-size:10px;color:var(--ios-cyan);font-weight:700">VIETMAP MOTORCYCLE NAVIGATION</div>
            <div style="font-size:15px;font-weight:700;margin-top:3px" id="lockNavTitle">85m → Nguyễn Huệ</div>
            <div style="font-size:11px;color:#8e8e93;margin-top:2px">Nhìn sang đồng hồ bên phải: Bản đồ vẫn tự xoay và đếm ngược!</div>
          </div>
          <button class="ios-btn" style="width:80%;padding:11px;border-radius:999px" onclick="unlockIphoneScreen()">🔓 Mở khóa iPhone</button>
        </div>
      </div>

      <div class="ios-tabbar">
        <button class="tab-btn active" id="btn-tab-nav" onclick="switchTab('nav')">
          <span style="font-size:16px">🧭</span>
          <span>Dẫn đường</span>
        </button>
        <button class="tab-btn" id="btn-tab-m2" onclick="switchTab('m2')">
          <span style="font-size:16px">⌚</span>
          <span>Kiểm thử Mốc 2 & 4</span>
        </button>
      </div>
    </div>
  </div>

  <!-- BÊN PHẢI: ĐỒNG HỒ HUAWEI WATCH FIT 4 PRO (408x480 CHỮ NHẬT BO GÓC) + NHẬT KÝ P2P -->
  <div class="watch-panel">
    <div class="watch-case" id="watchCase">
      <div class="watch-crown"></div>
      <div class="watch-side-btn"></div>
      <div class="watch-screen">
        <div id="watchMapBg"></div>
        <canvas id="watchCanvas" width="306" height="366"></canvas>

        <!-- Thẻ báo rẽ trên đồng hồ -->
        <div class="w-turn-banner" id="wBanner">
          <div class="w-icon-box" id="wIconBox">
            <canvas id="wArrowCanvas" width="32" height="32"></canvas>
          </div>
          <div style="flex:1;min-width:0">
            <div style="display:flex;align-items:center;gap:5px">
              <span style="font-size:20px;font-weight:800" id="wDist">85 m</span>
              <span id="wTurnNow" style="display:none;font-size:8px;font-weight:800;color:#00e676;background:rgba(0,230,118,0.18);padding:2px 5px;border-radius:5px">RẼ NGAY</span>
            </div>
            <div style="font-size:12px;color:#cfd8dc;white-space:nowrap;overflow:hidden;text-overflow:ellipsis" id="wRoad">Nguyễn Huệ</div>
          </div>
        </div>

      <div class="w-bottom-bar" style="z-index:5">
          <div style="text-align:center">
            <div style="font-size:15px;font-weight:800;color:#00e5ff;line-height:1" id="wSpd">32</div>
            <div style="font-size:8px;color:#78909c">km/h</div>
          </div>
          <div style="text-align:center">
            <div style="font-size:12px;font-weight:700" id="wRem">1.2 km</div>
            <div style="font-size:9px;color:#90a4ae" id="wEta">ETA 14:28</div>
          </div>
          <div style="display:flex;align-items:center;gap:4px;font-size:9px;font-weight:700">
            <span id="wDot" style="width:7px;height:7px;border-radius:50%;background:#00e676"></span>
            <span id="wStatus" style="color:#00e676">P2P</span>
          </div>
        </div>
      </div>
    </div>

    <div id="vibToast" style="height:18px;font-size:12px;font-weight:700;color:#00e676"></div>

    <div class="log-card">
      <div style="font-size:12px;font-weight:700;color:#64d2ff;margin-bottom:6px;display:flex;justify-content:space-between;">
        <span>📡 Nhật ký truyền gói tin P2P (iOS → Fit 4 Pro)</span>
        <span style="color:#30d158">VIETMAP Active</span>
      </div>
      <div class="log-box" id="logBox"></div>
    </div>
  </div>
</div>

<script>
let map, watchMap, riderMarker, destMarker, routeLine, accuracyCircle;
let currentRoute = [];
let currentSteps = [];
let routeIdx = 0;
let driveTimer = null;
let seqCounter = 10;
let btConnected = true;
let loadedTileKey = "";
let hubData = null;
let lastVibSeq = -1;
let gpsWatchId = null;
let realGpsLat = 21.001021;
let realGpsLng = 105.856575;
let realGpsHeading = 0;
let realGpsSpeedKmh = 0;
let realGpsAccuracy = 45;
let hasFirstGpsFix = false;

function switchTab(name) {
  ['nav', 'm2'].forEach(t => {
    document.getElementById('tab-' + t).classList.toggle('active', t === name);
    document.getElementById('btn-tab-' + t).classList.toggle('active', t === name);
  });
  if (name === 'nav' && map) setTimeout(() => map.invalidateSize(), 100);
}

function initMap() {
  map = L.map('iosMap', { zoomControl: false }).setView([realGpsLat, realGpsLng], 16);
  L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
    maxZoom: 19
  }).addTo(map);

  watchMap = L.map('watchMapBg', {
    zoomControl: false,
    attributionControl: false,
    dragging: false,
    scrollWheelZoom: false,
    doubleClickZoom: false,
    keyboard: false
  }).setView([realGpsLat, realGpsLng], 17);
  L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
    maxZoom: 19
  }).addTo(watchMap);

  const riderIcon = L.divIcon({
    html: '<div style="width:20px;height:20px;border-radius:50%;background:#00e5ff;border:3px solid #fff;box-shadow:0 0 12px #00e5ff;"></div>',
    iconSize: [20, 20],
    iconAnchor: [10, 10]
  });

  riderMarker = L.marker([realGpsLat, realGpsLng], { icon: riderIcon, draggable: true }).addTo(map);
  riderMarker.bindTooltip("Vị trí GPS thật của bạn (Có thể kéo để test lệch tuyến)", { direction: "top" });

  riderMarker.on('dragend', async function() {
    const pos = riderMarker.getLatLng();
    await onRealGpsUpdate(pos.lat, pos.lng, realGpsSpeedKmh, realGpsHeading, realGpsAccuracy || 5, false);
  });

  map.on('click', async function(e) {
    await startRealRoute(realGpsLat, realGpsLng, e.latlng.lat, e.latlng.lng);
  });

  // Khởi động ngay bộ thu GPS Thật (navigator.geolocation.watchPosition)
  startRealGpsTracking();
}

function startRealGpsTracking() {
  const statusEl = document.getElementById('gpsStatusLine');
  if (!navigator.geolocation) {
    statusEl.innerText = '⚠ Trình duyệt không hỗ trợ Geolocation, đang lấy vị trí qua mạng...';
    fallbackIpLocation();
    return;
  }

  locateRealGPS(true);

  if (gpsWatchId !== null) {
    navigator.geolocation.clearWatch(gpsWatchId);
  }
  gpsWatchId = navigator.geolocation.watchPosition(
    async (pos) => {
      const lat = pos.coords.latitude;
      const lng = pos.coords.longitude;
      const acc = Math.round(pos.coords.accuracy || 10);
      const spd = pos.coords.speed && pos.coords.speed > 0 ? Math.round(pos.coords.speed * 3.6) : 0;
      const hdg = pos.coords.heading && pos.coords.heading >= 0 ? Math.round(pos.coords.heading) : realGpsHeading;
      const centerMap = !hasFirstGpsFix;
      hasFirstGpsFix = true;
      await onRealGpsUpdate(lat, lng, spd, hdg, acc, centerMap);
    },
    (err) => {
      statusEl.innerText = `⚠ Quyền vị trí Windows/Trình duyệt (${err.message}) -> Đang lấy vị trí thực từ mạng IP...`;
      if (!hasFirstGpsFix) fallbackIpLocation();
    },
    {
      enableHighAccuracy: true,
      maximumAge: 0,
      timeout: 10000
    }
  );
}

async function locateRealGPS(recenter = true) {
  // Ưu tiên 1: Lấy từ cảm biến vị trí gốc của Windows (System.Device.Location.GeoCoordinateWatcher)
  try {
    const res = await fetch('/api/native-gps');
    const winGps = await res.json();
    if (winGps && winGps.lat && winGps.lng) {
      hasFirstGpsFix = true;
      await onRealGpsUpdate(winGps.lat, winGps.lng, 0, realGpsHeading, winGps.acc || 45, recenter);
      return;
    }
  } catch (e) {}

  // Ưu tiên 2: HTML5 Geolocation (dành cho iPhone Safari/WebKit)
  if (navigator.geolocation) {
    navigator.geolocation.getCurrentPosition(
      async (pos) => {
        hasFirstGpsFix = true;
        const lat = pos.coords.latitude;
        const lng = pos.coords.longitude;
        const acc = Math.round(pos.coords.accuracy || 15);
        const spd = pos.coords.speed && pos.coords.speed > 0 ? Math.round(pos.coords.speed * 3.6) : 0;
        const hdg = pos.coords.heading && pos.coords.heading >= 0 ? Math.round(pos.coords.heading) : realGpsHeading;
        await onRealGpsUpdate(lat, lng, spd, hdg, acc, recenter);
      },
      () => {},
      { enableHighAccuracy: true, maximumAge: 0, timeout: 6000 }
    );
  }
}

async function fallbackIpLocation() {
  await locateRealGPS(true);
}

let lastReverseTile = "";
let currentStreetLabel = "Vị trí hiện tại";

async function updateCurrentAddress(lat, lng) {
  const rKey = `${Math.round(lat * 500)}_${Math.round(lng * 500)}`;
  if (rKey === lastReverseTile) return;
  lastReverseTile = rKey;
  try {
    const res = await fetch(`/api/reverse?lat=${lat}&lng=${lng}`);
    const data = await res.json();
    if (data.address) {
      currentStreetLabel = data.street || data.name || "Vị trí hiện tại";
      document.getElementById('currentAddressLine').innerText = `📍 Vị trí hiện tại: ${data.address}`;
    }
  } catch (e) {}
}

async function onRealGpsUpdate(lat, lng, spdKmh, hdg, accuracyMeters, recenterMap = false) {
  updateCurrentAddress(lat, lng);
  // Tính góc di chuyển nếu phần cứng không trả về heading nhưng tọa độ có thay đổi
  if (haversineMeters(realGpsLat, realGpsLng, lat, lng) > 2) {
    const dy = lat - realGpsLat;
    const dx = lng - realGpsLng;
    hdg = Math.round((Math.atan2(dx, dy) * 180 / Math.PI + 360) % 360);
  }

  realGpsLat = lat;
  realGpsLng = lng;
  realGpsSpeedKmh = spdKmh;
  realGpsHeading = hdg;
  realGpsAccuracy = accuracyMeters;

  riderMarker.setLatLng([lat, lng]);
  if (accuracyCircle) map.removeLayer(accuracyCircle);
  accuracyCircle = L.circle([lat, lng], {
    radius: Math.min(accuracyMeters, 120),
    color: '#00e5ff',
    weight: 1,
    fillOpacity: 0.12
  }).addTo(map);

  if (recenterMap) {
    map.setView([lat, lng], 16);
  }

  document.getElementById('gpsStatusLine').innerText =
    `🛰️ GPS Thật: ${lat.toFixed(6)}, ${lng.toFixed(6)} (Độ chính xác ±${accuracyMeters}m)`;

  await syncNearbyRoadsToWatch(lat, lng, false);

  // Nếu chưa chọn tuyến đường: gửi trực tiếp vị trí GPS thật sang đồng hồ Fit 4 Pro
  if (currentRoute.length < 2) {
    seqCounter += 1;
    document.getElementById('iosTurnDist').innerText = `GPS Thật (±${accuracyMeters}m)`;
    document.getElementById('iosTurnRoad').innerText = `Tọa độ: ${lat.toFixed(5)}, ${lng.toFixed(5)}`;
    document.getElementById('iosSpeed').innerText = `${spdKmh} km/h`;
    document.getElementById('iosEta').innerText = `Chưa chọn đích`;

    await sendP2P({
      t: 'S',
      seq: seqCounter,
      ts: Math.floor(Date.now() / 1000),
      lat: lat,
      lng: lng,
      hdg: hdg,
      spd: spdKmh,
      mType: 'STRAIGHT',
      mDist: 0,
      road: currentStreetLabel,
      eta: '--:--',
      rem: 0,
      vib: 0,
      reroute: false
    });
    return;
  }

  // Nếu đang có tuyến đường VIETMAP: đối chiếu vị trí GPS thật lên tuyến đường
  let minD = 999999;
  let closestIdx = 0;
  for (let i = 0; i < currentRoute.length; i++) {
    const d = haversineMeters(lat, lng, currentRoute[i][0], currentRoute[i][1]);
    if (d < minD) { minD = d; closestIdx = i; }
  }

  // Nếu vị trí GPS thật đi lệch khỏi tuyến > 42m -> Rung báo lệch tuyến & gọi VIETMAP tính lại đường từ vị trí GPS thật!
  if (minD > 42 && destMarker) {
    seqCounter += 1;
    document.getElementById('iosTurnDist').innerText = '⚠ Lệch tuyến (' + Math.round(minD) + 'm)';
    document.getElementById('iosTurnRoad').innerText = 'Đang gọi VIETMAP tính lại đường từ GPS thật...';

    await sendP2P({
      t: 'S',
      seq: seqCounter,
      ts: Math.floor(Date.now() / 1000),
      lat: lat,
      lng: lng,
      hdg: hdg,
      spd: spdKmh,
      mType: 'UTURN',
      mDist: Math.round(minD),
      road: 'Đang tính lại đường...',
      eta: '--:--',
      rem: 0,
      vib: 3,
      reroute: true
    });

    const dest = destMarker.getLatLng();
    await startRealRoute(lat, lng, dest.lat, dest.lng, true);
    return;
  }

  // Tính khoảng cách từ vị trí GPS thật tới ngã rẽ VIETMAP tiếp theo
  let nextStep = currentSteps.find(s => haversineMeters(lat, lng, s.location[0], s.location[1]) > 15) || currentSteps[currentSteps.length - 1];
  let mDist = nextStep ? Math.round(haversineMeters(lat, lng, nextStep.location[0], nextStep.location[1])) : 0;
  let mType = nextStep ? nextStep.maneuverType : 'STRAIGHT';
  let road = nextStep ? nextStep.roadName : 'Đường phía trước';

  if ( closestIdx < currentRoute.length - 1 && spdKmh === 0 ) {
    const nextPt = currentRoute[closestIdx + 1];
    const dy = nextPt[0] - lat;
    const dx = nextPt[1] - lng;
    if (dy !== 0 || dx !== 0) {
      hdg = Math.round((Math.atan2(dx, dy) * 180 / Math.PI + 360) % 360);
    }
  }

  let rem = haversineMeters(lat, lng, currentRoute[closestIdx][0], currentRoute[closestIdx][1]);
  for (let i = closestIdx; i < currentRoute.length - 1; i++) {
    rem += haversineMeters(currentRoute[i][0], currentRoute[i][1], currentRoute[i+1][0], currentRoute[i+1][1]);
  }
  rem = Math.round(rem);

  if (rem < 20) {
    mType = 'ARRIVE';
    mDist = 0;
    road = 'Đã tới điểm đích';
  }

  const vib = mDist <= 35 && mDist > 10 ? 2 : (mDist <= 105 && mDist >= 75 ? 1 : 0);

  seqCounter += 1;
  const pkt = {
    t: 'S',
    seq: seqCounter,
    ts: Math.floor(Date.now() / 1000),
    lat: lat,
    lng: lng,
    hdg: hdg,
    spd: spdKmh,
    mType: mType,
    mDist: mDist,
    road: road,
    eta: '14:45',
    rem: rem,
    vib: vib,
    reroute: false
  };

  document.getElementById('iosTurnDist').innerText = `${mDist} m · ${mType}`;
  document.getElementById('iosTurnRoad').innerText = `Đường kế: ${road}`;
  document.getElementById('iosSpeed').innerText = `${spdKmh} km/h`;
  document.getElementById('iosEta').innerText = `Còn ${rem >= 1000 ? (rem/1000).toFixed(1) + ' km' : rem + ' m'}`;
  document.getElementById('lockNavTitle').innerText = `${mDist}m → ${road} (${spdKmh} km/h)`;

  await sendP2P(pkt);
}

async function sendP2P(packets) {
  await fetch('/api/p2p', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(packets)
  });
  await pollWatchState();
}

async function syncNearbyRoadsToWatch(lat, lng, force = false) {
  const tKey = `${Math.round(lat * 333)}_${Math.round(lng * 333)}`;
  if (!force && tKey === loadedTileKey) return;
  loadedTileKey = tKey;
  try {
    const res = await fetch(`/api/roads?lat=${lat}&lng=${lng}&radius=340`);
    const data = await res.json();
    if (data.roads && data.roads.length > 0) {
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
    if (!isReroute) map.fitBounds(routeLine.getBounds(), { padding: [24, 24] });

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
    await syncNearbyRoadsToWatch(oLat, oLng, true);
    await onRealGpsUpdate(oLat, oLng, realGpsSpeedKmh, realGpsHeading, realGpsAccuracy || 10, false);
  } catch (e) {}
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
    if (d < minD) { minD = d; closestIdx = i; }
  }

  if (minD > 42 && destMarker) {
    seqCounter += 1;
    document.getElementById('iosTurnDist').innerText = '⚠ Lệch tuyến (' + Math.round(minD) + 'm)';
    document.getElementById('iosTurnRoad').innerText = 'Đang gọi VIETMAP tính lại đường...';

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
    }, 1500);
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
    driveTimer = setInterval(stepOnce, 1200);
    btn.innerText = '⏸ Đang lái xe (Dừng)';
    btn.className = 'ios-btn red';
  }
}

async function stepOnce() {
  if (currentRoute.length < 2) {
    await startRealRoute(realGpsLat, realGpsLng, 21.0045, 105.8431);
  }
  if (currentRoute.length < 2) return;
  routeIdx = (routeIdx + 1) % currentRoute.length;
  const pt = currentRoute[routeIdx];
  await onRealGpsUpdate(pt[0], pt[1], 34, realGpsHeading, 8, false);
}

async function toggleDrive() {
  const btn = document.getElementById('driveBtn');
  if (driveTimer) {
    clearInterval(driveTimer);
    driveTimer = null;
    btn.innerText = '🧭 Bắt đầu chỉ đường (Chạy xe)';
    btn.className = 'ios-btn green';
  } else {
    if (currentRoute.length < 2) {
      await startRealRoute(realGpsLat, realGpsLng, 21.0045, 105.8431);
    }
    stepOnce();
    driveTimer = setInterval(stepOnce, 1200);
    btn.innerText = '⏸ Đang chỉ đường (Bấm để dừng)';
    btn.className = 'ios-btn red';
  }
}

async function searchPlace() {
  const q = document.getElementById('searchInput').value.trim();
  if (!q) return;
  const res = await fetch(`/api/search?q=${encodeURIComponent(q)}&lat=${realGpsLat}&lng=${realGpsLng}`);
  const data = await res.json();
  const box = document.getElementById('searchResults');
  if (!data.results || data.results.length === 0) {
    box.style.display = 'none';
    return;
  }
  box.style.display = 'block';
  box.innerHTML = data.results.map(r => {
    const safeName = r.name.replace(/'/g, "");
    return `
      <div class="search-item" style="display:flex;justify-content:space-between;align-items:center;gap:6px;">
        <div style="flex:1;min-width:0;" onclick="selectSearchResult(${r.lat}, ${r.lng}, '${safeName}')">
          <strong>${r.name}</strong> <span style="color:#30d158">[${data.provider || 'vietmap'}]</span><br/>
          <span style="color:#8e8e93">${r.address}</span>
        </div>
        <div style="display:flex;gap:4px;flex-shrink:0;">
          <button class="ios-btn green" style="padding:5px 8px;font-size:10px" onclick="selectSearchResult(${r.lat}, ${r.lng}, '${safeName}')">🧭 Chỉ đường</button>
          <button class="ios-btn gray" style="padding:5px 7px;font-size:10px" onclick="setAsMyCurrentGps(${r.lat}, ${r.lng}, '${safeName}')" title="Đặt làm vị trí hiện tại của tôi">📌 Vị trí tôi</button>
        </div>
      </div>
    `;
  }).join('');
}

async function setAsMyCurrentGps(lat, lng, name) {
  document.getElementById('searchResults').style.display = 'none';
  lastReverseTile = "";
  await onRealGpsUpdate(lat, lng, 0, 0, 5, true);
}

async function selectSearchResult(lat, lng, name) {
  document.getElementById('searchResults').style.display = 'none';
  document.getElementById('searchInput').value = name;
  await startRealRoute(realGpsLat, realGpsLng, lat, lng);
}

function lockIphoneScreen() { document.getElementById('lockOverlay').classList.add('locked'); }
function unlockIphoneScreen() { document.getElementById('lockOverlay').classList.remove('locked'); }
function startDriveAndLock() { lockIphoneScreen(); }

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
    btn.innerText = '🔌 Tắt Bluetooth tới đồng hồ';
    btn.className = 'ios-btn red';
    dot.style.background = '#30d158';
    txt.innerText = 'P2P Fit 4 Pro';
    await onRealGpsUpdate(realGpsLat, realGpsLng, realGpsSpeedKmh, realGpsHeading, realGpsAccuracy || 10, false);
  } else {
    btn.innerText = '🔗 Bật lại Bluetooth (Tự động SYNC lại đồng hồ)';
    btn.className = 'ios-btn green';
    dot.style.background = '#ff453a';
    txt.innerText = 'Đã ngắt BT';
    await pollWatchState();
  }
}

// --- VẼ MÀN HÌNH ĐỒNG HỒ HUAWEI WATCH FIT 4 PRO (BÊN PHẢI) ---

function drawVectorManeuverArrow(mType, isReroute) {
  const canvas = document.getElementById('wArrowCanvas');
  const c = canvas.getContext('2d');
  c.clearRect(0, 0, 32, 32);
  c.save();
  c.strokeStyle = '#05101A';
  c.lineWidth = 3.2;
  c.lineCap = 'round';
  c.lineJoin = 'round';

  if (isReroute || mType === 'UTURN') {
    c.beginPath(); c.moveTo(20, 26); c.lineTo(20, 13); c.arc(14, 13, 6, 0, Math.PI, true); c.lineTo(8, 22); c.stroke();
    c.beginPath(); c.moveTo(4, 18); c.lineTo(8, 23); c.lineTo(12, 18); c.stroke();
  } else if (mType === 'TURN_LEFT' || mType === 'SHARP_LEFT') {
    c.beginPath(); c.moveTo(21, 26); c.lineTo(21, 13); c.lineTo(8, 13); c.stroke();
    c.beginPath(); c.moveTo(13, 8); c.lineTo(7, 13); c.lineTo(13, 18); c.stroke();
  } else if (mType === 'TURN_RIGHT' || mType === 'SHARP_RIGHT') {
    c.beginPath(); c.moveTo(11, 26); c.lineTo(11, 13); c.lineTo(24, 13); c.stroke();
    c.beginPath(); c.moveTo(19, 8); c.lineTo(25, 13); c.lineTo(19, 18); c.stroke();
  } else {
    c.beginPath(); c.moveTo(16, 26); c.lineTo(16, 7); c.stroke();
    c.beginPath(); c.moveTo(10, 13); c.lineTo(16, 6); c.lineTo(22, 13); c.stroke();
  }
  c.restore();
}

function projectToWatchScreen(lat, lng, centerLat, centerLng, heading, w, h) {
  const scale = 1.65;
  const cosLat = Math.cos(centerLat * Math.PI / 180.0);
  const northM = (lat - centerLat) * 111320.0;
  const eastM = (lng - centerLng) * 111320.0 * cosLat;
  const rad = (heading * Math.PI) / 180.0;
  const rotX = eastM * Math.cos(rad) - northM * Math.sin(rad);
  const rotY = eastM * Math.sin(rad) + northM * Math.cos(rad);
  return { x: w * 0.5 + rotX / scale, y: h * 0.67 - rotY / scale };
}

function renderWatchFit4Pro() {
  if (!hubData) return;
  const s = hubData.state;
  const roads = hubData.roads || [];
  const route = hubData.routePoints || [];
  const isStale = !hubData.bluetoothEnabled || (hubData.ageSeconds > 12);

  document.getElementById('hdrPktCount').innerText = hubData.packetsReceived || 0;

  const banner = document.getElementById('wBanner');
  const iconBox = document.getElementById('wIconBox');
  const wDist = document.getElementById('wDist');
  const wRoad = document.getElementById('wRoad');
  const wTurnNow = document.getElementById('wTurnNow');

  if (isStale) {
    banner.style.background = 'rgba(38, 50, 56, 0.94)';
    banner.style.borderColor = '#ef5350';
    iconBox.style.background = '#546e7a';
    wDist.innerText = '⚠ Mất dữ liệu';
    wRoad.innerText = 'Đã ẩn chỉ dẫn cũ · Chờ nối lại';
    wTurnNow.style.display = 'none';
  } else if (s.reroute) {
    banner.style.background = 'rgba(78, 42, 4, 0.94)';
    banner.style.borderColor = '#ffa726';
    iconBox.style.background = '#ffa726';
    wDist.innerText = 'Lệch tuyến';
    wRoad.innerText = 'Đang tính lại đường...';
    wTurnNow.style.display = 'none';
  } else {
    banner.style.background = s.mDist <= 40 ? 'rgba(0, 77, 64, 0.94)' : 'rgba(16, 27, 40, 0.9)';
    banner.style.borderColor = s.mDist <= 40 ? '#00e676' : '#26384c';
    iconBox.style.background = s.mDist <= 40 ? '#00e676' : '#00b0ff';
    wTurnNow.style.display = s.mDist <= 40 ? 'inline-block' : 'none';
    wDist.innerText = s.mDist >= 1000 ? (s.mDist / 1000).toFixed(1) + ' km' : s.mDist + ' m';
    wRoad.innerText = s.road || 'Đường phía trước';
  }

  drawVectorManeuverArrow(s.mType, s.reroute);

  document.getElementById('wSpd').innerText = Math.round(s.spd || 0);
  document.getElementById('wRem').innerText = s.rem >= 1000 ? (s.rem / 1000).toFixed(1) + ' km' : s.rem + ' m';
  document.getElementById('wEta').innerText = 'ETA ' + (s.eta || '--:--');

  const wDot = document.getElementById('wDot');
  const wStatus = document.getElementById('wStatus');
  wDot.style.background = isStale ? '#ff5252' : '#00e676';
  wStatus.style.color = isStale ? '#ff5252' : '#00e676';
  wStatus.innerText = isStale ? 'MẤT KN' : 'P2P';

  if (s.vib > 0 && s.seq !== lastVibSeq) {
    lastVibSeq = s.seq;
    const wc = document.getElementById('watchCase');
    const vt = document.getElementById('vibToast');
    wc.classList.add('vibrating');
    vt.innerText = s.vib === 3 ? '📳 RUNG 3 NHỊP: Đi lệch tuyến!' : (s.vib === 2 ? '📳 RUNG MẠNH: Rẽ ngay (30m)!' : '📳 RUNG 2 NHỊP: Sắp rẽ (100m)');
    setTimeout(() => wc.classList.remove('vibrating'), 900);
  }

  if (watchMap) {
    watchMap.setView([s.lat, s.lng], 17, { animate: false });
    const bgEl = document.getElementById('watchMapBg');
    bgEl.style.transform = `rotate(${-s.hdg}deg)`;
  }

  const canvas = document.getElementById('watchCanvas');
  const c = canvas.getContext('2d');
  const w = canvas.width, h = canvas.height;
  const ax = w * 0.5, ay = h * 0.67;

  c.clearRect(0, 0, w, h);

  c.strokeStyle = 'rgba(0, 229, 255, 0.16)';
  c.lineWidth = 1;
  c.beginPath(); c.arc(ax, ay, 100 / 1.65, 0, Math.PI * 2); c.stroke();

  for (const seg of roads) {
    if (!seg.p || seg.p.length < 2) continue;
    c.save();
    c.lineCap = 'round'; c.lineJoin = 'round';
    c.strokeStyle = seg.c === 1 ? '#263447' : (seg.c === 2 ? '#1C2736' : '#151E2B');
    c.lineWidth = seg.c === 1 ? 8 : (seg.c === 2 ? 5 : 3);
    c.beginPath();
    const p0 = projectToWatchScreen(seg.p[0][0], seg.p[0][1], s.lat, s.lng, s.hdg, w, h);
    c.moveTo(p0.x, p0.y);
    for (let i = 1; i < seg.p.length; i++) {
      const pi = projectToWatchScreen(seg.p[i][0], seg.p[i][1], s.lat, s.lng, s.hdg, w, h);
      c.lineTo(pi.x, pi.y);
    }
    c.stroke();
    if (seg.n && seg.c <= 2) {
      const mid = seg.p[Math.floor(seg.p.length / 2)];
      const mp = projectToWatchScreen(mid[0], mid[1], s.lat, s.lng, s.hdg, w, h);
      if (mp.x > 24 && mp.x < w - 24 && mp.y > 80 && mp.y < h - 50) {
        c.fillStyle = '#607d8b';
        c.font = '10px sans-serif';
        c.textAlign = 'center';
        c.fillText(seg.n, mp.x, mp.y - 4);
      }
    }
    c.restore();
  }

  if (route.length >= 2) {
    c.save();
    c.lineCap = 'round'; c.lineJoin = 'round';
    c.strokeStyle = '#062B1F'; c.lineWidth = 11;
    c.beginPath();
    const r0 = projectToWatchScreen(route[0][0], route[0][1], s.lat, s.lng, s.hdg, w, h);
    c.moveTo(r0.x, r0.y);
    for (let i = 1; i < route.length; i++) {
      const ri = projectToWatchScreen(route[i][0], route[i][1], s.lat, s.lng, s.hdg, w, h);
      c.lineTo(ri.x, ri.y);
    }
    c.stroke();
    c.strokeStyle = isStale ? '#4B5B6E' : (s.reroute ? '#FFA726' : '#00E676');
    c.lineWidth = 6.5;
    c.stroke();
    c.restore();
  }

  c.save();
  c.fillStyle = isStale ? 'rgba(120,144,156,0.22)' : 'rgba(0,229,255,0.22)';
  c.beginPath(); c.arc(ax, ay, 18, 0, Math.PI * 2); c.fill();
  c.fillStyle = isStale ? '#90A4AE' : '#00E5FF';
  c.strokeStyle = '#FFF'; c.lineWidth = 2;
  c.beginPath();
  c.moveTo(ax, ay - 11); c.lineTo(ax + 9, ay + 9); c.lineTo(ax, ay + 4); c.lineTo(ax - 9, ay + 9);
  c.closePath(); c.fill(); c.stroke();
  c.restore();

  document.getElementById('logBox').innerHTML = (hubData.recentLogs || []).map(l => `<div style="padding:2px 0;border-bottom:1px solid rgba(255,255,255,0.04)">${l}</div>`).join('');
}

async function pollWatchState() {
  try {
    const res = await fetch('/api/state');
    hubData = await res.json();
    renderWatchFit4Pro();
  } catch (e) {}
  const hm = new Date().toTimeString().slice(0, 5);
  document.getElementById('iosClock').innerText = hm;
  document.getElementById('lockClock').innerText = hm;
}

window.addEventListener('DOMContentLoaded', () => {
  initMap();
  setInterval(pollWatchState, 1000);
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
            html = DUAL_SIMULATOR_HTML.replace("__LAN_IP__", lan_ip).encode("utf-8")
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

        if path == "/api/native-gps":
            gps = refresh_windows_native_gps()
            self._send_json(gps)
            return

        if path == "/api/reverse":
            lat = float((qs.get("lat") or ["10.775840"])[0])
            lng = float((qs.get("lng") or ["106.700420"])[0])
            if VIETMAP_API_KEY:
                try:
                    rev_url = (
                        f"https://maps.vietmap.vn/api/reverse?api-version=1.1"
                        f"&apikey={urllib.parse.quote(VIETMAP_API_KEY)}"
                        f"&point.lat={lat:.6f}&point.lon={lng:.6f}"
                    )
                    req = urllib.request.Request(rev_url, headers={"User-Agent": "GNavigation-iOS-Sim/1.0"})
                    with urllib.request.urlopen(req, timeout=6) as resp:
                        body = json.loads(resp.read().decode("utf-8"))
                    feats = (body.get("data") or {}).get("features") or []
                    if feats:
                        props = feats[0].get("properties") or {}
                        name = str(props.get("name") or props.get("street") or "Vị trí hiện tại")
                        addr = str(props.get("label") or name)
                        self._send_json({"provider": "vietmap", "name": name, "street": name, "address": addr})
                        return
                except Exception:
                    pass
            try:
                nom_url = f"https://nominatim.openstreetmap.org/reverse?format=json&lat={lat:.6f}&lon={lng:.6f}"
                req = urllib.request.Request(nom_url, headers={"User-Agent": "GNavigation-iOS-Sim/1.0"})
                with urllib.request.urlopen(req, timeout=6) as resp:
                    it = json.loads(resp.read().decode("utf-8"))
                addr = str(it.get("display_name") or f"{lat:.5f}, {lng:.5f}")
                road = str((it.get("address") or {}).get("road") or addr.split(",")[0])
                self._send_json({"provider": "nominatim", "name": road, "street": road, "address": addr})
                return
            except Exception:
                self._send_json({"name": "Vị trí hiện tại", "street": "Vị trí hiện tại", "address": f"{lat:.5f}, {lng:.5f}"})
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
                        add_log(f"✅ VIETMAP Search: '{q}' ({len(results)} kết quả)")
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

        self._send_json({"ok": True, "service": "g-navigation-dual-simulator"})

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
                    add_log("Bluetooth P2P ĐÃ KẾT NỐI LẠI -> Đồng bộ sang đồng hồ!")
                else:
                    WATCH_HUB["lastPacketTs"] = time.time() - 13.0
                    add_log("Bluetooth P2P ĐÃ NGẮT -> Đồng hồ ẩn chỉ dẫn cũ!")
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
    print(f" G Navigation Dual Simulator (iPhone + Watch Fit 4 Pro): http://localhost:{PORT}")
    print(f" VIETMAP_API_KEY configured: {bool(VIETMAP_API_KEY)}")
    print(f"============================================================")
    server.serve_forever()
