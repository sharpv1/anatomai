import { useRef,useState } from 'react';
import { AchievementGrid } from '../features/library/AchievementGrid';
import { summarizeHistory, type CompletedTest } from '../features/library/statistics';
import type { TelegramPlatform } from '../platform/telegram/TelegramPlatformAdapter';
import { useTelegramBackButton } from '../platform/telegram/useTelegramBackButton';
export function StatisticsPage({entries,platform,onBack}:{entries:CompletedTest[];platform:TelegramPlatform;onBack:()=>void}) {
 const {isTelegramContext,requestBack}=useTelegramBackButton(platform,onBack);
 const stats=summarizeHistory(entries);
 const levels=useRef<HTMLDivElement>(null);const history=useRef<HTMLDivElement>(null);const [explain,setExplain]=useState(false);
 return <section className="library-page statistics-page study-page"><header className="library-heading">{!isTelegramContext&&<button className="notes-back" onClick={requestBack}>‹ Назад</button>}<p className="eyebrow">Мой прогресс</p><h1>Моя статистика</h1><p className="library-subtitle">Только текущая сессия приложения. Без сохранения и синхронизации.</p></header>
 <section className="study-level"><p>Учебный прогресс</p><h2>Прогресс пока недоступен</h2><p>XP и уровни не подключены.</p><span>До следующего уровня —</span></section>
 <dl className="profile-stats">{[['Завершено тестов',stats.completed],['Средний результат',stats.average===null?'—':`${stats.average}%`]].map(([label,value])=><div key={label}><dd>{value}</dd><dt>{label}</dt></div>)}</dl>
 <nav className="study-menu" aria-label="Учебный прогресс"><button onClick={()=>levels.current?.scrollIntoView({block:'start'})}>Уровни и достижения <span>›</span></button><button onClick={()=>history.current?.scrollIntoView({block:'start'})}>История активности <span>›</span></button><button aria-expanded={explain} onClick={()=>setExplain(v=>!v)}>Как это работает <span>›</span></button></nav>
 {explain&&<p className="study-explanation">Учитываются только завершённые тесты этого запуска. После перезагрузки данные очищаются. XP не начисляются, серверной синхронизации нет. Ответов: {stats.answered}, правильных: {stats.correct}.</p>}
 <div ref={levels}><AchievementGrid entries={entries}/></div><div ref={history} tabIndex={-1}/>
 <section className="profile-week"><div className="library-section-title"><h2>Активность за неделю</h2></div><ol>{stats.week.map((count,i)=><li key={i}><span>{['Пн','Вт','Ср','Чт','Пт','Сб','Вс'][i]}</span><i>{count}</i></li>)}</ol></section>
 <div className="library-section-title"><h2>История тестов</h2></div>{entries.length===0?<div className="library-empty"><strong>Пока нет завершённых тестов</strong><p>Пройдите тест в этой сессии, чтобы увидеть результат здесь.</p></div>:<ol className="statistics-history">{[...entries].reverse().map(e=><li key={e.id}><strong>{e.result.test.title}</strong><span>{e.result.mode==='exam'?'Экзамен':'Обучение'} · {e.result.total?Math.round(e.result.score/e.result.total*100):0}% · {e.result.durationSeconds} сек</span><small>{new Date(e.completedAt).toLocaleString('ru')}</small></li>)}</ol>}</section>;
}
