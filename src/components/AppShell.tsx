import type { ReactNode } from 'react';
import type { AppRoute } from './BottomNavigation';
import { BottomNavigation } from './BottomNavigation';

type AppShellProps = { children: ReactNode; route: AppRoute; onRouteChange: (route: AppRoute) => void; toast: string; onCloseToast: () => void; hideNavigation?: boolean };

export function AppShell({ children, route, onRouteChange, toast, onCloseToast, hideNavigation = false }: AppShellProps) {
  return <main className={`shell${hideNavigation ? ' shell--test-flow' : ''}`}>{children}<BottomNavigation active={route} onChange={onRouteChange} hidden={hideNavigation} />{toast && <button className="toast show" onClick={onCloseToast}>{toast}</button>}</main>;
}
