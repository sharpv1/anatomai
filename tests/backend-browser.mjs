import assert from 'node:assert/strict';
import {mkdirSync,writeFileSync,readFileSync} from 'node:fs';
import {chromium} from 'playwright';
const active=process.env.MEDEXA_UI_URL??'http://127.0.0.1:5181';
const legacy=process.env.MEDEXA_LOCAL_URL??'http://127.0.0.1:5180';
const baseline=process.env.MEDEXA_BASE_URL??'http://127.0.0.1:5182';
for(const u of [active,legacy,baseline])assert.ok(['127.0.0.1','localhost'].includes(new URL(u).hostname),'Tests require isolated loopback servers');
const shots=process.env.MEDEXA_SCREENSHOTS??'docs/screenshots/frontend-6a';mkdirSync(shots,{recursive:true});
const ids={d:'11111111-1111-4111-8111-111111111111',t:'22222222-2222-4222-8222-222222222222',test:'33333333-3333-4333-8333-333333333333',q:'44444444-4444-4444-8444-444444444444',note:'55555555-5555-4555-8555-555555555555',o1:'66666666-6666-4666-8666-666666666666',o2:'77777777-7777-4777-8777-777777777777'};
const now='2026-11-22T06:00:00Z';
const user=n=>({id:n===1?'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa':'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb',telegram_user_id:String(n),first_name:n===1?'СЕРВЕР Один':'СЕРВЕР Два',last_name:'Оченьдлинноеимя Пользователя',username:null,photo_url:null,timezone:'UTC',language:'ru',version:1,roles:['student']});
const session=n=>({id:'88888888-8888-4888-8888-888888888888',user:user(n),csrf_token:'synthetic-csrf-'+n,expires_at:'2027-01-01T00:00:00Z',idle_expires_at:'2027-01-01T00:00:00Z'});
const summary=(n,empty=false)=>({completed_tests:empty?0:n===1?3:9,answered_count:empty?0:12,correct_count:empty?0:10,wrong_count:empty?0:2,skipped_count:0,average_percent:empty?null:83,practice_seconds:empty?null:120,activity_streak_days:empty?0:1,period:'all',timezone:'UTC',data_scope:'server_history',calculated_at:now});
const disc={id:ids.d,slug:'synthetic-anatomy',title:'Анатомия',icon_key:'anatomy',color_token:'blue',question_count:2,topic_count:1,note_count:1};
const topic={id:ids.t,discipline_id:ids.d,category_id:null,slug:'synthetic-heart',title:'Сердце и кровообращение — длинное медицинское название темы',question_count:2,test_definition_id:ids.test,available_modes:['learning','exam']};
const test={id:ids.test,topic_id:ids.t,slug:'synthetic-test',title:'Опубликованный серверный тест',exam_duration_seconds:120,question_count:2,available_modes:['learning','exam']};
const result={attempt_id:'99999999-9999-4999-8999-999999999999',title:'СЕРВЕРНЫЙ результат',total:2,correct:1,wrong:1,skipped:0,answered:2,percent:50,duration_seconds:80,started_at:'2026-11-22T05:58:40Z',finalized_at:now,finish_reason:'user_finish'};
const history=n=>({id:result.attempt_id,mode:'learning',discipline_id:ids.d,topic_id:ids.t,test_definition_id:ids.test,result:{...result,title:`СЕРВЕРНЫЙ результат ${n}`},activity_date:'2026-11-22',activity_timezone:'UTC'});
const reference={question_id:ids.q,revision_id:'abcdefab-cdef-4bcd-8abc-abcdefabcdef',number:17,kind:'single_choice',text:'Длинная медицинская формулировка: '+('анатомическое строение и кровообращение сердца ').repeat(18),options:[{id:ids.o1,position:0,code:'A',text:'Правильный длинный вариант: '+('анатомическое описание ').repeat(12)},{id:ids.o2,position:1,code:'B',text:'Нейтральный вариант ответа'}],correct_option_ids:[ids.o1]};
const envelope=data=>({data,meta:{request_id:'synthetic-ui-request',server_time:now,schema_version:'1'}});
const page=data=>({...envelope(data),page:{has_more:false,next_cursor:null,total:data.length},catalog_version:7});
const browser=await chromium.launch({executablePath:process.env.CHROMIUM_PATH??'/usr/bin/chromium',args:['--no-sandbox']});
const results=[];
async function setup(width,mode,{url=active,empty=false,missing=false,offline=false}={}){
 const p=await browser.newPage({viewport:{width,height:mode==='short'?568:812},reducedMotion:'reduce',timezoneId:'UTC'});
 await p.clock.setFixedTime(new Date(now));
 p.setDefaultTimeout(12000);
 const errors=[];p.on('pageerror',e=>errors.push(e.message));
 const state={cookie:null,posts:0,empty,offline,homeFailure:false,notes:false,historyMore:false,locked:false,private:[],mutations:[]};
 await p.route('https://telegram.org/**',r=>r.fulfill({contentType:'application/javascript',body:missing?'':`window.callbacks=new Set();window.Telegram={WebApp:{initData:new URLSearchParams({user:JSON.stringify({id:1,first_name:'UNVERIFIED SDK'})}).toString(),initDataUnsafe:{user:{id:1}},platform:'ios',version:'8.0',isFullscreen:${mode!=='expanded'},viewportHeight:${mode==='short'?568:812},viewportStableHeight:${mode==='short'?568:812},safeAreaInset:{top:${mode==='expanded'?0:59},bottom:34},contentSafeAreaInset:{top:${mode==='expanded'?0:45},bottom:0},ready(){},expand(){},onEvent(){},offEvent(){},BackButton:{isVisible:false,show(){this.isVisible=true},hide(){this.isVisible=false},onClick(cb){callbacks.add(cb)},offClick(cb){callbacks.delete(cb)}}}};` }));
 await p.route('**/api/v1/**',async route=>{
  const req=route.request(),u=new URL(req.url());assert.equal(u.origin,new URL(url).origin,'No external Backend requests');
  const path=u.pathname.slice('/api/v1'.length);
  const send=(body,status=200)=>route.fulfill({status,contentType:'application/json',body:JSON.stringify(body)});
  if(state.offline){await route.abort();return;}
  if(req.method()!=='GET'&&path!=='/auth/telegram')state.mutations.push(path);
  if(path==='/me/active-attempt')return send(envelope(null));
  if(path==='/auth/session')return state.cookie?send(envelope(session(state.cookie))):send({error:{code:'AUTH_REQUIRED'}},401);
  if(path==='/auth/telegram'){
   state.posts++;const id=JSON.parse(new URLSearchParams(JSON.parse(req.postData()).init_data).get('user')).id;
   state.cookie=id;return send(envelope(session(id)));
  }
  if(!state.cookie)return send({error:{code:'AUTH_REQUIRED'}},401);
  state.private.push({path,owner:state.cookie});
  const n=state.cookie,s=summary(n,state.empty);
  if(state.homeFailure&&path==='/me/home')return send({error:{code:'SERVICE_NOT_READY'}},503);
  if(path==='/me/home')return send(envelope({statistics:s,active_attempt:null,recent_results:state.empty?[]:[history(n)]}));
  if(path==='/me/statistics')return send(envelope(s));
  if(path==='/me/progress')return send(envelope({statistics:s,unattributed_topic_responses:0,source:'immutable_attempts'}));
  if(path==='/me/achievements')return send(envelope([{code:'first',title:'Первый шаг',state:state.empty?'locked':'unlocked',condition:'Первый завершённый тест',progress:state.empty?0:1,target:1,granted_at:null}]));
  if(path==='/me/recommendations')return send(envelope(state.empty?[]:[{topic_id:ids.t,discipline_id:ids.d,title:topic.title,question_count:2,reason:'weak_topic',observed_average_percent:50,observed_attempts:1}]));
  if(path==='/me/daily-topic')return send(envelope({local_date:'2026-11-22',timezone:'UTC',topic_id:state.empty?null:ids.t,title:state.empty?null:topic.title,discipline_id:state.empty?null:ids.d,question_count:state.empty?null:2,availability:state.empty?'empty':'available',catalog_version:7,selector_version:1}));
  if(path==='/me/activity')return send(envelope({timezone:'UTC',date_policy:'frozen_attempt_timezone',start:'2026-11-16',end:'2026-11-22',days:Array.from({length:7},(_,i)=>({date:`2026-11-${16+i}`,completed_tests:state.empty?0:i===6?3:0,answered_count:0,correct_count:0,practice_seconds:0,average_percent:null}))}));
  if(path==='/me/attempts'){const second=Boolean(u.searchParams.get('cursor'));const h=history(n);if(second){h.id='99999999-9999-4999-8999-999999999998';h.result={...h.result,attempt_id:h.id,title:'СЕРВЕРНЫЙ результат ещё'};}return send({...envelope(state.empty?[]:[h]),page:{has_more:state.historyMore&&!second,next_cursor:state.historyMore&&!second?'next-synthetic':null}});}
  if(path==='/disciplines')return send(page(state.empty?[]:[disc]));
  if(path==='/disciplines/'+ids.d)return send(envelope(disc));
  if(path==='/topics')return send(page(state.empty?[]:[topic]));
  if(path==='/topics/'+ids.t)return send(envelope(topic));
  if(path==='/me/topics/'+ids.t+'/summary')return send(envelope({topic_id:ids.t,completed_count:0,best_percent:null,ever_wrong_question_count:null,unresolved_wrong_question_count:null,favorites_count:null,favorites_status:'not_configured'}));
  if(path==='/test-definitions')return send(page(state.empty?[]:[test]));
  if(path==='/topics/'+ids.t+'/reference-questions'&&state.locked)return send({error:{code:'EXAM_REFERENCE_LOCKED'}},409);
  if(path==='/topics/'+ids.t+'/reference-questions')return send(page(u.searchParams.get('query')?.includes('нетсовпадений')?[]:[reference]));
  if(path==='/notes')return send(page(state.notes?[{id:ids.note,discipline_id:ids.d,topic_id:ids.t,title:'СЕРВЕРНЫЙ конспект'}]:[]));
  if(path==='/notes/'+ids.note)return send(envelope({id:ids.note,discipline_id:ids.d,topic_id:ids.t,title:'СЕРВЕРНЫЙ конспект',revision_id:ids.q,body:'СЕРВЕРНЫЙ текст. '+('Длинная медицинская формулировка. ').repeat(12),body_format:'plain_text',asset_id:null,download_available:false}));
  throw Error('Unexpected API route: '+path);
 });
 await p.goto(url);await p.addStyleTag({content:'*,*::before,*::after{animation:none!important;transition:none!important;caret-color:transparent!important}'});
 return {p,state,errors};
}
async function fit(p){const sizes=await p.evaluate(()=>({doc:document.documentElement.scrollWidth,width:innerWidth}));assert.ok(sizes.doc<=sizes.width+1,JSON.stringify(sizes));}
async function nativeBack(p){assert.equal(await p.evaluate(()=>callbacks.size),1);await p.evaluate(()=>[...callbacks][0]());}
async function compareRaster(p,a,b){
 if(a.equals(b))return {changedPixels:0,maxChannelDifference:0};
 return p.evaluate(async([left,right])=>{
  const load=src=>new Promise((resolve,reject)=>{const i=new Image();i.onload=()=>resolve(i);i.onerror=reject;i.src='data:image/png;base64,'+src;});
  const [x,y]=await Promise.all([load(left),load(right)]);const c=document.createElement('canvas');c.width=x.width;c.height=x.height;const ctx=c.getContext('2d',{willReadFrequently:true});ctx.drawImage(x,0,0);const u=ctx.getImageData(0,0,c.width,c.height).data;ctx.clearRect(0,0,c.width,c.height);ctx.drawImage(y,0,0);const v=ctx.getImageData(0,0,c.width,c.height).data;
  let changedPixels=0,maxChannelDifference=0;for(let i=0;i<u.length;i+=4){let changed=false;for(let j=0;j<4;j++){const d=Math.abs(u[i+j]-v[i+j]);maxChannelDifference=Math.max(d,maxChannelDifference);changed ||= d!==0;}if(changed)changedPixels++;}return {changedPixels,maxChannelDifference};
 },[a.toString('base64'),b.toString('base64')]);
}
async function screenshot(p,name){await p.screenshot({path:`${shots}/${name}.png`});}
try{
 for(const width of [375,390,430]){
  // Browser demo without Telegram launch stays local, with unchanged Home (at most 2/255 rounding on <0.1% pixels).
  const base=await setup(width,'fullscreen',{url:baseline,missing:true}),local=await setup(width,'fullscreen',{url:legacy,missing:true});
  for(const a of [base,local]){await a.p.locator('.hero').waitFor();await a.p.waitForTimeout(150);}
  const a=await base.p.screenshot(),b=await local.p.screenshot();if(!a.equals(b)){writeFileSync('/tmp/medexa6b-baseline-home.png',a);writeFileSync('/tmp/medexa6b-current-home.png',b);}const raster=await compareRaster(local.p,a,b);assert.ok(raster.maxChannelDifference<=2&&raster.changedPixels<width*812*.001,`flag-off Home differs at ${width}: ${JSON.stringify(raster)}`);assert.equal(await base.p.locator('link[rel=stylesheet]').getAttribute('href'),await local.p.locator('link[rel=stylesheet]').getAttribute('href'),'Production CSS content hashes must match');writeFileSync(`${shots}/home-local-${width}.png`,b);assert.equal(local.state.private.length,0);
  await base.p.close();await local.p.close();
  const {p,state,errors}=await setup(width,'fullscreen');
  await p.locator('.hero').waitFor();assert.equal(state.posts,1);assert.match(await p.locator('.greeting h1').innerText(),/СЕРВЕР/);await fit(p);await screenshot(p,`home-server-${width}`);
  assert.deepEqual(await p.locator('.stats dd').allTextContents(),['3','83%','2 мин']);
  // Reopen: cookie restore, no login replay.
  await p.evaluate(()=>window.dispatchEvent(new Event('pageshow')));await p.locator('.hero').waitFor();assert.equal(state.posts,1);
  await p.getByRole('button',{name:'Подробнее',exact:true}).click();await p.getByRole('heading',{name:'Моя статистика'}).waitFor();await p.locator('.statistics-history li').waitFor();await fit(p);if(width===390)await screenshot(p,'statistics-server-390');await nativeBack(p);await p.locator('.hero').waitFor();
  await p.locator('.daily-questions').click();await p.getByRole('heading',{name:'Ответы и разбор'}).waitFor();await p.locator('.question-review__card').waitFor();await fit(p);assert.equal(await p.locator('.question-review__answer--correct').count(),1);assert.match(await p.locator('.question-review__card h2').innerText(),/^17\./);if(width===390)await screenshot(p,'review-server-390');
  const input=p.getByPlaceholder('Найти вопрос');await input.fill('нетсовпадений');await p.getByText('В этой теме пока нет вопросов.').waitFor();await input.fill('сердце');await p.locator('.question-review__card').waitFor();await nativeBack(p);await p.locator('.hero').waitFor();
  await p.locator('.subject').first().click();await p.getByText('Материалы ещё не добавлены',{exact:true}).waitFor();await nativeBack(p);await p.locator('.hero').waitFor();
  await p.getByRole('button',{name:'Тесты',exact:true}).click();await p.locator('.test-card').first().click();await p.locator('.test-card').first().click();await p.locator('.topic-modes').waitFor();assert.equal(await p.locator('.topic-metrics dd').first().innerText(),'2');await fit(p);if(width===390)await screenshot(p,'topic-server-390');assert.equal(await p.locator('.topic-modes button').first().isEnabled(),true);assert.equal(state.mutations.length,0);await nativeBack(p);
  await p.getByRole('button',{name:'Профиль',exact:true}).click();await p.locator('.rp-user h1').waitFor();assert.match(await p.locator('.rp-user h1').innerText(),/СЕРВЕР Один/);await fit(p);if(width===390)await screenshot(p,'profile-server-390');
  // Change Telegram user: old account UI is removed, independently verified session and resources.
  await p.evaluate(()=>{const api=window.Telegram.WebApp;api.initData=new URLSearchParams({user:JSON.stringify({id:2,first_name:'UNVERIFIED TWO'})}).toString();api.initDataUnsafe.user.id=2;window.dispatchEvent(new Event('focus'));});
  await p.locator('.hero').waitFor();assert.equal(await p.locator('.stats dd').first().innerText(),'9');await p.getByRole('button',{name:'Профиль',exact:true}).click();await p.waitForFunction(()=>document.querySelector('.rp-user h1')?.textContent.includes('СЕРВЕР Два'));
  assert.equal(await p.getByText(/СЕРВЕР Один/).count(),0);assert.equal(state.posts,2);
  assert.equal(errors.length,0,errors.join('\n'));results.push({width,homeUnchanged:true,serverFlows:true});await p.close();
 }
 const empty=await setup(390,'expanded',{empty:true});await empty.p.locator('.hero').waitFor();assert.deepEqual(await empty.p.locator('.stats dd').allTextContents(),['0','—','—']);await screenshot(empty.p,'empty-server-390');await empty.p.getByRole('button',{name:'Тесты',exact:true}).click();await empty.p.getByText('Опубликованных материалов пока нет',{exact:true}).waitFor();await empty.p.close();
 const missing=await setup(390,'expanded',{missing:true});await missing.p.getByText('Откройте Mini App из Telegram для входа.').waitFor();assert.equal(missing.state.private.length,0);await missing.p.close();
 const offline=await setup(375,'short',{offline:true});await offline.p.getByRole('button',{name:'Повторить'}).click();offline.state.offline=false;await offline.p.getByRole('button',{name:'Повторить'}).click();await offline.p.locator('.hero').waitFor();await fit(offline.p);await screenshot(offline.p,'short-server-375');
 offline.state.homeFailure=true;await offline.p.evaluate(()=>window.dispatchEvent(new Event('pageshow')));await offline.p.getByRole('alert').waitFor();assert.equal(await offline.p.locator('.hero').count(),0);offline.state.homeFailure=false;await offline.p.getByRole('button',{name:'Повторить'}).click();await offline.p.locator('.hero').waitFor();
 // Expired cookie: request fails, auth restores, no local statistics fallback.
 offline.state.cookie=null;await offline.p.getByRole('button',{name:'Подробнее',exact:true}).click();await offline.p.locator('.statistics-history li').waitFor();assert.ok(offline.state.posts>=2);await offline.p.close();
 const notes=await setup(390,'expanded');notes.state.notes=true;notes.state.historyMore=true;await notes.p.locator('.hero').waitFor();await notes.p.locator('.subject').first().click();await notes.p.getByRole('button',{name:/СЕРВЕРНЫЙ конспект/}).click();await notes.p.getByText(/^СЕРВЕРНЫЙ текст/).waitFor();await fit(notes.p);await notes.p.goBack();await notes.p.getByRole('button',{name:/СЕРВЕРНЫЙ конспект/}).waitFor();await nativeBack(notes.p);await notes.p.locator('.hero').waitFor();await notes.p.getByRole('button',{name:'Подробнее',exact:true}).click();await notes.p.getByRole('button',{name:'Показать ещё',exact:true}).click();await notes.p.locator('.statistics-history li').nth(1).waitFor();assert.equal(await notes.p.locator('.statistics-history li').count(),2);await nativeBack(notes.p);await notes.p.locator('.hero').waitFor();notes.state.locked=true;await notes.p.locator('.daily-questions').click();await notes.p.getByText('Ответы доступны после завершения активного экзамена.').waitFor();assert.equal(await notes.p.locator('.question-review__card').count(),0);notes.state.locked=false;await notes.p.getByRole('button',{name:'Повторить',exact:true}).click();await notes.p.locator('.question-review__card').waitFor();await notes.p.close();
 console.log(JSON.stringify({results,empty:true,missingInitData:true,offlineRecovery:true,sessionExpiry:true,productionRequests:0}));
}finally{await browser.close();}
