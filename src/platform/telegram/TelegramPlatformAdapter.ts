export type TelegramPlatform = {
  readonly isTelegram: boolean;
  readonly canUseBackButton: boolean;
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

// Telegram system insets and content insets describe successive areas.
// An explicit SDK zero means that the host has already excluded that edge.
export function resolveInset(system: number | undefined, content: number | undefined, browserFallback = 0): number {
  const valid = (value: number | undefined) => Number.isFinite(value) && value! >= 0;
  return (valid(system) ? system! : Math.max(0, browserFallback)) + (valid(content) ? content! : 0);
}

// Creating the adapter is pure: React StrictMode may call the factory twice.
export function createTelegramPlatformAdapter(): TelegramPlatform {
  let telegram: TelegramWebApp | undefined;
  let initialized = false;
  let backCallback: (() => void) | undefined;
  let backAttached = false;
  let unzoomedViewport: { height: number; offsetTop: number } | undefined;
  const root = () => document.documentElement;
  let subscriptions: typeof events = [];
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
    const safe = supports('8.0') ? telegram?.safeAreaInset : undefined;
    const content = supports('8.0') ? telegram?.contentSafeAreaInset : undefined;
    for (const edge of ['top', 'bottom', 'left', 'right'] as const) {
      pixel(`--tg-safe-${edge}`, safe?.[edge]);
      pixel(`--tg-content-${edge}`, content?.[edge]);
      const system = safe?.[edge];
      const extra = resolveInset(0, content?.[edge]);
      // CSS env is a fallback, not an extra copy of the SDK system inset.
      const value = Number.isFinite(system) && system! >= 0
        ? `${resolveInset(system, content?.[edge])}px`
        : `calc(env(safe-area-inset-${edge}, 0px) + ${extra}px)`;
      root().style.setProperty(`--app-inset-${edge}`, value);
    }
    const positive = (value: number | undefined) => Number.isFinite(value) && value! > 0 ? value! : Infinity;
    const visual = window.visualViewport;
    const zoomed = Math.abs((visual?.scale ?? 1) - 1) > 0.01;
    if (!zoomed && visual) unzoomedViewport = { height: visual.height, offsetTop: visual.offsetTop ?? 0 };
    // Pinch zoom is intentional accessibility input, not a keyboard/layout resize.
    const height = Math.min(positive(telegram?.viewportHeight), positive(unzoomedViewport?.height), positive(window.innerHeight));
    pixel('--tg-viewport-height', Number.isFinite(height) ? height : 0);
    pixel('--tg-viewport-stable-height', telegram?.viewportStableHeight || height);
    pixel('--app-viewport-offset-top', unzoomedViewport?.offsetTop);
    root().dataset.anatomaiViewport = 'true';
    root().dataset.telegramFullscreen = String(Boolean(telegram?.isFullscreen));
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
    get canUseBackButton() { return Boolean(telegram?.BackButton && typeof telegram.BackButton.onClick === 'function' && typeof telegram.BackButton.offClick === 'function' && typeof telegram.BackButton.show === 'function' && typeof telegram.BackButton.hide === 'function' && supports('6.1')); },
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
        subscriptions = events.filter(([event]) => event === 'viewportChanged' || supports('8.0'));
        for (const [event, callback] of subscriptions) telegram.onEvent(event, callback);
      }
      window.addEventListener('resize', sync, { passive: true });
      window.visualViewport?.addEventListener('resize', sync, { passive: true });
      window.visualViewport?.addEventListener('scroll', sync, { passive: true });
      document.addEventListener('visibilitychange', sync);
      sync();
      attachBack();
    },
    dispose() {
      if (!initialized) return;
      detachBack();
      backCallback = undefined;
      for (const [event, callback] of subscriptions) telegram?.offEvent?.(event, callback);
      subscriptions = [];
      window.removeEventListener('resize', sync);
      window.visualViewport?.removeEventListener('resize', sync);
      window.visualViewport?.removeEventListener('scroll', sync);
      document.removeEventListener('visibilitychange', sync);
      telegram = undefined;
      unzoomedViewport = undefined;
      initialized = false;
      for (const edge of ['top', 'bottom', 'left', 'right']) {
        root().style.removeProperty(`--tg-safe-${edge}`);
        root().style.removeProperty(`--tg-content-${edge}`);
        root().style.removeProperty(`--app-inset-${edge}`);
      }
      for (const name of ['--tg-viewport-height', '--tg-viewport-stable-height', '--app-viewport-offset-top']) root().style.removeProperty(name);
      delete root().dataset.anatomaiViewport;
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
