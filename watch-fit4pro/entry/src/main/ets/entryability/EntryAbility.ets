import UIAbility from '@ohos.app.ability.UIAbility';
import hilog from '@ohos.hilog';
import window from '@ohos.window';
import AbilityConstant from '@ohos.app.ability.AbilityConstant';
import Want from '@ohos.app.ability.Want';

export default class EntryAbility extends UIAbility {
  onCreate(want: Want, launchParam: AbilityConstant.LaunchParam): void {
    hilog.info(0x0000, 'GNavWatch', '%{public}s', 'EntryAbility onCreate');
  }

  onDestroy(): void {
    hilog.info(0x0000, 'GNavWatch', '%{public}s', 'EntryAbility onDestroy');
  }

  onWindowStageCreate(windowStage: window.WindowStage): void {
    hilog.info(0x0000, 'GNavWatch', '%{public}s', 'EntryAbility onWindowStageCreate');

    // Giữ màn hình đồng hồ sáng hoặc luôn hiển thị khi đang dẫn đường xe máy
    windowStage.getMainWindow((err, mainWindow) => {
      if (!err && mainWindow) {
        try {
          mainWindow.setWindowKeepScreenOn(true);
        } catch (e) {
          hilog.warn(0x0000, 'GNavWatch', 'setWindowKeepScreenOn failed: %{public}s', JSON.stringify(e));
        }
      }
    });

    windowStage.loadContent('pages/Index', (err) => {
      if (err.code) {
        hilog.error(0x0000, 'GNavWatch', 'Failed to load content. Cause: %{public}s', JSON.stringify(err));
        return;
      }
      hilog.info(0x0000, 'GNavWatch', 'Succeeded in loading pages/Index.');
    });
  }

  onWindowStageDestroy(): void {
    hilog.info(0x0000, 'GNavWatch', '%{public}s', 'EntryAbility onWindowStageDestroy');
  }
}
