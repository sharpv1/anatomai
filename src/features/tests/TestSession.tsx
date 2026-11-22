import { useCallback, useEffect, useRef, useState } from 'react';
import { questionsForTest } from './data';
import { answerState, correctStreak } from './presentation';
import { useTestSession } from './useTestSession';
import type { TestDefinition, TestMode, TestResultData } from './types';
import type { TelegramPlatform } from '../../platform/telegram/TelegramPlatformAdapter';
import './TestSession.css';
import './TestScreens.css';
import { useTelegramBackButton } from '../../platform/telegram/useTelegramBackButton';

type TestSessionProps = { test: TestDefinition; platform: TelegramPlatform; onComplete: (result: TestResultData) => void; onExit: () => void; initialMode?: TestMode };

export function TestSession({ test, platform, onComplete, onExit, initialMode }: TestSessionProps) {
  const questions = questionsForTest(test.id);
  const [mode, setMode] = useState<TestMode | null>(initialMode ?? null);
  const session = useTestSession(test, questions, mode ?? 'learning', onComplete);
  const contentRef = useRef<HTMLDivElement>(null);
  const [discipline, category = ''] = test.title.split(':');
  const exit = useCallback(() => { if (!session.isDirty || window.confirm('Выйти из теста? Прогресс будет потерян.')) onExit(); }, [onExit, session.isDirty]);
  const { isTelegramContext, requestBack } = useTelegramBackButton(platform, exit);
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

  return <section className={`test-session${isTelegramContext ? ' test-session--native-back' : ''}${learning ? '' : ' test-session--exam'}`} aria-label="Прохождение теста">
    <header className="test-session__top">
      {!isTelegramContext && <button className="test-session__close" onClick={requestBack} aria-label="Назад к тестам">‹</button>}
      <div className="test-session__meta"><span title={test.title}>{discipline.trim()}{category && ` · ${category.trim()}`}</span><strong>Вопрос {session.questionIndex + 1} из {questions.length}</strong>
        <div className="test-session__track" role="progressbar" aria-label="Завершённые вопросы" aria-valuemin={0} aria-valuemax={questions.length} aria-valuenow={completed}><b style={{ width: `${(completed / questions.length) * 100}%` }} /></div>
        <div className="test-session__context"><p className="test-session__mode">{learning ? 'Обучение' : 'Экзамен'}</p>{streak >= 2 && <span className="test-streak" role="status">{streak} подряд</span>}</div>
      </div>
      <span className={`test-session__score ${!learning && session.secondsLeft < 60 ? 'urgent' : ''}`}>{!learning ? `◷ ${session.timeLabel}` : `${session.score} верно`}</span>
    </header>
    <div className="test-session__content" ref={contentRef}>
      <div className="test-question" key={session.question.id}>
        <h2 id="test-question-title">{session.question.text}</h2>
        {/* Future media can be rendered here without changing the question's scroll boundary. */}
        <div className="test-session__options" role="group" aria-labelledby="test-question-title">
          {session.question.answers.map((answer, index) => {
            const state = answerState(index, session.selectedAnswer, checked ? session.confirmedAnswer : null, session.question!.correctAnswer);
            return <button key={`${session.question!.id}-${index}`} className={`test-choice ${state}`} aria-pressed={session.selectedAnswer === index} disabled={checked} onClick={() => { if (learning) session.confirmAnswer(index); else session.selectAnswer(index); }}>
              <span className="test-choice__radio" aria-hidden="true"><i /></span><span className="test-choice__text">{answer}</span><b className="test-choice__mark" aria-hidden="true">{state === 'correct' ? '✓' : state === 'wrong' ? '×' : ''}</b>
            </button>;
          })}
        </div>
        {checked && <span className="test-answer-status" role="status">{session.confirmedAnswer === session.question.correctAnswer ? 'Правильно' : 'Ответ неверный. Правильный ответ выделен.'}</span>}
      </div>
    </div>
    <footer className="test-session__footer"><div className="test-session__footer-actions">
      <button className="test-session__skip" disabled={checked} onClick={session.skip}>Пропустить</button>
      <button className="test-session__action" disabled={session.selectedAnswer === null || (learning && !checked)} onClick={submit}>{actionLabel}</button>
    </div>{!learning && <small className="test-session__footer-note">Ответы проверим после завершения экзамена</small>}</footer>
  </section>;
}

