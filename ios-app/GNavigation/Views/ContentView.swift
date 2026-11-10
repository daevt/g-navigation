import SwiftUI
import MapKit
import UIKit

struct ContentView: View {
    @StateObject private var navEngine = NavigationEngine()
    @ObservedObject private var wearManager = WearEngineManager.shared

    @State private var searchQuery: String = ""
    @State private var searchResults: [SearchPlaceDTO] = []
    @State private var isSearching: Bool = false

    @State private var workerURLInput: String = AppConfig.workerBaseURL
    @State private var workerTokenInput: String = AppConfig.workerClientToken
    @State private var watchBundleInput: String = AppConfig.watchPeerBundleName
    @State private var watchFingerprintInput: String = AppConfig.watchPeerFingerprint

    var body: some View {
        TabView {
            navigationTab
                .tabItem {
                    Label("Dẫn đường", systemImage: "location.north.line.fill")
                }

            milestone2TestTab
                .tabItem {
                    Label("Kiểm thử Mốc 2", systemImage: "applewatch.radiowaves.left.and.right")
                }

            configAndLogsTab
                .tabItem {
                    Label("Cấu hình & Log", systemImage: "gearshape.2.fill")
                }
        }
        .preferredColorScheme(.dark)
        .onOpenURL { url in
            wearManager.handleOpenURL(url)
        }
    }

    // MARK: - Tab 1: Bản đồ & Dẫn đường xe máy (Mốc 3 & Mốc 4)

