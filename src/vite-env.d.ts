/// <reference types="vite/client" />

interface Window {
  Telegram?: {
    WebApp?: TelegramWebApp;
  };
}

type TelegramEvent = 'viewportChanged' | 'safeAreaChanged' | 'contentSafeAreaChanged' | 'fullscreenChanged' | 'fullscreenFailed';
type TelegramEventCallback = (event?: { error?: string; isStateStable?: boolean }) => void;

interface TelegramWebApp {
  initData?: string;
  platform?: string;
  version?: string;
  isVersionAtLeast?: (version: string) => boolean;
  ready: () => void;
  expand: () => void;
  requestFullscreen?: () => void;
  exitFullscreen?: () => void;
  isFullscreen?: boolean;
  viewportHeight?: number;
  viewportStableHeight?: number;
  safeAreaInset?: TelegramInsets;
  contentSafeAreaInset?: TelegramInsets;
  setHeaderColor?: (color: string) => void;
  setBackgroundColor?: (color: string) => void;
  setBottomBarColor?: (color: string) => void;
  disableVerticalSwipes?: () => void;
  onEvent?: (event: TelegramEvent, callback: TelegramEventCallback) => void;
  offEvent?: (event: TelegramEvent, callback: TelegramEventCallback) => void;
  BackButton?: {
    show: () => void;
    hide: () => void;
    onClick: (callback: () => void) => void;
    offClick: (callback: () => void) => void;
  };
  HapticFeedback?: {
    selectionChanged?: () => void;
    impactOccurred?: (style: 'light' | 'medium' | 'heavy' | 'rigid' | 'soft') => void;
  };
}

interface TelegramInsets {
  top?: number;
  bottom?: number;
  left?: number;
  right?: number;
}
