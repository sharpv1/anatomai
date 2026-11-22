/** Default-off build must never complete a local test after a Telegram launch. */
import assert from 'node:assert/strict';
import {chromium} from 'playwright';
const base=process.env.MEDEXA_LOCAL_URL??'http://127.0.0.1:5180';assert.ok(['localhost','127.0.0.1'].includes(new URL(base).hostname));
const browser=await chromium.launch({executablePath:process.env.CHROMIUM_PATH??'/usr/bin/chromium',args:['--no-sandbox']});
try {
 const p=await browser.newPage();const requests=[];const errors=[];p.on('pageerror',e=>errors.push(e.message));
 await p.route('https://telegram.org/**',r=>r.fulfill({contentType:'application/javascript',body:''}));
 await p.route('**/api/v1/**',r=>{requests.push(new URL(r.request().url()).pathname);return r.fulfill({status:401,contentType:'application/json',body:JSON.stringify({error:{code:'INIT_DATA_INVALID'}})});});
 await p.goto(base);await p.locator('.hero').waitFor();assert.equal(requests.length,0);
 await p.getByRole('button',{name:'Тесты',exact:true}).click();await p.locator('.test-card').first().click();await p.locator('.topic-page').waitFor({state:'visible'});
 // No focus/pageshow or polling tick: the legacy launch handler itself must guard this race.
 await p.evaluate(()=>{window.Telegram={WebApp:{initData:'malformed-proof',platform:'ios',version:'8.0',ready(){},expand(){},onEvent(){},offEvent(){}}};document.querySelector('.topic-modes button').click();});
 await p.getByRole('alert').waitFor();assert.equal(await p.locator('.test-question').count(),0);assert.equal(await p.locator('.page-view').count(),0);assert.ok(requests.includes('/api/v1/auth/telegram'));
 await p.evaluate(()=>{window.Telegram.WebApp.initData='';window.dispatchEvent(new Event('focus'));});await p.getByRole('alert').waitFor();await p.waitForTimeout(350);assert.equal(await p.locator('.page-view').count(),0);assert.equal(await p.locator('.hero').count(),0);assert.equal(await p.evaluate(()=>sessionStorage.getItem('anatomai:server-mode')),'1');await p.reload();await p.getByRole('alert').waitFor();assert.equal(await p.locator('.page-view').count(),0);assert.deepEqual(errors,[]);await p.close();
 const late=await browser.newPage();
 await late.route('https://telegram.org/**',r=>r.fulfill({contentType:'application/javascript',body:''}));
 await late.route('**/api/v1/**',r=>r.fulfill({status:401,contentType:'application/json',body:JSON.stringify({error:{code:'INIT_DATA_INVALID'}})}));
 await late.goto(base);await late.locator('.hero').waitFor();await late.getByRole('button',{name:'Тесты',exact:true}).click();await late.locator('.test-card').first().click();await late.getByRole('button',{name:'Обучение',exact:true}).click();
 for(let i=0;i<4;i++){await late.locator('.test-session__skip').click();}
 await late.locator('.test-choice').first().click();
 await late.evaluate(()=>{window.Telegram={WebApp:{initData:'malformed-proof',platform:'ios',version:'8.0',ready(){},expand(){},onEvent(){},offEvent(){}}};document.querySelector('.test-session__action').click();});
 await late.getByRole('alert').waitFor();assert.equal(await late.locator('.test-result,.page-view').count(),0);await late.close();
 const offline=await browser.newPage();let calls=0;
 await offline.route('https://telegram.org/**',r=>r.fulfill({contentType:'application/javascript',body:`window.Telegram={WebApp:{initData:'unverified-launch',platform:'ios',version:'8.0',ready(){},expand(){},onEvent(){},offEvent(){}}};`}));
 await offline.route('**/api/v1/**',r=>{calls++;return r.abort();});await offline.goto(base);await offline.getByRole('alert').waitFor();assert.ok(calls>0);assert.equal(await offline.locator('.hero,.test-question,.page-view').count(),0);await offline.getByRole('button',{name:'Повторить',exact:true}).click();await offline.getByRole('alert').waitFor();assert.equal(await offline.locator('.page-view').count(),0);await offline.close();
 console.log('PASS default-off Telegram entry, late SDK before start/finish, invalid proof, lost launch, offline/retry: no local fallback');
} finally {await browser.close();}
