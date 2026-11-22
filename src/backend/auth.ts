import { ApiClient, ApiError } from './client';
import { envelope, session, type Session } from './contracts';
export type Launch = {
    initData: string;
    userHint: string | null;
    conflictingIdentity?: boolean;
    requiresVerification?: boolean;
};
export function launchData(api?: {
    initData?: string;
    initDataUnsafe?: {
        user?: unknown;
    };
}): Launch {
    const initData = typeof api?.initData === 'string' ? api.initData.trim() : '';
    let id: unknown;
    try {
        id = (JSON.parse(new URLSearchParams(initData).get('user') ?? 'null') as {
            id?: unknown;
        } | null)?.id;
    }
    catch { /* Only a switch hint, never proof. */ }
    const rawId = typeof id === 'number' && Number.isSafeInteger(id) && id > 0 ? String(id) : null;
    const unsafeId = api?.initDataUnsafe?.user && typeof api.initDataUnsafe.user === 'object' ? (api.initDataUnsafe.user as {
        id?: unknown;
    }).id : null;
    const hint = typeof unsafeId === 'number' && Number.isSafeInteger(unsafeId) && unsafeId > 0 ? String(unsafeId) : null;
    return { initData, userHint: rawId ?? hint, ...(rawId && hint && rawId !== hint ? { conflictingIdentity: true } : {}), ...(initData && !rawId ? { requiresVerification: true } : {}) };
}
export type AuthState = {
    status: 'checking';
} | {
    status: 'ready';
    session: Session;
} | {
    status: 'error';
    error: unknown;
};
/** No storage, shared query cache, token export or automatic retry of mutations. */
export class AuthController {
    private state: AuthState = { status: 'checking' };
    private listeners = new Set<() => void>();
    private run = 0;
    private chain: Promise<void> = Promise.resolve();
    private disposed = false;
    constructor(readonly client: ApiClient, private readonly readLaunch: () => Launch) { client.onUnauthorized = () => { void this.bootstrap(); }; }
    getSnapshot = () => this.state;
    subscribe = (fn: () => void) => { this.listeners.add(fn); return () => { this.listeners.delete(fn); }; };
    private publish(state: AuthState) {
        this.state = state;
        for (const fn of this.listeners)
            fn();
    }
    bootstrap() {
        const run = ++this.run;
        this.disposed = false;
        this.client.reset();
        this.publish({ status: 'checking' });
        this.chain = this.chain.catch(() => { }).then(() => this.authenticate(run));
        return this.chain;
    }
    private async authenticate(run: number) {
        if (this.disposed || run !== this.run)
            return;
        const launch = this.readLaunch();
        try {
            if (launch.conflictingIdentity)
                throw new ApiError('INIT_DATA_REQUIRED');
            let restored: Session | null = null;
            try {
                restored = envelope(await this.client.raw('/auth/session', { auth: false }), session);
            }
            catch (e) {
                if (!(e instanceof ApiError) || e.status !== 401)
                    throw e;
            }
            // A missing/malformed signed user field must be verified rather than trusting the old cookie.
            const canRestore = restored && !launch.requiresVerification && (!launch.initData || launch.userHint === restored.user.telegram_user_id) && (!launch.userHint || launch.userHint === restored.user.telegram_user_id);
            let verified: Session;
            if (canRestore && restored)
                verified = restored;
            else {
                if (!launch.initData)
                    throw new ApiError('INIT_DATA_REQUIRED');
                const raw = await this.client.raw('/auth/telegram', { method: 'POST', auth: false, body: { init_data: launch.initData, timezone: Intl.DateTimeFormat().resolvedOptions().timeZone } });
                verified = envelope(raw, session);
                if (launch.userHint && verified.user.telegram_user_id !== launch.userHint)
                    throw new ApiError('IDENTITY_MISMATCH');
                const confirmed = envelope(await this.client.raw('/auth/session', { auth: false }), session);
                if (confirmed.user.id !== verified.user.id)
                    throw new ApiError('IDENTITY_MISMATCH');
                verified = confirmed;
            }
            if (this.disposed || run !== this.run)
                return;
            // Launch context can change while an auth response is in flight.
            const latest = this.readLaunch();
            if (latest.initData !== launch.initData || latest.userHint !== launch.userHint || latest.conflictingIdentity !== launch.conflictingIdentity) {
                void this.bootstrap();
                return;
            }
            this.client.setCsrf(verified.csrf_token);
            this.publish({ status: 'ready', session: verified });
        }
        catch (error) {
            if (!this.disposed && run === this.run) {
                this.client.reset();
                this.publish({ status: 'error', error });
            }
        }
    }
    dispose() { this.disposed = true; this.run++; this.client.reset(); }
}
