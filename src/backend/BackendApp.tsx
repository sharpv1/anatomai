import { useEffect, useMemo, useState, useSyncExternalStore } from 'react';
import { createTelegramPlatformAdapter } from '../platform/telegram/TelegramPlatformAdapter';
import { AppShell } from '../components/AppShell';
import { AppHeader } from '../components/AppHeader';
import type { AppRoute } from '../components/BottomNavigation';
import { ApiClient } from './client';
import { backendConfig } from './config';
import { AuthController, launchData, type AuthState } from './auth';
import { Status } from './react';
import { ServerHome, ServerProfile, ServerCatalog, ServerTopic, ServerReview, ServerStatistics, ServerNotes } from './screens';
type Navigation = {
    kind: 'tab';
    tab: AppRoute;
} | {
    kind: 'catalog';
    disciplineId: string;
} | {
    kind: 'topic';
    topicId: string;
} | {
    kind: 'review';
    topicId: string;
} | {
    kind: 'statistics';
} | {
    kind: 'notes';
    disciplineId: string;
    noteId?: string;
};
function navigation(value: unknown): Navigation | null {
    if (!value || typeof value !== 'object')
        return null;
    const v = value as Record<string, unknown>;
    if (v.kind === 'tab' && ['home', 'tests', 'notes', 'profile'].includes(String(v.tab)))
        return v as Navigation;
    if (v.kind === 'statistics')
        return { kind: 'statistics' };
    if ((v.kind === 'catalog' || v.kind === 'notes') && typeof v.disciplineId === 'string')
        return v as Navigation;
    if ((v.kind === 'topic' || v.kind === 'review') && typeof v.topicId === 'string')
        return v as Navigation;
    return null;
}
export default function BackendApp() {
    const platform = useMemo(() => createTelegramPlatformAdapter(), []);
    const auth = useMemo(() => new AuthController(new ApiClient(fetch, backendConfig.base), () => launchData(window.Telegram?.WebApp)), []);
    const [location, setLocation] = useState<{
        owner: string;
        nav: Navigation;
    } | null>(null);
    const snapshot = useSyncExternalStore(auth.subscribe, auth.getSnapshot, auth.getSnapshot);
    const state: AuthState = backendConfig.error ? { status: 'error', error: backendConfig.error } : snapshot;
    useEffect(() => { platform.init(); return () => platform.dispose(); }, [platform]);
    useEffect(() => {
        if (backendConfig.error)
            return;
        let previousApi = window.Telegram?.WebApp;
        const syncPlatform = () => {
            const api = window.Telegram?.WebApp;
            if (api !== previousApi) {
                previousApi = api;
                platform.dispose();
                platform.init();
                return true;
            }
            return false;
        };
        let previous = JSON.stringify(launchData(window.Telegram?.WebApp));
        const refresh = () => {
            if (document.visibilityState === 'visible') {
                syncPlatform();
                previous = JSON.stringify(launchData(window.Telegram?.WebApp));
                void auth.bootstrap();
            }
        };
        const timer = setInterval(() => {
            const latest = JSON.stringify(launchData(window.Telegram?.WebApp));
            if (syncPlatform() || latest !== previous) {
                previous = latest;
                void auth.bootstrap();
            }
        }, 1000);
        void auth.bootstrap();
        window.addEventListener('focus', refresh);
        window.addEventListener('pageshow', refresh);
        document.addEventListener('visibilitychange', refresh);
        return () => { clearInterval(timer); window.removeEventListener('focus', refresh); window.removeEventListener('pageshow', refresh); document.removeEventListener('visibilitychange', refresh); auth.dispose(); };
    }, [auth]);
    return state.status === 'ready' ? <Connected key={state.session.user.id} state={state} platform={platform} client={auth.client} nav={location?.owner === state.session.user.id ? location.nav : { kind: 'tab', tab: 'home' }} onNavigation={nav => setLocation({ owner: state.session.user.id, nav })}/> : <AppShell route="home" onRouteChange={() => { }} toast="" onCloseToast={() => { }}><AppHeader anonymous platform={platform} onNotifications={() => { }}/><Status label="авторизация" state={state.status === 'checking' ? { status: 'loading' } : { status: 'error', error: state.error }} retry={backendConfig.error ? undefined : () => { void auth.bootstrap(); }}/></AppShell>;
}
function Connected({ state, platform, client, nav, onNavigation }: {
    state: Extract<AuthState, {
        status: 'ready';
    }>;
    platform: ReturnType<typeof createTelegramPlatformAdapter>;
    client: ApiClient;
    nav: Navigation;
    onNavigation: (nav: Navigation) => void;
}) {
    const owner = state.session.user.id;
    const setNav = onNavigation;
    const [toast, setToast] = useState('');
    useEffect(() => {
        window.history.replaceState({ medexa6a: { owner, nav } }, '', window.location.pathname + window.location.search + (nav.kind === 'tab' ? '' : '#medexa-' + nav.kind));
        const sync = () => {
            const h = window.history.state?.medexa6a;
            const next = h?.owner === owner ? navigation(h.nav) : null;
            if (next)
                setNav(next);
            else if (!window.location.hash)
                setNav({ kind: 'tab', tab: 'home' });
        };
        window.addEventListener('popstate', sync);
        return () => window.removeEventListener('popstate', sync);
    }, [owner]);
    useEffect(() => {
        if (!toast)
            return;
        const timer = setTimeout(() => setToast(''), 2500);
        return () => clearTimeout(timer);
    }, [toast]);
    const go = (next: Navigation) => { window.history.pushState({ medexa6a: { owner, nav: next } }, '', '#medexa-' + next.kind); setNav(next); };
    const back = () => {
        if (window.history.state?.medexa6a?.owner === owner)
            window.history.back();
        else
            go({ kind: 'tab', tab: 'home' });
    };
    const base = { client, platform, user: state.session.user };
    const route: AppRoute = nav.kind === 'tab' ? nav.tab : nav.kind === 'notes' ? 'notes' : nav.kind === 'statistics' ? 'home' : 'tests';
    const nested = nav.kind === 'topic' || nav.kind === 'review' || nav.kind === 'statistics';
    return <AppShell route={route} onRouteChange={tab => go({ kind: 'tab', tab })} toast={toast} onCloseToast={() => setToast('')} hideNavigation={nested}>
  {nav.kind === 'statistics' ? <ServerStatistics {...base} onBack={back}/> : nav.kind === 'review' ? <ServerReview {...base} topicId={nav.topicId} onBack={back}/> : nav.kind === 'topic' ? <ServerTopic {...base} topicId={nav.topicId} onBack={back} onReview={() => go({ kind: 'review', topicId: nav.topicId })} notify={setToast}/> : nav.kind === 'catalog' || route === 'tests' ? <ServerCatalog key={nav.kind === 'catalog' ? nav.disciplineId : 'catalog'} {...base} disciplineId={nav.kind === 'catalog' ? nav.disciplineId : undefined} onDiscipline={disciplineId => go({ kind: 'catalog', disciplineId })} onTopic={topicId => go({ kind: 'topic', topicId })} onBack={back}/> : route === 'notes' ? <ServerNotes key={nav.kind === 'notes' ? nav.disciplineId : 'notes'} {...base} disciplineId={nav.kind === 'notes' ? nav.disciplineId : undefined} noteId={nav.kind === 'notes' ? nav.noteId : undefined} onNote={noteId => {
                if (nav.kind === 'notes')
                    go({ ...nav, noteId });
            }} onDiscipline={disciplineId => go({ kind: 'notes', disciplineId })} onBack={back}/> : route === 'profile' ? <ServerProfile {...base}/> : <ServerHome {...base} onTests={() => go({ kind: 'tab', tab: 'tests' })} onNotes={() => go({ kind: 'tab', tab: 'notes' })} onDiscipline={disciplineId => go({ kind: 'notes', disciplineId })} onDaily={topicId => go({ kind: 'review', topicId })} onStats={() => go({ kind: 'statistics' })} notify={setToast}/>}
  <button className="fullscreen-toggle" aria-label="Открыть полноэкранный режим" onClick={() => platform.requestFullscreen()}>⛶</button>
 </AppShell>;
}
