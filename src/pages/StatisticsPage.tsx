import { AchievementGrid } from '../features/library/AchievementGrid';
import { summarizeHistory, type CompletedTest } from '../features/library/statistics';
import type { TelegramPlatform } from '../platform/telegram/TelegramPlatformAdapter';
import { useTelegramBackButton } from '../platform/telegram/useTelegramBackButton';
export function StatisticsPage({entries,platform,onBack}:{entries:CompletedTest[];platform:TelegramPlatform;onBack:()=>void}) {
 const {isTelegramContext,requestBack}=useTelegramBackButton(platform,onBack);
 const stats=summarizeHistory(entries);
 return <section className="library-page statistics-page"><header className="library-heading">{!isTelegramContext&&<button className="notes-back" onClick={requestBack}>‹ Назад</button>}<p className="eyebrow">Мой прогресс</p><h1>Моя статистика</h1><p className="library-subtitle">Только текущая сессия приложения. Без сохранения и синхронизации.</p></header>
 <dl className="profile-stats">{[['Завершено тестов',stats.completed],['Средний результат',stats.average===null?'—':`${stats.average}%`],['Ответов',stats.answered],['Правильных',stats.correct]].map(([label,value])=><div key={label}><dd>{value}</dd><dt>{label}</dt></div>)}</dl>
 <AchievementGrid entries={entries}/>
 <section className="profile-week"><div className="library-section-title"><h2>Активность за неделю</h2></div><ol>{stats.week.map((count,i)=><li key={i}><span>{['Пн','Вт','Ср','Чт','Пт','Сб','Вс'][i]}</span><i>{count}</i></li>)}</ol></section>
 <div className="library-section-title"><h2>История тестов</h2></div>{entries.length===0?<div className="library-empty"><strong>Пока нет завершённых тестов</strong><p>Пройдите тест в этой сессии, чтобы увидеть результат здесь.</p></div>:<ol className="statistics-history">{[...entries].reverse().map(e=><li key={e.id}><strong>{e.result.test.title}</strong><span>{e.result.mode==='exam'?'Экзамен':'Обучение'} · {e.result.total?Math.round(e.result.score/e.result.total*100):0}% · {e.result.durationSeconds} сек</span><small>{new Date(e.completedAt).toLocaleString('ru')}</small></li>)}</ol>}</section>;
}
