import type { TestQuestion } from './types';

/** Read-only projection; does not change the test engine's single-answer model. */
export type ReviewQuestion = Omit<TestQuestion, 'correctAnswer' | 'explanation'> & {
  correctAnswer: number | readonly number[];
  explanation?: string;
};
export const REVIEW_BATCH_SIZE = 30;

export function correctReviewAnswers(question: ReviewQuestion): ReadonlySet<number> {
  const supplied = typeof question.correctAnswer === 'number'
    ? [question.correctAnswer] : Array.isArray(question.correctAnswer) ? question.correctAnswer : [];
  return new Set(supplied.filter(index => Number.isInteger(index) && index >= 0 && index < question.answers.length));
}

export function findReviewQuestions(questions: readonly ReviewQuestion[], query: string) {
  const normalize = (text: string) => text.normalize('NFC').toLocaleLowerCase('ru').replace(/ё/g, 'е');
  const words = normalize(query).trim().split(/\s+/).filter(Boolean);
  return questions.map((question, index) => ({ question, number: index + 1 }))
    .filter(({ question }) => words.every(word => normalize(question.text).includes(word)));
}
