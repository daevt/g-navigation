import {
  ConnectionMode,
  DemoDataset,
  GeoPoint,
  NavState,
  RoadSegment
} from '../models/NavModels';
import { WearEngineService } from '../services/WearEngineService';
import { MapCanvas } from '../components/MapCanvas';
import { TurnBanner } from '../components/TurnBanner';
import { BottomBar } from '../components/BottomBar';

@Entry
@Component
struct Index {
  @State navState: NavState = new NavState();
  @State routePoints: GeoPoint[] = DemoDataset.getSampleRoute();
  @State roadSegments: RoadSegment[] = DemoDataset.getSampleRoads();
  @State connectionMode: ConnectionMode = 'SIMULATOR_DEMO';
  @State zoomScaleMetersPerPx: number = 1.65;
  @State showTestDrawer: boolean = false;
  @State isAutoWalking: boolean = false;

  private wearService: WearEngineService = new WearEngineService();

  aboutToAppear(): void {
    this.wearService.setUpdateListener(
      (state: NavState, route: GeoPoint[], roads: RoadSegment[], mode: ConnectionMode) => {
        this.navState = state;
        this.routePoints = route;
        this.roadSegments = roads;
        this.connectionMode = mode;
      }
    );
    this.wearService.start();
  }

  aboutToDisappear(): void {
    this.wearService.stop();
  }

  private adjustZoom(delta: number): void {
    const next = this.zoomScaleMetersPerPx + delta;
    if (next >= 0.8 && next <= 3.5) {
      this.zoomScaleMetersPerPx = next;
    }
  }

  build() {
    Stack() {
      // 1. Lớp bản đồ nền tự vẽ bằng Canvas (Mốc 1 & Mốc 3)
      MapCanvas({
        navState: this.navState,
        routePoints: this.routePoints,
        roadSegments: this.roadSegments,
        isStale: this.connectionMode === 'STALE_DISCONNECTED',
        zoomScaleMetersPerPx: this.zoomScaleMetersPerPx
      })

      // 2. Lớp giao diện nổi (Thẻ chỉ dẫn rẽ ở trên + Nút thu phóng + Thanh trạng thái ở dưới)
      Column() {
        // Thẻ chỉ dẫn rẽ phía trên
        TurnBanner({
          navState: this.navState,
          isStale: this.connectionMode === 'STALE_DISCONNECTED'
        })
          .margin({ top: 20 })

        // Khoảng trống ở giữa dành cho bản đồ + Nút Zoom nhỏ bên phải
        Row() {
          Blank()
          Column() {
            Button('+')
              .width(26)
              .height(26)
              .fontSize(14)
              .fontColor('#E0F7FA')
              .backgroundColor('#AA101B28')
              .borderRadius(13)
              .onClick(() => {
                this.adjustZoom(-0.35);
              })

            Button('-')
              .width(26)
              .height(26)
              .fontSize(14)
              .fontColor('#E0F7FA')
              .backgroundColor('#AA101B28')
              .borderRadius(13)
              .margin({ top: 6 })
              .onClick(() => {
                this.adjustZoom(0.35);
              })
          }
          .margin({ right: 8 })
        }
        .width('100%')
        .layoutWeight(1)
        .alignItems(VerticalAlign.Center)

        // Thanh trạng thái phía dưới (chạm vào để mở bảng công cụ kiểm thử Mốc 1/Mốc 4)
        Row() {
          BottomBar({
            navState: this.navState,
            connectionMode: this.connectionMode
          })
        }
        .margin({ bottom: 16 })
        .onClick(() => {
          this.showTestDrawer = !this.showTestDrawer;
        })
      }
      .width('100%')
      .height('100%')
      .justifyContent(FlexAlign.SpaceBetween)
      .alignItems(HorizontalAlign.Center)

      // 3. Bảng điều khiển kiểm thử nhanh (dành cho DevEco Simulator ở Mốc 1 & kiểm thử Mốc 4)
      if (this.showTestDrawer) {
        Column() {
          Text('Kiểm thử Simulator & P2P')
            .fontSize(12)
            .fontWeight(FontWeight.Bold)
            .fontColor('#00E5FF')
            .margin({ bottom: 6 })

          Row() {
            Button(this.isAutoWalking ? 'Dừng chạy' : 'Chạy thử')
              .fontSize(10)
              .height(26)
              .backgroundColor(this.isAutoWalking ? '#E53935' : '#00897B')
              .onClick(() => {
                if (this.isAutoWalking) {
                  this.wearService.stopSimulatorWalk();
                  this.isAutoWalking = false;
                } else {
                  this.wearService.startSimulatorWalk();
                  this.isAutoWalking = true;
                }
              })

            Button('Bước kế')
              .fontSize(10)
              .height(26)
              .backgroundColor('#1E88E5')
              .margin({ left: 6 })
              .onClick(() => {
                this.wearService.stepSimulation();
              })
          }

          Row() {
            Button('Lệch tuyến')
              .fontSize(10)
              .height(26)
              .backgroundColor('#FB8C00')
              .onClick(() => {
                this.isAutoWalking = false;
                this.wearService.simulateRerouteAlert();
              })

            Button('Mất KN (Mốc 4)')
              .fontSize(10)
              .height(26)
              .backgroundColor('#546E7A')
              .margin({ left: 6 })
              .onClick(() => {
                this.isAutoWalking = false;
                this.wearService.simulateDisconnectStale();
              })
          }
          .margin({ top: 6 })

          Button('Đóng')
            .fontSize(10)
            .height(24)
            .width(80)
            .backgroundColor('#263238')
            .margin({ top: 8 })
            .onClick(() => {
              this.showTestDrawer = false;
            })
        }
        .width('88%')
        .padding(10)
        .backgroundColor('#F20D1520')
        .borderRadius(16)
        .border({ width: 1, color: '#00E5FF' })
      }
    }
    .width('100%')
    .height('100%')
    .backgroundColor('#0A0E14')
  }
}
