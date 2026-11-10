/**
 * Mô hình dữ liệu dẫn đường trên đồng hồ Huawei Watch Fit 4 Pro (ArkTS Strict Mode)
 */

export type ManeuverType =
  | 'STRAIGHT'
  | 'TURN_LEFT'
  | 'TURN_RIGHT'
  | 'SLIGHT_LEFT'
  | 'SLIGHT_RIGHT'
  | 'SHARP_LEFT'
  | 'SHARP_RIGHT'
  | 'UTURN'
  | 'ROUNDABOUT'
  | 'ARRIVE';

export class GeoPoint {
  lat: number = 0;
  lng: number = 0;

  constructor(lat: number, lng: number) {
    this.lat = lat;
    this.lng = lng;
  }
}

export class RoadSegment {
  /** Tên đường */
  name: string = '';
  /** Cấp đường: 1 = trục chính, 2 = đường phố, 3 = đường nội bộ/hẻm */
  roadClass: number = 2;
  /** Danh sách tọa độ */
  points: GeoPoint[] = [];

  constructor(name: string, roadClass: number, points: GeoPoint[]) {
    this.name = name;
    this.roadClass = roadClass;
    this.points = points;
  }
}

export class NavState {
  seq: number = 0;
  timestampSec: number = 0;
  lat: number = 10.775840;
  lng: number = 106.700420;
  heading: number = 42;
  speedKmh: number = 32;
  maneuverType: ManeuverType = 'TURN_RIGHT';
  maneuverDistMeters: number = 85;
  nextRoadName: string = 'Lê Lợi';
  etaText: string = '14:25';
  remainingMeters: number = 3420;
  vibrationCode: number = 0;
  isRerouting: boolean = false;
}

export type ConnectionMode = 'LIVE_P2P' | 'SIMULATOR_DEMO' | 'STALE_DISCONNECTED';

/**
 * Dữ liệu mẫu khu vực trung tâm Quận 1 (Lê Lợi - Nguyễn Huệ - Pasteur - Nam Kỳ Khởi Nghĩa)
 * Dùng cho Mốc 1 (chạy trong DevEco Simulator) và khi kiểm thử giao diện trực tiếp trên đồng hồ.
 */
export class DemoDataset {
  static getSampleRoute(): GeoPoint[] {
    return [
      new GeoPoint(10.774500, 106.698900),
      new GeoPoint(10.775150, 106.699650),
      new GeoPoint(10.775840, 106.700420),
      new GeoPoint(10.776480, 106.701120), // Giao lộ rẽ phải vào Lê Lợi / Nguyễn Huệ
      new GeoPoint(10.775800, 106.701950),
      new GeoPoint(10.775100, 106.702800),
      new GeoPoint(10.774450, 106.703600),
      new GeoPoint(10.775200, 106.704400),
      new GeoPoint(10.776100, 106.705300)
    ];
  }

  static getSampleRoads(): RoadSegment[] {
    return [
      new RoadSegment('Lê Lợi', 1, [
        new GeoPoint(10.773800, 106.698100),
        new GeoPoint(10.775150, 106.699650),
        new GeoPoint(10.776480, 106.701120),
        new GeoPoint(10.777600, 106.702400)
      ]),
      new RoadSegment('Nguyễn Huệ', 1, [
        new GeoPoint(10.777400, 106.700100),
        new GeoPoint(10.776480, 106.701120),
        new GeoPoint(10.775100, 106.702800),
        new GeoPoint(10.773600, 106.704600)
      ]),
      new RoadSegment('Pasteur', 2, [
        new GeoPoint(10.776900, 106.698200),
        new GeoPoint(10.775500, 106.699800),
        new GeoPoint(10.774000, 106.701500)
      ]),
      new RoadSegment('Nam Kỳ Khởi Nghĩa', 1, [
        new GeoPoint(10.776100, 106.697400),
        new GeoPoint(10.774700, 106.699000),
        new GeoPoint(10.773200, 106.700700)
      ]),
      new RoadSegment('Hàm Nghi', 1, [
        new GeoPoint(10.772200, 106.699800),
        new GeoPoint(10.773100, 106.702500),
        new GeoPoint(10.773900, 106.705100)
      ]),
      new RoadSegment('Đồng Khởi', 2, [
        new GeoPoint(10.778200, 106.701800),
        new GeoPoint(10.776600, 106.703500),
        new GeoPoint(10.775000, 106.705200)
      ]),
      new RoadSegment('Lê Thánh Tôn', 2, [
        new GeoPoint(10.774900, 106.697500),
        new GeoPoint(10.776900, 106.699900),
        new GeoPoint(10.778600, 106.701900)
      ]),
      new RoadSegment('Mạc Thị Bưởi', 3, [
        new GeoPoint(10.775500, 106.702200),
        new GeoPoint(10.776700, 106.703600)
      ])
    ];
  }
}
