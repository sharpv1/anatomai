import { useEffect, useMemo, useRef, useState } from 'react';
import type {TelegramPlatform} from '../platform/telegram/TelegramPlatformAdapter';
import {useTelegramBackButton} from '../platform/telegram/useTelegramBackButton';
import { disciplines, matchesSearch } from '../features/library/catalog';

export function NotesPage({platform,active,selectedId,onSelect,onBack,canGoBack,backLabel,resetSearch}:{platform:TelegramPlatform;active:boolean;selectedId:string|null;onSelect:(id:string)=>void;onBack:()=>void;canGoBack:boolean;backLabel:string;resetSearch:number}) {
  const {isTelegramContext,requestBack}=useTelegramBackButton(platform,onBack,active&&canGoBack,false);
  const [query, setQuery] = useState('');
  useEffect(()=>setQuery(''),[resetSearch]);
  const filtered = useMemo(() => disciplines.filter(item => matchesSearch(item.title, query)), [query]);
  const selected = disciplines.find(item => item.id === selectedId);
  const detailRef = useRef<HTMLElement>(null);
  const cards = useRef<Record<string, HTMLButtonElement | null>>({});
  const previousId=useRef(selectedId);
  useEffect(() => { if(active){if(selectedId)detailRef.current?.focus();else if(previousId.current)cards.current[previousId.current]?.focus();}previousId.current=selectedId; }, [selectedId,active]);
  return <section className="notes-page library-page" aria-labelledby="notes-title">
    <header className="library-heading">{canGoBack&&!isTelegramContext&&<button className="notes-back" onClick={requestBack}>‹ {backLabel}</button>}<p className="eyebrow">Знания под рукой</p><h1 id="notes-title">Конспекты</h1><p className="library-subtitle">Самое важное по вашим дисциплинам.</p></header>
    {selected ? <section className="notes-detail" ref={detailRef} tabIndex={-1} aria-label={`Конспекты: ${selected.title}`}>
      <div className="library-section-title"><h2>{selected.title}</h2></div>
      <div className="library-empty"><strong>Материалы ещё не добавлены</strong><p>В этой дисциплине пока нет конспектов.</p></div>
    </section> : <>
      <label className="library-search"><span aria-hidden="true">⌕</span><input value={query} onChange={event => setQuery(event.target.value)} aria-label="Найти дисциплину" placeholder="Найти дисциплину" /></label>
      <div className="library-section-title"><h2>Дисциплины</h2></div>
      <ul className="notes-list">{filtered.map(item => <li key={item.id}><button className="notes-card" ref={el => { cards.current[item.id] = el; }} onClick={() => onSelect(item.id)}><span className={`library-discipline-icon ${item.color}`} aria-hidden="true">{item.icon}</span><span className="notes-card__title">{item.title}</span><span className="library-chevron" aria-hidden="true">›</span></button></li>)}</ul>
      {filtered.length === 0 && <div className="library-empty" role="status"><strong>Дисциплина не найдена</strong><p>Попробуйте другое название.</p><button onClick={() => setQuery('')}>Сбросить поиск</button></div>}
    </>}
  </section>;
}
