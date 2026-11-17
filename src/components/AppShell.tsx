import { useLayoutEffect, useRef, type ReactNode } from 'react';
import type { AppRoute } from './BottomNavigation';
import { BottomNavigation } from './BottomNavigation';

type AppShellProps = { children: ReactNode; route: AppRoute; onRouteChange: (route: AppRoute) => void; toast: string; onCloseToast: () => void; hideNavigation?: boolean };

export function AppShell({ children, route, onRouteChange, toast, onCloseToast, hideNavigation = false }: AppShellProps) {
  const contentRef = useRef<HTMLDivElement>(null);
  useLayoutEffect(() => { contentRef.current?.scrollTo(0, 0); }, [route, hideNavigation]);
  return <main className={`shell${hideNavigation ? ' shell--test-flow' : ''}`}><div className="shell__viewport"><div className="shell__content" ref={contentRef}>{children}</div></div><BottomNavigation active={route} onChange={onRouteChange} hidden={hideNavigation} />{toast && <button className="toast show" onClick={onCloseToast}>{toast}</button>}</main>;
}
