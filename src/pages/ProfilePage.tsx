import type {User,Summary,Progress,Achievement} from '../backend/contracts';
import {identity} from '../backend/presentation';
import { useState } from 'react';
import type { TelegramPlatform } from '../platform/telegram/TelegramPlatformAdapter';
import {useTelegramIdentity} from '../features/library/useTelegramIdentity';
import { sessionStreak } from '../features/library/achievements';
import { ProfileIcon } from '../features/library/ProfileIcon';
import type { CompletedTest } from '../features/library/statistics';
import '../styles/profile-7.3.css';
import { PremiumDialog } from '../features/library/PremiumDialog';
const information = {
 settings: {label:'Настройки',status:'Недоступно',text:'Параметры пока недоступны. При наличии результатов можно очистить данные текущего запуска.'},
 notifications: {label:'Уведомления',status:'Не подключены',text:'Уведомления пока не подключены. Разрешения не запрашиваются, отправка сообщений не включается.'},
 support: {label:'Помощь и поддержка',status:'Справка',text:'Для практики выберите дисциплину и режим обучения или экзамена. Результаты доступны через «Подробнее» на Главной до перезагрузки приложения. Канал связи с поддержкой пока не настроен.'},
 about: {label:'О приложении',status:'UI 7.8',text:'ANATOMAI — медицинское учебное Telegram Mini App. Версия интерфейса 7.8. Платежи и серверная синхронизация результатов не подключены.'},
} as const;
export function ProfilePage({platform,entries,onReset,server}:{platform:TelegramPlatform;entries:CompletedTest[];onReset:()=>void;server?:{user:User;statistics:Summary;progress:Progress;achievements:Achievement[]}}){
 const local=useTelegramIdentity(platform);const {name,photoUrl}=server?identity(server.user):local;
 const [failedPhoto,setFailedPhoto]=useState<string|null>(null);
 const initials=name?.split(/\s+/).slice(0,2).map(s=>Array.from(s)[0]).join('').toLocaleUpperCase('ru');
 const streak=server?server.statistics.activity_streak_days:sessionStreak(entries);
 const [panel,setPanel]=useState<'premium'|keyof typeof information|null>(null);
 const openPanel=(next:NonNullable<typeof panel>)=>{window.history.pushState({profilePanel:next},'',`#profile-${next}`);setPanel(next);};
 const closePanel=()=>{if(panel&&window.location.hash===`#profile-${panel}`)window.history.back();else setPanel(null);};
 return <section className="profile-page library-page radix-profile" aria-label="Профиль">
  <header className="rp-user"><span className="rp-avatar" aria-hidden="true">{photoUrl&&failedPhoto!==photoUrl?<img src={photoUrl} alt="" loading="lazy" referrerPolicy="no-referrer" onError={()=>setFailedPhoto(photoUrl)}/>:initials||<ProfileIcon name="book"/>}</span><div className="rp-user-copy"><h1 dir="auto">{name||'Ваш профиль'}</h1><small>{name?'Telegram':'Имя пока недоступно'}</small></div>{streak!==null&&<div className="rp-indicators"><span aria-label={`Серия активности: ${streak===null?'нет данных':streak}`}><ProfileIcon name="flame"/>{streak??'—'}</span></div>}</header>
  <button className="profile-premium-row" onClick={()=>openPanel('premium')}><ProfileIcon name="crown"/><span><strong>ANATOMAI Premium</strong><small>Расширенные возможности — скоро</small></span><b aria-hidden="true">›</b></button>
  <nav className="rp-menu" aria-label="Разделы профиля">{(Object.keys(information) as Array<keyof typeof information>).map(key=><button key={key} onClick={()=>openPanel(key)}><span>{information[key].label}</span><small>{information[key].status}</small><b aria-hidden="true">›</b></button>)}</nav>
 {panel&&<PremiumDialog platform={platform} onClose={closePanel} title={panel==='premium'?undefined:information[panel].label} description={panel==='premium'?undefined:server&&panel==='support'?'Серверная история доступна через «Подробнее» на Главной. Запуск серверных тестов будет подключён отдельно. Канал поддержки пока не настроен.':server&&panel==='about'?'ANATOMAI — медицинское учебное Mini App. Подключены серверные каталог и персональные данные. XP и платежи не подключены.':server&&panel==='settings'?'Настройки и сброс серверного прогресса пока недоступны. Локальные результаты не объединяются с серверными.':information[panel].text}>{panel==='settings'&&(server?<p role="status">Завершено тестов: {server.progress.statistics.completed_tests}. Условий достижений выполнено: {server.achievements.filter(a=>a.state==='unlocked').length}. Серверные данные сохранены в аккаунте. Сброс недоступен.</p>:entries.length>0?<button className="settings-reset" onClick={()=>{if(window.confirm('Сбросить результаты текущей сессии и достижения? Отменить это действие нельзя.'))onReset();}}>Сбросить прогресс</button>:<p role="status">Результатов текущей сессии нет.</p>)}</PremiumDialog>}
 </section>;
}
