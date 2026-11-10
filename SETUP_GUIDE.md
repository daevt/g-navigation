# Hướng dẫn Triển khai G Navigation (Ngân sách 0 đồng trên Windows)

Tài liệu này hướng dẫn từng bước thực hiện theo đúng **4 mốc trong `PLAN.md`** cho bộ 3 thành phần đã được dựng sẵn trong project:

1. [`watch-fit4pro/`](watch-fit4pro): Ứng dụng đồng hồ **Huawei Watch Fit 4 Pro** (HarmonyOS / ArkTS) tự vẽ bản đồ bằng `Canvas`, hiển thị thẻ chỉ dẫn rẽ, rung báo rẽ và tự ẩn chỉ dẫn cũ khi mất kết nối.
2. [`ios-app/`](ios-app) + [`codemagic.yaml`](codemagic.yaml): Ứng dụng **iPhone (SwiftUI)** chạy nền khi khóa màn hình, chia gói tuyến đường & cụm đường nền gửi qua Wear Engine P2P, kèm cấu hình build `.ipa` miễn phí trên **Codemagic** để cài qua **Sideloadly** trên Windows.
3. [`backend-worker/`](backend-worker): **Cloudflare Worker** giữ khóa API `VIETMAP_API_KEY` (`vehicle=motorcycle`) và trích xuất vector đường nền OpenStreetMap có bộ nhớ đệm Edge.

---

## Mốc 1: Xác minh Huawei & Chạy thử trên DevEco Simulator (0 đồng)

### 1.1. Chạy ngay giao diện trong DevEco Simulator trên Windows
1. Cài đặt và mở **DevEco Studio** trên Windows.
2. Chọn **Open Project** → trỏ vào thư mục `c:\Users\lenovo\project\g-navigation\watch-fit4pro`.
3. Mở **Tools → Device Manager**, tải và khởi động máy ảo **Wearable** (ưu tiên kích thước vuông bo góc tương đương Fit 4 Pro).
4. Nhấn **Run (`Shift + F10`)** để chạy ứng dụng lên Simulator.
5. **Kiểm thử ngay trên Simulator**:
   - Giao diện sẽ hiển thị bản đồ nền đường phố Quận 1, đường dẫn màu xanh ngọc, thẻ báo rẽ phía trên (`85 m · Lê Lợi`) và thanh tốc độ/ETA phía dưới.
   - **Chạm vào thanh trạng thái phía dưới (`DEMO`)** để mở bảng **Kiểm thử Simulator & P2P**:
     - Bấm **Chạy thử** để xem xe di chuyển dọc tuyến và tự xoay bản đồ theo hướng đi (Heading-Up).
     - Bấm **Lệch tuyến** để kiểm tra giao diện cảnh báo đi chệch đường + rung 3 nhịp.
     - Bấm **Mất KN (Mốc 4)** để kiểm tra tính năng tự động ẩn chỉ dẫn cũ khi mất dữ liệu từ iPhone.

