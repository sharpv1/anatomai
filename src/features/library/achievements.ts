import type { CompletedTest } from './statistics';
export function sessionStreak(entries: CompletedTest[], now = new Date()): number | null {
  if (!entries.length) return null;
  const dayKey = (date: Date) => `${date.getFullYear()}-${date.getMonth()}-${date.getDate()}`;
  const days = new Set(entries.map(e => dayKey(new Date(e.completedAt))));
  const cursor = new Date(now);cursor.setHours(12,0,0,0);
  if (!days.has(dayKey(cursor))) cursor.setDate(cursor.getDate()-1);
  let count=0;while(days.has(dayKey(cursor))){count++;cursor.setDate(cursor.getDate()-1);}return count;
}
export function profileAchievements(entries: CompletedTest[], now = new Date()) {
 const correct=entries.reduce((sum,e)=>sum+e.result.score,0);
 return [
  {id:'first',title:'Первый шаг',caption:'Первый тест',icon:'play',unlocked:entries.length>0},
  {id:'three',title:'Три дня',caption:'3 дня подряд',icon:'flame',unlocked:(sessionStreak(entries,now)??0)>=3},
  {id:'anatomy',title:'Анатом',caption:'Блок анатомии',icon:'grid',unlocked:false},
  {id:'clinical',title:'Клиницист',caption:'Клинический блок',icon:'heart',unlocked:false},
  {id:'pharmacy',title:'Провизор',caption:'Фармакология',icon:'pill',unlocked:false},
  {id:'hundred',title:'Сотня',caption:'100 верных ответов',icon:'target',unlocked:correct>=100},
  {id:'perfect',title:'Без ошибок',caption:'Результат 100%',icon:'star',unlocked:entries.some(e=>e.result.total>0&&e.result.score===e.result.total)},
  {id:'memory',title:'Память',caption:'50 повторённых ошибок',icon:'repeat',unlocked:false},
  {id:'finish',title:'Финиш',caption:'Учебный маршрут',icon:'cap',unlocked:false},
 ] as const;
}
