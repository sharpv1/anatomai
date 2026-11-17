import type { TestAnswer } from './types';

export function answerState(index: number, selected: number | null, confirmed: number | null, correct: number) {
  if (confirmed !== null && index === correct) return 'correct';
  if (confirmed !== null && index === confirmed) return 'wrong';
  return selected === index ? 'selected' : 'idle';
}

export function correctStreak(answers: TestAnswer[], confirmed: number | null, correct: number) {
  if (confirmed !== null && confirmed !== correct) return 0;
  let streak = confirmed === correct ? 1 : 0;
  for (let i = answers.length - 1; i >= 0; i--) {
    if (answers[i].selectedAnswer === null || answers[i].selectedAnswer !== answers[i].correctAnswer) break;
    streak++;
  }
  return streak;
}
