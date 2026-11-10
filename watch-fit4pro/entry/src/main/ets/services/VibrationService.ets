import vibrator from '@ohos.vibrator';
import hilog from '@ohos.hilog';

/**
 * Dịch vụ điều khiển mô-tơ rung trên Huawei Watch Fit 4 Pro
 * - Code 1: Sắp tới khúc rẽ (~100m) -> 2 nhịp ngắn
 * - Code 2: Rẽ ngay (~30m) -> 1 nhịp dài + 1 nhịp dứt khoát
 * - Code 3: Đi lệch tuyến / Đang tính lại đường -> 3 nhịp cảnh báo
 */
export class VibrationService {
  private static lastVibSeq: number = -1;

  static triggerByPacket(seq: number, vibCode: number): void {
    if (vibCode <= 0 || seq === VibrationService.lastVibSeq) {
      return;
    }
    VibrationService.lastVibSeq = seq;
    VibrationService.triggerCode(vibCode);
  }

  static triggerCode(vibCode: number): void {
    if (vibCode === 1) {
      // Sắp rẽ (100m): 2 nhịp 140ms
      VibrationService.vibrateDuration(140);
      setTimeout(() => {
        VibrationService.vibrateDuration(140);
      }, 240);
    } else if (vibCode === 2) {
      // Rẽ ngay (30m): 1 nhịp mạnh 320ms + 1 nhịp 180ms
      VibrationService.vibrateDuration(320);
      setTimeout(() => {
        VibrationService.vibrateDuration(180);
      }, 420);
    } else if (vibCode === 3) {
      // Đi lệch tuyến / Reroute: 3 nhịp nhanh 110ms
      VibrationService.vibrateDuration(110);
      setTimeout(() => {
        VibrationService.vibrateDuration(110);
      }, 190);
      setTimeout(() => {
        VibrationService.vibrateDuration(220);
      }, 380);
    }
  }

  private static vibrateDuration(durationMs: number): void {
    try {
      vibrator.startVibration(
        {
          type: 'time',
          duration: durationMs
        },
        {
          id: 0,
          usage: 'notification'
        }
      );
    } catch (e) {
      hilog.warn(0x0000, 'GNavWatch', 'Vibrator fallback/simulator: %{public}s', JSON.stringify(e));
    }
  }
}
