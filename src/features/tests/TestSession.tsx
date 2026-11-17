import { useCallback, useEffect, useState } from 'react';
import { questionsForTest } from './data';
import { useTestSession } from './useTestSession';
import type { TestDefinition, TestMode, TestResultData } from './types';
import type { TelegramPlatform } from '../../platform/telegram/TelegramPlatformAdapter';
import './TestSession.css';

type TestSessionProps = { test: TestDefinition; platform: TelegramPlatform; onComplete: (result: TestResultData) => void; onExit: () => void };

export function TestSession({ test, platform, onComplete, onExit }: TestSessionProps) {
  const questions = questionsForTest(test.id);
  const [mode, setMode] = useState<TestMode | null>(null);
  const session = useTestSession(test, questions, mode ?? 'learning', onComplete);
  const [discipline, category = ''] = test.title.split(':');
  const exit = useCallback(() => { if (!session.isDirty || window.confirm('Выйти из теста? Прогресс будет потерян.')) onExit(); }, [onExit, session.isDirty]);
  useEffect(() => { platform.showBackButton(exit); const onPopState = () => exit(); window.addEventListener('popstate', onPopState); return () => { platform.hideBackButton(); window.removeEventListener('popstate', onPopState); }; }, [exit, platform]);

  if (!mode) return <section className="test-mode-picker"><div className="test-mode-picker__icon">{test.icon}</div><p className="eyebrow">{discipline.trim()}</p><h1>Выберите режим</h1><p className="test-mode-picker__hint">Один тест — два способа пройти материал. Режим можно выбрать заново при следующем запуске.</p><div className="test-mode-options"><button className="test-mode-card" onClick={() => setMode('learning')}><span>📖</span><strong>Обучение</strong><small>Выберите ответ и сразу получите объяснение. Идеально для повторения.</small><b>Без таймера · с подсказками</b></button><button className="test-mode-card" onClick={() => setMode('exam')}><span>🎯</span><strong>Экзамен</strong><small>Ответы проверяются только в конце. Пропуски и время учитываются в результате.</small><b>{questions.length} вопросов · {test.examMinutes} минут</b></button></div><button className="test-mode-back" onClick={onExit}>Вернуться к тестам</button></section>;
  if (!session.question) return null;
  const checked = session.confirmedAnswer !== null;
  const isLast = session.questionIndex === questions.length - 1;
  const canAdvance = mode === 'learning' ? checked : session.selectedAnswer !== null;
  return <section className="test-session" aria-label="Прохождение теста">
    <header className="test-session__top"><button className="test-session__close" onClick={exit} aria-label="Закрыть тест">×</button><div className="test-session__meta"><span>{discipline.trim()} {category && <><i>·</i> {category.trim()}</>}</span><strong>Вопрос {session.questionIndex + 1} из {questions.length}</strong><i className="test-session__track"><b style={{ width: `${((session.questionIndex + 1) / questions.length) * 100}%` }} /></i></div><span className={`test-session__score ${mode === 'exam' && session.secondsLeft < 60 ? 'urgent' : ''}`}>{mode === 'exam' ? `⏱ ${session.timeLabel}` : `${session.score} верно`}</span></header>
    <main className="test-session__content"><p className="test-session__mode">{mode === 'exam' ? 'Экзамен' : 'Режим обучения'}</p><h2>{session.question.text}</h2><div className="test-session__options" role="radiogroup" aria-label="Варианты ответа">{session.question.answers.map((answer, index) => { const correct = checked && index === session.question?.correctAnswer; const wrong = checked && index === session.confirmedAnswer && !correct; const selected = session.selectedAnswer === index; return <button key={answer} className={`test-choice ${selected ? 'selected' : ''} ${correct ? 'correct' : ''} ${wrong ? 'wrong' : ''}`} aria-pressed={selected} disabled={checked} onClick={() => { platform.hapticSelection(); if (mode === 'learning') session.confirmAnswer(index); else session.selectAnswer(index); }}><span className="test-choice__radio"><i /></span><span className="test-choice__letter">{String.fromCharCode(65 + index)}</span><span className="test-choice__text">{answer}</span>{correct && <b className="test-choice__mark">✓</b>}{wrong && <b className="test-choice__mark">×</b>}</button>; })}</div>{checked && <div className="test-explanation" role="status"><strong>{session.confirmedAnswer === session.question.correctAnswer ? 'Правильно' : 'Разберём ответ'}</strong><p>{session.question.explanation}</p></div>}</main>
    <footer className="test-session__footer"><div className="test-session__footer-actions">{(!canAdvance || mode === 'exam') && <button className="test-session__skip" onClick={session.skip}>{mode === 'exam' ? 'Пропустить' : 'Пропустить вопрос'}</button>}<button className="test-session__action" disabled={!canAdvance} onClick={() => { platform.hapticImpact(); session.next(); }}>{mode === 'exam' ? (isLast ? 'Завершить экзамен' : 'Далее') : (isLast ? 'Завершить тест' : 'Далее')}</button></div>{mode === 'exam' && <small className="test-session__footer-note">Ответы сохраняются на этом устройстве до завершения</small>}</footer>
  </section>;
}