### 1.2. Đăng ký quyền Wear Engine P2P trên Huawei Developer
1. Đăng nhập tài khoản cá nhân tại [Huawei Developer Console](https://developer.huawei.com/consumer/en/console).
2. Vào **AppGallery Connect** → Tạo project mới và thêm 2 ứng dụng:
   - **Ứng dụng Wearable (HarmonyOS)**: Bundle Name đặt là `com.gnavigation.watch`.
   - **Ứng dụng iOS**: Bundle ID tạm đặt là `com.gnavigation.ios` (lưu ý ở Mốc 2: sau khi ký bằng Sideloadly, nếu Sideloadly đổi Bundle ID thành `com.gnavigation.ios.XXXXX`, bạn cập nhật lại đúng chuỗi đó trên Huawei Console).
3. Vào mục **Health Kit / Wear Engine → Apply for Wear Engine**:
   - Chọn quyền **Device Manager** và **P2P (Point-to-Point communication)**.
   - Điền **Callback URL Scheme** cho bản iOS: `gnavigation://wearengine`.

---

## Mốc 2: Build `.ipa` bằng Codemagic Free & Cài lên iPhone qua Sideloadly (0 đồng)

### 2.1. Build `.ipa` không cần máy Mac bằng Codemagic
1. Đẩy toàn bộ thư mục `g-navigation` lên một kho chứa GitHub/GitLab cá nhân (có thể để Private).
2. Đăng nhập [Codemagic](https://codemagic.io/) bằng tài khoản GitHub/GitLab (gói Free có sẵn 500 phút build macOS M2 mỗi tháng).
3. Chọn仓库 `g-navigation` → Chọn workflow **`ios-sideloadly-free`** từ file [`codemagic.yaml`](codemagic.yaml) → bấm **Start new build**.
4. Sau khoảng 3–4 phút, tải file **`GNavigation-unsigned.ipa`** ở cột **Artifacts** về máy Windows.
   - *(Tùy chọn)* Khi đã tải bộ `HuaweiWearEngine.xcframework` từ Huawei Developer Console, bạn đặt vào `ios-app/Vendor/HuaweiWearEngine.xcframework` và khai báo trong `ios-app/project.yml` để kích hoạt SDK truyền BLE thật.

### 2.2. Ký và cài lên iPhone bằng Sideloadly trên Windows
1. Cài đặt **iTunes** (bản tải trực tiếp từ Apple, không phải bản Microsoft Store) và **iCloud** trên Windows, sau đó mở **Sideloadly**.
2. Cắm cáp iPhone vào máy tính, chọn thiết bị iPhone và nhập Apple ID miễn phí của bạn.
3. Kéo thả file `GNavigation-unsigned.ipa` vào Sideloadly:
   - Mở **Advanced Options** trong Sideloadly:
   - Nếu tài khoản chưa từng đụng độ Bundle ID, bạn có thể thử bỏ chọn *Use automatic bundle ID* để giữ nguyên `com.gnavigation.ios`. Nếu Apple bắt buộc gắn hậu tố Team ID cho tài khoản miễn phí, cứ để Sideloadly tự ký.
4. Trên iPhone, vào **Cài đặt → Cài đặt chung → Quản lý VPN & Thiết bị** → Tin cậy (Trust) chứng chỉ Apple ID của bạn, và bật **Developer Mode (Chế độ nhà phát triển)** trong **Quyền riêng tư & Bảo mật**.

### 2.3. Kiểm tra Bundle ID thực tế & Gửi gói tin mẫu khi khóa màn hình
1. Mở app **G Navigation** trên iPhone → chuyển sang tab thứ 2: **`Kiểm thử Mốc 2`**.
2. Xem ô **`Bundle ID thực tế`** (ví dụ `com.gnavigation.ios.A1B2C3D4`):
   - Bấm nút **Sao chép** và đảm bảo giá trị này khớp với cấu hình iOS App trên Huawei Wear Engine Console cũng như biến `IOS_PEER_BUNDLE_ID` trong [`WearEngineService.ets`](watch-fit4pro/entry/src/main/ets/services/WearEngineService.ets).
3. Bấm **`Xin quyền Huawei`** → **`Ping Fit 4 Pro`** → **`Gửi chỉ dẫn mẫu + Cụm đường giả ngay`**.
4. Bấm nút màu tím **`Bật phát liên tục rồi khóa màn hình iPhone`**, chọn cấp quyền vị trí **"Luôn luôn (Always)"**, sau đó bấm nút nguồn khóa màn hình iPhone để kiểm tra đồng hồ vẫn nhận dữ liệu đều đặn mỗi 2 giây.

---

## Mốc 3: Triển khai Cloudflare Worker cho VIETMAP Route v4 (`vehicle=motorcycle`)

1. Đăng ký khóa API dùng thử miễn phí tại [VIETMAP Maps API Console](https://maps.vietmap.vn/docs/map-api/console/register-api-key/).
2. Trên máy Windows, mở PowerShell tại thư mục `backend-worker`:
   ```powershell
   cd c:\Users\lenovo\project\g-navigation\backend-worker
   npm install
   npx wrangler login
   ```
3. Cất khóa API VIETMAP an toàn vào Cloudflare Secret (không lưu khóa trong mã nguồn):
   ```powershell
   npx wrangler secret put VIETMAP_API_KEY
   ```
4. Triển khai Worker lên mạng lưới Cloudflare miễn phí (100.000 request/ngày):
   ```powershell
   npm run deploy
   ```
5. Sao chép đường dẫn `https://g-navigation-worker.<ten-cua-ban>.workers.dev` vừa nhận được, mở app **G Navigation** trên iPhone → vào tab **`Cấu hình & Log`** → dán vào ô **URL Worker** và bấm **Lưu cấu hình**.
   - *(Lưu ý)*: Ngay cả khi bạn chưa kịp deploy Worker hoặc chưa có khóa VIETMAP, ứng dụng iPhone và Worker đều đã có sẵn chế độ dự phòng tự động qua **OpenStreetMap / OSRM** để bạn thử nghiệm tìm đường 0 đồng ngay lập tức.

---

## Mốc 4: Danh sách kiểm tra 3 chuyến đi thực tế (20–30 phút)

- [ ] **Chuyến 1 (Khóa màn hình iPhone ≥ 15 phút)**: Bắt đầu dẫn đường trên iPhone, khóa màn hình bỏ vào túi quần/balo. Kiểm tra Fit 4 Pro vẫn cập nhật khoảng cách tới ngã rẽ và rung 2 nhịp ở mốc 100m, rung nhịp dài ở mốc 30m.
- [ ] **Chuyến 2 (Cố tình đi lệch tuyến > 45m)**: Rẽ sang một nhánh đường khác. Kiểm tra sau ~2 nhịp GPS (khoảng 3–5 giây), đồng hồ rung 3 nhịp cảnh báo, hiển thị thẻ màu cam **`Lệch tuyến · Đang tính lại đường...`** và vẽ lại đường đi mới.
- [ ] **Chuyến 3 (Ngắt rồi nối lại Bluetooth)**: Tắt Bluetooth trên iPhone (hoặc để xa đồng hồ) quá **12 giây**. Kiểm tra đồng hồ tự động chuyển sang trạng thái **`⚠ Mất dữ liệu từ iPhone · Đã ẩn chỉ dẫn cũ`**. Sau đó bật lại Bluetooth (hoặc bấm nút *Đồng bộ lại đồng hồ*) để xác nhận đồng hồ tự nhận lại tuyến đường và trạng thái mới nhất.
