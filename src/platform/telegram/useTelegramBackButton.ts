import { useCallback, useEffect, useLayoutEffect, useRef, useSyncExternalStore } from 'react';
import type { TelegramPlatform } from './TelegramPlatformAdapter';

/** A screen owns one native callback and a reactive host-context snapshot. */
export function useTelegramBackButton(platform: TelegramPlatform, onBack: () => void, enabled = true, listenPopstate = true) {
  const latest = useRef(onBack);
  const dispatching = useRef(false);
  useLayoutEffect(() => { latest.current = onBack; }, [onBack]);
  const requestBack = useCallback(() => {
    if (dispatching.current) return;
    dispatching.current = true;
    try { latest.current(); } finally { queueMicrotask(() => { dispatching.current = false; }); }
  }, []);
  // Telegram client chrome can provide Back without mirroring BackButton.isVisible.
  const isTelegramContext = useSyncExternalStore(platform.subscribeBackButton, platform.getTelegramContextSnapshot, () => false);
  useEffect(() => {
    if (!enabled) return;
    const release = platform.bindBackButton(requestBack);
    if (listenPopstate) window.addEventListener('popstate', requestBack);
    return () => { release(); window.removeEventListener('popstate', requestBack); };
  }, [platform, requestBack, enabled, listenPopstate]);
  return { isTelegramContext, requestBack };
}
