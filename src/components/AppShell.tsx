import { useEffect, useLayoutEffect, useRef, type ReactNode } from 'react';
import { attachZoomLock } from '../platform/telegram/zoomLock';
import type { AppRoute } from './BottomNavigation';
import { BottomNavigation } from './BottomNavigation';

type AppShellProps = { children: ReactNode; route: AppRoute; onRouteChange: (route: AppRoute) => void; toast: string; onCloseToast: () => void; hideNavigation?: boolean };

export function AppShell({ children, route, onRouteChange, toast, onCloseToast, hideNavigation = false }: AppShellProps) {
  const shellRef = useRef<HTMLElement>(null);
  useEffect(() => { if (shellRef.current) return attachZoomLock(shellRef.current); }, []);
  const contentRef = useRef<HTMLDivElement>(null);
  const scrollPositions = useRef<Partial<Record<AppRoute, number>>>({});
  useLayoutEffect(() => { contentRef.current?.scrollTo(0, hideNavigation ? 0 : scrollPositions.current[route] ?? 0); }, [route, hideNavigation]);
  return <main ref={shellRef} className={`shell${hideNavigation ? ' shell--test-flow' : ''}`}><div className="shell__viewport"><div className="shell__content" ref={contentRef} onScroll={(event) => { if (!hideNavigation) scrollPositions.current[route] = event.currentTarget.scrollTop; }}>{children}</div></div><BottomNavigation active={route} onChange={onRouteChange} hidden={hideNavigation} />{toast && <button className="toast show" onClick={onCloseToast}>{toast}</button>}</main>;
}
