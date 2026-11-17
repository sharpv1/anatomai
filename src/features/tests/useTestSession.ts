import { useCallback, useEffect, useMemo, useState } from 'react';
import type { TestAnswer, TestDefinition, TestMode, TestQuestion, TestResultData } from './types';

export function useTestSession(test: TestDefinition, questions: TestQuestion[], mode: TestMode, onComplete: (result: TestResultData) => void) {
  const [questionIndex, setQuestionIndex] = useState(0);
  const [selectedAnswer, setSelectedAnswer] = useState<number | null>(null);
  const [confirmedAnswer, setConfirmedAnswer] = useState<number | null>(null);
  const [score, setScore] = useState(0);
  const [answers, setAnswers] = useState<TestAnswer[]>([]);
  const [secondsLeft, setSecondsLeft] = useState(test.examMinutes * 60);
  const [startedAt] = useState(() => Date.now());
  const question = questions[questionIndex];
  const isLearning = mode === 'learning';
  const isChecked = isLearning && confirmedAnswer !== null;
  const isDirty = questionIndex > 0 || selectedAnswer !== null || answers.length > 0;
  const finish = useCallback((nextAnswers: TestAnswer[], nextScore: number) => onComplete({ test, mode, total: questions.length, score: nextScore, answered: nextAnswers.filter((item) => item.selectedAnswer !== null).length, answers: nextAnswers, durationSeconds: Math.round((Date.now() - startedAt) / 1000) }), [mode, onComplete, questions.length, startedAt, test]);
  useEffect(() => { if (isLearning || secondsLeft <= 0) return; const timer = window.setInterval(() => setSecondsLeft((value) => Math.max(0, value - 1)), 1000); return () => window.clearInterval(timer); }, [isLearning, secondsLeft]);
  useEffect(() => { if (!isLearning && secondsLeft === 0 && question) { const current = { questionId: question.id, selectedAnswer, correctAnswer: question.correctAnswer }; const currentAnswers = answers.some((item) => item.questionId === question.id) ? answers : [...answers, current]; finish(currentAnswers, score + (selectedAnswer === question.correctAnswer ? 1 : 0)); } }, [answers, finish, isLearning, question, score, secondsLeft, selectedAnswer]);
  const selectAnswer = useCallback((answer: number) => { if (!isChecked) setSelectedAnswer(answer); }, [isChecked]);
  const confirmAnswer = useCallback((answer = selectedAnswer) => { if (answer === null || !question || isChecked) return; setSelectedAnswer(answer); setConfirmedAnswer(answer); if (answer === question.correctAnswer) setScore((value) => value + 1); }, [isChecked, question, selectedAnswer]);
  const next = useCallback(() => { if (!question || selectedAnswer === null || (isLearning && !isChecked)) return; const entry = { questionId: question.id, selectedAnswer, correctAnswer: question.correctAnswer }; const nextAnswers = [...answers, entry]; const nextScore = isLearning ? score : score + (selectedAnswer === question.correctAnswer ? 1 : 0); if (questionIndex === questions.length - 1) { finish(nextAnswers, nextScore); return; } setAnswers(nextAnswers); setScore(nextScore); setQuestionIndex((value) => value + 1); setSelectedAnswer(null); setConfirmedAnswer(null); }, [answers, finish, isChecked, isLearning, question, questionIndex, questions.length, score, selectedAnswer]);
  const skip = useCallback(() => { if (!question || (isLearning && isChecked)) return; const nextAnswers = [...answers, { questionId: question.id, selectedAnswer: null, correctAnswer: question.correctAnswer }]; if (questionIndex === questions.length - 1) { finish(nextAnswers, score); return; } setAnswers(nextAnswers); setQuestionIndex((value) => value + 1); setSelectedAnswer(null); setConfirmedAnswer(null); }, [answers, finish, isChecked, isLearning, question, questionIndex, questions.length, score]);
  const timeLabel = `${Math.floor(secondsLeft / 60).toString().padStart(2, '0')}:${(secondsLeft % 60).toString().padStart(2, '0')}`;
  return useMemo(() => ({ question, questionIndex, selectedAnswer, confirmedAnswer, score, answers, isChecked, isDirty, secondsLeft, timeLabel, selectAnswer, confirmAnswer, next, skip }), [answers, confirmedAnswer, confirmAnswer, isChecked, isDirty, next, question, questionIndex, score, secondsLeft, selectAnswer, selectedAnswer, skip, timeLabel]);
}
