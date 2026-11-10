#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Máy ảo Huawei Watch Fit 4 Pro & P2P Relay Server (Chạy trực tiếp trên Windows không cần cài nặng)
- Cổng mặc định: http://localhost:8787 (hoặc qua Wi-Fi LAN: http://192.168.102.80:8787)
- Cung cấp:
  1. Giao diện đồng hồ ảo Huawei Watch Fit 4 Pro (408x480 AMOLED) vẽ bản đồ Canvas y hệt code ArkTS.
  2. API /api/p2p nhận gói tin P2P ("S", "R", "M", "H") trực tiếp từ iPhone hoặc từ bộ phát thử.
  3. API /api/route, /api/roads, /api/search tương thích 100% với Cloudflare Worker (Mốc 3).
"""

import json
import math
import socket
import threading
import time
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORT = 8787


def get_lan_ip() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


# Trạng thái bộ nhớ đệm P2P giữa iPhone / Trình điều khiển và Đồng hồ ảo
STATE_LOCK = threading.Lock()
WATCH_HUB = {
    "lastPacketTs": time.time(),
    "mode": "SIMULATOR_DEMO",
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
        "rem": 1850,
        "vib": 0,
        "reroute": False,
    },
    "routeId": "demo_q1",
    "routePoints": [
        [10.774500, 106.698900],
        [10.775150, 106.699650],
        [10.775840, 106.700420],
        [10.776480, 106.701120],
        [10.775800, 106.701950],
        [10.775100, 106.702800],
        [10.774450, 106.703600],
        [10.775200, 106.704400],
        [10.776100, 106.705300],
    ],
    "routeChunks": {},
    "roadsTile": "demo_tile",
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
        {
            "n": "Hàm Nghi",
            "c": 1,
            "p": [
                [10.772200, 106.699800],
                [10.773100, 106.702500],
                [10.773900, 106.705100],
            ],
        },
    ],
    "roadChunks": {},
    "steps": [],
    "packetsReceived": 0,
    "recentLogs": [],
}


def add_log(msg: str) -> None:
    ts = time.strftime("%H:%M:%S")
    WATCH_HUB["recentLogs"].insert(0, f"[{ts}] {msg}")
    if len(WATCH_HUB["recentLogs"]) > 40:
        WATCH_HUB["recentLogs"].pop()


def process_p2p_packet(pkt: dict) -> None:
    with STATE_LOCK:
        pkt_type = pkt.get("t", "")
        if not pkt_type:
            return
        WATCH_HUB["lastPacketTs"] = time.time()
        WATCH_HUB["packetsReceived"] += 1
        WATCH_HUB["mode"] = "LIVE_P2P"

        if pkt_type == "H":
            add_log("Nhận Heartbeat (H) từ iPhone")
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
                f"P2P [S#{WATCH_HUB['state']['seq']}] {WATCH_HUB['state']['mType']} "
                f"{WATCH_HUB['state']['mDist']}m -> {WATCH_HUB['state']['road']} (vib={WATCH_HUB['state']['vib']})"
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
            add_log(f"P2P [R] Gói tuyến đường {idx + 1}/{tot} ({len(pts)} điểm)")
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
            add_log(f"P2P [M] Gói đường nền {idx + 1}/{tot} ({len(rds)} đoạn đường)")


def fetch_osrm_route(origin_lat: float, origin_lng: float, dest_lat: float, dest_lng: float) -> dict:
    coords = f"{origin_lng:.6f},{origin_lat:.6f};{dest_lng:.6f},{dest_lat:.6f}"
    url = f"https://router.project-osrm.org/route/v1/driving/{coords}?overview=full&geometries=geojson&steps=true"
    req = urllib.request.Request(url, headers={"User-Agent": "GNavigation-Simulator/1.0"})
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
        "routeId": f"sim_{int(time.time())}",
        "provider": "osm-simulator",
        "vehicle": "motorcycle",
        "distanceMeters": int(round(route.get("distance", 0))),
        "durationSeconds": int(round(route.get("duration", 0))),
        "points": pts,
        "steps": steps,
    }

    # Tự động cập nhật luôn lên mặt đồng hồ ảo khi iPhone gọi /api/route!
    with STATE_LOCK:
        WATCH_HUB["lastPacketTs"] = time.time()
        WATCH_HUB["mode"] = "LIVE_P2P"
        WATCH_HUB["routeId"] = result["routeId"]
        WATCH_HUB["routePoints"] = pts
        WATCH_HUB["steps"] = steps
        first_step = steps[1] if len(steps) > 1 else (steps[0] if steps else None)
        if pts:
            WATCH_HUB["state"]["lat"] = pts[0][0]
            WATCH_HUB["state"]["lng"] = pts[0][1]
        if len(pts) >= 2:
            dy = pts[1][0] - pts[0][0]
            dx = pts[1][1] - pts[0][1]
            WATCH_HUB["state"]["hdg"] = int((math.degrees(math.atan2(dx, dy)) + 360) % 360)
        if first_step:
            WATCH_HUB["state"]["mType"] = first_step["maneuverType"]
            WATCH_HUB["state"]["mDist"] = max(25, first_step["distanceMeters"])
            WATCH_HUB["state"]["road"] = first_step["roadName"]
        WATCH_HUB["state"]["rem"] = result["distanceMeters"]
        WATCH_HUB["state"]["eta"] = time.strftime(
            "%H:%M", time.localtime(time.time() + result["durationSeconds"])
        )
        WATCH_HUB["state"]["vib"] = 1
        WATCH_HUB["state"]["seq"] += 1
        add_log(
            f"Nhận tuyến đường mới ({len(pts)} điểm, {result['distanceMeters']}m) -> Đã đẩy lên đồng hồ ảo!"
        )

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


HTML_PAGE = r"""<!DOCTYPE html>
<html lang="vi">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>Huawei Watch Fit 4 Pro — Máy ảo G Navigation</title>
<style>
  :root {
    --bg: #070b10;
    --panel: #101824;
    --border: #1e2d42;
    --accent: #00e676;
    --cyan: #00e5ff;
    --warn: #ffa726;
    --danger: #ff5252;
    --text: #eceff1;
    --muted: #90a4ae;
  }
  * { box-sizing: border-box; }
  body {
    margin: 0;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    background: radial-gradient(circle at 25% 20%, #112233 0%, #06090e 70%);
    color: var(--text);
    min-height: 100vh;
    display: flex;
    flex-direction: column;
  }
  header {
    padding: 12px 24px;
    background: rgba(16, 24, 36, 0.85);
    border-bottom: 1px solid var(--border);
    display: flex;
    justify-content: space-between;
    align-items: center;
    flex-wrap: wrap;
    gap: 12px;
  }
  header h1 {
    margin: 0;
    font-size: 18px;
    display: flex;
    align-items: center;
    gap: 10px;
  }
  .badge {
    background: rgba(0, 229, 255, 0.15);
    color: var(--cyan);
    border: 1px solid var(--cyan);
    padding: 3px 10px;
    border-radius: 999px;
    font-size: 12px;
    font-weight: 600;
  }
  .main-grid {
    display: grid;
    grid-template-columns: 440px 1fr;
    gap: 24px;
    padding: 22px;
    max-width: 1400px;
    width: 100%;
    margin: 0 auto;
    align-items: start;
  }
  @media (max-width: 960px) {
    .main-grid { grid-template-columns: 1fr; justify-items: center; }
  }
  /* Khung vỏ đồng hồ Huawei Watch Fit 4 Pro */
  .watch-column {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 14px;
  }
  .watch-strap-top, .watch-strap-bottom {
    width: 170px;
    height: 36px;
    background: linear-gradient(90deg, #1b222c, #2c3746, #1b222c);
    border-radius: 10px;
    opacity: 0.85;
  }
  .watch-case {
    position: relative;
    width: 344px;
    height: 404px;
    background: linear-gradient(145deg, #3c4654, #1c222b);
    border-radius: 68px;
    padding: 16px;
    box-shadow:
      0 24px 60px rgba(0,0,0,0.75),
      inset 0 2px 4px rgba(255,255,255,0.25),
      inset 0 -3px 6px rgba(0,0,0,0.6);
    display: flex;
    align-items: center;
    justify-content: center;
    transition: transform 0.1s ease;
  }
  .watch-case.vibrating {
    animation: vibrateAnim 0.14s linear infinite;
    box-shadow: 0 0 36px rgba(0, 230, 118, 0.75), inset 0 2px 4px rgba(255,255,255,0.3);
  }
  @keyframes vibrateAnim {
    0% { transform: translate(0, 0) rotate(0deg); }
    25% { transform: translate(-3px, 1px) rotate(-0.8deg); }
    50% { transform: translate(3px, -1px) rotate(0.8deg); }
    75% { transform: translate(-2px, -1px) rotate(-0.5deg); }
    100% { transform: translate(0, 0) rotate(0deg); }
  }
  /* Núm xoay Digital Crown đỏ đặc trưng của Fit 4 Pro */
  .watch-crown {
    position: absolute;
    right: -13px;
    top: 86px;
    width: 13px;
    height: 48px;
    background: linear-gradient(180deg, #525d6e, #252c37);
    border-radius: 0 8px 8px 0;
    border-left: 3px solid #e53935;
    box-shadow: 2px 2px 6px rgba(0,0,0,0.5);
  }
  .watch-side-btn {
    position: absolute;
    right: -9px;
    top: 230px;
    width: 9px;
    height: 54px;
    background: linear-gradient(180deg, #434d5c, #202630);
    border-radius: 0 5px 5px 0;
  }
  .watch-screen {
    position: relative;
    width: 100%;
    height: 100%;
    background: #0A0E14;
    border-radius: 54px;
    overflow: hidden;
    border: 2px solid #05070a;
  }
  #mapCanvas {
    width: 100%;
    height: 100%;
    display: block;
  }
  /* Lớp phủ TurnBanner phía trên mặt đồng hồ */
  .turn-banner {
    position: absolute;
    top: 14px;
    left: 50%;
    transform: translateX(-50%);
    width: 90%;
    background: rgba(16, 27, 40, 0.88);
    border: 1px solid #26384c;
    border-radius: 22px;
    padding: 9px 12px;
    display: flex;
    align-items: center;
    gap: 10px;
    backdrop-filter: blur(6px);
    transition: all 0.2s ease;
  }
  .turn-banner.turn-now {
    background: rgba(0, 77, 64, 0.92);
    border-color: #00e676;
  }
  .turn-banner.reroute {
    background: rgba(78, 42, 4, 0.92);
    border-color: #ffa726;
  }
  .turn-banner.stale {
    background: rgba(38, 50, 56, 0.92);
    border-color: #ef5350;
  }
  .turn-icon-box {
    width: 44px;
    height: 44px;
    border-radius: 14px;
    background: #00b0ff;
    color: #05101a;
    font-size: 26px;
    font-weight: 800;
    display: flex;
    align-items: center;
    justify-content: center;
    flex-shrink: 0;
  }
  .turn-text-col {
    flex: 1;
    min-width: 0;
  }
  .turn-dist-row {
    display: flex;
    align-items: center;
    gap: 6px;
  }
  .turn-dist {
    font-size: 22px;
    font-weight: 800;
    color: #fff;
    line-height: 1.1;
  }
  .turn-now-pill {
    font-size: 9px;
    font-weight: 800;
    color: #00e676;
    background: rgba(0, 230, 118, 0.18);
    padding: 2px 6px;
    border-radius: 6px;
    display: none;
  }
  .turn-road {
    font-size: 13px;
    color: #cfd8dc;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    margin-top: 2px;
  }
  /* Nút thu phóng trên mặt đồng hồ */
  .zoom-controls {
    position: absolute;
    right: 10px;
    top: 50%;
    transform: translateY(-50%);
    display: flex;
    flex-direction: column;
    gap: 8px;
  }
  .zoom-btn {
    width: 30px;
    height: 30px;
    border-radius: 15px;
    border: 1px solid #26384c;
    background: rgba(16, 27, 40, 0.78);
    color: #e0f7fa;
    font-size: 16px;
    font-weight: bold;
    cursor: pointer;
  }
  /* Thanh trạng thái dưới cùng trên đồng hồ */
  .bottom-bar {
    position: absolute;
    bottom: 12px;
    left: 50%;
    transform: translateX(-50%);
    width: 86%;
    background: rgba(16, 27, 40, 0.9);
    border: 1px solid #243447;
    border-radius: 24px;
    padding: 7px 14px;
    display: flex;
    align-items: center;
    justify-content: space-between;
  }
  .spd-box {
    text-align: center;
  }
  .spd-val {
    font-size: 16px;
    font-weight: 800;
    color: var(--cyan);
    line-height: 1;
  }
  .spd-unit {
    font-size: 9px;
    color: #78909c;
  }
  .eta-box {
    text-align: center;
  }
  .rem-val {
    font-size: 13px;
    font-weight: 700;
    color: #fff;
  }
  .eta-val {
    font-size: 10px;
    color: #90a4ae;
  }
  .p2p-pill {
    display: flex;
    align-items: center;
    gap: 5px;
    font-size: 10px;
    font-weight: 700;
  }
  .p2p-dot {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    background: var(--accent);
  }
  /* Bảng điều khiển bên phải */
  .controls-column {
    display: flex;
    flex-direction: column;
    gap: 16px;
  }
  .card {
    background: var(--panel);
    border: 1px solid var(--border);
    border-radius: 16px;
    padding: 16px 18px;
  }
  .card h2 {
    margin: 0 0 10px 0;
    font-size: 15px;
    color: var(--cyan);
    display: flex;
    align-items: center;
    justify-content: space-between;
  }
  .btn-row {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
  }
  button.ctrl-btn {
    background: #1b2838;
    color: #fff;
    border: 1px solid #2c425c;
    border-radius: 10px;
    padding: 9px 13px;
    font-size: 13px;
    font-weight: 600;
    cursor: pointer;
    transition: all 0.15s;
  }
  button.ctrl-btn:hover {
    background: #25384e;
    border-color: var(--cyan);
  }
  button.ctrl-btn.primary {
    background: #00897b;
    border-color: #00e676;
  }
  button.ctrl-btn.warn {
    background: #e65100;
    border-color: #ffa726;
  }
  button.ctrl-btn.danger {
    background: #c62828;
    border-color: #ff5252;
  }
  .input-group {
    display: flex;
    gap: 8px;
    margin-bottom: 10px;
  }
  input[type="text"] {
    flex: 1;
    background: #090e15;
    border: 1px solid #26384c;
    color: #fff;
    padding: 9px 12px;
    border-radius: 10px;
    font-size: 13px;
  }
  .url-box {
    background: #080c12;
    border: 1px dashed var(--cyan);
    padding: 10px 12px;
    border-radius: 10px;
    font-family: monospace;
    font-size: 13px;
    color: var(--accent);
    margin: 6px 0;
    display: flex;
    justify-content: space-between;
    align-items: center;
  }
  .log-box {
    background: #070a0f;
    border: 1px solid #1b2738;
    border-radius: 10px;
    padding: 10px;
    height: 150px;
    overflow-y: auto;
    font-family: monospace;
    font-size: 12px;
    color: #b0bec5;
  }
  .log-line {
    padding: 2px 0;
    border-bottom: 1px solid rgba(255,255,255,0.04);
  }
  .vib-toast {
    height: 24px;
    font-size: 12px;
    font-weight: 700;
    color: var(--accent);
    text-align: center;
  }
</style>
</head>
<body>
<header>
  <h1>
    <span>⌚ Huawei Watch Fit 4 Pro — Máy ảo G Navigation</span>
    <span class="badge">408 × 480 AMOLED Canvas</span>
  </h1>
  <div style="font-size:13px;color:var(--muted);">
    Gói P2P đã nhận: <strong id="pktCount" style="color:var(--accent)">0</strong>
  </div>
</header>

<div class="main-grid">
  <!-- Cột trái: Đồng hồ ảo Huawei Watch Fit 4 Pro -->
  <div class="watch-column">
    <div class="watch-strap-top"></div>
    <div class="watch-case" id="watchCase">
      <div class="watch-crown" title="Núm xoay Digital Crown"></div>
      <div class="watch-side-btn" title="Nút chức năng"></div>
      <div class="watch-screen">
        <canvas id="mapCanvas" width="312" height="372"></canvas>

        <!-- Thẻ báo rẽ phía trên -->
        <div class="turn-banner" id="turnBanner">
          <div class="turn-icon-box" id="turnIcon">↱</div>
          <div class="turn-text-col">
            <div class="turn-dist-row">
              <span class="turn-dist" id="turnDist">85 m</span>
              <span class="turn-now-pill" id="turnNowPill">RẼ NGAY</span>
            </div>
            <div class="turn-road" id="turnRoad">Nguyễn Huệ</div>
          </div>
        </div>

        <!-- Nút Zoom -->
        <div class="zoom-controls">
          <button class="zoom-btn" onclick="adjustZoom(-0.3)">+</button>
          <button class="zoom-btn" onclick="adjustZoom(0.3)">−</button>
        </div>

        <!-- Thanh trạng thái dưới cùng -->
        <div class="bottom-bar">
          <div class="spd-box">
            <div class="spd-val" id="spdVal">32</div>
            <div class="spd-unit">km/h</div>
          </div>
          <div class="eta-box">
            <div class="rem-val" id="remVal">1.8 km</div>
            <div class="eta-val" id="etaVal">ETA 14:25</div>
          </div>
          <div class="p2p-pill">
            <span class="p2p-dot" id="p2pDot"></span>
            <span id="p2pLabel" style="color:#00e676">P2P</span>
          </div>
        </div>
      </div>
    </div>
    <div class="watch-strap-bottom"></div>
    <div class="vib-toast" id="vibToast"></div>
  </div>

  <!-- Cột phải: Bảng điều khiển kiểm thử & Kết nối với iPhone -->
  <div class="controls-column">
    <div class="card">
      <h2>
        <span>📱 1. Kết nối trực tiếp từ iPhone thật của bạn</span>
        <span style="font-size:11px;color:var(--accent)">Cùng mạng Wi-Fi</span>
      </h2>
      <div style="font-size:13px;color:var(--muted);line-height:1.45;">
        Mở app <strong>G Navigation</strong> trên iPhone → sang tab <strong>Cấu hình & Log</strong> → nhập địa chỉ máy ảo này vào ô <strong>URL Worker</strong> rồi bấm <strong>Lưu cấu hình</strong>:
      </div>
      <div class="url-box">
        <span id="lanUrlText">http://__LAN_IP__:8787</span>
        <button class="ctrl-btn" style="padding:4px 10px;font-size:11px" onclick="copyLanUrl()">Copy</button>
      </div>
      <div style="font-size:12px;color:var(--muted);">
        Sau đó ở tab <strong>Dẫn đường</strong> trên iPhone, khi bạn bấm <em>Nhà hát TP (Q.1)</em>, <em>Dinh Độc Lập</em> hoặc tìm đường bất kỳ, đồng hồ ảo bên trái sẽ tự động nhận tuyến đường và vẽ ngay lập tức!
      </div>
    </div>

    <div class="card">
      <h2>🛵 2. Giả lập chạy xe máy & Kiểm thử các Mốc (Mốc 1 → Mốc 4)</h2>
      <div class="btn-row">
        <button class="ctrl-btn primary" id="autoDriveBtn" onclick="toggleAutoDrive()">▶ Bắt đầu chạy xe dọc tuyến</button>
        <button class="ctrl-btn" onclick="stepForward()">⏭ Nhích 1 bước GPS</button>
        <button class="ctrl-btn" onclick="sendTurnNow30m()">🔔 Báo rẽ ngay (30m + Rung)</button>
        <button class="ctrl-btn warn" onclick="simulateOffRoute()">⚠ Giả lập đi lệch tuyến (Reroute)</button>
        <button class="ctrl-btn danger" onclick="simulateDisconnect()">🔌 Ngắt kết nối Bluetooth (Mốc 4)</button>
      </div>
    </div>

    <div class="card">
      <h2>🗺️ 3. Tìm đường xe máy thật (OSRM / VIETMAP) ngay trên máy ảo</h2>
      <div class="btn-row" style="margin-bottom:10px;">
        <button class="ctrl-btn" onclick="loadRealRoute(10.7721,106.6983, 10.7769,106.7032, 'Chợ Bến Thành → Nhà hát TP')">Chợ Bến Thành → Nhà hát TP</button>
        <button class="ctrl-btn" onclick="loadRealRoute(10.7769,106.7032, 10.7770,106.6953, 'Nhà hát TP → Dinh Độc Lập')">Nhà hát TP → Dinh Độc Lập</button>
        <button class="ctrl-btn" onclick="loadRealRoute(10.7770,106.6953, 10.7880,106.7052, 'Dinh Độc Lập → Thảo Cầm Viên')">Dinh Độc Lập → Thảo Cầm Viên</button>
      </div>
      <div style="font-size:12px;color:var(--muted);">
        Bấm một tuyến bất kỳ ở trên để máy ảo tải toàn bộ tọa độ đường phố thật và chạy mô phỏng từng ngã rẽ trên mặt đồng hồ.
      </div>
    </div>

    <div class="card">
      <h2>📡 Nhật ký gói tin P2P thời gian thực</h2>
      <div class="log-box" id="logBox"></div>
    </div>
  </div>
</div>

<script>
let zoomScaleMetersPerPx = 1.65;
let hubData = null;
let autoDriveTimer = null;
let routeCursor = 0;
let lastVibSeq = -1;
let forceStale = false;

const MANEUVER_SYMBOLS = {
  STRAIGHT: '↑',
  TURN_LEFT: '↰',
  TURN_RIGHT: '↱',
  SLIGHT_LEFT: '↖',
  SLIGHT_RIGHT: '↗',
  SHARP_LEFT: '↙',
  SHARP_RIGHT: '↘',
  UTURN: '↶',
  ROUNDABOUT: '⟳',
  ARRIVE: '🏁'
};

function adjustZoom(delta) {
  const next = zoomScaleMetersPerPx + delta;
  if (next >= 0.7 && next <= 4.0) {
    zoomScaleMetersPerPx = next;
    renderWatch();
  }
}

function copyLanUrl() {
  const txt = document.getElementById('lanUrlText').innerText;
  navigator.clipboard.writeText(txt);
}

async function pollState() {
  try {
    const res = await fetch('/api/state');
    hubData = await res.json();
    renderWatch();
  } catch (e) {}
}

function projectToScreen(lat, lng, centerLat, centerLng, heading, w, h) {
  const cosLat = Math.cos(centerLat * Math.PI / 180.0);
  const northMeters = (lat - centerLat) * 111320.0;
  const eastMeters = (lng - centerLng) * 111320.0 * cosLat;

  const rad = (heading * Math.PI) / 180.0;
  const cosH = Math.cos(rad);
  const sinH = Math.sin(rad);

  const rotX = eastMeters * cosH - northMeters * sinH;
  const rotY = eastMeters * sinH + northMeters * cosH;

  const anchorX = w * 0.5;
  const anchorY = h * 0.67;

  return {
    x: anchorX + rotX / zoomScaleMetersPerPx,
    y: anchorY - rotY / zoomScaleMetersPerPx
  };
}

function triggerVibrationUI(vibCode, seq) {
  if (!vibCode || seq === lastVibSeq) return;
  lastVibSeq = seq;
  const watchCase = document.getElementById('watchCase');
  const toast = document.getElementById('vibToast');
  watchCase.classList.add('vibrating');
  if (vibCode === 1) {
    toast.innerText = '📳 RUNG 2 NHỊP: Sắp tới ngã rẽ (100m)';
  } else if (vibCode === 2) {
    toast.innerText = '📳 RUNG MẠNH: Rẽ ngay (30m)!';
  } else if (vibCode === 3) {
    toast.innerText = '📳 RUNG CẢNH BÁO 3 NHỊP: Đi lệch tuyến — Đang tính lại đường!';
  }
  setTimeout(() => {
    watchCase.classList.remove('vibrating');
  }, 900);
}

function renderWatch() {
  if (!hubData) return;
  const s = hubData.state;
  const roads = hubData.roads || [];
  const route = hubData.routePoints || [];
  const isStale = forceStale || (hubData.ageSeconds > 12 && hubData.mode === 'LIVE_P2P');

  document.getElementById('pktCount').innerText = hubData.packetsReceived;

  // Cập nhật TurnBanner
  const banner = document.getElementById('turnBanner');
  const iconBox = document.getElementById('turnIcon');
  const distEl = document.getElementById('turnDist');
  const roadEl = document.getElementById('turnRoad');
  const pillEl = document.getElementById('turnNowPill');

  banner.className = 'turn-banner';
  if (isStale) {
    banner.classList.add('stale');
    iconBox.style.background = '#546e7a';
    iconBox.innerText = '⚠';
    distEl.innerText = 'Mất dữ liệu';
    roadEl.innerText = 'Đã ẩn chỉ dẫn cũ · Chờ nối lại';
    pillEl.style.display = 'none';
  } else if (s.reroute) {
    banner.classList.add('reroute');
    iconBox.style.background = '#ffa726';
    iconBox.innerText = '↻';
    distEl.innerText = 'Lệch tuyến';
    roadEl.innerText = 'Đang tính lại đường...';
    pillEl.style.display = 'none';
  } else {
    if (s.mDist <= 40) {
      banner.classList.add('turn-now');
      iconBox.style.background = '#00e676';
      pillEl.style.display = 'inline-block';
    } else {
      iconBox.style.background = '#00b0ff';
      pillEl.style.display = 'none';
    }
    iconBox.innerText = MANEUVER_SYMBOLS[s.mType] || '↑';
    distEl.innerText = s.mDist >= 1000 ? (s.mDist / 1000).toFixed(1) + ' km' : s.mDist + ' m';
    roadEl.innerText = s.road || 'Đường phía trước';
  }

  // Cập nhật BottomBar
  document.getElementById('spdVal').innerText = Math.round(s.spd || 0);
  document.getElementById('remVal').innerText = s.rem >= 1000 ? (s.rem / 1000).toFixed(1) + ' km' : s.rem + ' m';
  document.getElementById('etaVal').innerText = 'ETA ' + (s.eta || '--:--');

  const dot = document.getElementById('p2pDot');
  const lbl = document.getElementById('p2pLabel');
  if (isStale) {
    dot.style.background = '#ff5252';
    lbl.style.color = '#ff5252';
    lbl.innerText = 'MẤT KN';
  } else {
    dot.style.background = '#00e676';
    lbl.style.color = '#00e676';
    lbl.innerText = 'P2P';
  }

  triggerVibrationUI(s.vib, s.seq);

  // Vẽ bản đồ Canvas
  const canvas = document.getElementById('mapCanvas');
  const c = canvas.getContext('2d');
  const w = canvas.width;
  const h = canvas.height;
  const anchorX = w * 0.5;
  const anchorY = h * 0.67;

  c.clearRect(0, 0, w, h);
  c.fillStyle = '#0A0E14';
  c.fillRect(0, 0, w, h);

  // Vòng bán kính 100m
  c.strokeStyle = '#142030';
  c.lineWidth = 1;
  c.beginPath();
  c.arc(anchorX, anchorY, 100 / zoomScaleMetersPerPx, 0, Math.PI * 2);
  c.stroke();

  // Vẽ đường nền xung quanh
  for (const seg of roads) {
    if (!seg.p || seg.p.length < 2) continue;
    c.save();
    c.lineCap = 'round';
    c.lineJoin = 'round';
    c.strokeStyle = seg.c === 1 ? '#263447' : (seg.c === 2 ? '#1C2736' : '#151E2B');
    c.lineWidth = seg.c === 1 ? 8 : (seg.c === 2 ? 5 : 3);
    c.beginPath();
    const p0 = projectToScreen(seg.p[0][0], seg.p[0][1], s.lat, s.lng, s.hdg, w, h);
    c.moveTo(p0.x, p0.y);
    for (let i = 1; i < seg.p.length; i++) {
      const pi = projectToScreen(seg.p[i][0], seg.p[i][1], s.lat, s.lng, s.hdg, w, h);
      c.lineTo(pi.x, pi.y);
    }
    c.stroke();

    if (seg.n && seg.c <= 2) {
      const mid = seg.p[Math.floor(seg.p.length / 2)];
      const mp = projectToScreen(mid[0], mid[1], s.lat, s.lng, s.hdg, w, h);
      if (mp.x > 25 && mp.x < w - 25 && mp.y > 85 && mp.y < h - 55) {
        c.fillStyle = '#607d8b';
        c.font = '11px sans-serif';
        c.textAlign = 'center';
        c.fillText(seg.n, mp.x, mp.y - 5);
      }
    }
    c.restore();
  }

  // Vẽ tuyến đường chính
  if (route.length >= 2) {
    c.save();
    c.lineCap = 'round';
    c.lineJoin = 'round';
    c.strokeStyle = '#062B1F';
    c.lineWidth = 12;
    c.beginPath();
    const r0 = projectToScreen(route[0][0], route[0][1], s.lat, s.lng, s.hdg, w, h);
    c.moveTo(r0.x, r0.y);
    for (let i = 1; i < route.length; i++) {
      const ri = projectToScreen(route[i][0], route[i][1], s.lat, s.lng, s.hdg, w, h);
      c.lineTo(ri.x, ri.y);
    }
    c.stroke();

    c.strokeStyle = isStale ? '#4B5B6E' : (s.reroute ? '#FFA726' : '#00E676');
    c.lineWidth = 7;
    c.stroke();

    for (let i = 1; i < route.length - 1; i++) {
      const ni = projectToScreen(route[i][0], route[i][1], s.lat, s.lng, s.hdg, w, h);
      if (ni.y < anchorY + 12 && ni.y > 70) {
        c.fillStyle = '#ffffff';
        c.beginPath();
        c.arc(ni.x, ni.y, 3.2, 0, Math.PI * 2);
        c.fill();
      }
    }
    c.restore();
  }

  // Vẽ mũi tên vị trí xe máy
  c.save();
  c.fillStyle = isStale ? 'rgba(120, 144, 156, 0.22)' : 'rgba(0, 229, 255, 0.22)';
  c.beginPath();
  c.arc(anchorX, anchorY, 20, 0, Math.PI * 2);
  c.fill();

  c.fillStyle = isStale ? '#90A4AE' : '#00E5FF';
  c.strokeStyle = '#FFFFFF';
  c.lineWidth = 2;
  c.beginPath();
  c.moveTo(anchorX, anchorY - 12);
  c.lineTo(anchorX + 10, anchorY + 10);
  c.lineTo(anchorX, anchorY + 4);
  c.lineTo(anchorX - 10, anchorY + 10);
  c.closePath();
  c.fill();
  c.stroke();
  c.restore();

  // Cập nhật nhật ký
  const logBox = document.getElementById('logBox');
  logBox.innerHTML = (hubData.recentLogs || []).map(l => `<div class="log-line">${l}</div>`).join('');
}

async function sendP2P(pkt) {
  forceStale = false;
  await fetch('/api/p2p', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(pkt)
  });
  await pollState();
}

async function stepForward() {
  if (!hubData || !hubData.routePoints || hubData.routePoints.length < 2) return;
  const pts = hubData.routePoints;
  routeCursor = (routeCursor + 1) % (pts.length - 1);
  const curr = pts[routeCursor];
  const next = pts[routeCursor + 1];

  const dy = next[0] - curr[0];
  const dx = next[1] - curr[1];
  const hdg = Math.round((Math.atan2(dx, dy) * 180 / Math.PI + 360) % 360);
  const mDist = Math.max(15, (pts.length - 1 - routeCursor) * 35);
  const vib = mDist <= 35 ? 2 : (mDist <= 105 && mDist >= 70 ? 1 : 0);

  await sendP2P({
    t: 'S',
    seq: (hubData.state.seq || 0) + 1,
    ts: Math.floor(Date.now() / 1000),
    lat: curr[0],
    lng: curr[1],
    hdg: hdg,
    spd: 30 + (routeCursor % 4) * 3,
    mType: routeCursor < pts.length / 2 ? 'TURN_RIGHT' : 'TURN_LEFT',
    mDist: mDist,
    road: hubData.state.road || 'Nguyễn Huệ',
    eta: hubData.state.eta || '14:25',
    rem: Math.max(80, (pts.length - routeCursor) * 180),
    vib: vib,
    reroute: false
  });
}

function toggleAutoDrive() {
  const btn = document.getElementById('autoDriveBtn');
  if (autoDriveTimer) {
    clearInterval(autoDriveTimer);
    autoDriveTimer = null;
    btn.innerText = '▶ Bắt đầu chạy xe dọc tuyến';
  } else {
    stepForward();
    autoDriveTimer = setInterval(stepForward, 1400);
    btn.innerText = '⏸ Dừng chạy tự động';
  }
}

async function sendTurnNow30m() {
  if (!hubData) return;
  const s = hubData.state;
  await sendP2P({
    ...s,
    t: 'S',
    seq: s.seq + 1,
    mDist: 28,
    vib: 2,
    reroute: false
  });
}

async function simulateOffRoute() {
  if (autoDriveTimer) toggleAutoDrive();
  if (!hubData) return;
  const s = hubData.state;
  await sendP2P({
    ...s,
    t: 'S',
    seq: s.seq + 1,
    lat: s.lat + 0.00028,
    lng: s.lng - 0.00022,
    hdg: (s.hdg + 65) % 360,
    mType: 'UTURN',
    mDist: 45,
    road: 'Đang tính lại đường...',
    vib: 3,
    reroute: true
  });
}

function simulateDisconnect() {
  if (autoDriveTimer) toggleAutoDrive();
  forceStale = true;
  renderWatch();
}

async function loadRealRoute(oLat, oLng, dLat, dLng, label) {
  routeCursor = 0;
  forceStale = false;
  await fetch(`/api/route?origin=${oLat},${oLng}&dest=${dLat},${dLng}&vehicle=motorcycle`);
  await pollState();
}

setInterval(pollState, 1000);
pollState();
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

        if path in ("/", "/watch"):
            lan_ip = get_lan_ip()
            html = HTML_PAGE.replace("__LAN_IP__", lan_ip).encode("utf-8")
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
            with STATE_LOCK:
                self._send_json({"tile": WATCH_HUB["roadsTile"], "roads": WATCH_HUB["roads"]})
            return

        if path == "/api/search":
            q = (qs.get("q") or [""])[0].strip()
            if not q:
                self._send_json({"results": []})
                return
            try:
                nom_url = (
                    "https://nominatim.openstreetmap.org/search?format=json&countrycodes=vn&limit=5&q="
                    + urllib.parse.quote(q)
                )
                req = urllib.request.Request(nom_url, headers={"User-Agent": "GNavigation-Simulator/1.0"})
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
                add_log(f"iPhone tìm kiếm địa điểm: '{q}' ({len(results)} kết quả)")
                self._send_json({"provider": "simulator", "results": results})
            except Exception as e:
                self._send_json({"results": [], "error": str(e)})
            return

        self._send_json({"ok": True, "service": "g-navigation-watch-simulator"})

    def do_POST(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length) if length > 0 else b"{}"
        try:
            payload = json.loads(raw.decode("utf-8"))
        except Exception:
            payload = {}

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
    print(f" Watch Fit 4 Pro Virtual Simulator đang chạy tại:")
    print(f" -> Trên máy tính này: http://localhost:{PORT}")
    print(f" -> Kết nối từ iPhone (cùng Wi-Fi): http://{lan_ip}:{PORT}")
    print(f"============================================================")
    server.serve_forever()