    private var navigationTab: some View {
        NavigationStack {
            VStack(spacing: 12) {
                // Thanh trạng thái kết nối đồng hồ & Vị trí hiện tại
                VStack(alignment: .leading, spacing: 6) {
                    HStack {
                        Circle()
                            .fill(wearManager.state == .connectedP2P ? Color.green : Color.orange)
                            .frame(width: 10, height: 10)
                        Text(wearManager.state.rawValue)
                            .font(.caption.bold())
                        Spacer()
                        Text("Đã gửi: \(wearManager.sentPacketsCount) gói")
                            .font(.caption2)
                            .foregroundStyle(.secondary)
                    }

                    HStack {
                        Image(systemName: "location.fill")
                            .foregroundStyle(.cyan)
                            .font(.caption)
                        Text(
                            navEngine.hasRealGPSFix
                                ? String(format: "Vị trí hiện tại: %.5f, %.5f (±%dm)", navEngine.currentLocation.latitude, navEngine.currentLocation.longitude, navEngine.gpsAccuracyMeters)
                                : "Đang lấy vị trí GPS hiện tại..."
                        )
                        .font(.caption2)
                        .foregroundStyle(.cyan)
                        Spacer()
                        Button {
                            navEngine.requestLocationPermissions()
                        } label: {
                            Label("Vị trí hiện tại", systemImage: "scope")
                                .font(.caption2.bold())
                        }
                        .buttonStyle(.bordered)
                        .controlSize(.mini)
                    }
                }
                .padding(.horizontal, 14)
                .padding(.vertical, 8)
                .background(Color(.secondarySystemBackground))
                .clipShape(RoundedRectangle(cornerRadius: 10))

                // Ô tìm kiếm điểm đến (VIETMAP / OSM)
                HStack {
                    Image(systemName: "magnifyingglass")
                        .foregroundStyle(.secondary)
                    TextField("Tìm điểm đến (VD: Chợ Bến Thành, Dinh Độc Lập)...", text: $searchQuery)
                        .textFieldStyle(.plain)
                        .submitLabel(.search)
                        .onSubmit {
                            Task { await performSearch() }
                        }
                    if isSearching {
                        ProgressView()
                            .scaleEffect(0.8)
                    } else if !searchQuery.isEmpty {
                        Button("Tìm") {
                            Task { await performSearch() }
                        }
                        .font(.subheadline.bold())
                    }
                }
                .padding(10)
                .background(Color(.secondarySystemBackground))
                .clipShape(RoundedRectangle(cornerRadius: 12))

                // Danh sách kết quả tìm kiếm
                if !searchResults.isEmpty {
                    List(searchResults) { place in
                        Button {
                            searchResults = []
                            searchQuery = place.name
                            Task {
                                await navEngine.startNavigation(
                                    to: CLLocationCoordinate2D(latitude: place.lat, longitude: place.lng)
                                )
                            }
                        } label: {
                            VStack(alignment: .leading, spacing: 2) {
                                Text(place.name)
                                    .font(.subheadline.bold())
                                Text(place.address)
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                                    .lineLimit(1)
                            }
                        }
                    }
                    .listStyle(.plain)
                    .frame(maxHeight: 180)
                }

                // Thẻ trạng thái dẫn đường hiện tại
                if navEngine.isNavigating, let route = navEngine.activeRoute {
                    VStack(alignment: .leading, spacing: 10) {
                        HStack {
                            VStack(alignment: .leading, spacing: 4) {
                                Text(navEngine.isRerouting ? "Đang tính lại tuyến..." : "Cách khúc rẽ: \(navEngine.distanceToNextTurnMeters) m")
                                    .font(.title3.bold())
                                    .foregroundStyle(navEngine.isRerouting ? .orange : .green)

                                let stepName = route.steps.isEmpty ? "Đi theo tuyến" : route.steps[min(navEngine.currentStepIndex, route.steps.count - 1)].roadName
                                Text("Đường kế: \(stepName)")
                                    .font(.subheadline)
                            }
                            Spacer()
                            VStack(alignment: .trailing) {
                                Text("\(navEngine.currentSpeedKmh) km/h")
                                    .font(.headline)
                                    .foregroundStyle(.cyan)
                                Text("ETA \(navEngine.etaString)")
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                            }
                        }

                        HStack(spacing: 10) {
                            Button {
                                navEngine.resyncAllToWatch()
                            } label: {
                                Label("Đồng bộ lại đồng hồ", systemImage: "arrow.triangle.2.circlepath")
                                    .font(.caption.bold())
                                    .frame(maxWidth: .infinity)
                            }
                            .buttonStyle(.borderedProminent)
                            .tint(.blue)

                            Button(role: .destructive) {
                                navEngine.stopNavigation()
                            } label: {
                                Label("Dừng", systemImage: "xmark.circle.fill")
                                    .font(.caption.bold())
                            }
                            .buttonStyle(.bordered)
                        }
                    }
                    .padding(14)
                    .background(Color(.secondarySystemBackground))
                    .clipShape(RoundedRectangle(cornerRadius: 14))
                }

                // Các điểm đến mẫu nhanh để chạy thử ngay ngoài đường
                ScrollView(.horizontal, showsIndicators: false) {
                    HStack(spacing: 8) {
                        Button("🧭 ĐH Bách Khoa HN") {
                            Task {
                                await navEngine.startNavigation(
                                    to: CLLocationCoordinate2D(latitude: 21.0045, longitude: 105.8431)
                                )
                            }
                        }
                        .buttonStyle(.bordered)
                        .font(.caption)

                        Button("🧭 Hồ Gươm") {
                            Task {
                                await navEngine.startNavigation(
                                    to: CLLocationCoordinate2D(latitude: 21.0285, longitude: 105.8542)
                                )
                            }
                        }
                        .buttonStyle(.bordered)
                        .font(.caption)

                        Button("🧭 Times City") {
                            Task {
                                await navEngine.startNavigation(
                                    to: CLLocationCoordinate2D(latitude: 20.9958, longitude: 105.8675)
                                )
                            }
                        }
                        .buttonStyle(.bordered)
                        .font(.caption)

                        Button("🧭 Lăng Bác") {
                            Task {
                                await navEngine.startNavigation(
                                    to: CLLocationCoordinate2D(latitude: 21.0368, longitude: 105.8347)
                                )
                            }
                        }
                        .buttonStyle(.bordered)
                        .font(.caption)
                    }
                }

                // BẢN ĐỒ TƯƠNG TÁC TRỰC TIẾP TRÊN IPHONE (Hiển thị vị trí GPS thật + Tuyến đường xanh + Chạm chọn đích)
                ZStack(alignment: .bottomTrailing) {
                    InteractiveNavigationMapView(
                        userCoordinate: navEngine.currentLocation,
                        destinationCoordinate: navEngine.destinationCoord,
                        routePoints: navEngine.activeRoute?.points ?? [],
                        recenterTrigger: navEngine.recenterTrigger,
                        onSelectDestination: { coord in
                            Task {
                                await navEngine.startNavigation(to: coord)
                            }
                        }
                    )
                    .clipShape(RoundedRectangle(cornerRadius: 16))
                    .overlay(
                        RoundedRectangle(cornerRadius: 16)
                            .stroke(Color.white.opacity(0.15), lineWidth: 1)
                    )

                    VStack(spacing: 8) {
                        Button {
                            navEngine.requestLocationPermissions()
                        } label: {
                            Image(systemName: "location.fill")
                                .font(.system(size: 16, weight: .bold))
                                .foregroundStyle(.cyan)
                                .frame(width: 38, height: 38)
                                .background(.ultraThinMaterial)
                                .clipShape(Circle())
                                .shadow(radius: 4)
                        }
                    }
                    .padding(12)
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
            }
            .padding()
            .navigationTitle("G Navigation")
            .navigationBarTitleDisplayMode(.inline)
        }
    }

    // MARK: - Tab 2: Kiểm thử Mốc 2 (Bundle ID Sideloadly + P2P + Khóa màn hình)

    private var milestone2TestTab: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 14) {
                    // Hộp kiểm tra Bundle ID thực tế sau khi ký bằng Sideloadly
                    VStack(alignment: .leading, spacing: 6) {
                        Text("1. Kiểm tra định danh sau khi cài qua Sideloadly")
                            .font(.subheadline.bold())
                            .foregroundStyle(.cyan)

                        Text("Sideloadly miễn phí thường gắn thêm hậu tố vào Bundle ID. Hãy sao chép đúng chuỗi bên dưới để khớp với cấu hình Huawei Wear Engine và `WearEngineConfig.IOS_PEER_BUNDLE_ID`:")
                            .font(.caption)
                            .foregroundStyle(.secondary)

                        HStack {
                            VStack(alignment: .leading, spacing: 2) {
                                Text("Bundle ID thực tế:")
                                    .font(.caption2)
                                    .foregroundStyle(.secondary)
                                Text(AppConfig.runtimeBundleIdentifier)
                                    .font(.system(.footnote, design: .monospaced).bold())
                            }
                            Spacer()
                            Button("Sao chép") {
                                UIPasteboard.general.string = AppConfig.runtimeBundleIdentifier
                                wearManager.appendLog("Đã chép Bundle ID: \(AppConfig.runtimeBundleIdentifier)")
                            }
                            .buttonStyle(.bordered)
                            .font(.caption)
                        }
                        .padding(8)
                        .background(Color.black.opacity(0.35))
                        .clipShape(RoundedRectangle(cornerRadius: 8))

                        Text("Callback URL Scheme: \(AppConfig.callbackURLScheme)")
                            .font(.system(.caption, design: .monospaced))
                            .foregroundStyle(.green)
                    }
                    .padding(14)
                    .background(Color(.secondarySystemBackground))
                    .clipShape(RoundedRectangle(cornerRadius: 14))

                    // Hộp cấp quyền & Ping đồng hồ
                    VStack(alignment: .leading, spacing: 10) {
                        Text("2. Cấp quyền Wear Engine & Ping Fit 4 Pro")
                            .font(.subheadline.bold())
                            .foregroundStyle(.cyan)

                        HStack(spacing: 10) {
                            Button {
                                wearManager.requestWearEnginePermissions()
                            } label: {
                                Label("Xin quyền Huawei", systemImage: "checkmark.shield.fill")
                                    .font(.caption.bold())
                                    .frame(maxWidth: .infinity)
                            }
                            .buttonStyle(.borderedProminent)
                            .tint(.orange)

                            Button {
                                wearManager.discoverAndConnectWatch()
                            } label: {
                                Label("Ping Fit 4 Pro", systemImage: "wave.3.right")
                                    .font(.caption.bold())
                                    .frame(maxWidth: .infinity)
                            }
                            .buttonStyle(.borderedProminent)
                            .tint(.blue)
                        }

                        Text("Trạng thái cuối: \(wearManager.lastAckStatus)")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                    .padding(14)
                    .background(Color(.secondarySystemBackground))
                    .clipShape(RoundedRectangle(cornerRadius: 14))

                    // Hộp gửi chỉ dẫn mẫu & kiểm thử khóa màn hình
                    VStack(alignment: .leading, spacing: 10) {
                        Text("3. Gửi chỉ dẫn mẫu & Kiểm thử khóa màn hình (Mốc 2)")
                            .font(.subheadline.bold())
                            .foregroundStyle(.cyan)

                        Button {
                            navEngine.sendMilestone2SamplePayload()
                        } label: {
                            Label("Gửi chỉ dẫn mẫu + Cụm đường giả ngay", systemImage: "paperplane.fill")
                                .font(.subheadline.bold())
                                .frame(maxWidth: .infinity)
                                .padding(.vertical, 4)
                        }
                        .buttonStyle(.borderedProminent)
                        .tint(.green)

                        Button {
                            navEngine.toggleLockScreenSimulation()
                        } label: {
                            Label(
                                navEngine.isSimulatingLockScreen
                                    ? "Đang phát nền (2s/lần) — Bấm để dừng"
                                    : "Bật phát liên tục rồi khóa màn hình iPhone",
                                systemImage: navEngine.isSimulatingLockScreen ? "lock.open.rotation" : "lock.iphone"
                            )
                            .font(.subheadline.bold())
                            .frame(maxWidth: .infinity)
                            .padding(.vertical, 4)
                        }
                        .buttonStyle(.borderedProminent)
                        .tint(navEngine.isSimulatingLockScreen ? .red : .purple)

                        Text("Hướng dẫn Mốc 2 & Mốc 4: Bấm nút tím ở trên, sau đó bấm nút nguồn khóa màn hình iPhone trong 15 phút và quan sát đồng hồ Fit 4 Pro vẫn cập nhật khoảng cách & rung báo rẽ.")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                    .padding(14)
                    .background(Color(.secondarySystemBackground))
                    .clipShape(RoundedRectangle(cornerRadius: 14))
                }
                .padding()
            }
            .navigationTitle("Kiểm thử Mốc 2")
            .navigationBarTitleDisplayMode(.inline)
        }
    }

    // MARK: - Tab 3: Cấu hình & Nhật ký P2P

    private var configAndLogsTab: some View {
        NavigationStack {
            Form {
                Section("Cloudflare Worker (Mốc 3 - VIETMAP Proxy)") {
                    TextField("URL Worker (https://...workers.dev)", text: $workerURLInput)
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled()
                    SecureField("X-Client-Token (tùy chọn)", text: $workerTokenInput)
                }

                Section("Định danh đồng hồ Fit 4 Pro") {
                    TextField("Watch Bundle Name", text: $watchBundleInput)
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled()
                    TextField("Watch Fingerprint / App ID", text: $watchFingerprintInput)
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled()

                    Button("Lưu cấu hình") {
                        AppConfig.workerBaseURL = workerURLInput
                        AppConfig.workerClientToken = workerTokenInput
                        AppConfig.watchPeerBundleName = watchBundleInput
                        AppConfig.watchPeerFingerprint = watchFingerprintInput
                        wearManager.appendLog("Đã lưu cấu hình mới.")
                    }
                    .font(.subheadline.bold())
                }

                Section("Nhật ký truyền dữ liệu P2P (\(wearManager.logs.count))") {
                    ForEach(wearManager.logs, id: \.self) { line in
                        Text(line)
                            .font(.system(size: 11, design: .monospaced))
                    }
                }
            }
            .navigationTitle("Cấu hình & Nhật ký")
            .navigationBarTitleDisplayMode(.inline)
        }
    }

    private func performSearch() async {
        isSearching = true
        defer { isSearching = false }
        do {
            searchResults = try await BackendClient.shared.searchPlaces(
                query: searchQuery,
                near: navEngine.currentLocation
            )
        } catch {
            wearManager.appendLog("Lỗi tìm kiếm: \(error.localizedDescription)")
        }
    }
}

