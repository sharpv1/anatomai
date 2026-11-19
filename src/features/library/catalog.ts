import { demoTests, questionsForTest } from '../tests/data';

// Only loaded questions are counted. Demo progress/meta are not user statistics.
export const catalog = demoTests.map(test => ({ test, questionCount: questionsForTest(test.id).length }));
export const disciplines = catalog.map(({ test }) => ({ id: test.id, title: test.title.split(':')[0].trim(), icon: test.icon, color: test.color }));
export const levels = [...new Set(catalog.map(({ test }) => test.level))];
export const normalizeSearch = (value: string) => value.trim().toLocaleLowerCase('ru').replaceAll('ё', 'е');
export function matchesSearch(text: string, query: string) { return normalizeSearch(text).includes(normalizeSearch(query)); }

// Display-only Telegram data; never used to authorize a request or create statistics.
function userFromLaunchData(initData: string | undefined): unknown {
  try { return JSON.parse(new URLSearchParams(initData).get('user') ?? 'null'); } catch { return null; }
}
function displayIdentity(raw: unknown): { name: string | null; photoUrl: string | null } {
  if (!raw || typeof raw !== 'object') return { name: null, photoUrl: null };
  const user = raw as Record<string, unknown>;
  const name = [user.first_name, user.last_name].filter((v): v is string => typeof v === 'string' && Boolean(v.trim())).map(v => v.normalize('NFC').replace(/[\u0000-\u001f\u007f]/g,' ').trim().replace(/\s+/g,' ')).join(' ')
    || (typeof user.username === 'string' && user.username.trim() ? `@${user.username.trim()}` : null);
  let photoUrl: string | null = null;
  try {
    if (typeof user.photo_url === 'string') {
      const url = new URL(user.photo_url);
      if (url.protocol === 'https:' && !url.username && !url.password) photoUrl = url.href;
    }
  } catch { /* Missing/invalid images use initials. */ }
  return { name, photoUrl };
}
export function profileDisplayName(initData: string | undefined): string | null {
  return displayIdentity(userFromLaunchData(initData)).name;
}
export function telegramProfile(api?: { initData?: string; initDataUnsafe?: { user?: unknown } }) {
  const sdk=displayIdentity(api?.initDataUnsafe?.user);
  const launch=displayIdentity(userFromLaunchData(api?.initData));
  return {name:sdk.name??launch.name,photoUrl:sdk.photoUrl??launch.photoUrl};
}
