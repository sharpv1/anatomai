import { useEffect, useMemo, useRef, useState } from 'react';
import { disciplines, matchesSearch } from '../features/library/catalog';

export function NotesPage() {
  const [query, setQuery] = useState('');
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const filtered = useMemo(() => disciplines.filter(item => matchesSearch(item.title, query)), [query]);
  const selected = disciplines.find(item => item.id === selectedId);
  const detailRef = useRef<HTMLElement>(null);
  const cards = useRef<Record<string, HTMLButtonElement | null>>({});
  useEffect(() => { if (selectedId) detailRef.current?.focus(); }, [selectedId]);
  const back = () => { const id = selectedId; setSelectedId(null); requestAnimationFrame(() => { if (id) cards.current[id]?.focus(); }); };
  return <section className="notes-page library-page" aria-labelledby="notes-title">
    <header className="library-heading"><p className="eyebrow">Знания под рукой</p><h1 id="notes-title">Конспекты</h1><p className="library-subtitle">Самое важное по вашим дисциплинам.</p></header>
    {selected ? <section className="notes-detail" ref={detailRef} tabIndex={-1} aria-label={`Конспекты: ${selected.title}`}>
      <button className="notes-back" onClick={back}>‹ К дисциплинам</button>
      <div className="library-section-title"><h2>{selected.title}</h2></div>
      <div className="library-empty"><strong>Материалы ещё не добавлены</strong><p>В этой дисциплине пока нет конспектов.</p></div>
    </section> : <>
      <label className="library-search"><span aria-hidden="true">⌕</span><input value={query} onChange={event => setQuery(event.target.value)} aria-label="Найти дисциплину" placeholder="Найти дисциплину" /></label>
      <div className="library-section-title"><h2>Дисциплины</h2></div>
      <ul className="notes-list">{filtered.map(item => <li key={item.id}><button className="notes-card" ref={el => { cards.current[item.id] = el; }} onClick={() => setSelectedId(item.id)}><span className={`library-discipline-icon ${item.color}`} aria-hidden="true">{item.icon}</span><span className="notes-card__title">{item.title}</span><span className="library-chevron" aria-hidden="true">›</span></button></li>)}</ul>
      {filtered.length === 0 && <div className="library-empty" role="status"><strong>Дисциплина не найдена</strong><p>Попробуйте другое название.</p><button onClick={() => setQuery('')}>Сбросить поиск</button></div>}
    </>}
  </section>;
}
