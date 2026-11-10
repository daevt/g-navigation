import Foundation
import CoreLocation

/// Giao tiếp với Cloudflare Worker (bảo vệ khóa VIETMAP Route v4)
/// Có tích hợp chế độ dự phòng trực tiếp (OSRM/Nominatim) nếu người dùng chưa deploy Worker.
final class BackendClient {
    static let shared = BackendClient()
    private let session: URLSession

    private init() {
        let cfg = URLSessionConfiguration.default
        cfg.timeoutIntervalForRequest = 12
        self.session = URLSession(configuration: cfg)
    }

    private var isWorkerConfigured: Bool {
        let url = AppConfig.workerBaseURL
        return url.hasPrefix("http") && !url.contains("YOUR-SUBDOMAIN")
    }

    /// Tìm kiếm địa điểm
    func searchPlaces(query: String, near coord: CLLocationCoordinate2D) async throws -> [SearchPlaceDTO] {
        let trimmed = query.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return [] }

        if isWorkerConfigured {
            var comps = URLComponents(string: "\(AppConfig.workerBaseURL)/api/search")
            comps?.queryItems = [
                URLQueryItem(name: "q", value: trimmed),
                URLQueryItem(name: "lat", value: String(format: "%.6f", coord.latitude)),
                URLQueryItem(name: "lng", value: String(format: "%.6f", coord.longitude))
            ]
            if let url = comps?.url {
                var req = URLRequest(url: url)
                if !AppConfig.workerClientToken.isEmpty {
                    req.setValue(AppConfig.workerClientToken, forHTTPHeaderField: "X-Client-Token")
                }
                let (data, _) = try await session.data(for: req)
                let decoded = try JSONDecoder().decode(SearchResponseDTO.self, from: data)
                return decoded.results
            }
        }

