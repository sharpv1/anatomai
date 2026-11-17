export type TelegramPlatform = {
  readonly isTelegram: boolean;
  init(): void;
  dispose(): void;
  ready(): void;
  expand(): void;
  requestFullscreen(): boolean;
  exitFullscreen(): void;
  showBackButton(onClick: () => void): void;
  hideBackButton(): void;
  hapticSelection(): void;
  hapticImpact(): void;
};

// Creating the adapter is pure: React StrictMode may call the factory twice.
export function createTelegramPlatformAdapter(): TelegramPlatform {
  let telegram: TelegramWebApp | undefined;
  let initialized = false;
  let backCallback: (() => void) | undefined;
  let backAttached = false;
  const root = () => document.documentElement;
  const invoke = (action: () => void) => { try { action(); } catch { /* Older clients may reject optional API calls. */ } };
  const supports = (version: string) => {
    if (!telegram) return false;
    try {
      if (telegram.isVersionAtLeast) return telegram.isVersionAtLeast(version);
      const actual = (telegram.version ?? '0').split('.').map(Number);
      const required = version.split('.').map(Number);
      return actual[0] > required[0] || (actual[0] === required[0] && (actual[1] ?? 0) >= required[1]);
    } catch { return false; }
  };
  const pixel = (name: string, value: number | undefined) => {
    root().style.setProperty(name, `${Number.isFinite(value) ? Math.max(0, value!) : 0}px`);
  };
  const sync = () => {
    const safe = telegram?.safeAreaInset;
    const content = telegram?.contentSafeAreaInset;
    for (const edge of ['top', 'bottom', 'left', 'right'] as const) {
      pixel(`--tg-safe-${edge}`, safe?.[edge]);
      pixel(`--tg-content-${edge}`, content?.[edge]);
    }
    const height = window.visualViewport?.height ?? window.innerHeight;
    pixel('--tg-viewport-height', telegram?.viewportHeight || height);
    pixel('--tg-viewport-stable-height', telegram?.viewportStableHeight || telegram?.viewportHeight || height);
    const fullscreen = Boolean(telegram?.isFullscreen);
    root().dataset.telegramFullscreen = String(fullscreen);
    // Published UI 4.5 uses max(content.top, safe.top, 104) in fullscreen.
    pixel('--anatomai-top-clearance', fullscreen ? Math.max(content?.top ?? 0, safe?.top ?? 0, 104) : 0);
    root().dataset.telegramFullscreenAvailable = String(Boolean(telegram?.requestFullscreen && supports('8.0')));
  };
  const fullscreenChanged = () => { delete root().dataset.telegramFullscreenError; sync(); };
  const fullscreenFailed: TelegramEventCallback = (event) => {
    root().dataset.telegramFullscreenError = event?.error ?? 'UNKNOWN';
    sync();
  };
  const events: Array<[TelegramEvent, TelegramEventCallback]> = [
    ['viewportChanged', sync], ['safeAreaChanged', sync], ['contentSafeAreaChanged', sync],
    ['fullscreenChanged', fullscreenChanged], ['fullscreenFailed', fullscreenFailed],
  ];
  // A single stable bridge prevents stale React callbacks from accumulating.
  const backBridge = () => backCallback?.();
  const detachBack = () => {
    if (backAttached) invoke(() => telegram?.BackButton?.offClick(backBridge));
    backAttached = false;
    invoke(() => telegram?.BackButton?.hide());
  };
  const attachBack = () => {
    if (!telegram?.BackButton?.onClick || !telegram.BackButton.offClick || !backCallback) return;
    if (!backAttached) {
      telegram.BackButton.onClick(backBridge);
      backAttached = true;
    }
    telegram.BackButton.show();
  };
  const adapter: TelegramPlatform = {
    get isTelegram() { return Boolean(telegram); },
    init() {
      if (initialized) return;
      initialized = true;
      const api = window.Telegram?.WebApp;
      // The SDK also creates WebApp in ordinary browsers; presence alone is insufficient.
      telegram = api && (api.initData || (api.platform && api.platform !== 'unknown')) ? api : undefined;
      adapter.ready();
      adapter.expand();
      invoke(() => telegram?.setHeaderColor?.('#f5f7fb'));
      invoke(() => telegram?.setBackgroundColor?.('#f5f7fb'));
      if (supports('7.10')) invoke(() => telegram?.setBottomBarColor?.('#ffffff'));
      if (supports('7.7')) invoke(() => telegram?.disableVerticalSwipes?.());
      if (telegram?.onEvent && telegram.offEvent) {
        for (const [event, callback] of events) telegram.onEvent(event, callback);
      }
      window.addEventListener('resize', sync, { passive: true });
      window.visualViewport?.addEventListener('resize', sync, { passive: true });
      document.addEventListener('visibilitychange', sync);
      sync();
      attachBack();
    },
    dispose() {
      if (!initialized) return;
      detachBack();
      backCallback = undefined;
      for (const [event, callback] of events) telegram?.offEvent?.(event, callback);
      window.removeEventListener('resize', sync);
      window.visualViewport?.removeEventListener('resize', sync);
      document.removeEventListener('visibilitychange', sync);
      telegram = undefined;
      initialized = false;
      for (const edge of ['top', 'bottom', 'left', 'right']) {
        root().style.removeProperty(`--tg-safe-${edge}`);
        root().style.removeProperty(`--tg-content-${edge}`);
      }
      for (const name of ['--tg-viewport-height', '--tg-viewport-stable-height', '--anatomai-top-clearance']) root().style.removeProperty(name);
      delete root().dataset.telegramFullscreen;
      delete root().dataset.telegramFullscreenAvailable;
      delete root().dataset.telegramFullscreenError;
    },
    ready: () => invoke(() => telegram?.ready()),
    expand: () => invoke(() => telegram?.expand()),
    requestFullscreen() {
      if (!telegram?.requestFullscreen || !supports('8.0')) return false;
      delete root().dataset.telegramFullscreenError;
      try { telegram.requestFullscreen(); return true; }
      catch { fullscreenFailed({ error: 'REQUEST_FAILED' }); return false; }
    },
    exitFullscreen: () => { if (supports('8.0')) invoke(() => telegram?.exitFullscreen?.()); },
    showBackButton(callback) { backCallback = callback; attachBack(); },
    hideBackButton() { backCallback = undefined; detachBack(); },
    hapticSelection: () => { if (supports('6.1')) invoke(() => telegram?.HapticFeedback?.selectionChanged?.()); },
    hapticImpact: () => { if (supports('6.1')) invoke(() => telegram?.HapticFeedback?.impactOccurred?.('light')); },
  };
  return adapter;
}
