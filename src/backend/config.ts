import { apiBase } from './client';
export function integrationConfig(env: Record<string, unknown>) {
    const enabled = env.VITE_MEDEXA_BACKEND_ENABLED === 'true';
    return { enabled, base: enabled ? apiBase(typeof env.VITE_MEDEXA_API_BASE === 'string' ? env.VITE_MEDEXA_API_BASE : undefined) : '/api/v1' };
}
export const backendConfig = (() => {
    try {
        return { ...integrationConfig(import.meta.env), error: null as unknown };
    }
    catch (error) {
        return { enabled: import.meta.env.VITE_MEDEXA_BACKEND_ENABLED === 'true', base: '/api/v1', error };
    }
})();
