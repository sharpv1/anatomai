import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import type { AppRoute } from './components/BottomNavigation';
import { AppShell } from './components/AppShell';
import { TestResult } from './features/tests/TestResult';
import { TestSession } from './features/tests/TestSession';
import type { TestDefinition, TestResultData, TestMode } from './features/tests/types';
import { TopicPage } from './pages/TopicPage';
import { QuestionReviewPage } from './pages/QuestionReviewPage';
import { questionsForTest } from './features/tests/data';
import './styles/study-7.7.css';
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
import './styles/refinement-7.8.css';
import './styles/ux-8.2.css';
import {catalog,disciplines} from './features/library/catalog';

type AuxiliaryNavigation = {kind:'notes';disciplineId:string|null;origin:'home'|'notes';backTo:'home'|'catalog'} | {kind:'daily';testId:string};
function readAuxiliary(value: unknown): AuxiliaryNavigation|null {
 if(!value||typeof value!=='object')return null;const v=value as Record<string,unknown>;
 if(v.kind==='notes'&&(v.origin==='home'||v.origin==='notes')&&(v.backTo==='home'||v.backTo==='catalog')&&(v.disciplineId===null||disciplines.some(d=>d.id===v.disciplineId)))return v as AuxiliaryNavigation;
 if(v.kind==='daily'&&catalog.some(c=>c.test.id===v.testId&&c.questionCount>0))return v as AuxiliaryNavigation;
 return null;
}

