import { useCallback, useEffect, useRef, useState } from 'react';
import { questionsForTest } from './data';
import { answerState, correctStreak } from './presentation';
import { useTestSession } from './useTestSession';
import type { TestDefinition, TestMode, TestResultData } from './types';
import type { TelegramPlatform } from '../../platform/telegram/TelegramPlatformAdapter';
import './TestSession.css';

type TestSessionProps = { test: TestDefinition; platform: TelegramPlatform; onComplete: (result: TestResultData) => void; onExit: () => void };

export function TestSession({ test, platform, onComplete, onExit }: TestSessionProps) {
  const questions = questionsForTest(test.id);
  const [mode, setMode] = useState<TestMode | null>(null);
  const session = useTestSession(test, questions, mode ?? 'learning', onComplete);
  const contentRef = useRef<HTMLDivElement>(null);
  const [discipline, category = ''] = test.title.split(':');
  const exit = useCallback(() => { if (!session.isDirty || window.confirm('Выйти из теста? Прогресс будет потерян.')) onExit(); }, [onExit, session.isDirty]);
  useEffect(() => {
    platform.showBackButton(exit);
    window.addEventListener('popstate', exit);
    return () => { platform.hideBackButton(); window.removeEventListener('popstate', exit); };
  }, [exit, platform]);
  useEffect(() => { contentRef.current?.scrollTo(0, 0); }, [session.questionIndex]);

  if (!mode) return <section className="test-mode-picker">
    <div className="test-mode-picker__icon" aria-hidden="true">◫</div>
    <p className="eyebrow">{discipline.trim()}</p><h1>Как будем практиковаться?</h1>
    <p className="test-mode-picker__hint">{questions.length} вопросов · Выберите удобный темп</p>
    <div className="test-mode-options">
      <button className="test-mode-card" onClick={() => setMode('learning')}><span aria-hidden="true">✓</span><strong>Обучение</strong><small>Проверьте ответ и разберите объяснение перед следующим вопросом.</small><b>Без таймера · с объяснениями</b></button>
      <button className="test-mode-card" onClick={() => setMode('exam')}><span aria-hidden="true">◷</span><strong>Экзамен</strong><small>Пройдите тест самостоятельно. Проверка — только в конце.</small><b>{test.examMinutes} минут · без подсказок</b></button>
    </div>
    <button className="test-mode-back" onClick={onExit}>Вернуться к тестам</button>
  </section>;
  if (!session.question) return null;
  const learning = mode === 'learning';
  const checked = learning && session.confirmedAnswer !== null;
  const isLast = session.questionIndex === questions.length - 1;
  const streak = learning ? correctStreak(session.answers, session.confirmedAnswer, session.question.correctAnswer) : 0;
  const completed = session.questionIndex + (checked ? 1 : 0);
  const submit = () => {
    session.next();
  };
  const actionLabel = isLast ? (learning ? 'Завершить тест' : 'Завершить экзамен') : 'Далее';

  return <section className="test-session" aria-label="Прохождение теста">
    <header className="test-session__top">
      <button className="test-session__close" onClick={exit} aria-label="Назад к тестам">‹</button>
      <div className="test-session__meta"><span title={test.title}>{discipline.trim()}{category && ` · ${category.trim()}`}</span><strong>Вопрос {session.questionIndex + 1} из {questions.length}</strong>
        <div className="test-session__track" role="progressbar" aria-label="Завершённые вопросы" aria-valuemin={0} aria-valuemax={questions.length} aria-valuenow={completed}><b style={{ width: `${(completed / questions.length) * 100}%` }} /></div>
      </div>
      <span className={`test-session__score ${!learning && session.secondsLeft < 60 ? 'urgent' : ''}`}>{!learning ? `◷ ${session.timeLabel}` : `${session.score} верно`}</span>
    </header>
    <div className="test-session__content" ref={contentRef}>
      <div className="test-question" key={session.question.id}>
        <div className="test-session__context"><p className="test-session__mode">{learning ? 'Обучение' : 'Экзамен'}</p>{streak >= 2 && <span className="test-streak" role="status">{streak} подряд</span>}</div>
        <h2 id="test-question-title">{session.question.text}</h2>
        {/* Future media can be rendered here without changing the question's scroll boundary. */}
        <div className="test-session__options" role="group" aria-labelledby="test-question-title">
          {session.question.answers.map((answer, index) => {
            const state = answerState(index, session.selectedAnswer, checked ? session.confirmedAnswer : null, session.question!.correctAnswer);
            return <button key={`${session.question!.id}-${index}`} className={`test-choice ${state}`} aria-pressed={session.selectedAnswer === index} disabled={checked} onClick={() => { if (learning) session.confirmAnswer(index); else session.selectAnswer(index); }}>
              <span className="test-choice__radio" aria-hidden="true"><i /></span><span className="test-choice__letter" aria-hidden="true">{String.fromCharCode(65 + index)}</span><span className="test-choice__text">{answer}</span><b className="test-choice__mark" aria-hidden="true">{state === 'correct' ? '✓' : state === 'wrong' ? '×' : ''}</b>
            </button>;
          })}
        </div>
        {checked && session.question.explanation && <div className={`test-explanation ${session.confirmedAnswer === session.question.correctAnswer ? 'test-explanation--correct' : ''}`} role="status"><strong>{session.confirmedAnswer === session.question.correctAnswer ? 'Правильно' : 'Есть что повторить'}</strong>{session.question.explanation && <p>{session.question.explanation}</p>}</div>}
      </div>
    </div>
    <footer className="test-session__footer"><div className="test-session__footer-actions">
      {!checked && <button className="test-session__skip" onClick={session.skip}>Пропустить вопрос</button>}
      {(!learning || checked) && <button className="test-session__action" disabled={session.selectedAnswer === null} onClick={submit}>{actionLabel}</button>}
    </div>{!learning && <small className="test-session__footer-note">Ответы проверим после завершения экзамена</small>}</footer>
  </section>;
}
