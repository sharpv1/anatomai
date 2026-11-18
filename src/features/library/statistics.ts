import type { TestResultData } from '../tests/types';
export type CompletedTest = { id: string; completedAt: number; result: TestResultData };
export function summarizeHistory(entries: CompletedTest[], now = new Date()) {
  const average = entries.length ? Math.round(entries.reduce((sum, e) => sum + (e.result.total ? e.result.score / e.result.total * 100 : 0), 0) / entries.length) : null;
  const monday = new Date(now); monday.setHours(0,0,0,0); monday.setDate(monday.getDate() - (monday.getDay()+6)%7);
  const week = Array.from({length:7},(_,i)=>{const start=new Date(monday);start.setDate(start.getDate()+i);const end=new Date(start);end.setDate(end.getDate()+1);return entries.filter(e=>e.completedAt>=start.getTime()&&e.completedAt<end.getTime()).length;});
  return { average, completed: entries.length, answered: entries.reduce((sum,e)=>sum+e.result.answered,0), correct: entries.reduce((sum,e)=>sum+e.result.score,0), week };
}
