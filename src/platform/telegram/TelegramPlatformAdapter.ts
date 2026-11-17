export type TelegramPlatform = {
  isTelegram: boolean;
  ready(): void;
  expand(): void;
  requestFullscreen(): boolean;
  exitFullscreen(): void;
  showBackButton(onClick: () => void): void;
  hideBackButton(): void;
  hapticSelection(): void;
  hapticImpact(): void;
};

const root = document.documentElement;
const telegram = window.Telegram?.WebApp;

function setPixel(name: string, value: number | undefined) {
  root.style.setProperty(name, `${Math.max(0, value ?? 0)}px`);
}

function syncTelegramMetrics() {
  if (!telegram) return;
  const safe = telegram.safeAreaInset ?? {};
  const content = telegram.contentSafeAreaInset ?? {};
  setPixel('--tg-safe-top', safe.top);
  setPixel('--tg-safe-bottom', safe.bottom);
  setPixel('--tg-safe-left', safe.left);
  setPixel('--tg-safe-right', safe.right);
  setPixel('--tg-content-top', content.top);
  setPixel('--tg-content-bottom', content.bottom);
  setPixel('--tg-content-left', content.left);
  setPixel('--tg-content-right', content.right);
  setPixel('--tg-viewport-height', telegram.viewportHeight ?? window.innerHeight);
  setPixel('--tg-viewport-stable-height', telegram.viewportStableHeight ?? telegram.viewportHeight ?? window.innerHeight);
}

export function createTelegramPlatformAdapter(): TelegramPlatform {
  const adapter: TelegramPlatform = {
    isTelegram: Boolean(telegram),
    ready: () => telegram?.ready(),
    expand: () => telegram?.expand(),
    requestFullscreen: () => {
      if (!telegram?.requestFullscreen) return false;
      try {
        telegram.requestFullscreen();
        return true;
      } catch {
        return false;
      }
    },
    exitFullscreen: () => telegram?.exitFullscreen?.(),
    showBackButton: (onClick) => {
      telegram?.BackButton?.show();
      telegram?.BackButton?.onClick(onClick);
    },
    hideBackButton: () => telegram?.BackButton?.hide(),
    hapticSelection: () => telegram?.HapticFeedback?.selectionChanged?.(),
    hapticImpact: () => telegram?.HapticFeedback?.impactOccurred?.('light'),
  };

  if (telegram) {
    telegram.ready();
    telegram.expand();
    telegram.setHeaderColor?.('#f5f7fb');
    telegram.setBackgroundColor?.('#f5f7fb');
    telegram.setBottomBarColor?.('#ffffff');
    telegram.disableVerticalSwipes?.();
    syncTelegramMetrics();
    telegram.onEvent?.('viewportChanged', syncTelegramMetrics);
    telegram.onEvent?.('safeAreaChanged', syncTelegramMetrics);
    telegram.onEvent?.('contentSafeAreaChanged', syncTelegramMetrics);
    window.addEventListener('resize', syncTelegramMetrics, { passive: true });
  }

  return adapter;
}
