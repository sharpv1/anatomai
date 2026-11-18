import { useMemo, useState } from 'react';
import { LibraryIcon } from '../features/library/LibraryIcon';
import { catalog, levels, matchesSearch } from '../features/library/catalog';
import type { TestDefinition } from '../features/tests/types';

type TestsPageProps = { onSelectTest: (test: TestDefinition) => void };
export function TestsPage({ onSelectTest }: TestsPageProps) {
  const [query, setQuery] = useState('');
  const [level, setLevel] = useState('Все');
  const filtered = useMemo(() => catalog.filter(({ test }) => matchesSearch(test.title, query) && (level === 'Все' || test.level === level)), [level, query]);
  const quick = catalog.find(item => item.questionCount > 0);
  return <section className="tests-page library-page" aria-labelledby="tests-title">
    <header className="library-heading tests-head"><div><p className="eyebrow">Учиться с уверенностью</p><h1 id="tests-title">Тесты</h1><p className="library-subtitle">От вопроса — к пониманию.</p></div></header>
    <label className="tests-search library-search"><span aria-hidden="true">⌕</span><input value={query} onChange={event => setQuery(event.target.value)} placeholder="Найти дисциплину" aria-label="Найти тест" /></label>
    <div className="test-filters" role="group" aria-label="Сложность тестов">{['Все', ...levels].map(item => <button key={item} aria-pressed={level === item} className={`test-filter ${level === item ? 'active' : ''}`} onClick={() => setLevel(item)}>{item}</button>)}</div>
    {quick && <button className="library-quick" onClick={() => onSelectTest(quick.test)}><span className="library-quick__icon" aria-hidden="true"><LibraryIcon name="practice" /></span><span><strong>Быстрая практика</strong><small>{quick.test.title.split(':')[0]} · Обучение или экзамен</small></span><span className="library-chevron" aria-hidden="true">›</span></button>}
    <div className="library-section-title"><h2>Дисциплины</h2><span>{filtered.length} из {catalog.length}</span></div>
    <section className="test-list" aria-label="Каталог тестов">{filtered.map(({ test, questionCount }) => <button className="test-card" key={test.id} onClick={() => onSelectTest(test)}><span className={`test-card-icon ${test.color}`} aria-hidden="true">{test.icon}</span><span className="test-card-body"><strong className="test-card-title">{test.title}</strong><span className="test-card-meta">Вопросов: {questionCount} · Экзамен: {test.examMinutes} мин</span><span className="test-card-foot"><span className="test-level">{test.level}</span></span></span><span className="test-arrow" aria-hidden="true">›</span></button>)}</section>
    {filtered.length === 0 && <div className="library-empty" role="status"><strong>Тесты не найдены</strong><p>Попробуйте другое название или сложность.</p><button onClick={() => { setQuery(''); setLevel('Все'); }}>Сбросить поиск</button></div>}
  </section>;
}
