export type TelegramPlatform = {
  readonly isTelegram: boolean;
  readonly canUseBackButton: boolean;
  getBackButtonSnapshot(): boolean;
  getTelegramContextSnapshot(): boolean;
  subscribeBackButton(listener: () => void): () => void;
  bindBackButton(onClick: () => void): () => void;
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
  let attachedBackButton: TelegramWebApp['BackButton'];
  let backOwner: symbol | undefined;
  let backMonitor: ReturnType<typeof window.setInterval> | undefined;
  let nativeBackVisible = false;
  let telegramContext = false;
  let dispatchingBack = false;
  const backListeners = new Set<() => void>();
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
  const readTelegram = () => {
    const api = window.Telegram?.WebApp;
    // The SDK script also exists in browsers. Require launch data or a known host
    // platform together with the WebApp lifecycle API; this is UI detection, not auth.
    const host = ['ios', 'android', 'android_x', 'tdesktop', 'macos', 'weba', 'webk', 'unigram'].includes(api?.platform ?? '');
    const lifecycle = typeof api?.ready === 'function' && typeof api?.expand === 'function';
    return api && lifecycle && (api.initData?.trim() || host) ? api : undefined;
  };
  const publishBack = () => {
    // isVisible is SDK state, not proof of pixels drawn by the native client.
    const visible = Boolean(initialized && backCallback && backAttached && attachedBackButton === telegram?.BackButton && attachedBackButton?.isVisible === true);
    const context = initialized && Boolean(telegram);
    if (visible === nativeBackVisible && context === telegramContext) return;
    nativeBackVisible = visible;
    telegramContext = context;
    for (const listener of backListeners) listener();
  };
  const backBridge = () => {
    if (dispatchingBack || !backCallback) return;
    dispatchingBack = true;
    try { backCallback(); } finally { queueMicrotask(() => { dispatchingBack = false; }); }
  };
  const detachBack = () => {
    if (backAttached) {
      invoke(() => attachedBackButton?.offClick(backBridge));
      invoke(() => attachedBackButton?.hide());
    }
    backAttached = false;
    attachedBackButton = undefined;
    publishBack();
  };
  const attachBack = () => {
    if (!initialized || !adapter.canUseBackButton || !backCallback) { publishBack(); return; }
    const button = telegram!.BackButton!;
    if (attachedBackButton && attachedBackButton !== button) detachBack();
    try {
      const newAttachment = !backAttached;
      if (newAttachment) {
        button.onClick(backBridge);
        attachedBackButton = button;
        backAttached = true;
      }
      if (newAttachment || button.isVisible !== true) button.show();
    } catch {
      // Registration/show may be rejected by the client. Keep the in-app exit.
      invoke(() => button.offClick(backBridge));
      if (attachedBackButton === button) invoke(() => button.hide());
      backAttached = false;
      attachedBackButton = undefined;
    }
    publishBack();
  };
  const connect = (api: TelegramWebApp | undefined) => {
    let changed = api !== telegram;
    if (api !== telegram) {
      detachBack();
      for (const [event, callback] of subscriptions) telegram?.offEvent?.(event, callback);
      subscriptions = [];
      telegram = api;
      adapter.ready(); adapter.expand();
      invoke(() => telegram?.setHeaderColor?.('#f5f7fb'));
      invoke(() => telegram?.setBackgroundColor?.('#f5f7fb'));
      if (supports('7.10')) invoke(() => telegram?.setBottomBarColor?.('#ffffff'));
      if (supports('7.7')) invoke(() => telegram?.disableVerticalSwipes?.());
    }
    const next = telegram?.onEvent && telegram.offEvent ? events.filter(([event]) => event === 'viewportChanged' || supports('8.0')) : [];
    if (next.map(([name]) => name).join() !== subscriptions.map(([name]) => name).join()) {
      for (const [event, callback] of subscriptions) telegram?.offEvent?.(event, callback);
      subscriptions = next;
      for (const [event, callback] of subscriptions) telegram?.onEvent?.(event, callback);
      changed = true;
    }
    if (changed) sync();
    attachBack();
  };
  const stopBackMonitor = () => { if (backMonitor !== undefined) window.clearInterval(backMonitor); backMonitor = undefined; };
  const startBackMonitor = () => {
    if (!initialized || !backCallback || backMonitor !== undefined) return;
    // BackButton has no visibility-change event. Monitor only while a screen owns it.
    backMonitor = window.setInterval(() => { connect(readTelegram()); }, 250);
  };
  const bind = (callback: () => void) => {
    const owner = Symbol('back-screen'); backOwner = owner; backCallback = callback;
    if (initialized) connect(readTelegram());
    startBackMonitor();
    return () => {
      if (backOwner !== owner) return;
      backOwner = undefined; backCallback = undefined; stopBackMonitor(); detachBack();
    };
  };
  const adapter: TelegramPlatform = {
    get isTelegram() { return Boolean(telegram); },
    get canUseBackButton() { return Boolean(telegram?.BackButton && typeof telegram.BackButton.onClick === 'function' && typeof telegram.BackButton.offClick === 'function' && typeof telegram.BackButton.show === 'function' && typeof telegram.BackButton.hide === 'function' && supports('6.1')); },
    init() {
      if (initialized) return;
      initialized = true;
      connect(readTelegram());
      window.addEventListener('resize', sync, { passive: true });
      window.visualViewport?.addEventListener('resize', sync, { passive: true });
      window.visualViewport?.addEventListener('scroll', sync, { passive: true });
      document.addEventListener('visibilitychange', sync);
      sync();
      attachBack();
      startBackMonitor();
    },
    dispose() {
      if (!initialized) return;
      stopBackMonitor();
      detachBack();
      backOwner = undefined;
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
      publishBack();
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
    getBackButtonSnapshot: () => nativeBackVisible,
    getTelegramContextSnapshot: () => telegramContext,
    subscribeBackButton(listener) { backListeners.add(listener); return () => { backListeners.delete(listener); }; },
    bindBackButton: bind,
    showBackButton(callback) { bind(callback); },
    hideBackButton() { backOwner = undefined; backCallback = undefined; stopBackMonitor(); detachBack(); },
    hapticSelection: () => { if (supports('6.1')) invoke(() => telegram?.HapticFeedback?.selectionChanged?.()); },
    hapticImpact: () => { if (supports('6.1')) invoke(() => telegram?.HapticFeedback?.impactOccurred?.('light')); },
  };
  return adapter;
}
