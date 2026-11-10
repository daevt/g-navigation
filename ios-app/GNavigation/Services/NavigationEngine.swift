import Foundation
import CoreLocation
import Combine

/// Bộ máy dẫn đường trung tâm trên iPhone:
/// - Duy trì GPS chạy nền ngay cả khi khóa màn hình iPhone
/// - Tính khoảng cách tới khúc rẽ, phát lệnh rung (100m / 30m)
/// - Phát hiện đi lệch tuyến (> 42m) và tự động tính lại tuyến xe máy qua Cloudflare Worker
/// - Chia nhỏ tuyến đường & cụm đường nền gửi sang Huawei Watch Fit 4 Pro
@MainActor
final class NavigationEngine: NSObject, ObservableObject, CLLocationManagerDelegate {
    @Published var currentLocation: CLLocationCoordinate2D = CLLocationCoordinate2D(latitude: 21.028511, longitude: 105.854444)
    @Published var hasRealGPSFix: Bool = false
    @Published var gpsAccuracyMeters: Int = 0
    @Published var currentHeading: Double = 0
    @Published var currentSpeedKmh: Int = 0

    @Published var isNavigating: Bool = false
    @Published var isSimulatingLockScreen: Bool = false
    @Published var isRerouting: Bool = false

    @Published var activeRoute: RouteResponseDTO?
    @Published var currentStepIndex: Int = 0
    @Published var distanceToNextTurnMeters: Int = 85
    @Published var remainingDistanceMeters: Int = 0
    @Published var etaString: String = "--:--"

    private let locationManager = CLLocationManager()
    private let wearManager = WearEngineManager.shared
    private var packetSeq: Int = 0
    private var lastLoadedTileId: String = ""
    private var latestRoadsResponse: RoadsResponseDTO?
    private var destinationCoord: CLLocationCoordinate2D?

    private var fired100mVibForStep: Int = -1
    private var fired30mVibForStep: Int = -1
    private var offRouteCount: Int = 0

    private var heartbeatTimer: Timer?
    private var lockScreenSimTimer: Timer?
    private var simStepCursor: Int = 0

    override init() {
        super.init()
        locationManager.delegate = self
        locationManager.desiredAccuracy = kCLLocationAccuracyBestForNavigation
        locationManager.distanceFilter = 3
        locationManager.activityType = .automotiveNavigation
        locationManager.pausesLocationUpdatesAutomatically = false

        // Khi đồng hồ vừa kết nối lại Bluetooth (Mốc 4), tự động đồng bộ lại toàn bộ tuyến & trạng thái
        wearManager.onWatchRequestedSync = { [weak self] in
            Task { @MainActor in
                self?.resyncAllToWatch()
            }
        }

        // Khởi động GPS thật ngay khi mở app
        requestLocationPermissions()
    }

    func requestLocationPermissions() {
        locationManager.requestAlwaysAuthorization()
        if Bundle.main.object(forInfoDictionaryKey: "UIBackgroundModes") != nil {
            locationManager.allowsBackgroundLocationUpdates = true
        }
        locationManager.startUpdatingLocation()
        locationManager.startUpdatingHeading()
    }

    // MARK: - Mốc 2: Gửi chỉ dẫn mẫu + Cụm đường giả & Kiểm thử khóa màn hình

    func sendMilestone2SamplePayload() {
        wearManager.appendLog("Mốc 2: Gửi cụm đường giả (M) + tuyến mẫu (R) + chỉ dẫn mẫu (S)...")

        let routeChunks = P2PPacketChunker.makeRouteChunks(
            routeId: "m2_sample",
            points: SampleMilestone2Data.routePoints
        )
        wearManager.sendRouteChunks(routeChunks)

        let roadChunks = P2PPacketChunker.makeRoadChunks(
            tileId: "tile_q1_sample",
            roads: SampleMilestone2Data.roadCluster
        )
        wearManager.sendRoadChunks(roadChunks)

        packetSeq += 1
        let sampleState = P2PStatePacket(
            seq: packetSeq,
            ts: Int(Date().timeIntervalSince1970),
            lat: 10.775840,
            lng: 106.700420,
            hdg: 45,
            spd: 34,
            mType: "TURN_RIGHT",
            mDist: 85,
            road: "Nguyễn Huệ",
            eta: Self.computeETAString(secondsFromNow: 480),
            rem: 1850,
            vib: 1,
            reroute: false
        )
        wearManager.sendStatePacket(sampleState)
    }

