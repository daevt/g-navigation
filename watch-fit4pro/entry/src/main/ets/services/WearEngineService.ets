import hilog from '@ohos.hilog';
import util from '@ohos.util';
import {
  ConnectionMode,
  DemoDataset,
  GeoPoint,
  ManeuverType,
  NavState,
  RoadSegment
} from '../models/NavModels';
import { VibrationService } from './VibrationService';

/**
 * Cấu hình định danh ứng dụng iPhone đối tác qua Huawei Wear Engine P2P.
 * BẮT BUỘC khớp với Bundle ID thực tế của app iPhone (xem SETUP_GUIDE.md).
 */
export class WearEngineConfig {
  static readonly IOS_PEER_BUNDLE_ID: string = 'com.gnavigation.ios';
  /** Phải khớp với chứng chỉ / App ID đăng ký trên Huawei Developer Console */
  static readonly IOS_PEER_FINGERPRINT: string = 'com.gnavigation.ios';
  /** Thời gian tối đa (ms) không nhận được gói tin trước khi ẩn chỉ dẫn cũ (Mốc 4) */
  static readonly STALE_TIMEOUT_MS: number = 12000;
}

export type NavUpdateCallback = (
  state: NavState,
  route: GeoPoint[],
  roads: RoadSegment[],
  mode: ConnectionMode
) => void;

export class WearEngineService {
  private currentState: NavState = new NavState();
  private currentRoute: GeoPoint[] = DemoDataset.getSampleRoute();
  private currentRoads: RoadSegment[] = DemoDataset.getSampleRoads();
  private connectionMode: ConnectionMode = 'SIMULATOR_DEMO';

  private lastPacketTimeMs: number = Date.now();
  private currentRouteId: string = 'demo_route';
  private routeChunks: Map<number, GeoPoint[]> = new Map();
  private expectedRouteChunkTotal: number = 0;

  private currentTileId: string = '';
  private roadChunks: Map<number, RoadSegment[]> = new Map();
  private expectedRoadChunkTotal: number = 0;

  private listener: NavUpdateCallback | null = null;
  private watchdogTimerId: number = -1;
  private demoTimerId: number = -1;
  private demoProgressIdx: number = 2;

  setUpdateListener(cb: NavUpdateCallback): void {
    this.listener = cb;
    this.notifyListener();
  }

  /**
   * Khởi tạo lắng nghe Wear Engine P2P và bộ canh thời gian mất kết nối (Watchdog)
   */
  start(): void {
    this.startWatchdog();
    this.registerWearEngineP2P();
  }

  stop(): void {
    if (this.watchdogTimerId !== -1) {
      clearInterval(this.watchdogTimerId);
      this.watchdogTimerId = -1;
    }
    this.stopSimulatorWalk();
  }

  /**
   * Đăng ký nhận bản tin P2P từ iPhone qua Huawei Wear Engine SDK trên HarmonyOS.
   * Ghi chú: Trên máy ảo DevEco Simulator chưa có dịch vụ Wear Engine vật lý,
   * hàm này tự động giữ chế độ SIMULATOR_DEMO để bạn kiểm thử giao diện ở Mốc 1.
   */
  private registerWearEngineP2P(): void {
    try {
      // Khi build trên DevEco Studio có gắn kit @hms.core.wearEngine:
      // Bỏ comment khối import wearEngine khi chạy trên thiết bị thật có HMS Wear Engine Kit,
      // hoặc truyền payload từ EntryAbility / P2P Receiver vào handleRawPayloadBytes().
      hilog.info(
        0x0000,
        'GNavWatch',
        'WearEngine P2P ready for peer %{public}s',
        WearEngineConfig.IOS_PEER_BUNDLE_ID
      );
    } catch (e) {
      hilog.warn(0x0000, 'GNavWatch', 'Running in Simulator / No WearEngine hardware: %{public}s', JSON.stringify(e));
    }
  }

  /**
   * Nhận mảng byte UTF-8 từ callback của Wear Engine P2P
   */
  handleRawPayloadBytes(bytes: Uint8Array): void {
    try {
      const decoder = util.TextDecoder.create('utf-8');
      const jsonStr = decoder.decodeWithStream(bytes);
      this.handleIncomingJson(jsonStr);
    } catch (e) {
      hilog.error(0x0000, 'GNavWatch', 'Failed to decode P2P bytes: %{public}s', JSON.stringify(e));
    }
  }

