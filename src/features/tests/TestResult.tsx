import { useEffect, useMemo, useState } from 'react';
import { questionsForTest } from './data';
import type { TestResultData } from './types';
import type { TelegramPlatform } from '../../platform/telegram/TelegramPlatformAdapter';

type TestResultProps = { result: TestResultData; platform: TelegramPlatform; onBack: () => void; onRetake: () => void };
export function TestResult({ result, platform, onBack, onRetake }: TestResultProps) {
  const [showReview, setShowReview] = useState(false);
  useEffect(() => { platform.showBackButton(onBack); window.addEventListener('popstate', onBack); return () => { platform.hideBackButton(); window.removeEventListener('popstate', onBack); }; }, [onBack, platform]);
  const percent = result.total ? Math.round((result.score / result.total) * 100) : 0;
  const wrong = result.answers.filter((answer) => answer.selectedAnswer !== null && answer.selectedAnswer !== answer.correctAnswer).length;
  const skipped = result.answers.filter((answer) => answer.selectedAnswer === null).length;
  const reviewAnswers = result.answers.filter((answer) => answer.selectedAnswer !== answer.correctAnswer);
  const questions = useMemo(() => questionsForTest(result.test.id), [result.test.id]);
  const title = percent === 100 ? 'Все ответы верные' : percent >= 80 ? 'Отличный результат' : percent >= 60 ? 'Хорошая база' : 'Материал стоит повторить';
  return <section className="test-result"><div className={`test-result__badge ${percent < 60 ? 'low' : ''}`}><strong>{percent}%</strong></div><p className="eyebrow">{result.mode === 'exam' ? 'Экзамен завершён' : 'Тест завершён'}</p><h1>{title}</h1><p className="test-result__test">{result.test.title}</p><div className="test-result__stats"><div><strong>{result.score}</strong><span>Правильных</span></div><div><strong>{wrong}</strong><span>Ошибок</span></div><div><strong>{skipped}</strong><span>Пропущено</span></div></div><p className="test-result__caption">Верных ответов · {result.score} из {result.total}</p><p className="test-result__time">Фактическое время: <strong>{Math.floor(result.durationSeconds / 60)} мин {result.durationSeconds % 60} сек</strong></p><div className="test-result__actions">{reviewAnswers.length > 0 && <button className="test-session__action" onClick={() => setShowReview((value) => !value)}>{showReview ? 'Скрыть разбор' : 'Разобрать ошибки'}</button>}<button className="test-result__secondary" onClick={onRetake}>Пройти ещё раз</button><button className="test-result__secondary" onClick={onBack}>К тестам</button></div>{showReview && <div className="test-review" aria-label="Разбор ответов">{reviewAnswers.map((answer, index) => { const question = questions.find((item) => item.id === answer.questionId); const isCorrect = answer.selectedAnswer === answer.correctAnswer; return <article className={`test-review__item ${isCorrect ? 'right' : 'wrong'}`} key={answer.questionId}><strong>{index + 1}. {isCorrect ? 'Верно' : answer.selectedAnswer === null ? 'Пропуск' : 'Ошибка'}</strong><p>{question?.text}</p><span>{answer.selectedAnswer === null ? 'Ответ не выбран' : `Ваш ответ: ${String.fromCharCode(65 + answer.selectedAnswer)}`}</span><small>Правильный ответ: {String.fromCharCode(65 + answer.correctAnswer)}{question ? ` · ${question.answers[answer.correctAnswer]}` : ''}</small></article>; })}</div>}</section>;
}
