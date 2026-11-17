export type AppRoute = 'home' | 'tests' | 'notes' | 'profile';

type BottomNavigationProps = { active: AppRoute; onChange: (route: AppRoute) => void; hidden?: boolean };

const items: Array<{ route: AppRoute; icon: string; label: string }> = [
  { route: 'home', icon: 'M3 10 12 3l9 7M5 9v12h5v-7h4v7h5V9', label: 'Главная' },
  { route: 'tests', icon: 'M6 3h12v18H6zM9 8h6M9 12h6M9 16h4', label: 'Тесты' },
  { route: 'notes', icon: 'M4 4h7v16H4zM13 4h7v16h-7', label: 'Конспекты' },
  { route: 'profile', icon: 'M16 7a4 4 0 1 1-8 0 4 4 0 0 1 8 0M4 21v-2a8 8 0 0 1 16 0v2', label: 'Профиль' },
];

export function BottomNavigation({ active, onChange, hidden = false }: BottomNavigationProps) {
  return (
    <nav className={`bottom-nav ${hidden ? 'bottom-nav--hidden' : ''}`} aria-label="Основная навигация">
      <span className="nav-indicator" aria-hidden="true" style={{ transform: `translateX(calc(${items.findIndex(item => item.route === active)} * (100% + 4px)))` }} />
      {items.map((item) => (
        <button className={`nav-item ${active === item.route ? 'active' : ''}`} aria-current={active === item.route ? 'page' : undefined} key={item.route} onClick={() => onChange(item.route)}>
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d={item.icon} /></svg>{item.label}
        </button>
      ))}
    </nav>
  );
}
