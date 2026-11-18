import { profileAchievements } from './achievements';
import type { CompletedTest } from './statistics';
import { ProfileIcon } from './ProfileIcon';
import './AchievementGrid.css';
export function AchievementGrid({entries}:{entries:CompletedTest[]}){return <section className="achievement-section" aria-labelledby="achievement-title"><h2 id="achievement-title" className="rp-section">Достижения</h2><ul className="rp-achievements">{profileAchievements(entries).map(a=><li key={a.id} className={`rp-achievement ${a.unlocked?'is-unlocked':'is-locked'}`} aria-label={`${a.title}: ${a.unlocked?'получено в этой сессии':'заблокировано'}`}><span className="rp-achievement-icon"><ProfileIcon name={a.icon}/></span><strong>{a.title}</strong><small>{a.caption}</small></li>)}</ul><p className="rp-note">По результатам текущей сессии. Условия учебных блоков и маршрута пока недоступны.</p></section>;}
