/** Server attempts only. No local question bank, result calculation or localStorage. */
import { ApiClient, ApiError } from './client';
import { envelope, result as decodeResult, type Result } from './contracts';
export type Mode = 'learning' | 'exam';
export type Option = {
    id: string;
    position: number;
    code: string;
    text: string;
};
export type Feedback = {
    is_correct: boolean;
    correct_option_ids: string[];
    explanation?: string;
};
export type Item = {
    id: string;
    question_id: string;
    revision_id: string;
    position: number;
    text: string;
    options: Option[];
    selected_option_ids: string[];
    state: 'awaiting_answer' | 'checked' | 'draft';
    feedback?: Feedback;
};
export type Attempt = {
    id: string;
    mode: Mode;
    status: 'in_progress' | 'completed' | 'abandoned';
    version: number;
    title: string;
    scope: 'discipline' | 'topic' | 'test';
    discipline_id: string;
    topic_id: string | null;
    test_definition_id: string | null;
    total: number;
    current_position: number;
    started_at: string;
    deadline_at?: string;
    remaining_seconds?: number;
    current_item: Item | null;
    result?: Result;
};
export type Scope = {
    topic_id: string;
} | {
    discipline_id: string;
} | {
    test_definition_id: string;
};
export type ReviewItem = Omit<Item, 'state' | 'feedback'> & {
    correct_option_ids: string[];
    is_correct: boolean | null;
    explanation?: string;
};
const uuid = (v: unknown): v is string => typeof v === 'string' && /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(v);
const integer = (v: unknown, min = 0): v is number => Number.isSafeInteger(v) && Number(v) >= min;
const text = (v: unknown): v is string => typeof v === 'string';
function record(v: unknown): Record<string, unknown> { if (!v || typeof v !== 'object' || Array.isArray(v))
    throw new Error('DTO'); return v as Record<string, unknown>; }
function ensure(valid: unknown): asserts valid { if (!valid)
    throw new Error('DTO'); }
