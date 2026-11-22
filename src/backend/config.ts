import { apiBase } from './client';

export function integrationConfig(env: Record<string, unknown>, serverRequired = false) {
    const enabled = env.VITE_MEDEXA_BACKEND_ENABLED === 'true';
    return { enabled, base: enabled || serverRequired ? apiBase(typeof env.VITE_MEDEXA_API_BASE === 'string' ? env.VITE_MEDEXA_API_BASE : undefined) : '/api/v1' };
}

/** Routing hint only: Identity on the server must verify any supplied proof. */
export function hasTelegramLaunch(api?: { initData?: unknown }, fragment = ''): boolean {
    if (typeof api?.initData === 'string' && api.initData.trim().length > 0) return true;
    const params = new URLSearchParams(fragment.replace(/^[#?]/, ''));
    return params.has('tgWebAppData') || params.has('tgWebAppPlatform');
}

const buildConfig = {
    VITE_MEDEXA_BACKEND_ENABLED: import.meta.env.VITE_MEDEXA_BACKEND_ENABLED,
    VITE_MEDEXA_API_BASE: import.meta.env.VITE_MEDEXA_API_BASE,
};
export const backendConfig = (() => {
    try {
        // A Telegram launch can require this connection even without the browser opt-in.
        return { ...integrationConfig(buildConfig, true), error: null as unknown };
    }
    catch (error) {
        return { enabled: buildConfig.VITE_MEDEXA_BACKEND_ENABLED === 'true', base: '/api/v1', error };
    }
})();
