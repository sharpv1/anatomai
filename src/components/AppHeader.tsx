import type {TelegramPlatform} from '../platform/telegram/TelegramPlatformAdapter';
import {useTelegramIdentity} from '../features/library/useTelegramIdentity';
type AppHeaderProps = { onNotifications: () => void; platform: TelegramPlatform };

export function AppHeader({ onNotifications, platform }: AppHeaderProps) {
  const {name}=useTelegramIdentity(platform);
  const initials=name?.split(/\s+/).slice(0,2).map(s=>Array.from(s)[0]).join('')||'А';
  return (
    <header className="topbar">
      <div className="greeting">
        <div className="avatar" aria-hidden="true">{initials}</div>
        <div>
          <p className="eyebrow">{new Date().toLocaleDateString('ru',{weekday:'long',day:'numeric',month:'long'})}</p>
          <h1>{name?`Привет, ${name.split(' ')[0]} 👋`:'Добро пожаловать 👋'}</h1>
        </div>
      </div>
      <button className="icon-btn" aria-label="Уведомления" onClick={onNotifications}>
        <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M18 8a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9" /><path d="M10 21h4" /></svg>
      </button>
    </header>
  );
}
