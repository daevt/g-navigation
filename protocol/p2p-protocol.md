# Giao thức truyền dữ liệu P2P (iPhone ↔ Huawei Watch Fit 4 Pro)

Tài liệu này định nghĩa cấu trúc gói tin JSON rút gọn truyền qua **Huawei Wear Engine P2P** giữa ứng dụng iPhone (`GNavigation`) và ứng dụng đồng hồ (`watch-fit4pro`).

## 1. Nguyên tắc thiết kế cho Wear Engine P2P
- **Giới hạn kích thước gói tin**: Mỗi bản tin P2P (`WEP2PMessage`) được giữ dưới **900 bytes** (UTF-8 JSON với khóa viết tắt 1–2 ký tự) để đảm bảo độ trễ thấp (< 100ms) và không bị phân mảnh ở tầng Bluetooth BLE.
- **Tách luồng dữ liệu**:
  1. `S` (**State / Chỉ dẫn & Vị trí**): Gửi mỗi 1–2 giây (hoặc khi thay đổi > 3m / đổi góc > 5°). Rất nhẹ (~180 bytes).
  2. `R` (**Route Chunk / Tuyến đường**): Chia polyline của tuyến đường thành các gói nhỏ (`chunk`), chỉ gửi khi bắt đầu dẫn đường, khi tính lại tuyến (reroute), hoặc khi đồng hồ vừa kết nối lại Bluetooth.
  3. `M` (**Map Roads Chunk / Cụm đường nền xung quanh**): Gửi các đoạn đường xung quanh vị trí hiện tại (bán kính 250m–400m) theo từng gói nhỏ để đồng hồ tự vẽ bằng `Canvas`.
  4. `H` (**Heartbeat / Giữ kết nối**): Gửi mỗi 5 giây khi xe đứng yên lâu. Nếu đồng hồ không nhận được `S` hoặc `H` sau **12 giây**, đồng hồ tự động làm mờ/ẩn chỉ dẫn cũ và hiện cảnh báo **"Mất tín hiệu từ iPhone"** (đáp ứng Mốc 4).

---

## 2. Cấu trúc các loại bản tin

### 2.1. Bản tin trạng thái dẫn đường (`t: "S"`)
Gửi liên tục trong lúc di chuyển (kể cả khi iPhone khóa màn hình).

```json
{
  "t": "S",
  "seq": 42,
  "ts": 1731220000,
  "lat": 10.776889,
  "lng": 106.700806,
  "hdg": 65,
  "spd": 34,
  "mType": "TURN_RIGHT",
  "mDist": 85,
  "road": "Lê Lợi",
  "eta": "14:25",
  "rem": 3420,
  "vib": 1,
  "reroute": false
}
```

| Trường | Kiểu | Ý nghĩa |
|---|---|---|
| `t` | `string` | `"S"` — Gói tin trạng thái (Navigation State) |
| `seq` | `number` | Số thứ tự gói tin tăng dần |
| `ts` | `number` | Unix timestamp (giây) |
| `lat`, `lng` | `number` | Tọa độ GPS hiện tại của xe máy |
| `hdg` | `number` | Góc hướng di chuyển (`0`–`359` độ, Bắc = 0) |
| `spd` | `number` | Tốc độ hiện tại (`km/h`) |
| `mType` | `string` | Mã thao tác rẽ: `STRAIGHT`, `TURN_LEFT`, `TURN_RIGHT`, `SLIGHT_LEFT`, `SLIGHT_RIGHT`, `SHARP_LEFT`, `SHARP_RIGHT`, `UTURN`, `ROUNDABOUT`, `ARRIVE` |
| `mDist` | `number` | Khoảng cách tới điểm rẽ tiếp theo (mét) |
| `road` | `string` | Tên đường tiếp theo (tối đa 32 ký tự) |
| `eta` | `string` | Giờ đến dự kiến (`HH:mm`) |
| `rem` | `number` | Tổng quãng đường còn lại (mét) |
| `vib` | `number` | Lệnh rung trên đồng hồ: `0` = không rung, `1` = sắp rẽ (100m), `2` = rẽ ngay (30m), `3` = lệch tuyến / tính lại đường |
| `reroute` | `boolean` | `true` nếu đang tính lại tuyến do đi lệch |

---

### 2.2. Bản tin phân mảnh tuyến đường (`t: "R"`)
Tuyến đường chính được chia thành các gói tối đa 25 điểm tọa độ mỗi gói.

```json
{
  "t": "R",
  "id": "rt_102",
  "idx": 0,
  "tot": 3,
  "pts": [
    [10.776889, 106.700806],
    [10.777120, 106.701150],
    [10.777510, 106.701620]
  ]
}
```

| Trường | Kiểu | Ý nghĩa |
|---|---|---|
| `t` | `string` | `"R"` — Gói tin tuyến đường (Route Chunk) |
| `id` | `string` | Mã phiên tuyến đường (đổi mới khi reroute) |
| `idx` | `number` | Chỉ số gói hiện tại (`0 .. tot-1`) |
| `tot` | `number` | Tổng số gói của tuyến đường |
| `pts` | `number[][]` | Danh sách các cặp `[lat, lng]` làm tròn 6 chữ số thập phân |

---

### 2.3. Bản tin cụm đường nền xung quanh (`t: "M"`)
Để đồng hồ tự vẽ bản đồ nền xung quanh mà không cần tải ảnh nặng, iPhone gửi danh sách các đoạn đường lân cận (từ OSM/VIETMAP).

```json
{
  "t": "M",
  "tile": "10776_106700",
  "idx": 0,
  "tot": 2,
  "rds": [
    {
      "n": "Nguyễn Huệ",
      "c": 1,
      "p": [[10.7761, 106.7012], [10.7779, 106.7028]]
    },
    {
      "n": "Pasteur",
      "c": 2,
      "p": [[10.7755, 106.6998], [10.7782, 106.7015]]
    }
  ]
}
```

| Trường | Kiểu | Ý nghĩa |
|---|---|---|
| `t` | `string` | `"M"` — Gói tin đường nền (Map Roads Chunk) |
| `tile` | `string` | Mã ô lưới khu vực hiện tại |
| `idx`, `tot` | `number` | Chỉ số phân mảnh và tổng số mảnh của ô lưới |
| `rds` | `array` | Danh sách đoạn đường: `n` = tên đường (rỗng nếu hẻm nhỏ), `c` = cấp đường (`1`: trục chính, `2`: đường phố, `3`: đường nhỏ/hẻm), `p` = mảng `[lat, lng]` |

---

### 2.4. Bản tin từ Đồng hồ gửi ngược về iPhone (`t: "ACK"` / `"SYNC"`)
Khi đồng hồ mở app hoặc vừa kết nối lại Bluetooth sau khi đứt kết nối (Mốc 4), đồng hồ gửi bản tin yêu cầu đồng bộ lại toàn bộ tuyến đường và trạng thái mới nhất:

```json
{
  "t": "SYNC",
  "routeId": "rt_102",
  "bat": 85
}
```
