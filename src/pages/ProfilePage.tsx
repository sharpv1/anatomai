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
export function ProfilePage({platform,entries,onReset}:{platform:TelegramPlatform;entries:CompletedTest[];onReset:()=>void}){
 const {name,photoUrl}=useTelegramIdentity(platform);
 const [failedPhoto,setFailedPhoto]=useState<string|null>(null);
 const initials=name?.split(/\s+/).slice(0,2).map(s=>Array.from(s)[0]).join('').toLocaleUpperCase('ru');
 const streak=sessionStreak(entries);
 const [panel,setPanel]=useState<'premium'|keyof typeof information|null>(null);
 const openPanel=(next:NonNullable<typeof panel>)=>{window.history.pushState({profilePanel:next},'',`#profile-${next}`);setPanel(next);};
 const closePanel=()=>{if(panel&&window.location.hash===`#profile-${panel}`)window.history.back();else setPanel(null);};
 return <section className="profile-page library-page radix-profile" aria-label="Профиль">
  <header className="rp-user"><span className="rp-avatar" aria-hidden="true">{photoUrl&&failedPhoto!==photoUrl?<img src={photoUrl} alt="" loading="lazy" referrerPolicy="no-referrer" onError={()=>setFailedPhoto(photoUrl)}/>:initials||<ProfileIcon name="book"/>}</span><div className="rp-user-copy"><h1 dir="auto">{name||'Ваш профиль'}</h1><small>{name?'Telegram':'Имя пока недоступно'}</small></div>{streak!==null&&<div className="rp-indicators"><span aria-label={`Серия активности: ${streak===null?'нет данных':streak}`}><ProfileIcon name="flame"/>{streak??'—'}</span></div>}</header>
  <section className="premium-card"><ProfileIcon name="crown"/><h2>ANATOMAI Premium</h2><p>Расширенный доступ — скоро.</p><button onClick={()=>openPanel('premium')}>Подробнее</button></section>
  <nav className="rp-menu" aria-label="Разделы профиля">{(Object.keys(information) as Array<keyof typeof information>).map(key=><button key={key} onClick={()=>openPanel(key)}><span>{information[key].label}</span><small>{information[key].status}</small><b aria-hidden="true">›</b></button>)}</nav>
 {panel&&<PremiumDialog platform={platform} onClose={closePanel} title={panel==='premium'?undefined:information[panel].label} description={panel==='premium'?undefined:information[panel].text}>{panel==='settings'&&(entries.length>0?<button className="settings-reset" onClick={()=>{if(window.confirm('Сбросить результаты текущей сессии и достижения? Отменить это действие нельзя.'))onReset();}}>Сбросить прогресс</button>:<p role="status">Результатов текущей сессии нет.</p>)}</PremiumDialog>}
 </section>;
}
