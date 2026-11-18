import { useCallback, useEffect, useLayoutEffect, useRef, useSyncExternalStore } from 'react';
import type { TelegramPlatform } from './TelegramPlatformAdapter';

/** A screen owns one native callback and a reactive, conservative visibility snapshot. */
export function useTelegramBackButton(platform: TelegramPlatform, onBack: () => void) {
  const latest = useRef(onBack);
  const dispatching = useRef(false);
  useLayoutEffect(() => { latest.current = onBack; }, [onBack]);
  const requestBack = useCallback(() => {
    if (dispatching.current) return;
    dispatching.current = true;
    try { latest.current(); } finally { queueMicrotask(() => { dispatching.current = false; }); }
  }, []);
  const nativeVisible = useSyncExternalStore(platform.subscribeBackButton, platform.getBackButtonSnapshot, () => false);
  useEffect(() => {
    const release = platform.bindBackButton(requestBack);
    window.addEventListener('popstate', requestBack);
    return () => { release(); window.removeEventListener('popstate', requestBack); };
  }, [platform, requestBack]);
  return { nativeVisible, requestBack };
}
