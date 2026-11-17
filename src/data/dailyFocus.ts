export type DailyFocusMetrics = {
  streakLabel: string;
  xpLabel: string;
};

// Presentation-only demo values. Replace this source with real statistics later;
// rendering these labels does not award XP or record activity.
export const demoDailyFocusMetrics: DailyFocusMetrics = {
  streakLabel: '🔥 5 дней подряд',
  xpLabel: '✦ +120 XP за сегодня',
};
