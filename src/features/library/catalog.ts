import { demoTests, questionsForTest } from '../tests/data';

// Only loaded questions are counted. Demo progress/meta are not user statistics.
export const catalog = demoTests.map(test => ({ test, questionCount: questionsForTest(test.id).length }));
export const disciplines = catalog.map(({ test }) => ({ id: test.id, title: test.title.split(':')[0].trim(), icon: test.icon, color: test.color }));
export const levels = [...new Set(catalog.map(({ test }) => test.level))];
export const normalizeSearch = (value: string) => value.trim().toLocaleLowerCase('ru').replaceAll('ё', 'е');
export function matchesSearch(text: string, query: string) { return normalizeSearch(text).includes(normalizeSearch(query)); }

// Display-only Telegram launch data, never used for authorization or statistics.
export function profileDisplayName(initData: string | undefined): string | null {
  try {
    const raw: unknown = JSON.parse(new URLSearchParams(initData).get('user') ?? 'null');
    if (!raw || typeof raw !== 'object') return null;
    const user = raw as Record<string, unknown>;
    const name = [user.first_name, user.last_name].filter((v): v is string => typeof v === 'string' && Boolean(v.trim())).join(' ').trim();
    return name || (typeof user.username === 'string' && user.username.trim() ? `@${user.username.trim()}` : null);
  } catch { return null; }
}
