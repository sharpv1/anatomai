import { useEffect, useMemo, useRef, useState } from 'react';
import type { AppRoute } from './components/BottomNavigation';
import { AppShell } from './components/AppShell';
import { TestResult } from './features/tests/TestResult';
import { TestSession } from './features/tests/TestSession';
import type { TestDefinition, TestResultData } from './features/tests/types';
import { HomePage } from './pages/HomePage';
import { TestsPage } from './pages/TestsPage';
import { NotesPage } from './pages/NotesPage';
import { ProfilePage } from './pages/ProfilePage';
import { createTelegramPlatformAdapter } from './platform/telegram/TelegramPlatformAdapter';
import './styles/app.css';
import './styles/tokens.css';
import './features/tests/TestsExperience.css';
import './styles/motion.css';
import './styles/library-7.0.css';
import './styles/refinement-7.2.css';
import { StatisticsPage } from './pages/StatisticsPage';
import type { CompletedTest } from './features/library/statistics';

export default function App() {
  const platform = useMemo(() => createTelegramPlatformAdapter(), []);
  useEffect(() => { platform.init(); return () => platform.dispose(); }, [platform]);
  const [route, setRoute] = useState<AppRoute>('home');
  const [testScreen, setTestScreen] = useState<'catalog' | 'session' | 'result'>('catalog');
  const [selectedTest, setSelectedTest] = useState<TestDefinition | null>(null);
  const [result, setResult] = useState<TestResultData | null>(null);
  const [statistics, setStatistics] = useState(false);
  useEffect(() => { const sync = () => setStatistics(window.location.hash === '#statistics'); window.addEventListener('popstate', sync); return () => window.removeEventListener('popstate', sync); }, []);
  const [entries, setEntries] = useState<CompletedTest[]>([]);
  const runId = useRef(0);
  const recorded = useRef(new Set<number>());
  const openStatistics = () => { window.history.pushState({ statistics: true }, '', '#statistics'); setStatistics(true); };
  const closeStatistics = () => { if (window.location.hash === '#statistics') window.history.back(); else setStatistics(false); };
  const [toast, setToast] = useState('');

  useEffect(() => { if (!toast) return; const timeout = window.setTimeout(() => setToast(''), 2200); return () => window.clearTimeout(timeout); }, [toast]);
  const notify = (message: string) => setToast(message);
  const goTo = (nextRoute: AppRoute) => { setStatistics(false); setRoute(nextRoute); if (nextRoute === 'tests') setTestScreen('catalog'); };
  const openTest = (test: TestDefinition) => { runId.current++; setSelectedTest(test); setTestScreen('session'); window.history.pushState({ testSession: true }, '', '#test-session'); };
  const finishTest = (nextResult: TestResultData) => { if (!recorded.current.has(runId.current)) { recorded.current.add(runId.current); setEntries(old => [...old.slice(-99), {id: String(runId.current), completedAt: Date.now(), result: nextResult}]); } setResult(nextResult); setTestScreen('result'); window.history.pushState({ testResult: true }, '', '#test-result'); };
  const backToCatalog = () => { setTestScreen('catalog'); setSelectedTest(null); setResult(null); window.history.pushState({}, '', window.location.pathname); };
  const retakeTest = () => { runId.current++; setResult(null); setTestScreen('session'); window.history.pushState({ testSession: true }, '', '#test-session'); };
  const inTestFlow = route === 'tests' && testScreen !== 'catalog';

  return <AppShell route={route} onRouteChange={goTo} toast={toast} onCloseToast={() => setToast('')} hideNavigation={inTestFlow || statistics}>
    <div className="page-view" hidden={statistics || route !== 'home'}><HomePage onStartTest={() => goTo('tests')} onNotify={notify} onStatistics={openStatistics} /></div>
    <div className="page-view" hidden={statistics || route !== 'tests' || testScreen !== 'catalog'}><TestsPage onSelectTest={openTest} platform={platform} active={!statistics && route === 'tests' && testScreen === 'catalog'} /></div>
    <div className="page-view" hidden={statistics || route !== 'notes'}><NotesPage /></div>
    <div className="page-view" hidden={statistics || route !== 'profile'}><ProfilePage platform={platform} onProgress={openStatistics} onTests={() => goTo('tests')} /></div>
    {statistics && <StatisticsPage entries={entries} platform={platform} onBack={closeStatistics} />}
    {testScreen === 'session' && selectedTest && <TestSession test={selectedTest} platform={platform} onComplete={finishTest} onExit={backToCatalog} />}
    {testScreen === 'result' && result && <TestResult result={result} platform={platform} onBack={backToCatalog} onRetake={retakeTest} />}
    <button className="fullscreen-toggle" aria-label="Открыть полноэкранный режим" onClick={() => platform.requestFullscreen()}>⛶</button>
  </AppShell>;
}
