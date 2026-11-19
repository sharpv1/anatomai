import {useLayoutEffect, useRef, useState} from 'react';
import { questionsForTest } from '../features/tests/data';
import type { TestDefinition,TestMode } from '../features/tests/types';
import type { CompletedTest } from '../features/library/statistics';
import { topicSummary } from '../features/library/topicSummary';
import type { TelegramPlatform } from '../platform/telegram/TelegramPlatformAdapter';
import { useTelegramBackButton } from '../platform/telegram/useTelegramBackButton';
export function TopicPage({test,entries,platform,onBack,onStart,onReview,active=true}:{test:TestDefinition;entries:CompletedTest[];platform:TelegramPlatform;onBack:()=>void;onStart:(mode:TestMode)=>void;onReview:()=>void;active?:boolean}){
 const [all,setAll]=useState(false);
 const pageRef=useRef<HTMLElement>(null);const savedScroll=useRef(0);
 useLayoutEffect(()=>{if(active)pageRef.current?.scrollTo(0,savedScroll.current);},[active]);
 const openReview=()=>{savedScroll.current=pageRef.current?.scrollTop??0;onReview();};
 const {isTelegramContext,requestBack}=useTelegramBackButton(platform,onBack,active);const questions=questionsForTest(test.id);const stats=topicSummary(test.id,entries);const [discipline,...theme]=test.title.split(':');
 return <section ref={pageRef} hidden={!active} className="study-page topic-page"><header>{!isTelegramContext&&<button className="study-back" onClick={requestBack}>‹ К дисциплинам</button>}<p className="study-eyebrow">{discipline}</p><h1>{theme.join(':').trim()||discipline}</h1></header><dl className="topic-metrics">{[['Вопросов',questions.length],['Лучший результат',stats.best===null?'—':`${stats.best}%`],['Вопросов с ошибками',stats.errors??'—']].map(([label,value])=><div key={label}><dt>{label}</dt><dd>{value}</dd></div>)}</dl><p className="study-note">Результаты и ошибки — из текущей сессии. Нет завершённых тестов — нет результата.</p><div className="topic-modes"><button className="test-mode-card" onClick={()=>onStart('learning')}>Обучение</button><button className="test-mode-card" onClick={()=>onStart('exam')}>Экзамен</button></div><button className="topic-review-link" onClick={openReview}>Разбор вопросов <span aria-hidden="true">→</span></button><h2>Вопросы темы</h2><p className="study-note">Предпросмотр без проверки: правильные ответы и объяснения не раскрываются.</p><ol className="topic-questions">{(all?questions:questions.slice(0,3)).map((q,i)=><li key={q.id}><details><summary><span>{i+1}</span><strong>{q.text}</strong></summary><div className="topic-question-body"><ul>{q.answers.map((a,j)=><li key={j}>{a}</li>)}</ul></div></details></li>)}</ol>{questions.length>3&&<button className="topic-show-all" aria-expanded={all} onClick={()=>setAll(v=>!v)}>{all?'Свернуть':`Показать все (${questions.length})`}</button>}{!questions.length&&<p>В этой теме пока нет вопросов.</p>}</section>;
}
