import { useMemo, useState, useEffect } from 'react';
import { LibraryIcon } from '../features/library/LibraryIcon';
import { catalog, matchesSearch } from '../features/library/catalog';
import type { TestDefinition } from '../features/tests/types';

import type { TelegramPlatform } from '../platform/telegram/TelegramPlatformAdapter';
import { useTelegramBackButton } from '../platform/telegram/useTelegramBackButton';
type TestsPageProps = { onSelectTest: (test: TestDefinition) => void; platform: TelegramPlatform; active: boolean };
export function TestsPage({ onSelectTest, platform, active }: TestsPageProps) {
  const [query, setQuery] = useState('');
  const [selection, setSelection] = useState<{discipline?:string;topic?:string}>({});
  useEffect(()=>{if(!active)return;const sync=()=>setSelection(window.history.state?.catalog ?? {});window.addEventListener('popstate',sync);return()=>window.removeEventListener('popstate',sync);},[active]);
  const back=()=>window.history.back();
  const {isTelegramContext,requestBack}=useTelegramBackButton(platform,back,active&&Boolean(selection.discipline),false);
  const select=(next:typeof selection)=>{setSelection(next);window.history.pushState({catalog:next},'',next.topic?'#catalog-tests':'#catalog-topics');};

  const filtered = useMemo(() => catalog.filter(({ test }) => matchesSearch(test.title, query)), [query]);
  const quick = catalog.find(item => item.questionCount > 0);
  return <section className="tests-page library-page" aria-labelledby="tests-title">
    <header className="library-heading tests-head"><div><p className="eyebrow">Учиться с уверенностью</p><h1 id="tests-title">Тесты</h1><p className="library-subtitle">От вопроса — к пониманию.</p></div></header>
    <label className="tests-search library-search"><span aria-hidden="true">⌕</span><input value={query} onChange={event => setQuery(event.target.value)} placeholder="Найти дисциплину" aria-label="Найти тест" /></label>
    {quick && <button className="library-quick" onClick={() => onSelectTest(quick.test)}><span className="library-quick__icon" aria-hidden="true"><LibraryIcon name="practice" /></span><span><strong>Быстрая практика</strong><small>{quick.test.title.split(':')[0]} · Обучение или экзамен</small></span><span className="library-chevron" aria-hidden="true">›</span></button>}
    <div className="library-section-title"><h2>Дисциплины</h2><span>{filtered.length} из {catalog.length}</span></div>
    {selection.discipline && <div className="library-section-title">{!isTelegramContext&&<button className="notes-back" onClick={requestBack}>‹ Назад</button>}<h2>{selection.topic || selection.discipline}</h2><span>{selection.topic ? 'Тесты' : 'Темы'}</span></div>}
    <section className="test-list" aria-label="Каталог тестов">{filtered.filter(({test})=>!selection.discipline||test.title.split(':')[0].trim()===selection.discipline).map(({ test, questionCount }) => <button className="test-card" key={test.id} onClick={() => { const discipline=test.title.split(':')[0].trim(); const topic=test.title.split(':').slice(1).join(':').trim() || discipline; if(!selection.discipline && catalog.filter(item=>item.test.title.split(':')[0].trim()===discipline).length>1) select({discipline}); else onSelectTest(test); }}><span className={`test-card-icon ${test.color}`} aria-hidden="true">{test.icon}</span><span className="test-card-body"><strong className="test-card-title">{selection.discipline ? test.title.split(':').slice(1).join(':').trim() : test.title.split(':')[0].trim()}</strong><span className="test-card-topic">{test.title.split(':').slice(1).join(':').trim()}</span><span className="test-card-meta">Вопросов: {questionCount}</span></span><span className="test-arrow" aria-hidden="true">›</span></button>)}</section>
    {filtered.length === 0 && <div className="library-empty" role="status"><strong>Тесты не найдены</strong><p>Попробуйте другую дисциплину или тему.</p><button onClick={() => { setQuery(''); }}>Сбросить поиск</button></div>}
  </section>;
}
