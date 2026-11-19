/** Stable local-calendar selection over the existing loaded catalog. */
export function localDayKey(date: Date) {
  return `${date.getFullYear()}-${date.getMonth() + 1}-${date.getDate()}`;
}
export function millisecondsToNextLocalDay(date: Date) {
  return new Date(date.getFullYear(), date.getMonth(), date.getDate() + 1).getTime() - date.getTime() + 20;
}
export function selectDailyTopic<T extends { test: { id: string }; questionCount: number }>(catalog: readonly T[], date: Date): T | null {
  if (!Number.isFinite(date.getTime())) return null;
  const available = catalog.filter(item => item.questionCount > 0)
    .slice().sort((a, b) => a.test.id < b.test.id ? -1 : a.test.id > b.test.id ? 1 : 0);
  if (!available.length) return null;
  // Construct UTC from LOCAL components: DST/UTC midnight cannot change the date.
  const day = Math.floor(Date.UTC(date.getFullYear(), date.getMonth(), date.getDate()) / 86400000);
  return available[((day % available.length) + available.length) % available.length];
}
