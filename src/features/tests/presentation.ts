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

// View-only summary: unsubmitted questions count as unanswered, never as correct.
// The test engine and saved result are not modified.
export function resultSummary(result: { total: number; score: number; answers: TestAnswer[] }) {
  const wrong = result.answers.filter(answer => answer.selectedAnswer !== null && answer.selectedAnswer !== answer.correctAnswer).length;
  const skipped = result.answers.filter(answer => answer.selectedAnswer === null).length + Math.max(0, result.total - result.answers.length);
  return { percent: result.total ? Math.round(result.score / result.total * 100) : 0, wrong, skipped };
}
