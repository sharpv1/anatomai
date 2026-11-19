import { AchievementGrid } from '../features/library/AchievementGrid';
import { summarizeHistory, type CompletedTest } from '../features/library/statistics';
import type { TelegramPlatform } from '../platform/telegram/TelegramPlatformAdapter';
import { useTelegramBackButton } from '../platform/telegram/useTelegramBackButton';
export function StatisticsPage({entries,platform,onBack}:{entries:CompletedTest[];platform:TelegramPlatform;onBack:()=>void}) {
 const {isTelegramContext,requestBack}=useTelegramBackButton(platform,onBack);const stats=summarizeHistory(entries);const max=Math.max(1,...stats.week);
 return <section className="library-page statistics-page study-page"><header className="library-heading">{!isTelegramContext&&<button className="notes-back" onClick={requestBack}>‹ Назад</button>}<h1>Моя статистика</h1><p className="library-subtitle">Текущая сессия. После перезагрузки история очищается.</p></header>
 <dl className="profile-stats">{[['Завершено тестов',stats.completed],['Средний результат',stats.average===null?'—':`${stats.average}%`]].map(([label,value])=><div key={label}><dd>{value}</dd><dt>{label}</dt></div>)}</dl>
 <p className="stats-xp-info">XP и уровни пока недоступны. Синхронизации с сервером нет.</p>
 <section className="profile-week"><div className="library-section-title"><h2>Активность за неделю</h2></div><ol>{stats.week.map((count,i)=><li key={i}><strong>{count}</strong><i style={{height:count?`${Math.max(8,count/max*36)}px`:'2px'}}/><span>{['Пн','Вт','Ср','Чт','Пт','Сб','Вс'][i]}</span></li>)}</ol></section>
 <div className="library-section-title"><h2>История тестов</h2></div>{entries.length===0?<div className="library-empty"><strong>Нет завершённых тестов</strong><p>Результаты появятся здесь после прохождения.</p></div>:<ol className="statistics-history">{[...entries].reverse().map(e=><li key={e.id}><strong>{e.result.test.title}</strong><span>{e.result.mode==='exam'?'Экзамен':'Обучение'} · {e.result.total?Math.round(e.result.score/e.result.total*100):0}% · {e.result.durationSeconds} сек</span><small>{new Date(e.completedAt).toLocaleString('ru')}</small></li>)}</ol>}
 <details className="statistics-disclosure"><summary>Достижения</summary><AchievementGrid entries={entries} hideHeading/></details><details className="statistics-disclosure"><summary>Как считается статистика</summary><p>Учитываются завершения этого запуска, без сохранения и серверной синхронизации. Средний результат — среднее процентов попыток. Ответов: {stats.answered}, правильных: {stats.correct}. XP не начисляются.</p></details></section>;
}
