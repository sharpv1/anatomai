import { useMemo, useRef, useState } from 'react';
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
};

export function QuestionReviewPage({ title, questions, platform, onBack, listenPopstate=true, backLabel="К теме" }: Props) {
  const { isTelegramContext, requestBack } = useTelegramBackButton(platform, onBack, true, listenPopstate);
  const [query, setQuery] = useState('');
  const [limit, setLimit] = useState(REVIEW_BATCH_SIZE);
  const listRef = useRef<HTMLDivElement>(null);
  const matches = useMemo(() => findReviewQuestions(questions, query), [questions, query]);

  return <section className="question-review" aria-label="Ответы и разбор">
    <header className="question-review__header">
      {!isTelegramContext && <button className="question-review__back" onClick={requestBack}>‹ {backLabel}</button>}
      <h1>Ответы и разбор</h1>
      <p className="question-review__topic">{title}</p>
      <label className="question-review__search">
        <span>Поиск по вопросам</span>
        <input type="search" value={query} placeholder="Найти вопрос" onChange={event => {
          setQuery(event.target.value);
          setLimit(REVIEW_BATCH_SIZE);
          listRef.current?.scrollTo(0, 0);
        }} />
      </label>
      <p className="question-review__count" role="status">{query.trim() ? `Найдено: ${matches.length} из ${questions.length}` : `Вопросов: ${questions.length}`}</p>
    </header>
    <div ref={listRef} className="question-review__scroll" tabIndex={0} aria-label="Вопросы темы">
      <ol className="question-review__list">
        {matches.slice(0, limit).map(({ question, number }) => {
          const correct = correctReviewAnswers(question);
          return <li key={question.id}>
            <article className="question-review__card" aria-labelledby={`review-${question.id}`}>
              <h2 id={`review-${question.id}`}><span>{number}.</span> {question.text}</h2>
              <ul className="question-review__answers">
                {question.answers.map((answer, index) => <li key={index} className={correct.has(index) ? 'question-review__answer question-review__answer--correct' : 'question-review__answer'}>
                  <span className="question-review__mark" aria-hidden="true">{correct.has(index) ? '✓' : '•'}</span>
                  <span>{correct.has(index) && <span className="question-review__sr">Правильный ответ: </span>}{answer}</span>
                </li>)}
              </ul>
              {correct.size === 0 && <p className="question-review__empty">Правильный ответ не указан в данных.</p>}
              {question.explanation?.trim() && <details className="question-review__explanation"><summary>Объяснение</summary><p>{question.explanation}</p></details>}
            </article>
          </li>;
        })}
      </ol>
      {matches.length === 0 && <p className="question-review__empty">{questions.length ? 'Вопросы не найдены. Измените поисковый запрос.' : 'В этой теме пока нет вопросов.'}</p>}
      {limit < matches.length && <button className="question-review__more" onClick={() => setLimit(value => value + REVIEW_BATCH_SIZE)}>Показать ещё ({matches.length - limit})</button>}
    </div>
  </section>;
}
