/** Real endpoints, real cookie session and database. Only the Telegram host SDK is mocked. */
import assert from 'node:assert/strict';
import {readFileSync,writeFileSync,mkdirSync} from 'node:fs';
import {chromium} from 'playwright';
const f=JSON.parse(readFileSync(process.argv[2],'utf8'));assert.equal(new URL(f.origin).hostname,'127.0.0.1');assert.equal(new URL(f.origin).protocol,'https:');
const browser=await chromium.launch({executablePath:process.env.CHROMIUM_PATH??'/usr/bin/chromium',args:['--no-sandbox']});
const shots='docs/screenshots/frontend-6b';mkdirSync(shots,{recursive:true});
try {
 // Trust is relaxed only for this test's ephemeral self-signed loopback certificate.
 const context=await browser.newContext({ignoreHTTPSErrors:true,viewport:{width:390,height:844},reducedMotion:'reduce'});
 const p=await context.newPage();p.setDefaultTimeout(15000);const errors=[],apiErrors=[],writes=[];p.on('pageerror',e=>errors.push(e.message));
 p.on('response',async r=>{if(r.url().includes('/api/')){assert.equal(new URL(r.url()).origin,f.origin);if(r.status()>=400)apiErrors.push({path:new URL(r.url()).pathname,status:r.status()});}});
 p.on('request',r=>{if(r.url().includes('/api/')&&r.method()!=='GET')writes.push({method:r.method(),path:new URL(r.url()).pathname});});
 const launchUser=JSON.parse(new URLSearchParams(f.initData).get('user')).id;
 await p.route('https://telegram.org/**',r=>r.fulfill({contentType:'application/javascript',body:`window.callbacks=new Set();window.Telegram={WebApp:{initData:${JSON.stringify(f.initData)},initDataUnsafe:{user:{id:${launchUser}}},platform:'ios',version:'8.0',isFullscreen:true,viewportHeight:844,viewportStableHeight:844,safeAreaInset:{top:59,bottom:34},contentSafeAreaInset:{top:45,bottom:0},ready(){},expand(){},onEvent(){},offEvent(){},BackButton:{show(){},hide(){},onClick(cb){callbacks.add(cb)},offClick(cb){callbacks.delete(cb)}}}};`}));
 await p.goto(f.origin);await p.locator('.hero').waitFor();
 const cookies=await context.cookies(f.origin);const session=cookies.find(c=>c.name==='__Host-medexa_session');assert.ok(session?.httpOnly&&session.secure);assert.ok(!(await p.evaluate(()=>document.cookie)).includes('__Host-medexa_session'));
 async function topic(){await p.getByRole('button',{name:'Тесты',exact:true}).click();await p.locator('.test-card').click();await p.locator('.test-card').click();await p.locator('.topic-modes').waitFor();}
 let dropped=false;const submitHeaders=[];
 await p.route('**/api/v1/attempts/*/items/*/submit',async r=>{submitHeaders.push({key:r.request().headers()['idempotency-key'],match:r.request().headers()['if-match']});const response=await r.fetch();if(!dropped){dropped=true;await r.abort();}else await r.fulfill({response});});
 await topic();await p.locator('.topic-modes').getByRole('button',{name:'Обучение',exact:true}).click();await p.locator('.test-question').waitFor();
 assert.equal(await p.locator('.test-choice.correct').count(),0);await p.locator('.test-choice').first().click();await p.getByRole('button',{name:'Повторить запрос',exact:true}).waitFor();await p.getByRole('button',{name:'Повторить запрос',exact:true}).click();assert.equal(submitHeaders.length,2);assert.deepEqual(submitHeaders[0],submitHeaders[1]);await p.getByText('SYNTHETIC SERVER EXPLANATION',{exact:true}).waitFor();await p.waitForFunction(()=>!document.querySelector('.test-session__action').disabled);
 const learningStarts=writes.filter(w=>w.path==='/api/v1/attempts').length;
 await p.reload();await p.locator('.hero .start').waitFor();await p.locator('.hero .start').click();await p.getByText('SYNTHETIC SERVER EXPLANATION',{exact:true}).waitFor();assert.equal(writes.filter(w=>w.path==='/api/v1/attempts').length,learningStarts);
 await p.getByRole('button',{name:'Далее',exact:true}).click();await p.getByText('Вопрос 2 из 2',{exact:true}).waitFor();await p.waitForFunction(()=>!document.querySelector('.test-session__skip').disabled);await p.getByRole('button',{name:'Пропустить',exact:true}).click();await p.locator('.test-result').waitFor();assert.equal(await p.locator('.test-result__badge strong').innerText(),'50%');
 await p.screenshot({path:`${shots}/https-learning-result-390.png`});await p.getByRole('button',{name:'Разобрать ошибки',exact:true}).click();await p.locator('.test-review__item').first().waitFor();await p.getByRole('button',{name:'К тестам',exact:true}).click();await p.getByRole('button',{name:'Главная',exact:true}).click();await p.waitForFunction(()=>document.querySelector('.stats dd')?.textContent==='1');
 await topic();await p.locator('.topic-modes').getByRole('button',{name:'Экзамен',exact:true}).click();await p.locator('.test-question').waitFor();
 await p.locator('.test-choice').first().click();await p.waitForFunction(()=>!document.querySelector('.test-session__action').disabled);await p.locator('.test-choice').nth(1).click();await p.waitForFunction(()=>!document.querySelector('.test-session__action').disabled);assert.equal(await p.locator('.test-choice.correct').count(),0);assert.equal(await p.getByText('SYNTHETIC SERVER EXPLANATION',{exact:true}).count(),0);
 await p.getByRole('button',{name:'Далее',exact:true}).click();await p.getByText('Вопрос 2 из 2',{exact:true}).waitFor();await p.getByRole('button',{name:'Предыдущий вопрос'}).click();await p.getByText('Вопрос 1 из 2',{exact:true}).waitFor();assert.equal(await p.locator('.test-choice.selected').count(),1);await p.reload();await p.locator('.hero .start').waitFor();await p.locator('.hero .start').click();await p.getByText('Вопрос 1 из 2',{exact:true}).waitFor();assert.equal(await p.locator('.test-choice.selected').count(),1);
 await p.getByRole('button',{name:'Далее',exact:true}).click();await p.getByText('Вопрос 2 из 2',{exact:true}).waitFor();await p.waitForFunction(()=>!document.querySelector('.test-session__action').disabled);await p.getByRole('button',{name:'Завершить экзамен',exact:true}).click();await p.locator('.test-result').waitFor();assert.equal(await p.locator('.test-result__badge strong').innerText(),'0%');await p.getByRole('button',{name:'Разобрать ошибки',exact:true}).click();await p.getByText('SYNTHETIC SERVER EXPLANATION',{exact:true}).first().waitFor();await p.screenshot({path:`${shots}/https-exam-review-390.png`});
 await p.getByRole('button',{name:'К тестам',exact:true}).click();await topic();
 // The published test definition has a genuine four-second server deadline.
 await p.locator('.test-list .test-card').filter({hasText:'SYNTHETIC DEADLINE'}).getByRole('button',{name:'Экзамен',exact:true}).click();await p.locator('.test-question').waitFor();await p.waitForFunction(()=>!document.querySelector('.test-session__action').disabled);await p.locator('.test-choice').first().click();await p.waitForFunction(()=>!document.querySelector('.test-session__action').disabled);
 await p.getByRole('button',{name:'Назад к тестам',exact:true}).count().then(async count=>{if(count)await p.getByRole('button',{name:'Назад к тестам',exact:true}).click();else await p.evaluate(()=>[...callbacks][0]());});
 await p.getByRole('button',{name:'Главная',exact:true}).click();await p.locator('.hero').waitFor();
 // Close the page: the DB-backed finalizer must complete without client requests.
 await p.close();await new Promise(r=>setTimeout(r,6500));
 const {execFileSync}=await import('node:child_process');execFileSync(process.env.MEDEXA_E2E_PYTHON,[process.env.MEDEXA_E2E_DB_CHECK],{stdio:'pipe',env:process.env});
 const after=await context.newPage();await after.goto(f.origin);await after.locator('.hero').waitFor();await after.waitForFunction(()=>document.querySelector('.stats dd')?.textContent==='3');
 assert.deepEqual(errors,[]);assert.ok(apiErrors.every(e=>e.path==='/api/v1/auth/session'&&e.status===401),JSON.stringify(apiErrors));
 const result={backend:'real FastAPI HTTPS + PostgreSQL16',migration:'0010_progress_statistics',learning:true,exam:true,serverResult:true,secureHttpOnlyCookie:true,csrf:true,reopen:true,editableExam:true,exactMutationReplayAfterRealResponseLoss:true,protectedReview:true,backgroundTimeoutAfterPageClose:true,completedTests:3,apiErrors,realTelegramIOS:false};writeFileSync(`${shots}/https-results.json`,JSON.stringify(result,null,2));console.log(JSON.stringify(result));
}finally{await browser.close();}
