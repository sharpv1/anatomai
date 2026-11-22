import { useMemo, useRef, useState, type ReactNode } from 'react';
import { correctReviewAnswers, findReviewQuestions, REVIEW_BATCH_SIZE, type ReviewQuestion } from '../features/tests/questionReview';
import type { TelegramPlatform } from '../platform/telegram/TelegramPlatformAdapter';
import { useTelegramBackButton } from '../platform/telegram/useTelegramBackButton';
import './QuestionReviewPage.css';

type Props = {
  title: string;
  questions: readonly ReviewQuestion[];
  platform: TelegramPlatform;
  onBack: () => void;
  listenPopstate?: boolean;
  backLabel?: string;
  server?: {total:number|null;pending?:boolean;numbers?:Record<string,number>;status?:ReactNode;hasMore:boolean;onMore:()=>void;query:string;onQuery:(query:string)=>void;loadingMore?:boolean};
};

export function QuestionReviewPage({ title, questions, platform, onBack, listenPopstate=true, backLabel="К теме",server }: Props) {
  const { isTelegramContext, requestBack } = useTelegramBackButton(platform, onBack, true, listenPopstate);
  const [localQuery, setQuery] = useState('');
  const query=server?.query??localQuery;
  const [limit, setLimit] = useState(REVIEW_BATCH_SIZE);
  const listRef = useRef<HTMLDivElement>(null);
  const matches = useMemo(() => findReviewQuestions(questions, server?'':query), [questions, query,server]);

  return <section className="question-review" aria-label="Ответы и разбор">
    <header className="question-review__header">
      {!isTelegramContext && <button className="question-review__back" onClick={requestBack}>‹ {backLabel}</button>}
      <h1>Ответы и разбор</h1>
      <p className="question-review__topic">{title}</p>
      <label className="question-review__search">
        <span>Поиск по вопросам</span>
        <input type="search" value={query} placeholder="Найти вопрос" onChange={event => {
          if(server)server.onQuery(event.target.value);else setQuery(event.target.value);
          setLimit(REVIEW_BATCH_SIZE);
          listRef.current?.scrollTo(0, 0);
        }} />
      </label>
      <p className="question-review__count" role="status">{server?(server.total===null?(server.pending?'Загрузка вопросов…':'Вопросы недоступны'):`Вопросов: ${server.total}`):query.trim() ? `Найдено: ${matches.length} из ${questions.length}` : `Вопросов: ${questions.length}`}</p>
    </header>
    <div ref={listRef} className="question-review__scroll" tabIndex={0} aria-label="Вопросы темы">
      {server?.status}<ol className="question-review__list">
        {(server?matches:matches.slice(0, limit)).map(({ question, number }) => {
          const correct = correctReviewAnswers(question);
          return <li key={question.id}>
            <article className="question-review__card" aria-labelledby={`review-${question.id}`}>
              <h2 id={`review-${question.id}`}><span>{server?.numbers?.[question.id]??number}.</span> {question.text}</h2>
              <ul className="question-review__answers">
                {question.answers.map((answer, index) => <li key={index} className={correct.has(index) ? 'question-review__answer question-review__answer--correct' : 'question-review__answer'}>
                  <span className="question-review__mark" aria-hidden="true">{correct.has(index) ? '✓' : '•'}</span>
                  <span>{correct.has(index) && <span className="question-review__sr">Правильный ответ: </span>}{answer}</span>
                </li>)}
              </ul>
              {correct.size === 0 && <p className="question-review__empty">Правильный ответ не указан в данных.</p>}
            </article>
          </li>;
        })}
      </ol>
      {matches.length === 0 && (!server||server.total!==null)&& <p className="question-review__empty">{questions.length ? 'Вопросы не найдены. Измените поисковый запрос.' : 'В этой теме пока нет вопросов.'}</p>}
      {server?.hasMore&&<button className="question-review__more" disabled={server.loadingMore} onClick={server.onMore}>Показать ещё</button>}
      {!server&&limit < matches.length && <button className="question-review__more" onClick={() => setLimit(value => value + REVIEW_BATCH_SIZE)}>Показать ещё ({matches.length - limit})</button>}
    </div>
  </section>;
}
