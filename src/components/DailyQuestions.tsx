import { useEffect, useMemo, useState } from 'react';
import { catalog } from '../features/library/catalog';
import { localDayKey, millisecondsToNextLocalDay, selectDailyTopic } from '../features/library/dailyTopic';
import type { TestDefinition } from '../features/tests/types';

export function DailyQuestions({ onOpen, topics=catalog }: { onOpen: (test: TestDefinition) => void; topics?: readonly (typeof catalog)[number][] }) {
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
  return <>
    <div className="section"><h3>Вопросы дня</h3></div>
    {selected ? <button className="review daily-questions" onClick={() => onOpen(selected.test)}>
      <span className="review-art" aria-hidden="true">{selected.test.icon}</span>
      <span className="review-copy"><b>{discipline}</b><span className="daily-questions__topic">{theme.join(':').trim() || discipline}</span><small>Вопросов: {selected.questionCount} · Ответы и разбор</small></span>
      <span className="review-arrow" aria-hidden="true">→</span>
    </button> : <section className="review daily-questions" role="status"><p>Пока нет доступных вопросов.</p></section>}
  </>;
}