export default function App() {
  const platform = useMemo(() => createTelegramPlatformAdapter(), []);
  useEffect(() => { platform.init(); return () => platform.dispose(); }, [platform]);
  const [route, setRoute] = useState<AppRoute>('home');
  const [testScreen, setTestScreen] = useState<'catalog' | 'topic' | 'review' | 'session' | 'result'>('catalog');
  const [reviewOrigin,setReviewOrigin]=useState<'topic'|'home'>('topic');
  const [notesId,setNotesId]=useState<string|null>(null);
  const [notesOrigin,setNotesOrigin]=useState<'home'|'notes'|null>(null);
  const [notesReset,setNotesReset]=useState(0);
  const auxiliary=useRef<AuxiliaryNavigation|null>(null);
  const [initialMode,setInitialMode] = useState<TestMode>('learning');
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

  const applyAuxiliary = useCallback((nav: AuxiliaryNavigation) => {
    auxiliary.current = nav;
    setStatistics(false);
    setResult(null);
    if (nav.kind === 'notes') {
      setRoute('notes');
      setNotesId(nav.disciplineId);
      setNotesOrigin(nav.origin);
      setTestScreen('catalog');
      setReviewOrigin('topic');
      setSelectedTest(null);
    } else {
      setRoute('home');
      setSelectedTest(catalog.find(item => item.test.id === nav.testId)!.test);
      setReviewOrigin('home');
      setTestScreen('review');
    }
  }, []);

  useEffect(() => {
    const sync = () => {
      const nav = readAuxiliary(window.history.state?.ux82);
      if (nav) { applyAuxiliary(nav); return; }
      if (!auxiliary.current) return;
      const root = window.history.state?.ux82Root;
      const fallback = auxiliary.current.kind === 'notes' ? auxiliary.current.origin : 'home';
      auxiliary.current = null;
      setRoute(root === 'notes' || root === 'home' ? root : fallback);
      setNotesId(null);
      setNotesOrigin(null);
      setTestScreen('catalog');
      setSelectedTest(null);
      setReviewOrigin('topic');
    };
    sync();
    window.addEventListener('popstate', sync);
    return () => window.removeEventListener('popstate', sync);
  }, [applyAuxiliary]);

  const pushAuxiliary = (nav: AuxiliaryNavigation) => {
    if (!auxiliary.current) {
      window.history.replaceState({ ...window.history.state, ux82Root: route }, '', window.location.href);
    }
    const hash = nav.kind === 'daily' ? '#daily-answers'
      : `#notes${nav.disciplineId ? `/${encodeURIComponent(nav.disciplineId)}` : ''}`;
    window.history.pushState({ ux82: nav }, '', hash);
    applyAuxiliary(nav);
  };
  const openHomeNotes = (disciplineId: string | null) => {
    setNotesReset(value => value + 1);
    pushAuxiliary({ kind: 'notes', disciplineId, origin: 'home', backTo: 'home' });
  };

  useEffect(() => { if (!toast) return; const timeout = window.setTimeout(() => setToast(''), 2200); return () => window.clearTimeout(timeout); }, [toast]);
  const notify = (message: string) => setToast(message);
  const goTo = (nextRoute: AppRoute) => { if(auxiliary.current){window.history.replaceState({},'',window.location.pathname);auxiliary.current=null;}setNotesId(null);setNotesOrigin(null);setStatistics(false); setRoute(nextRoute); if (nextRoute === 'tests') setTestScreen('catalog'); };
  const openTest = (test: TestDefinition) => { setReviewOrigin('topic');setSelectedTest(test); setTestScreen('topic'); window.history.pushState({ topic: true }, '', '#topic'); };
  const openQuestionReview = () => { setReviewOrigin('topic');window.history.pushState({ questionReview: true }, '', '#question-review'); setTestScreen('review'); };
  const closeQuestionReview = () => { if(reviewOrigin==='home'){window.history.back();return;}if (window.location.hash === '#question-review') window.history.back(); else setTestScreen('topic'); };
  const backFromTopic = () => { if (window.location.hash === '#question-review') setTestScreen('review'); else backToCatalog(); };
  const startTopic=(mode:TestMode)=>{runId.current++;setInitialMode(mode);setTestScreen('session');window.history.pushState({testSession:true},'','#test-session');};
  const backToTopic=()=>{setTestScreen('topic');window.history.pushState({topic:true},'','#topic');};
  const finishTest = (nextResult: TestResultData) => { if (!recorded.current.has(runId.current)) { recorded.current.add(runId.current); setEntries(old => [...old.slice(-99), {id: String(runId.current), completedAt: Date.now(), result: nextResult}]); } setResult(nextResult); setTestScreen('result'); window.history.pushState({ testResult: true }, '', '#test-result'); };
  const backToCatalog = () => { setTestScreen('catalog'); setSelectedTest(null); setResult(null); window.history.pushState({}, '', window.location.pathname); };
  const retakeTest = () => { setResult(null);backToTopic(); };
  const homeReview=testScreen==='review'&&reviewOrigin==='home';
  const inTestFlow = (route === 'tests' && testScreen !== 'catalog')||homeReview;

  return <AppShell route={route} onRouteChange={goTo} toast={toast} onCloseToast={() => setToast('')} hideNavigation={inTestFlow || statistics}>
    <div className="page-view" hidden={statistics || route !== 'home'||homeReview}><HomePage onStartTest={() => goTo('tests')} onNotify={notify} onStatistics={openStatistics} onNotes={() => openHomeNotes(null)} onNoteDiscipline={id=>openHomeNotes(id)} onDailyReview={test=>pushAuxiliary({kind:'daily',testId:test.id})} entries={entries} platform={platform} /></div>
    <div className="page-view" hidden={statistics || route !== 'tests' || testScreen !== 'catalog'}><TestsPage onSelectTest={openTest} platform={platform} active={!statistics && route === 'tests' && testScreen === 'catalog'} /></div>
    <div className="page-view" hidden={statistics || route !== 'notes'}><NotesPage platform={platform} active={!statistics&&route==='notes'} selectedId={notesId} onSelect={id=>pushAuxiliary({kind:'notes',disciplineId:id,origin:auxiliary.current?.kind==='notes'?auxiliary.current.origin:'notes',backTo:'catalog'})} onBack={()=>window.history.back()} canGoBack={notesOrigin==='home'||notesId!==null} backLabel={auxiliary.current?.kind==='notes'&&auxiliary.current.backTo==='catalog'?'К дисциплинам':'На главную'} resetSearch={notesReset}/></div>
    <div className="page-view" hidden={statistics || route !== 'profile'}><ProfilePage platform={platform} entries={entries} onReset={() => setEntries([])} /></div>
    {statistics && <StatisticsPage entries={entries} platform={platform} onBack={closeStatistics} />}
    {(testScreen === 'topic' || (testScreen === 'review'&&reviewOrigin==='topic')) && selectedTest && <TopicPage test={selectedTest} entries={entries} platform={platform} onBack={backFromTopic} onStart={startTopic} onReview={openQuestionReview} active={testScreen === 'topic'}/>}
    {testScreen === 'review' && selectedTest && <QuestionReviewPage title={selectedTest.title} questions={questionsForTest(selectedTest.id)} platform={platform} onBack={closeQuestionReview} listenPopstate={reviewOrigin==='topic'} backLabel={reviewOrigin==='home'?'На главную':'К теме'}/>}
    {testScreen === 'session' && selectedTest && <TestSession test={selectedTest} platform={platform} onComplete={finishTest} onExit={backToTopic} initialMode={initialMode} />}
    {testScreen === 'result' && result && <TestResult result={result} platform={platform} onBack={backToCatalog} onRetake={retakeTest} />}
    <button className="fullscreen-toggle" aria-label="Открыть полноэкранный режим" onClick={() => platform.requestFullscreen()}>⛶</button>
  </AppShell>;
}
