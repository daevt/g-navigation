import Foundation
import CoreLocation

// MARK: - Dữ liệu trả về từ Cloudflare Worker (VIETMAP / OSM)

struct RouteStepDTO: Codable, Identifiable {
    var id: String { "\(maneuverType)_\(distanceMeters)_\(location.first ?? 0)" }
    let maneuverType: String
    let text: String
    let roadName: String
    let distanceMeters: Int
    let durationSeconds: Int
    let location: [Double]
    let interval: [Int]
}

struct RouteResponseDTO: Codable {
    let routeId: String
    let provider: String
    let vehicle: String
    let distanceMeters: Int
    let durationSeconds: Int
    let points: [[Double]]
    let steps: [RouteStepDTO]
}

struct CompactRoadDTO: Codable {
    /// Tên đường
    let n: String
    /// Cấp đường: 1 = trục chính, 2 = đường phố, 3 = hẻm/đường nội bộ
    let c: Int
    /// Danh sách tọa độ `[lat, lng]`
    let p: [[Double]]
}

struct RoadsResponseDTO: Codable {
    let tile: String
    let roads: [CompactRoadDTO]
}

struct SearchPlaceDTO: Codable, Identifiable {
    var id: String { "\(name)_\(lat)_\(lng)" }
    let name: String
    let address: String
    let lat: Double
    let lng: Double
}

struct SearchResponseDTO: Codable {
    let provider: String?
    let results: [SearchPlaceDTO]
}

// MARK: - Các gói tin P2P rút gọn gửi sang Huawei Watch Fit 4 Pro

struct P2PStatePacket: Codable {
    var t: String = "S"
    let seq: Int
    let ts: Int
    let lat: Double
    let lng: Double
    let hdg: Int
    let spd: Int
    let mType: String
    let mDist: Int
    let road: String
    let eta: String
    let rem: Int
    let vib: Int
    let reroute: Bool
}

struct P2PRouteChunkPacket: Codable {
    var t: String = "R"
    let id: String
    let idx: Int
    let tot: Int
    let pts: [[Double]]
}

struct P2PRoadChunkPacket: Codable {
    var t: String = "M"
    let tile: String
    let idx: Int
    let tot: Int
    let rds: [CompactRoadDTO]
}

struct P2PHeartbeatPacket: Codable {
    var t: String = "H"
    let ts: Int
}

// MARK: - Bộ chia nhỏ gói tin (Chunker) đảm bảo mỗi bản tin P2P < 900 bytes

enum P2PPacketChunker {
    /// Chia danh sách điểm tọa độ của tuyến đường thành các gói tối đa 22 điểm/gói
    static func makeRouteChunks(routeId: String, points: [[Double]], maxPointsPerChunk: Int = 22) -> [P2PRouteChunkPacket] {
        guard !points.isEmpty else { return [] }
        var chunks: [[[Double]]] = []
        var idx = 0
        while idx < points.count {
            let end = min(idx + maxPointsPerChunk, points.count)
            var slice = Array(points[idx..<end])
            // Nối điểm cuối của gói trước vào đầu gói sau để đường vẽ không bị đứt nét
            if idx > 0, let prevLast = chunks.last?.last {
                slice.insert(prevLast, at: 0)
            }
            chunks.append(slice)
            idx = end
        }
        let total = chunks.count
        return chunks.enumerated().map { offset, pts in
            P2PRouteChunkPacket(id: routeId, idx: offset, tot: total, pts: pts)
        }
    }

    /// Chia các đoạn đường nền xung quanh thành từng gói tối đa 6 đoạn đường/gói
    static func makeRoadChunks(tileId: String, roads: [CompactRoadDTO], maxRoadsPerChunk: Int = 6) -> [P2PRoadChunkPacket] {
        guard !roads.isEmpty else { return [] }
        var groups: [[CompactRoadDTO]] = []
        var idx = 0
        while idx < roads.count {
            let end = min(idx + maxRoadsPerChunk, roads.count)
            groups.append(Array(roads[idx..<end]))
            idx = end
        }
        let total = groups.count
        return groups.enumerated().map { offset, rds in
            P2PRoadChunkPacket(tile: tileId, idx: offset, tot: total, rds: rds)
        }
    }
}

// MARK: - Dữ liệu mẫu dùng cho Mốc 2 ("Gửi chỉ dẫn mẫu và một cụm đường giả sang đồng hồ")

enum SampleMilestone2Data {
    static let routePoints: [[Double]] = [
        [10.774500, 106.698900],
        [10.775150, 106.699650],
        [10.775840, 106.700420],
        [10.776480, 106.701120],
        [10.775800, 106.701950],
        [10.775100, 106.702800],
        [10.774450, 106.703600]
    ]

    static let roadCluster: [CompactRoadDTO] = [
        CompactRoadDTO(n: "Lê Lợi", c: 1, p: [
            [10.773800, 106.698100],
            [10.775150, 106.699650],
            [10.776480, 106.701120],
            [10.777600, 106.702400]
        ]),
        CompactRoadDTO(n: "Nguyễn Huệ", c: 1, p: [
            [10.777400, 106.700100],
            [10.776480, 106.701120],
            [10.775100, 106.702800],
            [10.773600, 106.704600]
        ]),
        CompactRoadDTO(n: "Pasteur", c: 2, p: [
            [10.776900, 106.698200],
            [10.775500, 106.699800],
            [10.774000, 106.701500]
        ]),
        CompactRoadDTO(n: "Đồng Khởi", c: 2, p: [
            [10.778200, 106.701800],
            [10.776600, 106.703500],
            [10.775000, 106.705200]
        ])
    ]
}