        // Dự phòng trực tiếp qua Nominatim (0 đồng) khi chưa cấu hình Worker URL
        var comps = URLComponents(string: "https://nominatim.openstreetmap.org/search")
        comps?.queryItems = [
            URLQueryItem(name: "format", value: "json"),
            URLQueryItem(name: "countrycodes", value: "vn"),
            URLQueryItem(name: "limit", value: "5"),
            URLQueryItem(name: "q", value: trimmed)
        ]
        guard let url = comps?.url else { return [] }
        var req = URLRequest(url: url)
        req.setValue("GNavigation-iOS/1.0", forHTTPHeaderField: "User-Agent")
        let (data, _) = try await session.data(for: req)
        guard let arr = try JSONSerialization.jsonObject(with: data) as? [[String: Any]] else {
            return []
        }
        return arr.compactMap { item in
            guard let disp = item["display_name"] as? String,
                  let latStr = item["lat"] as? String,
                  let lonStr = item["lon"] as? String,
                  let lat = Double(latStr),
                  let lng = Double(lonStr) else { return nil }
            let shortName = disp.components(separatedBy: ",").first ?? disp
            return SearchPlaceDTO(name: shortName, address: disp, lat: lat, lng: lng)
        }
    }

    /// Tính tuyến đường xe máy (`vehicle=motorcycle`)
    func fetchMotorcycleRoute(from origin: CLLocationCoordinate2D, to dest: CLLocationCoordinate2D) async throws -> RouteResponseDTO {
        if isWorkerConfigured {
            var comps = URLComponents(string: "\(AppConfig.workerBaseURL)/api/route")
            comps?.queryItems = [
                URLQueryItem(name: "origin", value: String(format: "%.6f,%.6f", origin.latitude, origin.longitude)),
                URLQueryItem(name: "dest", value: String(format: "%.6f,%.6f", dest.latitude, dest.longitude)),
                URLQueryItem(name: "vehicle", value: "motorcycle")
            ]
            if let url = comps?.url {
                var req = URLRequest(url: url)
                if !AppConfig.workerClientToken.isEmpty {
                    req.setValue(AppConfig.workerClientToken, forHTTPHeaderField: "X-Client-Token")
                }
                let (data, _) = try await session.data(for: req)
                return try JSONDecoder().decode(RouteResponseDTO.self, from: data)
            }
        }

        // Dự phòng trực tiếp OSRM khi chưa điền Cloudflare Worker URL
        let coordPair = String(format: "%.6f,%.6f;%.6f,%.6f", origin.longitude, origin.latitude, dest.longitude, dest.latitude)
        let urlStr = "https://router.project-osrm.org/route/v1/driving/\(coordPair)?overview=full&geometries=geojson&steps=true"
        guard let url = URL(string: urlStr) else {
            throw URLError(.badURL)
        }
        let (data, _) = try await session.data(from: url)
        guard let root = try JSONSerialization.jsonObject(with: data) as? [String: Any],
              let routes = root["routes"] as? [[String: Any]],
              let first = routes.first,
              let geom = first["geometry"] as? [String: Any],
              let rawCoords = geom["coordinates"] as? [[Double]] else {
            throw URLError(.cannotParseResponse)
        }

        let pts: [[Double]] = rawCoords.map { [round6($0[1]), round6($0[0])] }
        let dist = Int((first["distance"] as? Double) ?? 0)
        let dur = Int((first["duration"] as? Double) ?? 0)

        var parsedSteps: [RouteStepDTO] = []
        if let legs = first["legs"] as? [[String: Any]],
           let rawSteps = legs.first?["steps"] as? [[String: Any]] {
            for s in rawSteps {
                let road = (s["name"] as? String)?.trimmingCharacters(in: .whitespacesAndNewlines) ?? "Đường phía trước"
                let sDist = Int((s["distance"] as? Double) ?? 0)
                let sDur = Int((s["duration"] as? Double) ?? 0)
                let man = s["maneuver"] as? [String: Any]
                let mType = Self.mapOsrmManeuver(
                    type: man?["type"] as? String,
                    modifier: man?["modifier"] as? String
                )
                let locArr = (man?["location"] as? [Double]) ?? [origin.longitude, origin.latitude]
                let stepLoc = [round6(locArr[1]), round6(locArr[0])]
                parsedSteps.append(
                    RouteStepDTO(
                        maneuverType: mType,
                        text: road.isEmpty ? "Đi thẳng" : road,
                        roadName: road.isEmpty ? "Đường phía trước" : road,
                        distanceMeters: sDist,
                        durationSeconds: sDur,
                        location: stepLoc,
                        interval: [0, 0]
                    )
                )
            }
        }

        return RouteResponseDTO(
            routeId: "osrm_\(Int(Date().timeIntervalSince1970))",
            provider: "direct-osm",
            vehicle: "motorcycle",
            distanceMeters: dist,
            durationSeconds: dur,
            points: pts,
            steps: parsedSteps
        )
    }

    /// Tải cụm đường nền xung quanh vị trí hiện tại để gửi sang đồng hồ tự vẽ bằng Canvas
    func fetchNearbyRoads(coord: CLLocationCoordinate2D, radius: Int = 320) async -> RoadsResponseDTO {
        if isWorkerConfigured {
            var comps = URLComponents(string: "\(AppConfig.workerBaseURL)/api/roads")
            comps?.queryItems = [
                URLQueryItem(name: "lat", value: String(format: "%.6f", coord.latitude)),
                URLQueryItem(name: "lng", value: String(format: "%.6f", coord.longitude)),
                URLQueryItem(name: "radius", value: "\(radius)")
            ]
            if let url = comps?.url {
                var req = URLRequest(url: url)
                if !AppConfig.workerClientToken.isEmpty {
                    req.setValue(AppConfig.workerClientToken, forHTTPHeaderField: "X-Client-Token")
                }
                if let (data, _) = try? await session.data(for: req),
                   let decoded = try? JSONDecoder().decode(RoadsResponseDTO.self, from: data) {
                    return decoded
                }
            }
        }

        let tileLat = Int(round(coord.latitude * 333))
        let tileLng = Int(round(coord.longitude * 333))
        return RoadsResponseDTO(
            tile: "\(tileLat)_\(tileLng)",
            roads: SampleMilestone2Data.roadCluster
        )
    }

    private static func mapOsrmManeuver(type: String?, modifier: String?) -> String {
        if type == "arrive" { return "ARRIVE" }
        if type == "roundabout" || type == "rotary" { return "ROUNDABOUT" }
        switch modifier {
        case "uturn": return "UTURN"
        case "sharp left": return "SHARP_LEFT"
        case "left": return "TURN_LEFT"
        case "slight left": return "SLIGHT_LEFT"
        case "sharp right": return "SHARP_RIGHT"
        case "right": return "TURN_RIGHT"
        case "slight right": return "SLIGHT_RIGHT"
        default: return "STRAIGHT"
        }
    }

    private func round6(_ val: Double) -> Double {
        (val * 1_000_000).rounded() / 1_000_000
    }
}
