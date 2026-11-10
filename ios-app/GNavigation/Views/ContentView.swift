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
                } else {
                    // Các điểm đến mẫu nhanh để chạy thử ngay ngoài đường
                    VStack(alignment: .leading, spacing: 8) {
                        Text("Điểm đến thử nhanh (Xe máy · Motorcycle):")
                            .font(.caption.bold())
                            .foregroundStyle(.secondary)

                        HStack(spacing: 8) {
                            Button("Nhà hát TP (Q.1)") {
                                Task {
                                    await navEngine.startNavigation(
                                        to: CLLocationCoordinate2D(latitude: 10.7769, longitude: 106.7032)
                                    )
                                }
                            }
                            .buttonStyle(.bordered)
                            .font(.caption)

                            Button("Dinh Độc Lập") {
                                Task {
                                    await navEngine.startNavigation(
                                        to: CLLocationCoordinate2D(latitude: 10.7770, longitude: 106.6953)
                                    )
                                }
                            }
                            .buttonStyle(.bordered)
                            .font(.caption)
                        }
                    }
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .padding(12)
                    .background(Color(.secondarySystemBackground))
                    .clipShape(RoundedRectangle(cornerRadius: 12))
                }

                Spacer()
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
