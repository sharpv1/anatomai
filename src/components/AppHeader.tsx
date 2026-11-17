type AppHeaderProps = { onNotifications: () => void };

export function AppHeader({ onNotifications }: AppHeaderProps) {
  return (
    <header className="topbar">
      <div className="greeting">
        <div className="avatar">АИ</div>
        <div>
          <p className="eyebrow">Понедельник, 16 ноября</p>
          <h1>Привет, Айдана 👋</h1>
        </div>
      </div>
      <button className="icon-btn" aria-label="Уведомления" onClick={onNotifications}>
        <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M18 8a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9" /><path d="M10 21h4" /></svg>
      </button>
    </header>
  );
}
