import type { Decoder, Page } from './contracts';
import { envelope, listEnvelope } from './contracts';
export class ApiError extends Error {
    constructor(public readonly code: string, public readonly status = 0, public readonly requestId?: string) { super(code); this.name = 'ApiError'; }
}
export function apiMessage(error: unknown): string {
    if (!(error instanceof ApiError))
        return 'Не удалось загрузить данные. Повторите запрос.';
    if (error.code === 'INVALID_API_CONFIG')
        return 'Подключение к серверу не настроено.';
    if (error.code === 'INIT_DATA_REQUIRED')
        return 'Откройте Mini App из Telegram для входа.';
    if (error.code === 'AUTH_REQUIRED' || error.code === 'SESSION_EXPIRED' || error.status === 401)
        return 'Сессия истекла. Откройте Mini App заново из Telegram.';
    if (error.code === 'EXAM_REFERENCE_LOCKED')
        return 'Ответы доступны после завершения активного экзамена.';
    if (error.code === 'TIMEOUT')
        return 'Сервер не ответил вовремя. Повторите запрос.';
    if (error.code === 'NETWORK')
        return 'Нет связи с сервером. Проверьте сеть и повторите запрос.';
    if (error.status === 403)
        return 'Доступ не подтверждён. Откройте Mini App заново из Telegram.';
    return 'Не удалось загрузить серверные данные. Повторите запрос.';
}
export function apiBase(value = '/api/v1'): string {
    // Same-origin only: cookies/initData must never go to a configurable third-party host.
    if (!/^\/[a-zA-Z0-9/_-]+$/.test(value) || value.startsWith('//') || value.includes('..'))
        throw new ApiError('INVALID_API_CONFIG');
    return value.replace(/\/$/, '');
}
export class ApiClient {
    private csrf: string | null = null;
    private revision = 0;
    private pending = new Set<AbortController>();
    onUnauthorized: () => void = () => { };
    constructor(private readonly fetcher: typeof fetch = fetch, private readonly base = apiBase(), private readonly timeoutMs = 10000) { apiBase(base); this.fetcher = fetcher.bind(globalThis); }
    setCsrf(value: string) { this.csrf = value; }
    reset() {
        this.revision++;
        this.csrf = null;
        for (const c of this.pending)
            c.abort();
        this.pending.clear();
    }
    async raw(path: string, options: {
        method?: 'GET' | 'POST' | 'PATCH' | 'DELETE';
        body?: unknown;
        signal?: AbortSignal;
        auth?: boolean;
    } = {}): Promise<unknown> {
        if (!/^\/[a-zA-Z0-9/_-]*$/.test(path.split('?')[0]) || path.startsWith('//') || path.includes('#'))
            throw new ApiError('INVALID_API_PATH');
        const rev = this.revision, controller = new AbortController();
        if (options.auth !== false)
            this.pending.add(controller);
        const abort = () => controller.abort();
        options.signal?.addEventListener('abort', abort, { once: true });
        if (options.signal?.aborted)
            controller.abort();
        let timedOut = false;
        const timer = setTimeout(() => { timedOut = true; controller.abort(); }, this.timeoutMs);
        try {
            const method = options.method ?? 'GET', headers: Record<string, string> = { Accept: 'application/json' };
            if (options.body !== undefined)
                headers['Content-Type'] = 'application/json';
            if (method !== 'GET' && options.auth !== false) {
                if (!this.csrf)
                    throw new ApiError('CSRF_REQUIRED');
                headers['X-CSRF-Token'] = this.csrf;
            }
            const response = await this.fetcher(this.base + path, { method, headers, credentials: 'include', cache: 'no-store', redirect: 'error', signal: controller.signal, ...(options.body !== undefined ? { body: JSON.stringify(options.body) } : {}) });
            if (rev !== this.revision || controller.signal.aborted)
                throw new ApiError(timedOut ? 'TIMEOUT' : 'CANCELLED');
            let json: unknown;
            try {
                json = await response.json();
            }
            catch {
                throw new ApiError('INVALID_RESPONSE', response.status);
            }
            if (rev !== this.revision || controller.signal.aborted)
                throw new ApiError(timedOut ? 'TIMEOUT' : 'CANCELLED');
            if (!response.ok) {
                const err = (json as {
                    error?: {
                        code?: unknown;
                        request_id?: unknown;
                    };
                })?.error;
                const code = typeof err?.code === 'string' ? err.code : 'API_ERROR';
                if (response.status === 401 && options.auth !== false)
                    this.onUnauthorized();
                throw new ApiError(code, response.status, typeof err?.request_id === 'string' ? err.request_id : undefined);
            }
            return json;
        }
        catch (error) {
            if (error instanceof ApiError)
                throw error;
            if (controller.signal.aborted)
                throw new ApiError(timedOut ? 'TIMEOUT' : 'CANCELLED');
            throw new ApiError('NETWORK');
        }
        finally {
            clearTimeout(timer);
            this.pending.delete(controller);
            options.signal?.removeEventListener('abort', abort);
        }
    }
    async get<T>(path: string, decode: Decoder<T>, signal?: AbortSignal): Promise<T> {
        const raw = await this.raw(path, { signal });
        try {
            return envelope(raw, decode);
        }
        catch {
            throw new ApiError('INVALID_DTO');
        }
    }
    async list<T>(path: string, decode: Decoder<T>, signal?: AbortSignal): Promise<Page<T>> {
        const raw = await this.raw(path, { signal });
        try {
            return listEnvelope(raw, decode);
        }
        catch {
            throw new ApiError('INVALID_DTO');
        }
    }
}
export function query(values: Record<string, string | number | null | undefined>): string {
    const p = new URLSearchParams();
    for (const [k, v] of Object.entries(values))
        if (v !== undefined && v !== null && v !== '')
            p.set(k, String(v));
    return p.size ? '?' + p.toString() : '';
}
