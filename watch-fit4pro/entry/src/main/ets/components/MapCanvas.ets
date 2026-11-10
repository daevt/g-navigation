import { GeoPoint, NavState, RoadSegment } from '../models/NavModels';

class ScreenPt {
  x: number = 0;
  y: number = 0;

  constructor(x: number, y: number) {
    this.x = x;
    this.y = y;
  }
}

@Component
export struct MapCanvas {
  @Prop @Watch('onDataChange') navState: NavState = new NavState();
  @Prop @Watch('onDataChange') routePoints: GeoPoint[] = [];
  @Prop @Watch('onDataChange') roadSegments: RoadSegment[] = [];
  @Prop @Watch('onDataChange') isStale: boolean = false;
  @Prop @Watch('onDataChange') zoomScaleMetersPerPx: number = 1.65;
  @Prop @Watch('onDataChange') panOffsetX: number = 0;
  @Prop @Watch('onDataChange') panOffsetY: number = 0;
  @Prop @Watch('onDataChange') northUpMode: boolean = false;

  private settings: RenderingContextSettings = new RenderingContextSettings(true);
  private ctx: CanvasRenderingContext2D = new CanvasRenderingContext2D(this.settings);
  private canvasW: number = 240;
  private canvasH: number = 280;

  onDataChange(): void {
    this.drawMap();
  }

  /**
   * Chuyển đổi tọa độ (lat, lng) sang tọa độ màn hình (x, y)
   * với góc xoay Heading-Up (hướng xe di chuyển luôn hướng lên đỉnh đồng hồ).
   */
  private projectToScreen(lat: number, lng: number): ScreenPt {
    const centerLat = this.navState.lat;
    const centerLng = this.navState.lng;
    const cosLat = Math.cos(centerLat * Math.PI / 180.0);

    // Đổi chênh lệch độ sang mét
    const northMeters = (lat - centerLat) * 111320.0;
    const eastMeters = (lng - centerLng) * 111320.0 * cosLat;

    // Xoay theo góc heading (Heading-Up) hoặc giữ cố định hướng Bắc (North-Up)
    const activeAngle = this.northUpMode ? 0.0 : this.navState.heading;
    const rad = (activeAngle * Math.PI) / 180.0;
    const cosH = Math.cos(rad);
    const sinH = Math.sin(rad);

    const rotX = eastMeters * cosH - northMeters * sinH;
    const rotY = eastMeters * sinH + northMeters * cosH;

    const anchorX = this.canvasW * 0.5 + this.panOffsetX;
    const anchorY = this.canvasH * 0.67 + this.panOffsetY;

    const px = anchorX + rotX / this.zoomScaleMetersPerPx;
    const py = anchorY - rotY / this.zoomScaleMetersPerPx;
    return new ScreenPt(px, py);
  }

