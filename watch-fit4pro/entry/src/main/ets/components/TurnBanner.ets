import { ManeuverType, NavState } from '../models/NavModels';

@Component
export struct TurnBanner {
  @Prop navState: NavState = new NavState();
  @Prop isStale: boolean = false;

  private getManeuverSymbol(mType: ManeuverType): string {
    switch (mType) {
      case 'TURN_LEFT':
        return '↰';
      case 'TURN_RIGHT':
        return '↱';
      case 'SLIGHT_LEFT':
        return '↖';
      case 'SLIGHT_RIGHT':
        return '↗';
      case 'SHARP_LEFT':
        return '↙';
      case 'SHARP_RIGHT':
        return '↘';
      case 'UTURN':
        return '↶';
      case 'ROUNDABOUT':
        return '⟳';
      case 'ARRIVE':
        return '🏁';
      default:
        return '↑';
    }
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
      // Mốc 4: Tự động ẩn chỉ dẫn cũ khi mất dữ liệu từ iPhone
      Row() {
        Column() {
          Text('⚠ Mất dữ liệu từ iPhone')
            .fontSize(13)
            .fontWeight(FontWeight.Bold)
            .fontColor('#FFCC80')
          Text('Đã ẩn chỉ dẫn cũ · Tự đồng bộ khi nối lại')
            .fontSize(10)
            .fontColor('#B0BEC5')
            .margin({ top: 2 })
            .maxLines(1)
            .textOverflow({ overflow: TextOverflow.Ellipsis })
        }
        .alignItems(HorizontalAlign.Start)
        .width('100%')
      }
      .width('92%')
      .padding({ left: 12, right: 12, top: 8, bottom: 8 })
      .backgroundColor(this.getBannerBgColor())
      .borderRadius(16)
      .border({ width: 1, color: '#546E7A' })
    } else {
      Row() {
        // Khối biểu tượng mũi tên chỉ hướng rẽ
        Column() {
          Text(this.navState.isRerouting ? '↻' : this.getManeuverSymbol(this.navState.maneuverType))
            .fontSize(24)
            .fontWeight(FontWeight.Bold)
            .fontColor('#061019')
        }
        .width(42)
        .height(42)
        .justifyContent(FlexAlign.Center)
        .alignItems(HorizontalAlign.Center)
        .backgroundColor(this.getIconBadgeColor())
        .borderRadius(12)

        // Khoảng cách tới khúc rẽ & Tên đường tiếp theo
        Column() {
          Row() {
            Text(this.navState.isRerouting ? 'Lệch tuyến' : this.formatDistance(this.navState.maneuverDistMeters))
              .fontSize(20)
              .fontWeight(FontWeight.Bold)
              .fontColor('#FFFFFF')

            if (this.navState.maneuverDistMeters <= 40 && !this.navState.isRerouting) {
              Text('RẼ NGAY')
                .fontSize(9)
                .fontWeight(FontWeight.Bold)
                .fontColor('#00E676')
                .padding({ left: 6, right: 5, top: 2, bottom: 2 })
                .backgroundColor('#1A00E676')
                .borderRadius(6)
                .margin({ left: 6 })
            }
          }
          .alignItems(VerticalAlign.Center)

          Text(this.navState.isRerouting ? 'Đang tính lại đường...' : this.navState.nextRoadName)
            .fontSize(13)
            .fontWeight(FontWeight.Medium)
            .fontColor('#CFD8DC')
            .maxLines(1)
            .textOverflow({ overflow: TextOverflow.Ellipsis })
            .margin({ top: 2 })
        }
        .alignItems(HorizontalAlign.Start)
        .layoutWeight(1)
        .margin({ left: 10 })
      }
      .width('92%')
      .padding({ left: 10, right: 12, top: 8, bottom: 8 })
      .backgroundColor(this.getBannerBgColor())
      .borderRadius(18)
      .border({
        width: 1,
        color: this.navState.maneuverDistMeters <= 40 ? '#00E676' : '#26384C'
      })
    }
  }
}