/** Same presentation/CSS, driven exclusively by a confirmed server snapshot. */
export function ServerTestSession({ attempt, platform, busy, seconds, onExit, onAction, status }: {
    attempt: import('../../backend/attempts').Attempt;
    platform: TelegramPlatform;
    busy: boolean;
    seconds: number;
    onExit: () => void;
    onAction: (action: 'submit' | 'draft' | 'advance' | 'skip' | 'finish' | 'navigate', value?: string | number) => void;
    status: import('react').ReactNode;
}) {
    const { isTelegramContext, requestBack } = useTelegramBackButton(platform, onExit, true, false);
    const content = useRef<HTMLDivElement>(null);
    const item = attempt.current_item;
    useEffect(() => { content.current?.scrollTo(0, 0); }, [item?.id]);
    if (!item)
        return null;
    const learning = attempt.mode === 'learning', checked = learning && item.state === 'checked';
    const feedback = checked ? item.feedback : undefined;
    const completed = attempt.current_position + (checked ? 1 : 0);
    return <section className={`test-session${isTelegramContext ? ' test-session--native-back' : ''}${learning ? '' : ' test-session--exam'}`} aria-label="Прохождение теста">
    <header className="test-session__top">
      {!isTelegramContext && <button className="test-session__close" onClick={requestBack} aria-label="Назад к тестам">‹</button>}
      <div className="test-session__meta"><span title={attempt.title}>{attempt.title}</span><strong>Вопрос {attempt.current_position + 1} из {attempt.total}</strong>
        <div className="test-session__track" role="progressbar" aria-label="Завершённые вопросы" aria-valuemin={0} aria-valuemax={attempt.total} aria-valuenow={completed}><b style={{ width: `${completed / attempt.total * 100}%` }}/></div>
        <div className="test-session__context"><p className="test-session__mode">{learning ? 'Обучение' : 'Экзамен'}</p>{!learning && attempt.current_position > 0 && <button className="notes-back" disabled={busy} onClick={() => onAction('navigate', attempt.current_position - 1)}>Предыдущий вопрос</button>}</div>
      </div>
      {!learning && <span className={`test-session__score ${seconds < 60 ? 'urgent' : ''}`} aria-label="Осталось времени">◷ {Math.floor(seconds / 60)}:{String(seconds % 60).padStart(2, '0')}</span>}
    </header>
    <div className="test-session__content" ref={content}>
      {status}
      <div className="test-question"><h2 id="test-question-title">{item.text}</h2>
        <div className="test-session__options" role="group" aria-labelledby="test-question-title">
          {item.options.map(option => {
            const selected = item.selected_option_ids.includes(option.id);
            const state = feedback ? (feedback.correct_option_ids.includes(option.id) ? 'correct' : selected ? 'wrong' : '') : selected ? 'selected' : '';
            return <button key={option.id} className={`test-choice ${state}`} aria-pressed={selected} disabled={busy || checked} onClick={() => onAction(learning ? 'submit' : 'draft', !learning && selected ? undefined : option.id)}><span className="test-choice__radio" aria-hidden="true"><i /></span><span className="test-choice__text">{option.text}</span><b className="test-choice__mark" aria-hidden="true">{state === 'correct' ? '✓' : state === 'wrong' ? '×' : ''}</b></button>;
        })}
        </div>
        {feedback && <><span className="test-answer-status" role="status">{feedback.is_correct ? 'Правильно' : 'Ответ неверный. Правильный ответ выделен.'}</span>{feedback.explanation && <p className="study-note">{feedback.explanation}</p>}</>}
      </div>
    </div>
    <footer className="test-session__footer"><div className="test-session__footer-actions">
      <button className="test-session__skip" disabled={busy || checked} onClick={() => onAction('skip')}>Пропустить</button>
      <button className="test-session__action" disabled={busy || (learning && !checked)} onClick={() => onAction(attempt.current_position === attempt.total - 1 ? 'finish' : 'advance')}>{attempt.current_position === attempt.total - 1 ? (learning ? 'Завершить тест' : 'Завершить экзамен') : 'Далее'}</button>
    </div>{!learning && <small className="test-session__footer-note">Ответы проверим после завершения экзамена</small>}</footer>
  </section>;
}
