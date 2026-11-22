import type {Daily} from '../backend/contracts';
import { useEffect, useMemo, useState } from 'react';
import { catalog } from '../features/library/catalog';
import { localDayKey, millisecondsToNextLocalDay, selectDailyTopic } from '../features/library/dailyTopic';
import type { TestDefinition } from '../features/tests/types';

export function DailyQuestions({ onOpen, topics=catalog,server,onServerOpen,disciplineLabel }: { onOpen: (test: TestDefinition) => void; topics?: readonly (typeof catalog)[number][];server?:Daily;onServerOpen?:(id:string)=>void;disciplineLabel?:string }) {
  const [day, setDay] = useState(() => new Date());
  useEffect(() => {
    let timer: ReturnType<typeof setTimeout>;
    const refresh = () => {
      const now = new Date();
      setDay(previous => localDayKey(previous) === localDayKey(now) ? previous : now);
      clearTimeout(timer);
      timer = setTimeout(refresh, millisecondsToNextLocalDay(now));
    };
    const visible = () => { if (document.visibilityState === 'visible') refresh(); };
    refresh();
    window.addEventListener('focus', refresh);
    document.addEventListener('visibilitychange', visible);
    return () => { clearTimeout(timer); window.removeEventListener('focus', refresh); document.removeEventListener('visibilitychange', visible); };
  }, []);
  const selected = useMemo(() => selectDailyTopic(topics, day), [day,topics]);
  const [discipline, ...theme] = selected?.test.title.split(':') ?? [];
  if(server)return server.availability==='available'&&server.topic_id?<button className="review daily-questions" aria-label={`Вопросы дня: ${server.title}. Ответы и разбор`} onClick={()=>onServerOpen?.(server.topic_id!)}><span className="review-art" aria-hidden="true">✚</span><span className="review-copy"><b>{disciplineLabel??'Вопросы дня'}</b><span className="daily-questions__topic" title={server.title??''}>{server.title}</span><small>Вопросов: {server.question_count}</small></span><span className="review-arrow" aria-hidden="true">→</span></button>:<section className="review daily-questions" role="status"><p>{server.availability==='withdrawn'?'Тема дня временно недоступна.':'Пока нет доступных вопросов.'}</p></section>;
  return <>
    {selected ? <button className="review daily-questions" aria-label={`Вопросы дня: ${discipline}. ${theme.join(':').trim() || discipline}. Вопросов: ${selected.questionCount}. Ответы и разбор`} onClick={() => onOpen(selected.test)}>
      <span className="review-art" aria-hidden="true">{selected.test.icon}</span>
      <span className="review-copy"><b>{discipline}</b><span className="daily-questions__topic" title={theme.join(':').trim() || discipline}>{theme.join(':').trim() || discipline}</span><small>Вопросов: {selected.questionCount}</small></span>
      <span className="review-arrow" aria-hidden="true">→</span>
    </button> : <section className="review daily-questions" aria-label="Вопросы дня" role="status"><p>Пока нет доступных вопросов.</p></section>}
  </>;
}
