/** Synthetic transport scenarios; NOT a Telegram iOS or live-backend test. */
import assert from 'node:assert/strict';
import {mkdirSync,writeFileSync} from 'node:fs';
import {chromium} from 'playwright';
import {fixture,id,envelope,clone,complete} from './attempt-fixtures.mjs';
const base=process.env.MEDEXA_UI_URL??'http://127.0.0.1:5181';assert.ok(['localhost','127.0.0.1'].includes(new URL(base).hostname));
const shots='docs/screenshots/frontend-6b';mkdirSync(shots,{recursive:true});
const browser=await chromium.launch({executablePath:process.env.CHROMIUM_PATH??'/usr/bin/chromium',args:['--no-sandbox']});
const logs=[];
async function setup(width,telegram=true,height=812){
 const p=await browser.newPage({viewport:{width,height},reducedMotion:'reduce'});p.setDefaultTimeout(10000);const errors=[];p.on('pageerror',e=>errors.push(e.message));
 if(!telegram)await p.addInitScript(()=>sessionStorage.setItem('anatomai:server-mode','1'));
 const state={a:null,owner:1,offline:false,loss:false,conflict:false,posts:0,commands:[],receipts:new Map(),history:0,expire:false,authLoss:false,startFailure:false,reviewCalls:0};
 await p.route('https://telegram.org/**',r=>r.fulfill({contentType:'application/javascript',body:telegram?`window.callbacks=new Set();window.Telegram={WebApp:{initData:new URLSearchParams({user:JSON.stringify({id:1})}).toString(),initDataUnsafe:{user:{id:1}},platform:'ios',version:'8.0',isFullscreen:true,viewportHeight:${height},viewportStableHeight:${height},safeAreaInset:{top:59,bottom:34},contentSafeAreaInset:{top:45,bottom:0},ready(){},expand(){},onEvent(){},offEvent(){},BackButton:{show(){},hide(){},onClick(cb){callbacks.add(cb)},offClick(cb){callbacks.delete(cb)}}}};`:''}));
 const send=(r,v,status=200)=>r.fulfill({status,contentType:'application/json',body:JSON.stringify(v)});
 await p.route('**/api/v1/**',async r=>{
  const req=r.request(),u=new URL(req.url()),path=u.pathname.slice(7);assert.equal(u.origin,new URL(base).origin);
  if(state.offline)return r.abort();
  const ok=v=>send(r,envelope(clone(v)));const fail=(s,code)=>send(r,{error:{code}},s);
  const summary={completed_tests:state.history,answered_count:state.history,correct_count:state.history,wrong_count:0,skipped_count:state.history,average_percent:state.history?50:null,practice_seconds:state.history?60:null,activity_streak_days:0,period:'all',timezone:'UTC',data_scope:'server_history',calculated_at:new Date().toISOString()};
  const d={id:id(2),slug:'anatomy',title:'Анатомия',icon_key:'anatomy',color_token:'blue',question_count:2,topic_count:1,note_count:0};
  const t={id:id(3),discipline_id:id(2),category_id:null,slug:'heart',title:'Сердце — длинное название темы',question_count:2,test_definition_id:null,available_modes:['learning','exam']};
  const page=data=>send(r,{...envelope(data),page:{has_more:false,next_cursor:null,total:data.length},catalog_version:1});
  if(path==='/auth/session'||path==='/auth/telegram'){
   if(path==='/auth/telegram'){state.owner=JSON.parse(new URLSearchParams(req.postDataJSON().init_data).get('user')).id;state.a=null;}
   return ok({id:id(20),user:{id:id(state.owner+30),telegram_user_id:String(state.owner),first_name:'SYNTHETIC '+state.owner,last_name:null,username:null,photo_url:null,timezone:'UTC',language:'ru',version:1,roles:['student']},csrf_token:'csrf-'+state.owner,expires_at:'2027-01-01T00:00:00Z',idle_expires_at:'2027-01-01T00:00:00Z'});
  }
  if(path==='/me/home')return ok({statistics:summary,active_attempt:state.a?.status==='in_progress'?state.a:null,recent_results:[]});
  if(path==='/me/statistics')return ok(summary);
  if(path==='/me/recommendations'||path==='/me/achievements')return ok([]);
  if(path==='/me/daily-topic')return ok({local_date:'2026-11-22',timezone:'UTC',topic_id:id(3),title:t.title,discipline_id:id(2),question_count:2,availability:'available',catalog_version:1,selector_version:1});
  if(path==='/disciplines')return page([d]);if(path==='/disciplines/'+id(2))return ok(d);
  if(path==='/topics')return page([t]);if(path==='/topics/'+id(3))return ok(t);
  if(path==='/me/topics/'+id(3)+'/summary')return ok({topic_id:id(3),completed_count:state.history,best_percent:null,ever_wrong_question_count:null,unresolved_wrong_question_count:null,favorites_count:null,favorites_status:'not_configured'});
  if(path==='/test-definitions')return page([]);
  if(path==='/me/active-attempt')return ok(state.a);
  if(path.endsWith('/review')||path.endsWith('/result-review')){
   state.reviewCalls++;if(state.a?.status!=='completed')return fail(409,'RESULT_NOT_AVAILABLE');
   const i=fixture().current_item;delete i.state;i.correct_option_ids=[id(7)];i.is_correct=true;i.selected_option_ids=[id(7)];i.explanation='SYNTHETIC REVIEW';
   return ok(path.endsWith('/result-review')?{items:[i],next_cursor:null,has_more:false}:{items:[i],total:1,next_offset:null});
  }
  if(req.method()==='GET'&&path==='/attempts/'+id(1)){
   if(state.expire&&state.a?.mode==='exam'&&state.a.status==='in_progress'){complete(state.a,'timeout');state.history++;}
   return ok(state.a);
  }
  if(req.method()!=='GET'&&path.startsWith('/attempts')){
   if(state.authLoss){state.authLoss=false;return fail(401,'AUTH_REQUIRED');}
   state.posts++;const h=req.headers(),body=req.postDataJSON();assert.equal(h['x-csrf-token'],'csrf-'+state.owner);assert.match(h['idempotency-key'],/^[\da-f-]{36}$/i);state.commands.push({path,body,headers:h});
   const key=h['idempotency-key'];const replay=state.receipts.get(key);if(replay){assert.equal(replay.match,h['if-match']);assert.deepEqual(replay.body,body);return ok(replay.value);}
   if(path==='/attempts'&&state.startFailure)return fail(503,'SERVICE_NOT_READY');
   if(state.conflict){state.conflict=false;state.a.version++;return fail(409,'ATTEMPT_VERSION_CONFLICT');}
   if(path==='/attempts'){state.a=fixture(body.mode);state.a.current_item.text+=' '+('Длинный медицинский вопрос. ').repeat(25);}
   else {
    assert.equal(h['if-match'],`"attempt-${state.a.id}-${state.a.version}"`);
    const a=state.a,i=a.current_item;
    if(path.endsWith('/submit')){i.state='checked';i.selected_option_ids=body.selected_option_ids;i.feedback={is_correct:body.selected_option_ids[0]===id(7),correct_option_ids:[id(7)],explanation:'SYNTHETIC LEARNING EXPLANATION'};}
    else if(path.endsWith('/draft'))i.selected_option_ids=body.selected_option_ids;
    else if(path.endsWith('/navigate')){a.current_position=body.position;i.position=body.position;i.id=id(4+body.position);i.selected_option_ids=body.position===0?[id(8)]:[];}
    else if(path.endsWith('/finish')||(path.endsWith('/skip')&&a.current_position===1)){complete(a);state.history++;}
    else if(path.endsWith('/advance')||path.endsWith('/skip')){a.current_position++;a.current_item=clone(fixture(a.mode).current_item);a.current_item.position=a.current_position;a.current_item.id=id(4+a.current_position);}
    a.version++;
   }
   state.receipts.set(key,{body,match:h['if-match'],value:clone(state.a)});
   if(state.loss){state.loss=false;return r.abort();}return ok(state.a);
  }
  throw Error('Unexpected mock route '+path);
 });
 await p.goto(base);await p.locator('.hero').waitFor();return {p,state,errors};
}
async function start(p,mode,question=true){await p.getByRole('button',{name:'Тесты',exact:true}).click();await p.locator('.test-card').click();await p.locator('.test-card').click();await p.locator('.topic-modes').getByRole('button',{name:mode,exact:true}).click();if(question)await p.locator('.test-question').waitFor();}
async function fit(p){assert.equal(await p.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),true);const footer=p.locator('.test-session__footer');if(await footer.count()){const b=await footer.boundingBox();assert.ok(b.y>=0&&b.y+b.height<=p.viewportSize().height-25,JSON.stringify(b));}}
async function nativeBack(p){assert.equal(await p.evaluate(()=>callbacks.size),1);await p.evaluate(()=>[...callbacks][0]());}
try{
 for(const width of [375,390,430]){
  const {p,state,errors}=await setup(width,true,width===375?568:812);
  await start(p,'Обучение');await fit(p);assert.equal(await p.locator('.test-choice.correct').count(),0);state.loss=true;await p.locator('.test-choice').first().click();await p.getByRole('button',{name:'Повторить запрос'}).waitFor();assert.equal(state.posts,2);await p.evaluate(()=>document.dispatchEvent(new Event('visibilitychange')));await p.getByRole('button',{name:'Повторить запрос'}).waitFor();assert.equal(await p.locator('.test-session__action').isDisabled(),true);await p.getByRole('button',{name:'Повторить запрос'}).click();await p.getByText('SYNTHETIC LEARNING EXPLANATION',{exact:true}).waitFor();await p.waitForFunction(()=>!document.querySelector('.test-session__action').disabled);assert.equal(state.posts,3);await p.locator('.test-session__content').evaluate(e=>e.scrollTop=e.scrollHeight);await p.screenshot({path:`${shots}/learning-${width}.png`});await fit(p);
  await nativeBack(p);await p.locator('.test-card').waitFor();await p.getByRole('button',{name:'Главная',exact:true}).click();await p.locator('.hero .start').click();await p.getByText('SYNTHETIC LEARNING EXPLANATION',{exact:true}).waitFor();assert.equal(state.posts,3);
  await p.reload();await p.locator('.hero .start').waitFor();await p.locator('.hero .start').click();await p.getByText('SYNTHETIC LEARNING EXPLANATION',{exact:true}).waitFor();assert.equal(state.posts,3);
  await p.getByRole('button',{name:'Далее',exact:true}).click();await p.getByText('Вопрос 2 из 2',{exact:true}).waitFor();await p.waitForFunction(()=>!document.querySelector('.test-session__skip').disabled);await p.getByRole('button',{name:'Пропустить',exact:true}).click();await p.locator('.test-result').waitFor();assert.equal(await p.locator('.test-result__badge strong').innerText(),'50%');await p.getByRole('button',{name:'Разобрать ошибки',exact:true}).click();await p.locator('.test-review__item').waitFor();await p.screenshot({path:`${shots}/result-${width}.png`});await fit(p);await p.getByRole('button',{name:'К тестам',exact:true}).click();await p.getByRole('button',{name:'Главная',exact:true}).click();await p.waitForFunction(()=>document.querySelector('.stats dd')?.textContent==='1');
  const completedReviews=state.reviewCalls;await start(p,'Экзамен');await p.locator('.test-choice').first().click();await p.waitForFunction(()=>!document.querySelector('.test-session__action').disabled);assert.equal(state.a.current_item.selected_option_ids[0],id(7));assert.equal(await p.locator('.test-choice.correct').count(),0);assert.equal(await p.getByText('SYNTHETIC LEARNING EXPLANATION',{exact:true}).count(),0);assert.equal(state.reviewCalls,completedReviews);
  await p.locator('.test-choice').nth(1).click();await p.waitForFunction(()=>!document.querySelector('.test-session__action').disabled);assert.equal(state.a.current_item.selected_option_ids[0],id(8));state.conflict=true;await p.getByRole('button',{name:'Далее',exact:true}).click();await p.getByRole('alert').waitFor();assert.equal(state.a.current_position,0);await p.getByRole('button',{name:'Обновить',exact:true}).click();await p.waitForFunction(()=>!document.querySelector('.test-session__action').disabled);await p.getByRole('button',{name:'Далее',exact:true}).click();await p.getByText('Вопрос 2 из 2',{exact:true}).waitFor();await p.getByRole('button',{name:'Предыдущий вопрос'}).click();await p.getByText('Вопрос 1 из 2',{exact:true}).waitFor();assert.equal(await p.locator('.test-choice.selected').count(),1);await p.screenshot({path:`${shots}/exam-${width}.png`});await fit(p);
  state.expire=true;await p.evaluate(()=>document.dispatchEvent(new Event('visibilitychange')));await p.locator('.test-result').waitFor();assert.equal(state.a.result.finish_reason,'timeout');await p.getByRole('button',{name:'Разобрать ошибки',exact:true}).click();await p.getByText('SYNTHETIC REVIEW',{exact:true}).waitFor();await nativeBack(p);await p.locator('.test-card').waitFor();assert.deepEqual(errors,[]);logs.push({width,learning:true,exam:true,resume:true,timeout:true,conflict:true,requestReplay:true});await p.close();
 }
 const {p,state,errors}=await setup(390,false);await start(p,'Обучение');assert.equal(await p.getByRole('button',{name:'Назад к тестам',exact:true}).count(),1);state.offline=true;await p.locator('.test-choice').first().click();await p.getByRole('button',{name:'Повторить запрос'}).waitFor();assert.equal(await p.locator('.test-choice.correct').count(),0);state.offline=false;await p.getByRole('button',{name:'Повторить запрос'}).click();await p.getByText('SYNTHETIC LEARNING EXPLANATION',{exact:true}).waitFor();await p.getByRole('button',{name:'Назад к тестам',exact:true}).click();await p.locator('.test-card').waitFor();assert.deepEqual(errors,[]);await p.close();
 const rejected=await setup(390);rejected.state.startFailure=true;await start(rejected.p,'Обучение',false);await rejected.p.getByRole('button',{name:'Повторить запрос'}).waitFor();assert.equal(await rejected.p.locator('.test-question,.page-view').count(),0);assert.equal(rejected.state.a,null);assert.equal(rejected.state.posts,1);rejected.state.startFailure=false;await rejected.p.getByRole('button',{name:'Повторить запрос'}).click();await rejected.p.locator('.test-question').waitFor();assert.equal(rejected.state.posts,2);assert.equal(rejected.state.commands[0].headers['idempotency-key'],rejected.state.commands[1].headers['idempotency-key']);assert.deepEqual(rejected.errors,[]);await rejected.p.close();
 const expired=await setup(390);await start(expired.p,'Обучение');expired.state.authLoss=true;await expired.p.locator('.test-choice').first().click();await expired.p.getByRole('button',{name:'Повторить запрос'}).waitFor();await expired.p.waitForFunction(()=>!document.querySelector('[role=alert] button')?.disabled);assert.equal(expired.state.posts,1);await expired.p.getByRole('button',{name:'Повторить запрос'}).click();await expired.p.getByText('SYNTHETIC LEARNING EXPLANATION',{exact:true}).waitFor();assert.equal(expired.state.posts,2);assert.deepEqual(expired.errors,[]);await expired.p.close();
 const account=await setup(390);await start(account.p,'Экзамен');await account.p.locator('.test-choice').first().click();await account.p.waitForFunction(()=>!document.querySelector('.test-session__action').disabled);await account.p.evaluate(()=>{const a=window.Telegram.WebApp;a.initData=new URLSearchParams({user:JSON.stringify({id:2})}).toString();a.initDataUnsafe.user.id=2;window.dispatchEvent(new Event('focus'));});await account.p.locator('.hero').waitFor();assert.equal(await account.p.locator('.test-question').count(),0);assert.equal(account.state.owner,2);await account.p.close();
 writeFileSync(`${shots}/mock-results.json`,JSON.stringify({scenarios:logs,browserFallback:true,offline:true,accountIsolation:true,identity401DuringMutation:true,start503NoLocalFallback:true,backend:'mock',realTelegramIOS:false},null,2));console.log(JSON.stringify(logs));
}finally{await browser.close();}
