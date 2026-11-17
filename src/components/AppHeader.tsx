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
        ♧<i className="dot" />
      </button>
    </header>
  );
}