  private drawMap(): void {
    const c = this.ctx;
    if (!c || this.canvasW <= 0 || this.canvasH <= 0) {
      return;
    }

    const w = this.canvasW;
    const h = this.canvasH;
    const anchorX = w * 0.5 + this.panOffsetX;
    const anchorY = h * 0.67 + this.panOffsetY;

    // 1. Nền tối AMOLED tiết kiệm pin và chống chói ngoài trời
    c.clearRect(0, 0, w, h);
    c.fillStyle = '#0A0E14';
    c.fillRect(0, 0, w, h);

    // 2. Vòng cung khoảng cách 100m xung quanh xe
    const ringRadiusPx = 100.0 / this.zoomScaleMetersPerPx;
    c.save();
    c.strokeStyle = '#142030';
    c.lineWidth = 1;
    c.beginPath();
    c.arc(anchorX, anchorY, ringRadiusPx, 0, Math.PI * 2);
    c.stroke();
    c.restore();

    // 3. Vẽ mạng lưới đường nền xung quanh
    for (let i = 0; i < this.roadSegments.length; i++) {
      const seg = this.roadSegments[i];
      if (seg.points.length < 2) {
        continue;
      }

      c.save();
      c.lineCap = 'round';
      c.lineJoin = 'round';

      if (seg.roadClass === 1) {
        c.strokeStyle = '#263447';
        c.lineWidth = 7;
      } else if (seg.roadClass === 2) {
        c.strokeStyle = '#1C2736';
        c.lineWidth = 5;
      } else {
        c.strokeStyle = '#151E2B';
        c.lineWidth = 3;
      }

      c.beginPath();
      const firstPt = this.projectToScreen(seg.points[0].lat, seg.points[0].lng);
      c.moveTo(firstPt.x, firstPt.y);

      for (let j = 1; j < seg.points.length; j++) {
        const pt = this.projectToScreen(seg.points[j].lat, seg.points[j].lng);
        c.lineTo(pt.x, pt.y);
      }
      c.stroke();

      // Vẽ tên đường cho đường trục chính/phụ
      if (seg.name.length > 0 && seg.roadClass <= 2 && seg.points.length >= 2) {
        const midIdx = Math.floor(seg.points.length / 2);
        const midPt = this.projectToScreen(seg.points[midIdx].lat, seg.points[midIdx].lng);
        if (midPt.x > 24 && midPt.x < w - 24 && midPt.y > 76 && midPt.y < h - 48) {
          c.fillStyle = '#5C738F';
          c.font = '10vp sans-serif';
          c.textAlign = 'center';
          c.fillText(seg.name, midPt.x, midPt.y - 4);
        }
      }
      c.restore();
    }

    // 4. Vẽ tuyến đường dẫn đường chính (Route Polyline)
    if (this.routePoints.length >= 2) {
      c.save();
      c.lineCap = 'round';
      c.lineJoin = 'round';

      // Lớp viền ngoài (casing) giúp nổi bật trên đường nền
      c.strokeStyle = '#062B1F';
      c.lineWidth = 11;
      c.beginPath();
      const r0 = this.projectToScreen(this.routePoints[0].lat, this.routePoints[0].lng);
      c.moveTo(r0.x, r0.y);
      for (let k = 1; k < this.routePoints.length; k++) {
        const rk = this.projectToScreen(this.routePoints[k].lat, this.routePoints[k].lng);
        c.lineTo(rk.x, rk.y);
      }
      c.stroke();

      // Lớp lõi tuyến đường (Màu xanh ngọc khi bình thường, màu cam khi lệch tuyến, xám khi mất tín hiệu)
      if (this.isStale) {
        c.strokeStyle = '#4B5B6E';
      } else if (this.navState.isRerouting) {
        c.strokeStyle = '#FFA726';
      } else {
        c.strokeStyle = '#00E676';
      }
      c.lineWidth = 6.5;
      c.stroke();

      // Đánh dấu các nút giao rẽ trên bản đồ
      for (let m = 1; m < this.routePoints.length - 1; m++) {
        const nodePt = this.projectToScreen(this.routePoints[m].lat, this.routePoints[m].lng);
        if (nodePt.y < anchorY + 10 && nodePt.y > 60) {
          c.fillStyle = '#FFFFFF';
          c.beginPath();
          c.arc(nodePt.x, nodePt.y, 3.2, 0, Math.PI * 2);
          c.fill();
        }
      }
      c.restore();
    }

    // 5. Vẽ nón tầm nhìn và biểu tượng vị trí xe máy hiện tại
    c.save();
    // Vòng hào quang bán trong suốt quanh vị trí xe
    c.fillStyle = this.isStale ? 'rgba(120, 144, 156, 0.22)' : 'rgba(0, 229, 255, 0.20)';
    c.beginPath();
    c.arc(anchorX, anchorY, 18, 0, Math.PI * 2);
    c.fill();

    // Mũi tên vị trí xe (Chevron hướng lên trên)
    c.fillStyle = this.isStale ? '#90A4AE' : '#00E5FF';
    c.strokeStyle = '#FFFFFF';
    c.lineWidth = 2;
    c.beginPath();
    c.moveTo(anchorX, anchorY - 11);
    c.lineTo(anchorX + 9, anchorY + 9);
    c.lineTo(anchorX, anchorY + 4);
    c.lineTo(anchorX - 9, anchorY + 9);
    c.closePath();
    c.fill();
    c.stroke();
    c.restore();
  }

  build() {
    Canvas(this.ctx)
      .width('100%')
      .height('100%')
      .backgroundColor('#0A0E14')
      .onReady(() => {
        this.canvasW = this.ctx.width;
        this.canvasH = this.ctx.height;
        this.drawMap();
      })
  }
}
