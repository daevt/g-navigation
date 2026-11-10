import { ManeuverType, NavState } from '../models/NavModels';

@Component
export struct TurnBanner {
  @Prop @Watch('onBannerChange') navState: NavState = new NavState();
  @Prop @Watch('onBannerChange') isStale: boolean = false;

  private iconSettings: RenderingContextSettings = new RenderingContextSettings(true);
  private iconCtx: CanvasRenderingContext2D = new CanvasRenderingContext2D(this.iconSettings);

  onBannerChange(): void {
    this.drawManeuverArrow();
  }

  /**
   * Vẽ mũi tên chỉ hướng bằng Vector Canvas sắc nét trên mọi font hệ thống HarmonyOS
   */
  private drawManeuverArrow(): void {
    const c = this.iconCtx;
    if (!c) {
      return;
    }
    const w = 38;
    const h = 38;
    c.clearRect(0, 0, w, h);

    c.save();
    c.strokeStyle = '#05101A';
    c.fillStyle = '#05101A';
    c.lineWidth = 3.5;
    c.lineCap = 'round';
    c.lineJoin = 'round';

    const m = this.navState.maneuverType;
    if (this.navState.isRerouting || m === 'UTURN') {
      // Mũi tên quay đầu U-Turn
      c.beginPath();
      c.moveTo(24, 30);
      c.lineTo(24, 15);
      c.arc(17, 15, 7, 0, Math.PI, true);
      c.lineTo(10, 26);
      c.stroke();

      c.beginPath();
      c.moveTo(5, 22);
      c.lineTo(10, 28);
      c.lineTo(15, 22);
      c.stroke();
    } else if (m === 'TURN_LEFT' || m === 'SHARP_LEFT') {
      // Mũi tên rẽ trái
      c.beginPath();
      c.moveTo(24, 30);
      c.lineTo(24, 15);
      c.lineTo(10, 15);
      c.stroke();

      c.beginPath();
      c.moveTo(16, 9);
      c.lineTo(9, 15);
      c.lineTo(16, 21);
      c.stroke();
    } else if (m === 'SLIGHT_LEFT') {
      // Chếch trái
      c.beginPath();
      c.moveTo(23, 30);
      c.lineTo(23, 20);
      c.lineTo(12, 10);
      c.stroke();

      c.beginPath();
      c.moveTo(19, 9);
      c.lineTo(11, 9);
      c.lineTo(11, 17);
      c.stroke();
    } else if (m === 'SLIGHT_RIGHT') {
      // Chếch phải
      c.beginPath();
      c.moveTo(15, 30);
      c.lineTo(15, 20);
      c.lineTo(26, 10);
      c.stroke();

      c.beginPath();
      c.moveTo(19, 9);
      c.lineTo(27, 9);
      c.lineTo(27, 17);
      c.stroke();
    } else if (m === 'TURN_RIGHT' || m === 'SHARP_RIGHT') {
      // Mũi tên rẽ phải
      c.beginPath();
      c.moveTo(14, 30);
      c.lineTo(14, 15);
      c.lineTo(28, 15);
      c.stroke();

      c.beginPath();
      c.moveTo(22, 9);
      c.lineTo(29, 15);
      c.lineTo(22, 21);
      c.stroke();
    } else {
      // Đi thẳng / Mặc định
      c.beginPath();
      c.moveTo(19, 30);
      c.lineTo(19, 9);
      c.stroke();

      c.beginPath();
      c.moveTo(12, 16);
      c.lineTo(19, 8);
      c.lineTo(26, 16);
      c.stroke();
    }

    c.restore();
  }

  private formatDistance(meters: number): string {
    if (meters >= 1000) {
      return `${(meters / 1000.0).toFixed(1)} km`;
    }
    return `${Math.max(0, Math.round(meters))} m`;
  }

  private getBannerBgColor(): string {
    if (this.isStale) {
      return '#CC263238';
    }
    if (this.navState.isRerouting) {
      return '#DD4E2A04';
    }
    if (this.navState.maneuverDistMeters <= 40) {
      return '#E6004D40';
    }
    return '#D9101B28';
  }

  private getIconBadgeColor(): string {
    if (this.isStale) {
      return '#546E7A';
    }
    if (this.navState.isRerouting) {
      return '#FF9800';
    }
    if (this.navState.maneuverDistMeters <= 40) {
      return '#00E676';
    }
    return '#00B0FF';
  }

  build() {
    if (this.isStale) {
      Row() {
        Column() {
          Text('⚠ Mất dữ liệu từ iPhone')
            .fontSize(12)
            .fontWeight(FontWeight.Bold)
            .fontColor('#FFCC80')
          Text('Đã ẩn chỉ dẫn cũ · Chờ nối lại')
            .fontSize(9)
            .fontColor('#B0BEC5')
            .margin({ top: 2 })
            .maxLines(1)
            .textOverflow({ overflow: TextOverflow.Ellipsis })
        }
        .alignItems(HorizontalAlign.Center)
        .width('100%')
      }
      .width('78%')
      .padding({ left: 10, right: 10, top: 7, bottom: 7 })
      .backgroundColor(this.getBannerBgColor())
      .borderRadius(20)
      .border({ width: 1, color: '#546E7A' })
    } else {
      Row() {
        // Hộp vẽ mũi tên Vector
        Stack() {
          Canvas(this.iconCtx)
            .width(38)
            .height(38)
            .onReady(() => {
              this.drawManeuverArrow();
            })
        }
        .width(38)
        .height(38)
        .backgroundColor(this.getIconBadgeColor())
        .borderRadius(12)

        // Khoảng cách tới khúc rẽ & Tên đường tiếp theo
        Column() {
          Row() {
            Text(this.navState.isRerouting ? 'Lệch tuyến' : this.formatDistance(this.navState.maneuverDistMeters))
              .fontSize(18)
              .fontWeight(FontWeight.Bold)
              .fontColor('#FFFFFF')

            if (this.navState.maneuverDistMeters <= 40 && !this.navState.isRerouting) {
              Text('RẼ NGAY')
                .fontSize(8)
                .fontWeight(FontWeight.Bold)
                .fontColor('#00E676')
                .padding({ left: 5, right: 5, top: 2, bottom: 2 })
                .backgroundColor('#1A00E676')
                .borderRadius(6)
                .margin({ left: 5 })
            }
          }
          .alignItems(VerticalAlign.Center)

          Text(this.navState.isRerouting ? 'Đang tính lại đường...' : this.navState.nextRoadName)
            .fontSize(12)
            .fontWeight(FontWeight.Medium)
            .fontColor('#CFD8DC')
            .maxLines(1)
            .textOverflow({ overflow: TextOverflow.Ellipsis })
            .margin({ top: 1 })
        }
        .alignItems(HorizontalAlign.Start)
        .layoutWeight(1)
        .margin({ left: 8 })
      }
      .width('78%')
      .padding({ left: 9, right: 11, top: 7, bottom: 7 })
      .backgroundColor(this.getBannerBgColor())
      .borderRadius(20)
      .border({
        width: 1,
        color: this.navState.maneuverDistMeters <= 40 ? '#00E676' : '#26384C'
      })
    }
  }
}
