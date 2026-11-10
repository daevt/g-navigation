import { ConnectionMode, NavState } from '../models/NavModels';

@Component
export struct BottomBar {
  @Prop navState: NavState = new NavState();
  @Prop connectionMode: ConnectionMode = 'SIMULATOR_DEMO';

  private formatRemaining(meters: number): string {
    if (meters >= 1000) {
      return `${(meters / 1000.0).toFixed(1)} km`;
    }
    return `${Math.max(0, Math.round(meters))} m`;
  }

  private getStatusColor(): string {
    if (this.connectionMode === 'LIVE_P2P') {
      return '#00E676';
    }
    if (this.connectionMode === 'SIMULATOR_DEMO') {
      return '#00E5FF';
    }
    return '#FF5252';
  }

  private getStatusLabel(): string {
    if (this.connectionMode === 'LIVE_P2P') {
      return 'P2P';
    }
    if (this.connectionMode === 'SIMULATOR_DEMO') {
      return 'DEMO';
    }
    return 'MẤT KN';
  }

  build() {
    Row() {
      // Tốc độ hiện tại (km/h)
      Column() {
        Text(`${Math.round(this.navState.speedKmh)}`)
          .fontSize(15)
          .fontWeight(FontWeight.Bold)
          .fontColor('#00E5FF')
        Text('km/h')
          .fontSize(8)
          .fontColor('#78909C')
      }
      .alignItems(HorizontalAlign.Center)

      Divider()
        .vertical(true)
        .height(18)
        .color('#26384C')
        .margin({ left: 8, right: 8 })

      // Quãng đường còn lại & Giờ đến dự kiến (ETA)
      Column() {
        Text(this.formatRemaining(this.navState.remainingMeters))
          .fontSize(12)
          .fontWeight(FontWeight.Bold)
          .fontColor('#FFFFFF')
        Text(`ETA ${this.navState.etaText}`)
          .fontSize(9)
          .fontColor('#90A4AE')
      }
      .alignItems(HorizontalAlign.Center)
      .layoutWeight(1)

      Divider()
        .vertical(true)
        .height(18)
        .color('#26384C')
        .margin({ left: 8, right: 8 })

      // Trạng thái kết nối Wear Engine P2P
      Row() {
        Circle({ width: 6, height: 6 })
          .fill(this.getStatusColor())
        Text(this.getStatusLabel())
          .fontSize(9)
          .fontWeight(FontWeight.Medium)
          .fontColor(this.getStatusColor())
          .margin({ left: 4 })
      }
      .alignItems(VerticalAlign.Center)
    }
    .width('88%')
    .padding({ left: 12, right: 12, top: 6, bottom: 6 })
    .backgroundColor('#D9101B28')
    .borderRadius(20)
    .border({ width: 1, color: '#243447' })
  }
}
