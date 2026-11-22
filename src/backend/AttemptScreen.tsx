import { useEffect, useState, useSyncExternalStore } from 'react';
import { ServerTestSession } from '../features/tests/TestSession';
import { ServerTestResult } from '../features/tests/TestResult';
import type { TelegramPlatform } from '../platform/telegram/TelegramPlatformAdapter';
import { useTelegramBackButton } from '../platform/telegram/useTelegramBackButton';
import { AttemptController, examReview, learningReview, type Attempt, type ReviewItem } from './attempts';
import { apiMessage } from './client';
import { Status, useResource } from './react';
function Review({ controller, attempt }: {
    controller: AttemptController;
    attempt: Attempt;
}) {
    const [page, setPage] = useState<{
        offset: number;
        cursor: string | null;
    }>({ offset: 0, cursor: null });
    const [previous, setPrevious] = useState<ReviewItem[]>([]);
    const { state, retry } = useResource(async (signal) => {
        if (attempt.mode === 'exam') {
            const p = await controller.client.get(`/attempts/${attempt.id}/review?offset=${page.offset}&limit=30`, examReview, signal);
            return { items: p.items, more: p.next_offset !== null, next: { offset: p.next_offset ?? 0, cursor: null } };
        }
        const p = await controller.client.get(`/attempts/${attempt.id}/result-review?selection=all&limit=30${page.cursor ? '&cursor=' + encodeURIComponent(page.cursor) : ''}`, learningReview, signal);
        return { items: p.items, more: p.has_more, next: { offset: 0, cursor: p.next_cursor } };
    }, [controller, attempt.id, page]);
    return <div className="test-review" aria-label="Разбор ответов"><Status state={state} retry={retry}/>{[...previous, ...(state.status === 'ready' ? state.data.items : [])].map(i => <article className={`test-review__item ${i.is_correct ? '' : 'wrong'}`} key={i.id}><strong>{i.position + 1}. {i.text}</strong>{i.options.map(o => <p key={o.id}>{i.correct_option_ids.includes(o.id) ? '✓ ' : ''}{o.text}{i.selected_option_ids.includes(o.id) ? ' — ваш ответ' : ''}</p>)}{i.explanation && <small>{i.explanation}</small>}</article>)}{state.status === 'ready' && state.data.more && <button className="question-review__more" onClick={() => { setPrevious(v => [...v, ...state.data.items]); setPage(state.data.next); }}>Показать ещё</button>}</div>;
}
export function AttemptScreen({ controller, platform, onBack }: {
    controller: AttemptController;
    platform: TelegramPlatform;
    onBack: () => void;
}) {
    const state = useSyncExternalStore(controller.subscribe, controller.getSnapshot, controller.getSnapshot);
    const [now, setNow] = useState(performance.now());
    useEffect(() => { void controller.refresh(); const visible = () => { if (document.visibilityState === 'visible')
        void controller.refresh(); }; document.addEventListener('visibilitychange', visible); return () => document.removeEventListener('visibilitychange', visible); }, [controller]);
    const a = state.value;
    const running = a?.status === 'in_progress' && a.mode === 'exam';
    useEffect(() => { if (!running)
        return; const timer = setInterval(() => setNow(performance.now()), 500); return () => clearInterval(timer); }, [running]);
    const seconds = Math.max(0, (a?.remaining_seconds ?? 0) - Math.floor(Math.max(0, now - state.receivedAt) / 1000));
    // The display never finalizes locally. GET asks the server to reconcile its deadline.
    useEffect(() => { if (!running)
        return; const timer = setInterval(() => { void controller.refresh(); }, seconds === 0 ? 2000 : 15000); return () => clearInterval(timer); }, [controller, running, seconds === 0]);
    const ready = a?.status === 'in_progress' || a?.status === 'completed';
    const back = useTelegramBackButton(platform, onBack, !ready, false);
    const status = state.error || state.pending ? <div className="library-empty" role="alert"><strong>{state.error ? apiMessage(state.error) : 'Сохранение требует подтверждения.'}</strong><p>{state.pending ? 'Сохранение не подтверждено. Повтор отправит тот же запрос.' : 'Обновите состояние с сервера перед продолжением.'}</p><button onClick={() => { void (state.pending ? controller.retry() : controller.refresh()); }} disabled={state.busy}>{state.pending ? 'Повторить запрос' : 'Обновить'}</button></div> : state.busy ? <p className="study-note" role="status">Синхронизация с сервером…</p> : null;
    if (a?.status === 'completed' && a.result)
        return <>{status}<ServerTestResult busy={state.busy || Boolean(state.pending)} key={a.id} result={a.result} mode={a.mode} platform={platform} onBack={onBack} onRetake={() => { if (!state.busy && !state.pending)
            void controller.start(a.mode, a.scope === 'test' ? { test_definition_id: a.test_definition_id! } : a.scope === 'topic' ? { topic_id: a.topic_id! } : { discipline_id: a.discipline_id }); }} review={<Review controller={controller} attempt={a}/>}/></>;
    if (a?.status === 'in_progress')
        return <ServerTestSession attempt={a} platform={platform} seconds={seconds} busy={state.busy || Boolean(state.pending)} onExit={onBack} status={status} onAction={(action, value) => { void controller.action(action, value); }}/>;
    return <section className="study-page">{!back.isTelegramContext && <button className="study-back" onClick={back.requestBack}>‹ К тестам</button>}{status}{!state.busy && !state.error && <p>Активной попытки нет. Выберите тему в каталоге.</p>}</section>;
}