  /**
   * Giải mã các gói tin JSON rút gọn: "S" (State), "R" (Route Chunk), "M" (Map Roads), "H" (Heartbeat)
   */
  handleIncomingJson(jsonStr: string): void {
    try {
      const pkt: Record<string, Object> = JSON.parse(jsonStr) as Record<string, Object>;
      const pktType = String(pkt['t'] ?? '');
      if (!pktType) {
        return;
      }

      this.lastPacketTimeMs = Date.now();
      this.stopSimulatorWalk();
      this.connectionMode = 'LIVE_P2P';

      if (pktType === 'H') {
        // Heartbeat giữ kết nối sống khi dừng đèn đỏ
        this.notifyListener();
        return;
      }

      if (pktType === 'S') {
        const nextState = new NavState();
        nextState.seq = Number(pkt['seq'] ?? (this.currentState.seq + 1));
        nextState.timestampSec = Number(pkt['ts'] ?? Math.floor(Date.now() / 1000));
        nextState.lat = Number(pkt['lat'] ?? this.currentState.lat);
        nextState.lng = Number(pkt['lng'] ?? this.currentState.lng);
        nextState.heading = Number(pkt['hdg'] ?? this.currentState.heading);
        nextState.speedKmh = Number(pkt['spd'] ?? 0);
        nextState.maneuverType = (String(pkt['mType'] ?? 'STRAIGHT')) as ManeuverType;
        nextState.maneuverDistMeters = Number(pkt['mDist'] ?? 0);
        nextState.nextRoadName = String(pkt['road'] ?? '');
        nextState.etaText = String(pkt['eta'] ?? '--:--');
        nextState.remainingMeters = Number(pkt['rem'] ?? 0);
        nextState.vibrationCode = Number(pkt['vib'] ?? 0);
        nextState.isRerouting = Boolean(pkt['reroute'] ?? false);

        this.currentState = nextState;
        VibrationService.triggerByPacket(nextState.seq, nextState.vibrationCode);
        this.notifyListener();
        return;
      }

      if (pktType === 'R') {
        const routeId = String(pkt['id'] ?? 'rt_live');
        const idx = Number(pkt['idx'] ?? 0);
        const tot = Number(pkt['tot'] ?? 1);
        const rawPts = pkt['pts'] as number[][];

        if (routeId !== this.currentRouteId) {
          this.currentRouteId = routeId;
          this.routeChunks.clear();
          this.expectedRouteChunkTotal = tot;
        }

        const chunkPoints: GeoPoint[] = [];
        if (Array.isArray(rawPts)) {
          for (let i = 0; i < rawPts.length; i++) {
            const pair = rawPts[i];
            if (Array.isArray(pair) && pair.length >= 2) {
              chunkPoints.push(new GeoPoint(Number(pair[0]), Number(pair[1])));
            }
          }
        }
        this.routeChunks.set(idx, chunkPoints);

        // Ghép các mảnh tuyến đường theo thứ tự
        const merged: GeoPoint[] = [];
        for (let c = 0; c < this.expectedRouteChunkTotal; c++) {
          const part = this.routeChunks.get(c);
          if (part) {
            for (let j = 0; j < part.length; j++) {
              merged.push(part[j]);
            }
          }
        }
        if (merged.length >= 2) {
          this.currentRoute = merged;
          this.notifyListener();
        }
        return;
      }

      if (pktType === 'M') {
        const tileId = String(pkt['tile'] ?? 'tile_0');
        const idx = Number(pkt['idx'] ?? 0);
        const tot = Number(pkt['tot'] ?? 1);
        const rawRoads = pkt['rds'] as Record<string, Object>[];

        if (tileId !== this.currentTileId) {
          this.currentTileId = tileId;
          this.roadChunks.clear();
          this.expectedRoadChunkTotal = tot;
        }

        const parsedSegments: RoadSegment[] = [];
        if (Array.isArray(rawRoads)) {
          for (let i = 0; i < rawRoads.length; i++) {
            const rObj = rawRoads[i];
            const rName = String(rObj['n'] ?? '');
            const rClass = Number(rObj['c'] ?? 2);
            const rPtsRaw = rObj['p'] as number[][];
            const pts: GeoPoint[] = [];
            if (Array.isArray(rPtsRaw)) {
              for (let k = 0; k < rPtsRaw.length; k++) {
                const pair = rPtsRaw[k];
                if (Array.isArray(pair) && pair.length >= 2) {
                  pts.push(new GeoPoint(Number(pair[0]), Number(pair[1])));
                }
              }
            }
            if (pts.length >= 2) {
              parsedSegments.push(new RoadSegment(rName, rClass, pts));
            }
          }
        }

        this.roadChunks.set(idx, parsedSegments);
        const mergedRoads: RoadSegment[] = [];
        for (let c = 0; c < this.expectedRoadChunkTotal; c++) {
          const part = this.roadChunks.get(c);
          if (part) {
            for (let j = 0; j < part.length; j++) {
              mergedRoads.push(part[j]);
            }
          }
        }
        if (mergedRoads.length > 0) {
          this.currentRoads = mergedRoads;
          this.notifyListener();
        }
      }
    } catch (err) {
      hilog.error(0x0000, 'GNavWatch', 'Invalid P2P JSON: %{public}s', JSON.stringify(err));
    }
  }

