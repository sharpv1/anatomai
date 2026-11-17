import { useEffect, useMemo, useState } from 'react';
import { questionsForTest } from './data';
import { resultSummary } from './presentation';
import type { TestResultData } from './types';
import type { TelegramPlatform } from '../../platform/telegram/TelegramPlatformAdapter';

type TestResultProps = { result: TestResultData; platform: TelegramPlatform; onBack: () => void; onRetake: () => void };
export function TestResult({ result, platform, onBack, onRetake }: TestResultProps) {
  const [showReview, setShowReview] = useState(false);
  useEffect(() => {
    platform.showBackButton(onBack);
    window.addEventListener('popstate', onBack);
    return () => { platform.hideBackButton(); window.removeEventListener('popstate', onBack); };
  }, [onBack, platform]);
  const { percent, wrong, skipped } = resultSummary(result);
  const questions = useMemo(() => questionsForTest(result.test.id), [result.test.id]);
  const submittedIds = new Set(result.answers.map(answer => answer.questionId));
  const reviewAnswers = [
    ...result.answers.filter(answer => answer.selectedAnswer !== answer.correctAnswer),
    ...questions.filter(question => !submittedIds.has(question.id)).slice(0, Math.max(0, result.total - result.answers.length)).map(question => ({ questionId: question.id, selectedAnswer: null, correctAnswer: question.correctAnswer })),
  ];
  const hasReview = reviewAnswers.length > 0;
  const title = percent === 100 ? 'Все ответы верные' : percent >= 80 ? 'Отличный результат' : percent >= 60 ? 'Хорошая база' : 'Материал стоит повторить';
  return <section className="test-result" aria-label="Результат теста">
    <p className="eyebrow">{result.mode === 'exam' ? 'Экзамен завершён' : 'Тест завершён'}</p>
    <div className={`test-result__badge ${percent < 60 ? 'low' : ''}`}><strong>{percent}%</strong></div>
    <h1>{title}</h1>
    <p className="test-result__test">{result.test.title}</p>
    <div className="test-result__progress" role="progressbar" aria-label="Правильные ответы" aria-valuemin={0} aria-valuemax={100} aria-valuenow={percent}><span style={{ transform: `scaleX(${Math.max(0, Math.min(100, percent)) / 100})` }} /></div>
    <div className="test-result__stats">
      <div><strong>{result.score}</strong><span>Правильных</span></div>
      <div><strong>{wrong}</strong><span>Ошибок</span></div>
      <div><strong>{skipped}</strong><span>Пропущено</span></div>
    </div>
    <p className="test-result__caption">Верных ответов · {result.score} из {result.total}</p>
    <p className="test-result__time">Фактическое время: <strong>{Math.floor(result.durationSeconds / 60)} мин {result.durationSeconds % 60} сек</strong></p>
    <div className="test-result__actions">
      {hasReview && <button className="test-session__action" aria-expanded={showReview} aria-controls="test-review" onClick={() => setShowReview(value => !value)}>{showReview ? 'Скрыть разбор' : 'Разобрать ошибки'}</button>}
      <button className="test-result__secondary" onClick={onRetake}>Пройти ещё раз</button>
      <button className={hasReview ? 'test-result__secondary' : 'test-session__action'} onClick={onBack}>К тестам</button>
    </div>
    {showReview && <div className="test-review" id="test-review" aria-label="Разбор ответов">
      {reviewAnswers.map(answer => {
        const question = questions.find(item => item.id === answer.questionId);
        const questionNumber = questions.findIndex(item => item.id === answer.questionId) + 1;
        return <article className="test-review__item wrong" key={answer.questionId}>
          <strong>{questionNumber > 0 ? `${questionNumber}. ` : ''}{answer.selectedAnswer === null ? 'Пропуск' : 'Ошибка'}</strong>
          {question && <p>{question.text}</p>}
          <span>{answer.selectedAnswer === null ? 'Ответ не выбран' : `Ваш ответ: ${String.fromCharCode(65 + answer.selectedAnswer)}`}</span>
          <small>Правильный ответ: {String.fromCharCode(65 + answer.correctAnswer)}{question ? ` · ${question.answers[answer.correctAnswer]}` : ''}</small>
        </article>;
      })}
    </div>}
  </section>;
}