function keys(v: Record<string, unknown>, allowed: string[]) { ensure(Object.keys(v).every(k => allowed.includes(k))); }
function ids(v: unknown, max: number): asserts v is string[] { ensure(Array.isArray(v) && v.length <= max && v.every(uuid) && new Set(v).size === v.length); }
function itemBase(v: unknown) {
    const i = record(v);
    ensure(uuid(i.id) && uuid(i.question_id) && uuid(i.revision_id) && integer(i.position) && text(i.text));
    ensure(Array.isArray(i.options) && i.options.length >= 2 && i.options.length <= 8);
    for (const o of i.options) {
        const p = record(o);
        keys(p, ['id', 'position', 'code', 'text']);
        ensure(uuid(p.id) && integer(p.position) && text(p.code) && text(p.text));
    }
    const options = i.options as Option[];
    ensure(new Set(options.map(o => o.id)).size === options.length);
    ids(i.selected_option_ids, 1);
    ensure(i.selected_option_ids.every(id => options.some(o => o.id === id)));
    return i;
}
export function attempt(v: unknown): Attempt {
    const a = record(v);
    keys(a, ['id', 'mode', 'status', 'version', 'title', 'scope', 'discipline_id', 'topic_id', 'test_definition_id', 'total', 'current_position', 'started_at', 'deadline_at', 'remaining_seconds', 'current_item', 'result']);
    ensure(uuid(a.id) && ['learning', 'exam'].includes(String(a.mode)) && ['in_progress', 'completed', 'abandoned'].includes(String(a.status)) && integer(a.version, 1) && text(a.title) && ['discipline', 'topic', 'test'].includes(String(a.scope)) && uuid(a.discipline_id) && (a.topic_id === null || uuid(a.topic_id)) && (a.test_definition_id === null || uuid(a.test_definition_id)) && integer(a.total, 1) && a.total <= 5000 && integer(a.current_position) && Number.isFinite(Date.parse(String(a.started_at))));
    if (a.mode === 'exam')
        ensure(Number.isFinite(Date.parse(String(a.deadline_at))) && integer(a.remaining_seconds));
    else
        ensure(!('deadline_at' in a) && !('remaining_seconds' in a));
    if (a.status === 'in_progress') {
        ensure(!('result' in a) && a.current_position < a.total);
        const i = itemBase(a.current_item);
        keys(i, ['id', 'question_id', 'revision_id', 'position', 'text', 'options', 'selected_option_ids', 'state', ...(a.mode === 'learning' && i.state === 'checked' ? ['feedback'] : [])]);
        ensure(i.position === a.current_position);
        if (a.mode === 'exam')
            ensure(i.state === 'draft');
        else if (i.state === 'awaiting_answer')
            ensure((i.selected_option_ids as string[]).length === 0);
        else {
            ensure(i.state === 'checked' && (i.selected_option_ids as string[]).length === 1);
            const f = record(i.feedback);
            keys(f, ['is_correct', 'correct_option_ids', 'explanation']);
            ids(f.correct_option_ids, 1);
            ensure(f.correct_option_ids.length === 1 && (i.options as Option[]).some(o => o.id === (f.correct_option_ids as string[])[0]) && typeof f.is_correct === 'boolean' && (!('explanation' in f) || text(f.explanation)));
        }
    }
    else {
        ensure(a.current_item === null);
        if (a.status === 'completed') {
            const r = decodeResult(a.result);
            ensure(r.attempt_id === a.id && r.total === a.total && r.correct + r.wrong + r.skipped === r.total && r.answered === r.correct + r.wrong);
        }
        else
            ensure(!('result' in a));
    }
    return v as Attempt;
}
export const activeAttempt = (v: unknown) => v === null ? null : attempt(v);
export function examReview(v: unknown): {
    items: ReviewItem[];
    total: number;
    next_offset: number | null;
} {
    const p = record(v);
    ensure(Array.isArray(p.items) && integer(p.total) && (p.next_offset === null || integer(p.next_offset)));
    for (const v of p.items) {
        const i = itemBase(v);
        keys(i, ['id', 'question_id', 'revision_id', 'position', 'text', 'options', 'selected_option_ids', 'correct_option_ids', 'is_correct', 'explanation']);
        ensure(!('explanation' in i) || text(i.explanation));
        ids(i.correct_option_ids, 1);
        ensure(i.correct_option_ids.length === 1 && (i.options as Option[]).some(o => o.id === (i.correct_option_ids as string[])[0]) && (i.is_correct === null || typeof i.is_correct === 'boolean'));
    }
    return v as {
        items: ReviewItem[];
        total: number;
        next_offset: number | null;
    };
}
export function learningReview(v: unknown): {
    items: ReviewItem[];
    next_cursor: string | null;
    has_more: boolean;
} {
    const p = record(v);
    examReview({ items: p.items, total: 0, next_offset: null });
    ensure(typeof p.has_more === 'boolean' && (p.next_cursor === null || text(p.next_cursor)));
    return v as {
        items: ReviewItem[];
        next_cursor: string | null;
        has_more: boolean;
    };
}
export const etag = (a: Attempt) => `"attempt-${a.id}-${a.version}"`;
export type Intent = Readonly<{
    path: string;
    method: 'POST' | 'PUT';
    body: string;
    key: string;
    match?: string;
}>;
export type AttemptState = {
    value: Attempt | null;
    busy: boolean;
    loaded: boolean;
    error: unknown | null;
    pending: Intent | null;
    receivedAt: number;
};
export class AttemptController {
    private state: AttemptState = { value: null, busy: false, loaded: false, error: null, pending: null, receivedAt: 0 };
    private listeners = new Set<() => void>();
    private generation = 0;
    private stopped = false;
    constructor(readonly client: ApiClient, readonly owner: string, private key = () => crypto.randomUUID(), private clock = () => performance.now()) { }
    getSnapshot = () => this.state;
    subscribe = (fn: () => void) => { this.listeners.add(fn); return () => this.listeners.delete(fn); };
    private publish(p: Partial<AttemptState>) { if (this.stopped)
        return; this.state = { ...this.state, ...p }; for (const fn of this.listeners)
        fn(); }
    dispose() { this.generation++; this.stopped = true; this.state = { value: null, busy: false, loaded: false, error: null, pending: null, receivedAt: 0 }; this.listeners.clear(); }
    private async read(id?: string) { return id ? this.client.get('/attempts/' + id, attempt) : this.client.get('/me/active-attempt', activeAttempt); }
    async refresh(id?: string) {
        if (this.state.busy || this.stopped)
            return;
        const generation = this.generation;
        this.publish({ busy: true });
        try {
            const value = await this.read(id ?? this.state.value?.id);
            if (generation === this.generation)
                this.publish({ value, loaded: true, error: null, receivedAt: this.clock() });
        }
        catch (error) {
            if (generation === this.generation)
                this.publish({ error, loaded: true });
        }
        finally {
            if (generation === this.generation)
                this.publish({ busy: false });
        }
    }
    async start(mode: Mode, scope: Scope) {
        if (this.state.busy || this.state.pending || this.stopped)
            return;
        // A known active attempt is resumed, never silently discarded or replaced.
        if (this.state.value?.status === 'in_progress') {
            await this.refresh();
            return;
        }
        return this.send(Object.freeze({ path: '/attempts', method: 'POST', body: JSON.stringify({ mode, ...scope }), key: this.key() }));
    }
    async action(action: 'submit' | 'draft' | 'advance' | 'skip' | 'finish' | 'abandon' | 'navigate', value?: string | number) {
        const a = this.state.value;
        if (!a || a.status !== 'in_progress' || this.state.busy || this.state.pending || this.stopped)
            return;
        const i = a.current_item!;
        const suffix = action === 'submit' || action === 'draft' ? `items/${i.id}/${action}` : action;
        const body = action === 'submit' || action === 'draft' ? { selected_option_ids: value ? [value] : [] } : action === 'navigate' ? { position: value } : action === 'advance' || action === 'skip' ? { item_id: i.id } : action === 'abandon' ? { reason: 'user_exit' } : {};
        return this.send(Object.freeze({ path: `/attempts/${a.id}/${suffix}`, method: action === 'draft' ? 'PUT' : 'POST', body: JSON.stringify(body), key: this.key(), match: etag(a) }));
    }
    retry = async () => { if (this.state.pending && !this.state.busy)
        await this.send(this.state.pending); };
    private async send(intent: Intent) {
        const generation = this.generation;
        this.publish({ busy: true, error: null, pending: intent });
        let id = this.state.value?.id;
        try {
            const json = await this.client.raw(intent.path, { method: intent.method, body: JSON.parse(intent.body), mutation: { key: intent.key, match: intent.match } });
            const receipt = envelope(json, attempt);
            id = receipt.id;
            // Replays can return an OLD projection. Always resume before permitting another command.
            const value = await this.read(id);
            if (generation === this.generation)
                this.publish({ value, loaded: true, pending: null, error: null, receivedAt: this.clock() });
        }
        catch (error) {
            if (generation !== this.generation)
                return;
            const uncertain = !(error instanceof ApiError) || error.status === 0 || error.status >= 500 || error.status === 401;
            this.publish({ error, pending: uncertain ? intent : null });
            try {
                const value = await this.read(intent.path === '/attempts' ? undefined : id);
                if (generation === this.generation)
                    this.publish({ value, loaded: true, receivedAt: this.clock() });
            }
            catch { /* Keep the last confirmed state and original intent; no automatic mutation. */ }
        }
        finally {
            if (generation === this.generation)
                this.publish({ busy: false });
        }
    }
}
