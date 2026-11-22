import { useEffect, useState } from 'react';
import App from './App';
import BackendApp from './backend/BackendApp';
import { backendConfig, hasTelegramLaunch } from './backend/config';

/** A Telegram launch selects the server path; only Identity verifies its proof.
 * Once selected, API/auth failures must never mount the local test engine.
 */
const serverModeKey = 'anatomai:server-mode';
function savedServerMode() {
    try { return sessionStorage.getItem(serverModeKey) === '1'; } catch { return false; }
}
const launchPresent = () => hasTelegramLaunch(window.Telegram?.WebApp, window.location.hash) || hasTelegramLaunch(undefined, window.location.search);
export function Application() {
    const [server, setServer] = useState(() => backendConfig.enabled || savedServerMode() || launchPresent());
    const requireServer = () => setServer(true);
    useEffect(() => {
        if (server) {
            // Only a routing bit: never store identity, proof, answers or history here.
            try { sessionStorage.setItem(serverModeKey, '1'); } catch { /* Storage can be blocked. */ }
            return;
        }
        const check = () => { if (launchPresent()) setServer(true); };
        const timer = window.setInterval(check, 250);
        window.addEventListener('focus', check);
        window.addEventListener('pageshow', check);
        document.addEventListener('visibilitychange', check);
        check();
        return () => {
            clearInterval(timer);
            window.removeEventListener('focus', check);
            window.removeEventListener('pageshow', check);
            document.removeEventListener('visibilitychange', check);
        };
    }, [server]);
    return server ? <BackendApp/> : <App onServerRequired={requireServer}/>;
}
