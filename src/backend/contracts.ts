/** Read-only DTOs match backend/app/{identity,content,progress}/schemas.py. */
export type User = {
    id: string;
    telegram_user_id: string;
    first_name: string;
    last_name: string | null;
    username: string | null;
    photo_url: string | null;
    timezone: string;
    language: string;
    version: number;
    roles: string[];
};
export type Session = {
    id: string;
    user: User;
    csrf_token: string;
    expires_at: string;
    idle_expires_at: string;
};
export type Discipline = {
    id: string;
    slug: string;
    title: string;
    icon_key: string;
    color_token: string;
    question_count: number;
    topic_count: number;
    note_count: number;
};
export type Topic = {
    id: string;
    discipline_id: string;
    category_id: string | null;
    slug: string;
    title: string;
    question_count: number;
    test_definition_id: string | null;
    available_modes: ('learning' | 'exam')[];
};
export type Test = {
    id: string;
    topic_id: string;
    slug: string;
    title: string;
    exam_duration_seconds: number;
    question_count: number;
    available_modes: ('learning' | 'exam')[];
};
export type Summary = {
    completed_tests: number;
    answered_count: number;
    correct_count: number;
    wrong_count: number;
    skipped_count: number;
    average_percent: number | null;
    practice_seconds: number | null;
    activity_streak_days: number;
    period: 'all' | 'week' | 'month';
    timezone: string;
    data_scope: 'server_history';
    calculated_at: string;
};
export type Result = {
    attempt_id: string;
    title: string;
    total: number;
    correct: number;
    wrong: number;
    skipped: number;
    answered: number;
    percent: number;
    duration_seconds: number;
    started_at: string;
    finalized_at: string;
    finish_reason: 'last_question' | 'user_finish' | 'timeout';
};
export type HistoryItem = {
    id: string;
    mode: 'learning' | 'exam';
    discipline_id: string;
    topic_id: string | null;
    test_definition_id: string | null;
    result: Result;
    activity_date: string;
    activity_timezone: string;
};
// Continue metadata only: never adapt an attempt into the local test engine.
export type ActiveAttempt = {
    id: string;
    mode: 'learning' | 'exam';
    title: string;
    status: 'in_progress';
    total: number;
    current_position: number;
};
export type Home = {
    statistics: Summary;
    active_attempt: ActiveAttempt | null;
    recent_results: HistoryItem[];
};
export type Recommendation = {
    topic_id: string;
    discipline_id: string;
    title: string;
    question_count: number;
    reason: 'weak_topic';
    observed_average_percent: number;
    observed_attempts: number;
};
export type Daily = {
    local_date: string;
    timezone: string;
    topic_id: string | null;
    title: string | null;
    discipline_id: string | null;
    question_count: number | null;
    availability: 'available' | 'withdrawn' | 'empty';
    catalog_version: number;
    selector_version: 1;
};
export type Achievement = {
    code: string;
    title: string;
    state: 'unlocked' | 'locked' | 'not_configured';
    condition: string;
    progress: number | null;
    target: number | null;
    granted_at: null;
};
export type Progress = {
    statistics: Summary;
    unattributed_topic_responses: number;
    source: 'immutable_attempts';
};
export type Activity = {
    timezone: string;
    date_policy: 'frozen_attempt_timezone';
    start: string;
    end: string;
    days: {
        date: string;
        completed_tests: number;
        answered_count: number;
        correct_count: number;
        practice_seconds: number;
        average_percent: number | null;
    }[];
};
export type TopicSummary = {
    topic_id: string;
    completed_count: number;
    best_percent: number | null;
    ever_wrong_question_count: number | null;
    unresolved_wrong_question_count: number | null;
    favorites_count: number | null;
    favorites_status: 'not_configured';
};
export type NoteSummary = {
    id: string;
    discipline_id: string;
    topic_id: string | null;
    title: string;
};
export type Note = NoteSummary & {
    revision_id: string;
    body: string | null;
    body_format: 'plain_text';
    asset_id: string | null;
    download_available: boolean;
};
export type Reference = {
    question_id: string;
    revision_id: string;
    number: number;
    kind: 'single_choice';
    text: string;
    options: {
        id: string;
        position: number;
        code: string;
        text: string;
    }[];
    correct_option_ids: string[];
};
export type Page<T> = {
    data: T[];
    page: {
        has_more: boolean;
        next_cursor: string | null;
        total?: number;
    };
    catalog_version?: number;
};
export type Decoder<T> = (v: unknown) => T;
function object(v: unknown): Record<string, unknown> {
    if (!v || typeof v !== 'object' || Array.isArray(v))
        throw Error('INVALID_DTO');
    return v as Record<string, unknown>;
}
const str = (v: unknown): v is string => typeof v === 'string';
const num = (v: unknown): v is number => Number.isSafeInteger(v) && Number(v) >= 0;
const nullable = (v: unknown) => v === null || num(v);
function timestamp(v: unknown): v is string { return str(v) && Number.isFinite(Date.parse(v)); }
function timezone(v: unknown): v is string { if (!str(v))
    return false; try {
    new Intl.DateTimeFormat('ru', { timeZone: v });
    return true;
}
catch {
    return false;
} }
function checked<T>(v: unknown, test: (o: Record<string, unknown>) => boolean): T {
    const o = object(v);
    if (!test(o))
        throw Error('INVALID_DTO');
    return v as T;
}
export const user: Decoder<User> = v => checked(v, o => str(o.id) && str(o.telegram_user_id) && str(o.first_name) && timezone(o.timezone) && str(o.language) && (o.photo_url === null || str(o.photo_url)) && (o.last_name === null || str(o.last_name)) && (o.username === null || str(o.username)) && num(o.version) && Array.isArray(o.roles) && o.roles.every(str));
export const session: Decoder<Session> = v => {
    const o = object(v);
    const u = user(o.user);
    if (!str(o.id) || !str(o.csrf_token) || !o.csrf_token || !str(o.expires_at) || !Number.isFinite(Date.parse(o.expires_at)) || !str(o.idle_expires_at) || !Number.isFinite(Date.parse(o.idle_expires_at)))
        throw Error('INVALID_DTO');
    return { ...o, user: u } as Session;
};
export const discipline: Decoder<Discipline> = v => checked(v, o => str(o.id) && str(o.title) && str(o.slug) && str(o.icon_key) && str(o.color_token) && num(o.question_count) && num(o.topic_count) && num(o.note_count));
export const topic: Decoder<Topic> = v => checked(v, o => str(o.id) && str(o.discipline_id) && str(o.title) && num(o.question_count) && Array.isArray(o.available_modes) && o.available_modes.every(m => m === 'learning' || m === 'exam') && (o.test_definition_id === null || str(o.test_definition_id)));
export const test: Decoder<Test> = v => checked(v, o => str(o.id) && str(o.topic_id) && str(o.title) && num(o.question_count) && num(o.exam_duration_seconds) && Array.isArray(o.available_modes) && o.available_modes.every(m => m === 'learning' || m === 'exam'));
export const summary: Decoder<Summary> = v => checked(v, o => ['completed_tests', 'answered_count', 'correct_count', 'wrong_count', 'skipped_count', 'activity_streak_days'].every(k => num(o[k])) && nullable(o.average_percent) && Number(o.average_percent) <= 100 && nullable(o.practice_seconds) && str(o.timezone) && str(o.calculated_at) && o.data_scope === 'server_history' && ['all', 'week', 'month'].includes(String(o.period)));
export const result: Decoder<Result> = v => checked(v, o => str(o.attempt_id) && str(o.title) && ['total', 'correct', 'wrong', 'skipped', 'answered', 'percent', 'duration_seconds'].every(k => num(o[k])) && Number(o.percent) <= 100 && timestamp(o.started_at) && timestamp(o.finalized_at) && ['last_question', 'user_finish', 'timeout'].includes(String(o.finish_reason)));
export const history: Decoder<HistoryItem> = v => { const o = object(v); result(o.result); return checked(v, r => str(r.id) && (r.mode === 'learning' || r.mode === 'exam') && str(r.discipline_id) && str(r.activity_date) && timezone(r.activity_timezone)); };
export const home: Decoder<Home> = v => {
    const o = object(v);
    summary(o.statistics);
    array(history)(o.recent_results);
    if (o.active_attempt !== null) {
        checked(o.active_attempt, a => str(a.id) && str(a.title) && (a.mode === 'learning' || a.mode === 'exam') && a.status === 'in_progress' && num(a.total) && num(a.current_position));
    }
    return v as Home;
};
export const recommendation: Decoder<Recommendation> = v => checked(v, o => str(o.topic_id) && str(o.discipline_id) && str(o.title) && num(o.question_count) && num(o.observed_average_percent) && num(o.observed_attempts) && o.reason === 'weak_topic');
export const daily: Decoder<Daily> = v => checked(v, o => str(o.local_date) && str(o.timezone) && ['available', 'withdrawn', 'empty'].includes(String(o.availability)) && num(o.catalog_version) && o.selector_version === 1 && (o.availability !== 'available' || (str(o.topic_id) && str(o.title) && str(o.discipline_id) && num(o.question_count))));
export const achievement: Decoder<Achievement> = v => checked(v, o => str(o.code) && str(o.title) && str(o.condition) && ['unlocked', 'locked', 'not_configured'].includes(String(o.state)) && nullable(o.progress) && nullable(o.target) && o.granted_at === null);
export const progress: Decoder<Progress> = v => { const o = object(v); summary(o.statistics); return checked(v, r => num(r.unattributed_topic_responses) && r.source === 'immutable_attempts'); };
export const activity: Decoder<Activity> = v => { const o = object(v); array(x => checked(x, d => str(d.date) && ['completed_tests', 'answered_count', 'correct_count', 'practice_seconds'].every(k => num(d[k])) && nullable(d.average_percent)))(o.days); return checked(v, r => str(r.timezone) && str(r.start) && str(r.end) && r.date_policy === 'frozen_attempt_timezone'); };
export const topicSummary: Decoder<TopicSummary> = v => checked(v, o => str(o.topic_id) && num(o.completed_count) && ['best_percent', 'ever_wrong_question_count', 'unresolved_wrong_question_count', 'favorites_count'].every(k => nullable(o[k])) && o.favorites_status === 'not_configured');
export const noteSummary: Decoder<NoteSummary> = v => checked(v, o => str(o.id) && str(o.discipline_id) && str(o.title) && (o.topic_id === null || str(o.topic_id)));
export const note: Decoder<Note> = v => { noteSummary(v); return checked(v, o => str(o.revision_id) && (o.body === null || str(o.body)) && o.body_format === 'plain_text' && (o.asset_id === null || str(o.asset_id)) && typeof o.download_available === 'boolean'); };
export const reference: Decoder<Reference> = v => {
    const o = object(v);
    const opts = array(x => checked<Reference['options'][number]>(x, r => str(r.id) && num(r.position) && str(r.text) && str(r.code)))(o.options);
    if (opts.length < 2 || opts.length > 8 || !Array.isArray(o.correct_option_ids) || o.correct_option_ids.length !== 1 || !o.correct_option_ids.every(id => str(id) && opts.some(p => p.id === id)))
        throw Error('INVALID_DTO');
    return checked(v, r => str(r.question_id) && str(r.revision_id) && num(r.number) && r.kind === 'single_choice' && str(r.text));
};
export function array<T>(decode: Decoder<T>): Decoder<T[]> {
    return v => {
        if (!Array.isArray(v))
            throw Error('INVALID_DTO');
        return v.map(decode);
    };
}
export function page<T>(decode: Decoder<T>): Decoder<Page<T>> {
    return v => {
        const o = object(v), p = object(o.page);
        if (typeof p.has_more !== 'boolean' || (p.next_cursor !== null && !str(p.next_cursor)) || (p.has_more && !p.next_cursor))
            throw Error('INVALID_DTO');
        return { data: array(decode)(o.data), page: p as Page<T>['page'], ...(num(o.catalog_version) ? { catalog_version: o.catalog_version } : {}) };
    };
}
export function envelope<T>(v: unknown, decode: Decoder<T>): T {
    const o = object(v), m = object(o.meta);
    if (!str(m.request_id) || !str(m.server_time) || !('data' in o))
        throw Error('INVALID_ENVELOPE');
    return decode(o.data);
}
export function listEnvelope<T>(v: unknown, decode: Decoder<T>): Page<T> { const o = object(v); object(o.meta); return page(decode)(o); }
