import { useMemo, useState } from 'react';
import { demoTests } from '../features/tests/data';
import type { TestDefinition, TestFilter } from '../features/tests/types';

type TestsPageProps = { onSelectTest: (test: TestDefinition) => void };

export function TestsPage({ onSelectTest }: TestsPageProps) {
  const [query, setQuery] = useState('');
  const [filter, setFilter] = useState<TestFilter>('all');
  const filtered = useMemo(() => demoTests.filter((test) => {
    const matchesQuery = `${test.title} ${test.level}`.toLowerCase().includes(query.toLowerCase());
    const matchesFilter = filter === 'all' || (filter === 'active' && test.progress > 0) || (filter === 'new' && test.progress === 0);
    return matchesQuery && matchesFilter;
  }), [filter, query]);
  const completed = demoTests.filter((test) => test.progress > 0).length;

  return <section className="tests-page">
    <header className="tests-head"><div><p className="eyebrow">Практика</p><h1>Тесты</h1></div><div className="tests-summary"><strong>{completed}/{demoTests.length}</strong><span>в процессе</span></div></header>
    <label className="tests-search"><span>⌕</span><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Найти тест" aria-label="Найти тест" /></label>
    <div className="test-filters" role="group" aria-label="Фильтр тестов">{(['all', 'active', 'new'] as TestFilter[]).map((item) => <button key={item} aria-pressed={filter === item} className={`test-filter ${filter === item ? 'active' : ''}`} onClick={() => setFilter(item)}>{item === 'all' ? 'Все' : item === 'active' ? 'В процессе' : 'Новые'}</button>)}</div>
    <section className="test-list" aria-label="Каталог тестов">{filtered.map((test) => <button className="test-card" key={test.id} onClick={() => onSelectTest(test)}><span className={`test-card-icon ${test.color}`}>{test.icon}</span><span className="test-card-body"><strong className="test-card-title">{test.title}</strong><span className="test-card-meta">{test.meta}</span><span className="test-card-foot"><span className="test-level">{test.level}</span><span className="test-progress"><i style={{ width: `${test.progress}%` }} /></span><small>{test.progress}%</small></span></span><span className="test-arrow">›</span></button>)}</section>
    {filtered.length === 0 && <div className="empty-state">Ничего не найдено</div>}
  </section>;
}
