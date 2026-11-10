import Foundation

/// Cấu hình trung tâm của ứng dụng G Navigation trên iPhone.
/// Người dùng có thể chỉnh sửa trực tiếp trong tab "Cấu hình" trên iPhone mà không cần build lại IPA.
struct AppConfig {
    private static let defaults = UserDefaults.standard

    /// URL của Cloudflare Worker (Mốc 3)
    static var workerBaseURL: String {
        get { defaults.string(forKey: "cfg_worker_url") ?? "https://g-navigation-worker.YOUR-SUBDOMAIN.workers.dev" }
        set { defaults.set(newValue.trimmingCharacters(in: .whitespacesAndNewlines), forKey: "cfg_worker_url") }
    }

    /// Token bảo mật tùy chọn gửi kèm header `X-Client-Token` tới Cloudflare Worker
    static var workerClientToken: String {
        get { defaults.string(forKey: "cfg_worker_token") ?? "" }
        set { defaults.set(newValue.trimmingCharacters(in: .whitespacesAndNewlines), forKey: "cfg_worker_token") }
    }

    /// Bundle Name của ứng dụng đồng hồ trên Fit 4 Pro (`AppScope/app.json5`)
    static var watchPeerBundleName: String {
        get { defaults.string(forKey: "cfg_watch_bundle") ?? "com.gnavigation.watch" }
        set { defaults.set(newValue.trimmingCharacters(in: .whitespacesAndNewlines), forKey: "cfg_watch_bundle") }
    }

    /// App ID / Fingerprint của ứng dụng đồng hồ đăng ký trên Huawei Developer
    static var watchPeerFingerprint: String {
        get { defaults.string(forKey: "cfg_watch_fingerprint") ?? "com.gnavigation.watch" }
        set { defaults.set(newValue.trimmingCharacters(in: .whitespacesAndNewlines), forKey: "cfg_watch_fingerprint") }
    }

    /// Callback URL Scheme đã đăng ký trong Info.plist và trên Huawei Wear Engine Console
    static var callbackURLScheme: String {
        get { defaults.string(forKey: "cfg_callback_scheme") ?? "gnavigation://wearengine" }
        set { defaults.set(newValue.trimmingCharacters(in: .whitespacesAndNewlines), forKey: "cfg_callback_scheme") }
    }

    /// Bundle ID thực tế lúc chạy (rất quan trọng khi cài qua Sideloadly vì Sideloadly có thể thêm hậu tố Team ID)
    static var runtimeBundleIdentifier: String {
        Bundle.main.bundleIdentifier ?? "com.gnavigation.ios"
    }
}