// MARK: - Bản đồ MapKit tương tác trên iPhone (Vẽ tuyến đường xanh + Vị trí GPS thật + Chạm lên bản đồ để dẫn đường)

struct InteractiveNavigationMapView: UIViewRepresentable {
    let userCoordinate: CLLocationCoordinate2D
    let destinationCoordinate: CLLocationCoordinate2D?
    let routePoints: [[Double]]
    let recenterTrigger: Int
    let onSelectDestination: (CLLocationCoordinate2D) -> Void

    func makeCoordinator() -> Coordinator {
        Coordinator(onSelectDestination: onSelectDestination)
    }

    func makeUIView(context: Context) -> MKMapView {
        let mapView = MKMapView(frame: .zero)
        mapView.delegate = context.coordinator
        mapView.showsUserLocation = true
        mapView.showsCompass = true
        mapView.showsScale = true
        mapView.pointOfInterestFilter = .includingAll

        let region = MKCoordinateRegion(
            center: userCoordinate,
            latitudinalMeters: 900,
            longitudinalMeters: 900
        )
        mapView.setRegion(region, animated: false)

        // Cho phép chạm hoặc nhấn giữ lên bản đồ iPhone để chọn điểm đến chỉ đường
        let tapGesture = UITapGestureRecognizer(target: context.coordinator, action: #selector(Coordinator.handleMapTap(_:)))
        tapGesture.numberOfTapsRequired = 1
        mapView.addGestureRecognizer(tapGesture)

        context.coordinator.mapView = mapView
        return mapView
    }

    func updateUIView(_ mapView: MKMapView, context: Context) {
        // 1. Khi người dùng bấm nút Vị trí hiện tại hoặc mới lấy được GPS lần đầu -> Đưa tâm bản đồ về vị trí thật
        if context.coordinator.lastRecenterTrigger != recenterTrigger {
            context.coordinator.lastRecenterTrigger = recenterTrigger
            let region = MKCoordinateRegion(
                center: userCoordinate,
                latitudinalMeters: 800,
                longitudinalMeters: 800
            )
            mapView.setRegion(region, animated: true)
        } else if !context.coordinator.hasCenteredOnce && (userCoordinate.latitude != 21.028511 || userCoordinate.longitude != 105.854444) {
            context.coordinator.hasCenteredOnce = true
            let region = MKCoordinateRegion(
                center: userCoordinate,
                latitudinalMeters: 800,
                longitudinalMeters: 800
            )
            mapView.setRegion(region, animated: true)
        }

        // 2. Cập nhật ghim Điểm đến
        let existingPins = mapView.annotations.filter { !($0 is MKUserLocation) }
        mapView.removeAnnotations(existingPins)
        if let dest = destinationCoordinate {
            let pin = MKPointAnnotation()
            pin.coordinate = dest
            pin.title = "Điểm đến"
            mapView.addAnnotation(pin)
        }

        // 3. Cập nhật đường vẽ lộ trình VIETMAP (MKPolyline màu xanh lá sáng)
        let routeSignature = "\(routePoints.count)_\(routePoints.first?.first ?? 0)_\(routePoints.last?.last ?? 0)"
        if context.coordinator.lastRouteSignature != routeSignature {
            context.coordinator.lastRouteSignature = routeSignature
            mapView.removeOverlays(mapView.overlays)

            let coords: [CLLocationCoordinate2D] = routePoints.compactMap { pt in
                guard pt.count >= 2 else { return nil }
                return CLLocationCoordinate2D(latitude: pt[0], longitude: pt[1])
            }
            if coords.count >= 2 {
                let polyline = MKPolyline(coordinates: coords, count: coords.count)
                mapView.addOverlay(polyline)
                mapView.setVisibleMapRect(
                    polyline.boundingMapRect,
                    edgePadding: UIEdgeInsets(top: 44, left: 36, bottom: 44, right: 36),
                    animated: true
                )
            }
        }
    }

    final class Coordinator: NSObject, MKMapViewDelegate {
        weak var mapView: MKMapView?
        let onSelectDestination: (CLLocationCoordinate2D) -> Void
        var lastRecenterTrigger: Int = -1
        var lastRouteSignature: String = ""
        var hasCenteredOnce: Bool = false

        init(onSelectDestination: @escaping (CLLocationCoordinate2D) -> Void) {
            self.onSelectDestination = onSelectDestination
        }

        @objc func handleMapTap(_ gesture: UITapGestureRecognizer) {
            guard gesture.state == .ended, let mapView = mapView else { return }
            let point = gesture.location(in: mapView)
            let coord = mapView.convert(point, toCoordinateFrom: mapView)
            onSelectDestination(coord)
        }

        func mapView(_ mapView: MKMapView, rendererFor overlay: MKOverlay) -> MKOverlayRenderer {
            if let polyline = overlay as? MKPolyline {
                let renderer = MKPolylineRenderer(polyline: polyline)
                renderer.strokeColor = UIColor(red: 0.19, green: 0.82, blue: 0.35, alpha: 0.95)
                renderer.lineWidth = 6.0
                renderer.lineCap = .round
                renderer.lineJoin = .round
                return renderer
            }
            return MKOverlayRenderer(overlay: overlay)
        }
    }
}
