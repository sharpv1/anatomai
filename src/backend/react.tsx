import { useEffect, useMemo, useRef, useState, type DependencyList } from 'react';
import { ApiClient, apiMessage, ApiError, query } from './client';
import type { Decoder, Page } from './contracts';
export type Resource<T> = {
    status: 'loading';
} | {
    status: 'error';
    error: unknown;
} | {
    status: 'ready';
    data: T;
};
export function Status({ state, retry, label = 'Данные' }: {
    state: Resource<unknown>;
    retry?: () => void;
    label?: string;
}) {
    if (state.status === 'ready')
        return null;
    return <div className="library-empty" role={state.status === 'error' ? 'alert' : 'status'}><strong>{state.status === 'loading' ? `Загрузка: ${label.toLocaleLowerCase('ru')}…` : 'Данные недоступны'}</strong>{state.status === 'error' && <><p>{apiMessage(state.error)}</p>{retry && <button onClick={retry}>Повторить</button>}</>}</div>;
}
export function useResource<T>(load: (signal: AbortSignal) => Promise<T>, deps: DependencyList) {
    const [version, setVersion] = useState(0), sequence = useRef(0);
    const key = useMemo(() => Symbol(), [...deps, version]);
    const [snapshot, setSnapshot] = useState<{
        key: symbol;
        value: Resource<T>;
    }>({ key, value: { status: 'loading' } });
    useEffect(() => {
        const n = ++sequence.current, c = new AbortController();
        setSnapshot({ key, value: { status: 'loading' } });
        void load(c.signal).then(data => {
            if (n === sequence.current && !c.signal.aborted)
                setSnapshot({ key, value: { status: 'ready', data } });
        }, error => {
            if (n === sequence.current && !c.signal.aborted)
                setSnapshot({ key, value: { status: 'error', error } });
        });
        return () => { sequence.current++; c.abort(); };
    }, [key]);
    const state: Resource<T> = snapshot.key === key ? snapshot.value : { status: 'loading' };
    return { state, retry: () => setVersion(v => v + 1) };
}
export function usePages<T>(client: ApiClient, path: string, decode: Decoder<T>) {
    const cursor = useRef<string | null>(null), inFlight = useRef(false), [version, setVersion] = useState(0);
    const key = useMemo(() => Symbol(), [client, path, version]);
    const [snapshot, setSnapshot] = useState<{
        key: symbol;
        value: Resource<Page<T>>;
    }>({ key, value: { status: 'loading' } });
    const sequence = useRef(0), controller = useRef<AbortController | null>(null);
    const load = async (next: string | null, replace: boolean) => {
        if (!replace && inFlight.current)
            return;
        controller.current?.abort();
        const c = new AbortController();
        controller.current = c;
        const n = ++sequence.current;
        inFlight.current = true;
        if (replace)
            setSnapshot({ key, value: { status: 'loading' } });
        try {
            const page = await client.list(path + (path.includes('?') ? '&' : '?') + new URLSearchParams(next ? { cursor: next } : {}).toString(), decode, c.signal);
            if (n !== sequence.current || c.signal.aborted)
                return;
            cursor.current = page.page.next_cursor;
            setSnapshot(old => ({ key, value: { status: 'ready', data: { ...page, data: !replace && old.key === key && old.value.status === 'ready' ? [...old.value.data.data, ...page.data] : page.data } } }));
        }
        catch (error) {
            if (n === sequence.current && !c.signal.aborted && !(error instanceof ApiError && error.code === 'CANCELLED'))
                setSnapshot({ key, value: { status: 'error', error } });
        }
        finally {
            if (n === sequence.current)
                inFlight.current = false;
        }
    };
    useEffect(() => { cursor.current = null; void load(null, true); return () => { sequence.current++; controller.current?.abort(); }; }, [key]);
    const state: Resource<Page<T>> = snapshot.key === key ? snapshot.value : { status: 'loading' };
    return { state, retry: () => setVersion(v => v + 1), more: () => { if (cursor.current && state.status === 'ready' && state.data.page.has_more)
            void load(cursor.current, false); } };
}
export { query };
