import { useState, useSyncExternalStore } from 'react';
import { LibraryIcon } from '../features/library/LibraryIcon';
import type { TelegramPlatform } from '../platform/telegram/TelegramPlatformAdapter';
import { telegramProfile } from '../features/library/catalog';

const weekdays = ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс'];
export function ProfilePage({ platform }: { platform: TelegramPlatform }) {
  const isTelegram = useSyncExternalStore(platform.subscribeBackButton, platform.getTelegramContextSnapshot, () => false);
  const { name, photoUrl } = isTelegram ? telegramProfile(window.Telegram?.WebApp) : { name: null, photoUrl: null };
  const [failedPhoto, setFailedPhoto] = useState<string | null>(null);
  const initials = name?.split(/\s+/).slice(0, 2).map(part => Array.from(part)[0]).join('').toLocaleUpperCase('ru');
  return <section className="profile-page library-page" aria-labelledby="profile-title">
    <header className="library-heading"><p className="eyebrow">Ваш путь в медицине</p><h1 id="profile-title">Профиль</h1></header>
    <section className="profile-identity" aria-label="Данные профиля">
      <div className="profile-identity__top"><span className="profile-avatar" aria-hidden="true">{photoUrl && failedPhoto !== photoUrl ? <img src={photoUrl} alt="" loading="lazy" referrerPolicy="no-referrer" onError={() => setFailedPhoto(photoUrl)} /> : initials || <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"><circle cx="12" cy="8" r="4" /><path d="M4 22v-3a8 8 0 0 1 16 0v3" /></svg>}</span><div><h2>{name || 'Ваш профиль'}</h2><p>{name ? 'ANATOMAI' : 'Имя пока недоступно'}</p></div></div>
      <p className="profile-data-note">Уровень и XP пока недоступны.</p>
    </section>
    <section className="profile-week" aria-labelledby="week-title"><div className="library-section-title"><h2 id="week-title">Активность</h2><span>За неделю</span></div><ol>{weekdays.map(day => <li key={day}><span>{day}</span><i aria-label={`${day}: нет данных`}>—</i></li>)}</ol><p className="profile-data-note">Нет данных об активности за эту неделю.</p></section>
    <div className="library-section-title"><h2>Статистика</h2></div>
    <dl className="profile-stats">{([['Средний результат', 'percent'], ['Пройденные тесты', 'check'], ['Серия активности', 'activity'], ['Ответов на вопросы', 'list']] as const).map(([label, icon]) => <div key={label}><span className="profile-stat-icon" aria-hidden="true"><LibraryIcon name={icon} /></span><dd aria-label={`${label}: нет данных`}>—</dd><dt>{label}</dt></div>)}</dl>
    <section className="profile-history"><div className="library-section-title"><h2>История тестов</h2></div><div className="library-empty"><strong>Пока нет результатов</strong><p>История тестов пока недоступна.</p></div></section>
  </section>;
}