  /**
   * Bộ canh thời gian (Watchdog): Nếu đang ở LIVE_P2P mà quá 12 giây không có gói tin mới,
   * tự động chuyển sang STALE_DISCONNECTED để ẩn chỉ dẫn cũ (đáp ứng Mốc 4).
   */
  private startWatchdog(): void {
    if (this.watchdogTimerId !== -1) {
      clearInterval(this.watchdogTimerId);
    }
    this.watchdogTimerId = setInterval(() => {
      if (this.connectionMode === 'LIVE_P2P') {
        const elapsed = Date.now() - this.lastPacketTimeMs;
        if (elapsed > WearEngineConfig.STALE_TIMEOUT_MS) {
          this.connectionMode = 'STALE_DISCONNECTED';
          this.notifyListener();
        }
      }
    }, 2000);
  }

  // --- Các chế độ mô phỏng dành cho Mốc 1 (DevEco Simulator) & Mốc 4 ---

  startSimulatorWalk(): void {
    this.stopSimulatorWalk();
    this.connectionMode = 'SIMULATOR_DEMO';
    this.currentRoute = DemoDataset.getSampleRoute();
    this.currentRoads = DemoDataset.getSampleRoads();
    this.demoProgressIdx = 1;

    this.demoTimerId = setInterval(() => {
      this.stepSimulation();
    }, 1800);
  }

  stopSimulatorWalk(): void {
    if (this.demoTimerId !== -1) {
      clearInterval(this.demoTimerId);
      this.demoTimerId = -1;
    }
  }

  stepSimulation(): void {
    const pts = this.currentRoute;
    if (pts.length < 2) {
      return;
    }
    this.demoProgressIdx = (this.demoProgressIdx + 1) % (pts.length - 1);
    const curr = pts[this.demoProgressIdx];
    const next = pts[this.demoProgressIdx + 1];

    const dy = next.lat - curr.lat;
    const dx = next.lng - curr.lng;
    const angleDeg = (Math.atan2(dx, dy) * 180 / Math.PI + 360) % 360;

    const nextState = new NavState();
    nextState.seq = this.currentState.seq + 1;
    nextState.lat = curr.lat;
    nextState.lng = curr.lng;
    nextState.heading = Math.round(angleDeg);
    nextState.speedKmh = 30 + (this.demoProgressIdx % 3) * 4;
    nextState.isRerouting = false;

    if (this.demoProgressIdx <= 2) {
      nextState.maneuverType = 'TURN_RIGHT';
      nextState.maneuverDistMeters = Math.max(15, (3 - this.demoProgressIdx) * 45);
      nextState.nextRoadName = 'Nguyễn Huệ';
      nextState.vibrationCode = nextState.maneuverDistMeters <= 45 ? 2 : 0;
    } else if (this.demoProgressIdx <= 5) {
      nextState.maneuverType = 'TURN_LEFT';
      nextState.maneuverDistMeters = Math.max(20, (6 - this.demoProgressIdx) * 55);
      nextState.nextRoadName = 'Đồng Khởi';
      nextState.vibrationCode = 0;
    } else {
      nextState.maneuverType = 'ARRIVE';
      nextState.maneuverDistMeters = 30;
      nextState.nextRoadName = 'Nhà hát Thành phố';
      nextState.vibrationCode = 1;
    }

    nextState.etaText = '14:25';
    nextState.remainingMeters = Math.max(120, (pts.length - this.demoProgressIdx) * 280);

    this.currentState = nextState;
    this.connectionMode = 'SIMULATOR_DEMO';
    VibrationService.triggerByPacket(nextState.seq, nextState.vibrationCode);
    this.notifyListener();
  }

  simulateRerouteAlert(): void {
    this.stopSimulatorWalk();
    const s = new NavState();
    s.seq = this.currentState.seq + 1;
    s.lat = this.currentState.lat + 0.00025;
    s.lng = this.currentState.lng - 0.00020;
    s.heading = (this.currentState.heading + 55) % 360;
    s.speedKmh = 26;
    s.isRerouting = true;
    s.maneuverType = 'UTURN';
    s.maneuverDistMeters = 40;
    s.nextRoadName = 'Đang tính lại tuyến...';
    s.etaText = '--:--';
    s.remainingMeters = this.currentState.remainingMeters + 350;
    s.vibrationCode = 3;

    this.currentState = s;
    this.connectionMode = 'SIMULATOR_DEMO';
    VibrationService.triggerByPacket(s.seq, s.vibrationCode);
    this.notifyListener();
  }

  simulateDisconnectStale(): void {
    this.stopSimulatorWalk();
    this.connectionMode = 'STALE_DISCONNECTED';
    this.notifyListener();
  }

  private notifyListener(): void {
    if (this.listener) {
      this.listener(
        this.currentState,
        this.currentRoute,
        this.currentRoads,
        this.connectionMode
      );
    }
  }
}
