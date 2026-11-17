export type TestFilter = 'all' | 'active' | 'new';
export type TestMode = 'learning' | 'exam';

export type TestDefinition = {
  id: string; icon: string; title: string; meta: string; level: string; progress: number;
  color: 'blue' | 'mint' | 'violet' | 'orange'; examMinutes: number;
};
export type TestQuestion = { id: string; text: string; answers: string[]; correctAnswer: number; explanation: string };
export type TestAnswer = { questionId: string; selectedAnswer: number | null; correctAnswer: number };
export type TestResultData = { test: TestDefinition; mode: TestMode; total: number; score: number; answered: number; answers: TestAnswer[]; durationSeconds: number };
