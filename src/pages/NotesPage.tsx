import { useMemo, useState } from 'react';
import { disciplines, matchesSearch } from '../features/library/catalog';

export function NotesPage() {
  const [query, setQuery] = useState('');
  const filtered = useMemo(() => disciplines.filter(item => matchesSearch(item.title, query)), [query]);
  return <section className="notes-page library-page" aria-labelledby="notes-title">
    <header className="library-heading"><p className="eyebrow">Знания под рукой</p><h1 id="notes-title">Конспекты</h1><p className="library-subtitle">Самое важное по вашим дисциплинам.</p></header>
    <label className="library-search"><span aria-hidden="true">⌕</span><input value={query} onChange={event => setQuery(event.target.value)} aria-label="Найти дисциплину" placeholder="Найти дисциплину" /></label>
    <div className="library-notice"><span aria-hidden="true">≡</span><div><strong>Библиотека конспектов</strong><p>Материалы пока не добавлены.</p></div></div>
    <div className="library-section-title"><h2>Дисциплины</h2></div>
    <ul className="notes-list">{filtered.map(item => <li className="notes-card" key={item.id}><span className={`library-discipline-icon ${item.color}`} aria-hidden="true">{item.icon}</span><div><h3>{item.title}</h3><p>Пока нет материалов</p></div></li>)}</ul>
    {filtered.length === 0 && <div className="library-empty" role="status"><strong>Дисциплина не найдена</strong><p>Попробуйте другое название.</p><button onClick={() => setQuery('')}>Сбросить поиск</button></div>}
  </section>;
}