    /// Bật/tắt chế độ phát liên tục khi khóa màn hình iPhone (dùng cho Mốc 2 & Mốc 4)
    func toggleLockScreenSimulation() {
        if isSimulatingLockScreen {
            stopLockScreenSimulation()
            return
        }
        requestLocationPermissions()
        isSimulatingLockScreen = true
        simStepCursor = 0
        sendMilestone2SamplePayload()

        wearManager.appendLog("Bắt đầu phát P2P định kỳ mỗi 2 giây. Hãy khóa màn hình iPhone để kiểm tra!")
        lockScreenSimTimer = Timer.scheduledTimer(withTimeInterval: 2.0, repeats: true) { [weak self] _ in
            Task { @MainActor in
                self?.tickLockScreenSimulation()
            }
        }
    }

    func stopLockScreenSimulation() {
        lockScreenSimTimer?.invalidate()
        lockScreenSimTimer = nil
        isSimulatingLockScreen = false
        wearManager.appendLog("Đã dừng chế độ phát thử khóa màn hình.")
    }

    private func tickLockScreenSimulation() {
        let pts = SampleMilestone2Data.routePoints
        guard pts.count >= 2 else { return }

        let idx = simStepCursor % (pts.count - 1)
        let curr = pts[idx]
        let next = pts[idx + 1]
        simStepCursor += 1

        let distLeft = max(15, 120 - (simStepCursor % 6) * 20)
        let vib = distLeft == 35 ? 2 : (distLeft == 95 ? 1 : 0)

        let dy = next[0] - curr[0]
        let dx = next[1] - curr[1]
        let hdg = Int((atan2(dx, dy) * 180.0 / .pi + 360.0).truncatingRemainder(dividingBy: 360.0))

        packetSeq += 1
        let pkt = P2PStatePacket(
            seq: packetSeq,
            ts: Int(Date().timeIntervalSince1970),
            lat: curr[0],
            lng: curr[1],
            hdg: hdg,
            spd: 32,
            mType: idx < 3 ? "TURN_RIGHT" : "TURN_LEFT",
            mDist: distLeft,
            road: idx < 3 ? "Nguyễn Huệ" : "Đồng Khởi",
            eta: Self.computeETAString(secondsFromNow: 420),
            rem: max(150, 1800 - (simStepCursor % 15) * 90),
            vib: vib,
            reroute: false
        )
        wearManager.sendStatePacket(pkt)
    }

    // MARK: - Mốc 3 & Mốc 4: Dẫn đường xe máy thật với VIETMAP / OSM

    func startNavigation(to destination: CLLocationCoordinate2D) async {
        stopLockScreenSimulation()
        requestLocationPermissions()
        destinationCoord = destination
        isRerouting = false
        offRouteCount = 0
        fired100mVibForStep = -1
        fired30mVibForStep = -1

        do {
            wearManager.appendLog("Đang tính tuyến xe máy tới (\(String(format: "%.5f, %.5f", destination.latitude, destination.longitude)))...")
            let route = try await BackendClient.shared.fetchMotorcycleRoute(from: currentLocation, to: destination)
            activeRoute = route
            currentStepIndex = 0
            remainingDistanceMeters = route.distanceMeters
            etaString = Self.computeETAString(secondsFromNow: route.durationSeconds)
            isNavigating = true

            // Chia nhỏ và gửi polyline tuyến đường sang đồng hồ
            let routeChunks = P2PPacketChunker.makeRouteChunks(routeId: route.routeId, points: route.points)
            wearManager.sendRouteChunks(routeChunks)

            // Tải cụm đường nền xung quanh vị trí xuất phát
            await updateNearbyRoadsIfNeeded(for: currentLocation, force: true)

            // Gửi gói trạng thái đầu tiên
            broadcastCurrentNavState(vibCode: 1)
            startHeartbeatTimer()
        } catch {
            wearManager.appendLog("Lỗi tính tuyến: \(error.localizedDescription)")
        }
    }

