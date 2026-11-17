import { useEffect, useMemo, useState } from 'react';
import type { AppRoute } from './components/BottomNavigation';
import { AppShell } from './components/AppShell';
import { TestResult } from './features/tests/TestResult';
import { TestSession } from './features/tests/TestSession';
import type { TestDefinition, TestResultData } from './features/tests/types';
import { HomePage } from './pages/HomePage';
import { TestsPage } from './pages/TestsPage';
import { createTelegramPlatformAdapter } from './platform/telegram/TelegramPlatformAdapter';
import './styles/app.css';
import './features/tests/TestsExperience.css';
import './styles/motion.css';

export default function App() {
  const platform = useMemo(() => createTelegramPlatformAdapter(), []);
  useEffect(() => { platform.init(); return () => platform.dispose(); }, [platform]);
  const [route, setRoute] = useState<AppRoute>('home');
  const [testScreen, setTestScreen] = useState<'catalog' | 'session' | 'result'>('catalog');
  const [selectedTest, setSelectedTest] = useState<TestDefinition | null>(null);
  const [result, setResult] = useState<TestResultData | null>(null);
  const [toast, setToast] = useState('');

  useEffect(() => { if (!toast) return; const timeout = window.setTimeout(() => setToast(''), 2200); return () => window.clearTimeout(timeout); }, [toast]);
  const notify = (message: string) => setToast(message);
  const goTo = (nextRoute: AppRoute) => { setRoute(nextRoute); if (nextRoute === 'tests') setTestScreen('catalog'); else if (nextRoute !== 'home') notify('Раздел скоро здесь'); };
  const openTest = (test: TestDefinition) => { setSelectedTest(test); setTestScreen('session'); window.history.pushState({ testSession: true }, '', '#test-session'); };
  const finishTest = (nextResult: TestResultData) => { setResult(nextResult); setTestScreen('result'); window.history.pushState({ testResult: true }, '', '#test-result'); };
  const backToCatalog = () => { setTestScreen('catalog'); setSelectedTest(null); setResult(null); window.history.pushState({}, '', window.location.pathname); };
  const retakeTest = () => { setResult(null); setTestScreen('session'); window.history.pushState({ testSession: true }, '', '#test-session'); };
  const inTestFlow = route === 'tests' && testScreen !== 'catalog';

  return <AppShell route={route} onRouteChange={goTo} toast={toast} onCloseToast={() => setToast('')} hideNavigation={inTestFlow}>
    <div className="page-view" hidden={route !== 'home'}><HomePage onStartTest={() => goTo('tests')} onNotify={notify} /></div>
    <div className="page-view" hidden={route !== 'tests' || testScreen !== 'catalog'}><TestsPage onSelectTest={openTest} /></div>
    {testScreen === 'session' && selectedTest && <TestSession test={selectedTest} platform={platform} onComplete={finishTest} onExit={backToCatalog} />}
    {testScreen === 'result' && result && <TestResult result={result} platform={platform} onBack={backToCatalog} onRetake={retakeTest} />}
    <button className="fullscreen-toggle" aria-label="Открыть полноэкранный режим" onClick={() => platform.requestFullscreen()}>⛶</button>
  </AppShell>;
}
