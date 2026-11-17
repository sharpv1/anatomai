export type AppRoute = 'home' | 'tests' | 'notes' | 'profile';

type BottomNavigationProps = { active: AppRoute; onChange: (route: AppRoute) => void; hidden?: boolean };

const items: Array<{ route: AppRoute; icon: string; label: string }> = [
  { route: 'home', icon: '⌂', label: 'Главная' },
  { route: 'tests', icon: '◫', label: 'Тесты' },
  { route: 'notes', icon: '▤', label: 'Конспекты' },
  { route: 'profile', icon: '◉', label: 'Профиль' },
];

export function BottomNavigation({ active, onChange, hidden = false }: BottomNavigationProps) {
  return (
    <nav className={`bottom-nav ${hidden ? 'bottom-nav--hidden' : ''}`} aria-label="Основная навигация">
      {items.map((item) => (
        <button className={`nav-item ${active === item.route ? 'active' : ''}`} key={item.route} onClick={() => onChange(item.route)}>
          <span>{item.icon}</span>{item.label}
        </button>
      ))}
    </nav>
  );
}