    func stopNavigation() {
        isNavigating = false
        activeRoute = nil
        destinationCoord = nil
        heartbeatTimer?.invalidate()
        heartbeatTimer = nil
        wearManager.appendLog("Đã kết thúc dẫn đường.")
    }

    /// Đồng bộ lại toàn bộ tuyến đường + đường nền + trạng thái khi đồng hồ nối lại Bluetooth (Mốc 4)
    func resyncAllToWatch() {
        if let route = activeRoute {
            let rChunks = P2PPacketChunker.makeRouteChunks(routeId: route.routeId, points: route.points)
            wearManager.sendRouteChunks(rChunks)
        }
        if let roads = latestRoadsResponse {
            let mChunks = P2PPacketChunker.makeRoadChunks(tileId: roads.tile, roads: roads.roads)
            wearManager.sendRoadChunks(mChunks)
        }
        if isNavigating {
            broadcastCurrentNavState(vibCode: 0)
        }
    }

    private func startHeartbeatTimer() {
        heartbeatTimer?.invalidate()
        heartbeatTimer = Timer.scheduledTimer(withTimeInterval: 5.0, repeats: true) { [weak self] _ in
            Task { @MainActor in
                guard let self = self, self.isNavigating else { return }
                self.wearManager.sendHeartbeat()
            }
        }
    }

    private func updateNearbyRoadsIfNeeded(for coord: CLLocationCoordinate2D, force: Bool = false) async {
        let tileLat = Int(round(coord.latitude * 333))
        let tileLng = Int(round(coord.longitude * 333))
        let tileKey = "\(tileLat)_\(tileLng)"

        guard force || tileKey != lastLoadedTileId else { return }
        lastLoadedTileId = tileKey

        let roadsRes = await BackendClient.shared.fetchNearbyRoads(coord: coord)
        latestRoadsResponse = roadsRes
        let chunks = P2PPacketChunker.makeRoadChunks(tileId: roadsRes.tile, roads: roadsRes.roads)
        wearManager.sendRoadChunks(chunks)
    }

    private func evaluatePositionOnRoute(_ location: CLLocation) {
        guard isNavigating, let route = activeRoute else { return }

        let coord = location.coordinate
        // 1. Kiểm tra lệch tuyến (> 42m so với các đoạn của polyline)
        let minDistanceToPolyline = Self.distanceFromPointToPolylineMeters(coord: coord, polyline: route.points)
        if minDistanceToPolyline > 42 {
            offRouteCount += 1
            if offRouteCount >= 2 && !isRerouting, let dest = destinationCoord {
                isRerouting = true
                broadcastCurrentNavState(vibCode: 3)
                Task {
                    await startNavigation(to: dest)
                }
                return
            }
        } else {
            offRouteCount = 0
        }

        // 2. Cập nhật bước rẽ tiếp theo
        if !route.steps.isEmpty {
            let safeIdx = min(currentStepIndex, route.steps.count - 1)
            let step = route.steps[safeIdx]
            if step.location.count >= 2 {
                let stepLoc = CLLocation(latitude: step.location[0], longitude: step.location[1])
                let dist = Int(location.distance(from: stepLoc))
                distanceToNextTurnMeters = dist

                // Nếu đã đi qua nút giao (< 18m), chuyển sang bước tiếp theo
                if dist < 18 && currentStepIndex < route.steps.count - 1 {
                    currentStepIndex += 1
                }
            }
        }

        // 3. Quyết định mã rung báo rẽ (100m -> vib 1, 30m -> vib 2)
        var vib = 0
        if distanceToNextTurnMeters <= 32 && fired30mVibForStep != currentStepIndex {
            fired30mVibForStep = currentStepIndex
            vib = 2
        } else if distanceToNextTurnMeters <= 105 && distanceToNextTurnMeters > 35 && fired100mVibForStep != currentStepIndex {
            fired100mVibForStep = currentStepIndex
            vib = 1
        }

        broadcastCurrentNavState(vibCode: vib)

        Task {
            await updateNearbyRoadsIfNeeded(for: coord)
        }
    }

