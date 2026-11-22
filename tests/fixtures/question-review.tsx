// Test-only fixture: never imported by the application or its production entry.
import {useEffect,useMemo} from 'react';
import {createRoot} from 'react-dom/client';
import {DailyQuestions} from '../../src/components/DailyQuestions';
import {QuestionReviewPage} from '../../src/pages/QuestionReviewPage';
import {AppShell} from '../../src/components/AppShell';
import {createTelegramPlatformAdapter} from '../../src/platform/telegram/TelegramPlatformAdapter';
import {questionsForTest} from '../../src/features/tests/data';
import type {ReviewQuestion} from '../../src/features/tests/questionReview';
import '../../src/styles/app.css';
import '../../src/styles/tokens.css';
import '../../src/styles/viewport.css';
function Fixture(){
 const platform=useMemo(()=>createTelegramPlatformAdapter(),[]);
 useEffect(()=>{platform.init();return()=>platform.dispose();},[platform]);
 const variant=new URLSearchParams(location.search).get('case');
 const sample=questionsForTest('anatomy')[0];
 const questions:ReviewQuestion[]=variant==='empty'?[]:variant==='multi'?[{id:'multi-fixture',text:'Тестовый пример нескольких правильных вариантов',answers:['Тестовый вариант A','Тестовый вариант B','Тестовый вариант C'],correctAnswer:[0,2]}]:Array.from({length:200},(_,i)=>({...sample,id:`fixture-${i}`,text:`Тестовая длинная формулировка ${i+1}. ${sample.text.repeat(6)}`,answers:sample.answers.map(a=>a.repeat(12))}));
 if(variant==='daily-empty')return <AppShell route="home" onRouteChange={()=>{}} toast="" onCloseToast={()=>{}}><DailyQuestions topics={[]} onOpen={()=>{throw new Error('Unavailable question action');}}/></AppShell>;
 return <AppShell route="tests" onRouteChange={()=>{}} hideNavigation toast="" onCloseToast={()=>{}}><QuestionReviewPage title="Тестовая длинная тема без изменения реального банка вопросов" questions={questions} platform={platform} onBack={()=>history.back()}/></AppShell>;
}
createRoot(document.getElementById('root')!).render(<Fixture/>);
