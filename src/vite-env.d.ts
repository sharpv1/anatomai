/// <reference types="vite/client" />

interface Window {
  Telegram?: {
    WebApp?: TelegramWebApp;
  };
}

interface TelegramWebApp {
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
  onEvent?: (event: string, callback: () => void) => void;
  BackButton?: {
    show: () => void;
    hide: () => void;
    onClick: (callback: () => void) => void;
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