    private func broadcastCurrentNavState(vibCode: Int) {
        guard let route = activeRoute else { return }
        let step: RouteStepDTO? = route.steps.isEmpty ? nil : route.steps[min(currentStepIndex, route.steps.count - 1)]

        packetSeq += 1
        let pkt = P2PStatePacket(
            seq: packetSeq,
            ts: Int(Date().timeIntervalSince1970),
            lat: currentLocation.latitude,
            lng: currentLocation.longitude,
            hdg: Int(currentHeading),
            spd: currentSpeedKmh,
            mType: step?.maneuverType ?? "STRAIGHT",
            mDist: distanceToNextTurnMeters,
            road: step?.roadName ?? "Đường phía trước",
            eta: etaString,
            rem: remainingDistanceMeters,
            vib: vibCode,
            reroute: isRerouting
        )
        wearManager.sendStatePacket(pkt)
    }

    // MARK: - CLLocationManagerDelegate

    nonisolated func locationManager(_ manager: CLLocationManager, didUpdateLocations locations: [CLLocation]) {
        guard let latest = locations.last else { return }
        Task { @MainActor in
            self.currentLocation = latest.coordinate
            self.hasRealGPSFix = true
            self.gpsAccuracyMeters = max(1, Int(round(latest.horizontalAccuracy)))
            if latest.course >= 0 {
                self.currentHeading = latest.course
            }
            if latest.speed >= 0 {
                self.currentSpeedKmh = Int(round(latest.speed * 3.6))
            }
            if self.isNavigating {
                self.evaluatePositionOnRoute(latest)
            } else {
                // Ngay cả khi chưa chọn điểm đến, vẫn đồng bộ vị trí GPS thật sang đồng hồ
                self.packetSeq += 1
                let freeRidePkt = P2PStatePacket(
                    seq: self.packetSeq,
                    ts: Int(Date().timeIntervalSince1970),
                    lat: latest.coordinate.latitude,
                    lng: latest.coordinate.longitude,
                    hdg: Int(self.currentHeading),
                    spd: self.currentSpeedKmh,
                    mType: "STRAIGHT",
                    mDist: 0,
                    road: "GPS thực tế (±\(self.gpsAccuracyMeters)m)",
                    eta: "--:--",
                    rem: 0,
                    vib: 0,
                    reroute: false
                )
                self.wearManager.sendStatePacket(freeRidePkt)
                await self.updateNearbyRoadsIfNeeded(for: latest.coordinate)
            }
        }
    }

    nonisolated func locationManager(_ manager: CLLocationManager, didUpdateHeading newHeading: CLHeading) {
        guard newHeading.trueHeading >= 0 || newHeading.magneticHeading >= 0 else { return }
        let hdg = newHeading.trueHeading >= 0 ? newHeading.trueHeading : newHeading.magneticHeading
        Task { @MainActor in
            if self.currentSpeedKmh < 5 {
                self.currentHeading = hdg
            }
        }
    }

    // MARK: - Tiện ích tính toán khoảng cách

    private static func computeETAString(secondsFromNow: Int) -> String {
        let arrival = Date().addingTimeInterval(TimeInterval(secondsFromNow))
        let fmt = DateFormatter()
        fmt.dateFormat = "HH:mm"
        return fmt.string(from: arrival)
    }

    private static func distanceFromPointToPolylineMeters(coord: CLLocationCoordinate2D, polyline: [[Double]]) -> Double {
        guard !polyline.isEmpty else { return 0 }
        let userLoc = CLLocation(latitude: coord.latitude, longitude: coord.longitude)
        var minMeters = Double.greatestFiniteMagnitude
        for pt in polyline {
            guard pt.count >= 2 else { continue }
            let d = userLoc.distance(from: CLLocation(latitude: pt[0], longitude: pt[1]))
            if d < minMeters {
                minMeters = d
            }
        }
        return minMeters
    }
}
