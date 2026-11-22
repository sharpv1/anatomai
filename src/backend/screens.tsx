import { useState } from 'react';
import { HomePage } from '../pages/HomePage';
import { ProfilePage } from '../pages/ProfilePage';
import { StatisticsPage } from '../pages/StatisticsPage';
import { QuestionReviewPage } from '../pages/QuestionReviewPage';
import { AppHeader } from '../components/AppHeader';
import { LibraryIcon } from '../features/library/LibraryIcon';
import { useTelegramBackButton } from '../platform/telegram/useTelegramBackButton';
import type { TelegramPlatform } from '../platform/telegram/TelegramPlatformAdapter';
import { ApiClient } from './client';
import * as dto from './contracts';
import { Status, useResource, usePages, query } from './react';
import { review, subject } from './presentation';
type Base = {
    client: ApiClient;
    platform: TelegramPlatform;
    user: dto.User;
};
export function ServerHome({ client, platform, user, onTests, onNotes, onDiscipline, onDaily, onStats, notify }: Base & {
    onTests: () => void;
    onNotes: () => void;
    onDiscipline: (id: string) => void;
    onDaily: (id: string) => void;
    onStats: () => void;
    notify: (message: string) => void;
}) {
    const { state, retry } = useResource(async (signal) => {
        const [home, recommendations, daily, disciplines] = await Promise.all([client.get('/me/home', dto.home, signal), client.get('/me/recommendations', dto.array(dto.recommendation), signal), client.get('/me/daily-topic', dto.daily, signal), client.list('/disciplines?limit=4', dto.discipline, signal)]);
        const dailyDiscipline = daily.discipline_id ? (disciplines.data.find(d => d.id === daily.discipline_id) ?? await client.get('/disciplines/' + encodeURIComponent(daily.discipline_id), dto.discipline, signal)) : null;
        return { home, recommendations, daily, disciplines: disciplines.data, dailyDisciplineTitle: dailyDiscipline?.title ?? null };
    }, [client]);
    if (state.status !== 'ready')
        return <><AppHeader platform={platform} verifiedUser={user} onNotifications={() => notify('Уведомления пока не подключены')}/><Status state={state} retry={retry} label="главная"/></>;
    return <HomePage platform={platform} entries={[]} onStartTest={onTests} onNotify={notify} onStatistics={onStats} onNotes={onNotes} onNoteDiscipline={onDiscipline} onDailyReview={() => { }} server={{ ...state.data, user, onDaily }}/>;
}
export function ServerProfile({ client, platform, user }: Base) {
    const { state, retry } = useResource(async (signal) => { const [statistics, progress, achievements] = await Promise.all([client.get('/me/statistics', dto.summary, signal), client.get('/me/progress', dto.progress, signal), client.get('/me/achievements', dto.array(dto.achievement), signal)]); return { statistics, progress, achievements }; }, [client]);
    if (state.status !== 'ready')
        return <section className="profile-page library-page"><h1>Профиль</h1><Status state={state} retry={retry}/></section>;
    return <ProfilePage platform={platform} entries={[]} onReset={() => { }} server={{ ...state.data, user }}/>;
}
export function ServerStatistics({ client, platform, onBack }: Base & {
    onBack: () => void;
}) {
    const { state, retry } = useResource(async (signal) => { const [statistics, activity, achievements] = await Promise.all([client.get('/me/statistics', dto.summary, signal), client.get('/me/activity', dto.activity, signal), client.get('/me/achievements', dto.array(dto.achievement), signal)]); return { statistics, activity, achievements }; }, [client]);
    const pages = usePages(client, '/me/attempts?limit=20', dto.history);
    const ready = state.status === 'ready' && pages.state.status === 'ready';
    // This container owns Back only while the presentation page is not mounted.
    const back = useTelegramBackButton(platform, onBack, !ready, false);
    if (!ready)
        return <section className="library-page study-page"><header className="library-heading">{!back.isTelegramContext && <button className="notes-back" onClick={back.requestBack}>‹ Назад</button>}<h1>Моя статистика</h1></header><Status state={state.status === 'ready' ? pages.state : state} retry={() => { retry(); pages.retry(); }}/></section>;
    if (state.status !== 'ready' || pages.state.status !== 'ready')
        return null;
    return <StatisticsPage entries={[]} platform={platform} onBack={onBack} listenPopstate={false} server={{ ...state.data, history: pages.state.data.data, hasMore: pages.state.data.page.has_more, onMore: pages.more }}/>;
}
export function ServerCatalog({ client, platform, disciplineId, onDiscipline, onTopic, onBack }: Base & {
    disciplineId?: string;
    onDiscipline: (id: string) => void;
    onTopic: (id: string) => void;
    onBack: () => void;
}) {
    const [search, setSearch] = useState('');
    const back = useTelegramBackButton(platform, onBack, Boolean(disciplineId), false);
    const quick = useResource(signal => client.list('/test-definitions?limit=30', dto.test, signal), [client]);
    const disciplinePage = usePages(client, '/disciplines' + query({ query: search, limit: 30 }), dto.discipline);
    const topics = usePages(client, '/topics' + query({ discipline_id: disciplineId, query: search, limit: 30 }), dto.topic);
    const page = disciplineId ? topics : disciplinePage;
    return <section className="tests-page library-page"><header className="library-heading tests-head"><div><p className="eyebrow">Учиться с уверенностью</p><h1>Тесты</h1><p className="library-subtitle">От вопроса — к пониманию.</p></div></header><label className="tests-search library-search"><span aria-hidden="true">⌕</span><input value={search} onChange={e => setSearch(e.target.value)} placeholder={disciplineId ? 'Найти тему' : 'Найти дисциплину'} aria-label="Найти тест"/></label><>{!disciplineId && quick.state.status === 'ready' && quick.state.data.data.find(t => t.question_count > 0) && <button className="library-quick" onClick={() => onTopic(quick.state.status === 'ready' ? quick.state.data.data.find(t => t.question_count > 0)!.topic_id : '')}><span className="library-quick__icon"><LibraryIcon name="practice"/></span><span><strong>Быстрая практика</strong><small>Обучение или экзамен</small></span><span className="library-chevron">›</span></button>}</><div className="library-section-title"><h2>{disciplineId ? 'Темы' : 'Дисциплины'}</h2>{disciplineId && !back.isTelegramContext && <button className="notes-back" onClick={back.requestBack}>К дисциплинам</button>}</div><Status state={page.state} retry={page.retry} label="каталог"/>{page.state.status === 'ready' && <><section className="test-list" aria-label="Каталог тестов">{page.state.data.data.map(item => <button className="test-card" key={item.id} onClick={() => disciplineId ? onTopic(item.id) : onDiscipline(item.id)}><span className="test-card-icon blue" aria-hidden="true"><LibraryIcon name="practice"/></span><span className="test-card-body"><strong className="test-card-title">{item.title}</strong><span className="test-card-meta">Вопросов: {item.question_count}</span></span><span className="test-arrow" aria-hidden="true">›</span></button>)}</section>{!page.state.data.data.length && <div className="library-empty" role="status"><strong>{search ? 'Ничего не найдено' : 'Опубликованных материалов пока нет'}</strong></div>}{page.state.data.page.has_more && <button className="question-review__more" onClick={page.more}>Показать ещё</button>}</>}</section>;
}
export function ServerTopic({ client, platform, topicId, onBack, onReview, notify }: Base & {
    topicId: string;
    onBack: () => void;
    onReview: () => void;
    notify: (text: string) => void;
}) {
    const { state, retry } = useResource(async (signal) => { const [topic, stats] = await Promise.all([client.get('/topics/' + encodeURIComponent(topicId), dto.topic, signal), client.get('/me/topics/' + encodeURIComponent(topicId) + '/summary', dto.topicSummary, signal)]); const discipline = await client.get('/disciplines/' + encodeURIComponent(topic.discipline_id), dto.discipline, signal); return { topic, stats, discipline }; }, [client, topicId]);
    const tests = usePages(client, '/test-definitions' + query({ topic_id: topicId, limit: 30 }), dto.test);
    const { isTelegramContext, requestBack } = useTelegramBackButton(platform, onBack, true, false);
    return <section className="study-page topic-page"><header>{!isTelegramContext && <button className="study-back" onClick={requestBack}>‹ К дисциплинам</button>}{state.status === 'ready' && <><p className="study-eyebrow">{state.data.discipline.title}</p><h1>{state.data.topic.title}</h1></>}</header><Status state={state} retry={retry} label="тема"/>{state.status === 'ready' && <><dl className="topic-metrics">{[['Вопросов', state.data.topic.question_count], ['Лучший результат', state.data.stats.best_percent === null ? '—' : `${state.data.stats.best_percent}%`], ['Вопросов с ошибками', state.data.stats.ever_wrong_question_count ?? '—']].map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{value}</dd></div>)}</dl><p className="study-note">Серверная история. Запуск серверного тестирования пока недоступен.</p><div className="topic-modes"><button className="test-mode-card" aria-disabled="true" onClick={() => notify('Серверное обучение пока недоступно')}>Обучение</button><button className="test-mode-card" aria-disabled="true" onClick={() => notify('Серверный экзамен пока недоступен')}>Экзамен</button></div><button className="topic-review-link" onClick={onReview}>Ответы и разбор <span aria-hidden="true">→</span></button><Status state={tests.state} retry={tests.retry} label="опубликованные тесты"/>{tests.state.status === 'ready' && <><section className="test-list" aria-label="Опубликованные тесты">{tests.state.data.data.map(test => <div className="test-card" key={test.id}><span className="test-card-body"><strong className="test-card-title">{test.title}</strong><span className="test-card-meta">Вопросов: {test.question_count} · {test.available_modes.map(m => m === 'exam' ? 'Экзамен' : 'Обучение').join(' / ')}</span></span></div>)}</section>{tests.state.data.page.has_more && <button className="question-review__more" onClick={tests.more}>Показать ещё тесты</button>}</>}</>}</section>;
}
export function ServerReview({ client, platform, topicId, onBack }: Base & {
    topicId: string;
    onBack: () => void;
}) {
    const [search, setSearch] = useState('');
    const detail = useResource(signal => client.get('/topics/' + encodeURIComponent(topicId), dto.topic, signal), [client, topicId]);
    const pages = usePages(client, '/topics/' + encodeURIComponent(topicId) + '/reference-questions' + query({ query: search, limit: 30 }), dto.reference);
    const ready = detail.state.status === 'ready';
    const back = useTelegramBackButton(platform, onBack, !ready, false);
    if (!ready)
        return <section className="study-page"><header>{!back.isTelegramContext && <button className="study-back" onClick={back.requestBack}>‹ Назад</button>}<h1>Ответы и разбор</h1></header><Status state={detail.state.status === 'ready' ? pages.state : detail.state} retry={() => { detail.retry(); pages.retry(); }}/></section>;
    if (detail.state.status !== 'ready')
        return null;
    return <QuestionReviewPage key={topicId} title={detail.state.data.title} questions={pages.state.status === 'ready' ? pages.state.data.data.map(review) : []} platform={platform} onBack={onBack} listenPopstate={false} server={{ total: pages.state.status === 'ready' ? (pages.state.data.page.total ?? pages.state.data.data.length) : null, pending: pages.state.status === 'loading', numbers: pages.state.status === 'ready' ? Object.fromEntries(pages.state.data.data.map(q => [q.question_id, q.number])) : {}, status: <Status state={pages.state} retry={pages.retry}/>, hasMore: pages.state.status === 'ready' && pages.state.data.page.has_more, onMore: pages.more, query: search, onQuery: setSearch }}/>;
}
export function ServerNotes({ client, platform, disciplineId, onDiscipline, onBack, noteId, onNote }: Base & {
    disciplineId?: string;
    noteId?: string;
    onNote: (id: string) => void;
    onDiscipline: (id: string) => void;
    onBack: () => void;
}) {
    const [search, setSearch] = useState('');
    const discs = usePages(client, '/disciplines' + query({ query: search, limit: 30 }), dto.discipline);
    const notes = usePages(client, '/notes' + query({ discipline_id: disciplineId, query: search, limit: 30 }), dto.noteSummary);
    const detail = useResource(signal => disciplineId ? client.get('/disciplines/' + encodeURIComponent(disciplineId), dto.discipline, signal) : Promise.resolve(null), [client, disciplineId]);
    const body = useResource(signal => noteId ? client.get('/notes/' + encodeURIComponent(noteId), dto.note, signal) : Promise.resolve(null), [client, noteId]);
    const back = onBack;
    const native = useTelegramBackButton(platform, back, Boolean(disciplineId || noteId), false);
    const page = disciplineId ? notes : discs;
    return <section className="notes-page library-page"><header className="library-heading">{(disciplineId || noteId) && !native.isTelegramContext && <button className="notes-back" onClick={native.requestBack}>‹ Назад</button>}<p className="eyebrow">Знания под рукой</p><h1>Конспекты</h1><p className="library-subtitle">Самое важное по вашим дисциплинам.</p></header>{noteId ? <><Status state={body.state} retry={body.retry}/>{body.state.status === 'ready' && body.state.data && <section className="notes-detail"><h2>{body.state.data.title}</h2>{body.state.data.body ? <p style={{ whiteSpace: 'pre-wrap', overflowWrap: 'anywhere' }}>{body.state.data.body}</p> : <div className="library-empty">Текст пока недоступен. Файл здесь не загружается.</div>}</section>}</> : <><label className="library-search"><span aria-hidden="true">⌕</span><input value={search} onChange={e => setSearch(e.target.value)} placeholder="Найти дисциплину или материал" aria-label="Найти дисциплину"/></label><div className="library-section-title"><h2>{disciplineId ? (detail.state.status === 'ready' ? detail.state.data?.title : 'Конспекты') : 'Дисциплины'}</h2></div><Status state={page.state} retry={page.retry}/>{disciplineId && <Status state={detail.state} retry={detail.retry}/>} {page.state.status === 'ready' && <><ul className="notes-list">{page.state.data.data.map(item => <li key={item.id}><button className="notes-card" onClick={() => disciplineId ? onNote(item.id) : onDiscipline(item.id)}><span className={`library-discipline-icon ${'color_token' in item ? subject(item).color : 'blue'}`} aria-hidden="true"><LibraryIcon name="practice"/></span><span className="notes-card__title">{item.title}</span><span className="library-chevron" aria-hidden="true">›</span></button></li>)}</ul>{page.state.data.data.length === 0 && <div className="library-empty"><strong>{disciplineId ? 'Материалы ещё не добавлены' : 'Дисциплина не найдена'}</strong><p>{disciplineId ? 'В этой дисциплине пока нет конспектов.' : 'Попробуйте другое название.'}</p></div>}{page.state.data.page.has_more && <button className="question-review__more" onClick={page.more}>Показать ещё</button>}</>}</>}</section>;
}
