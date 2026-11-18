import { useState, useSyncExternalStore } from 'react';
import type { TelegramPlatform } from '../platform/telegram/TelegramPlatformAdapter';
import { telegramProfile } from '../features/library/catalog';
import { profileAchievements, sessionStreak } from '../features/library/achievements';
import { ProfileIcon } from '../features/library/ProfileIcon';
import type { CompletedTest } from '../features/library/statistics';
import '../styles/profile-7.3.css';
export function ProfilePage({platform,entries,onReset}:{platform:TelegramPlatform;entries:CompletedTest[];onReset:()=>void}){
 const isTelegram=useSyncExternalStore(platform.subscribeBackButton,platform.getTelegramContextSnapshot,()=>false);
 const {name,photoUrl}=isTelegram?telegramProfile(window.Telegram?.WebApp):{name:null,photoUrl:null};
 const [failedPhoto,setFailedPhoto]=useState<string|null>(null);
 const initials=name?.split(/\s+/).slice(0,2).map(s=>Array.from(s)[0]).join('').toLocaleUpperCase('ru');
 const streak=sessionStreak(entries);
 return <section className="profile-page library-page radix-profile" aria-label="Профиль">
  <header className="rp-user"><span className="rp-avatar" aria-hidden="true">{photoUrl&&failedPhoto!==photoUrl?<img src={photoUrl} alt="" loading="lazy" referrerPolicy="no-referrer" onError={()=>setFailedPhoto(photoUrl)}/>:initials||<ProfileIcon name="book"/>}</span><h1>{name||'Ваш профиль'}</h1><div className="rp-indicators"><span aria-label={`Серия активности: ${streak===null?'нет данных':streak}`}><ProfileIcon name="flame"/>{streak??'—'}</span><span aria-label="XP: нет данных"><ProfileIcon name="bolt"/>—</span></div></header>
  <h2 className="rp-section">Достижения</h2><ul className="rp-achievements">{profileAchievements(entries).map(a=><li key={a.id} className={`rp-achievement ${a.unlocked?'is-unlocked':'is-locked'}`} aria-label={`${a.title}: ${a.unlocked?'получено в этой сессии':'заблокировано'}`}><span className="rp-achievement-icon"><ProfileIcon name={a.icon}/></span><strong>{a.title}</strong><small>{a.caption}</small></li>)}</ul>
  <p className="rp-note">Достижения и серия — по результатам текущей сессии. Условия учебных блоков и маршрута пока недоступны.</p>
  <h2 className="rp-section">Доступ</h2><div className="rp-row rp-access"><ProfileIcon name="book"/><div><strong>Бесплатный доступ</strong><p>Тесты в режимах обучения и экзамена. Просмотр статистики текущей сессии.</p></div></div>
  <div className="rp-row rp-muted" aria-disabled="true"><ProfileIcon name="star"/><div><strong>Premium</strong><small>Платные функции не подключены</small></div><span className="rp-status">Недоступно</span></div>
  <h2 className="rp-section">Прогресс</h2><div className="rp-row"><ProfileIcon name="progress"/><div><strong>Текущая сессия</strong><p>Результаты хранятся в памяти до перезагрузки. Синхронизации с аккаунтом нет.</p></div></div>
  {entries.length>0&&<><h2 className="rp-section">Настройки</h2><button className="rp-row rp-reset" onClick={()=>{if(window.confirm('Сбросить результаты текущей сессии и достижения? Отменить это действие нельзя.'))onReset();}}><ProfileIcon name="trash"/><strong>Сбросить прогресс</strong></button></>}
 </section>;
}
