import { useState, useSyncExternalStore } from 'react';
import { LibraryIcon } from '../features/library/LibraryIcon';
import type { TelegramPlatform } from '../platform/telegram/TelegramPlatformAdapter';
import { telegramProfile } from '../features/library/catalog';

export function ProfilePage({ platform, onProgress, onTests }: { platform: TelegramPlatform; onProgress: () => void; onTests: () => void }) {
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
    <div className="library-section-title"><h2>Достижения</h2><span>Скоро</span></div>
    <div className="library-empty" aria-disabled="true"><strong>Учебные достижения</strong><p>Функция пока недоступна.</p></div>
    <div className="library-section-title"><h2>Доступ</h2></div>
    <button className="profile-action" onClick={onTests}><LibraryIcon name="practice" /><span><strong>Практика</strong><small>Обучение и экзамен</small></span><b>›</b></button>
    <div className="library-section-title"><h2>Мои данные</h2></div>
    <button className="profile-action" onClick={onProgress}><LibraryIcon name="activity" /><span><strong>Мой прогресс</strong><small>Статистика текущей сессии</small></span><b>›</b></button>
    <div className="library-section-title"><h2>Настройки</h2><span>Скоро</span></div><div className="library-empty" aria-disabled="true"><strong>Напоминания и учебные цели</strong><p>Пока недоступны. Подписки и покупки не подключены.</p></div>
  </section>;
}
