import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import ts from 'typescript';
import {chromium} from 'playwright';
const browser=await chromium.launch({executablePath:process.env.CHROMIUM_EXECUTABLE_PATH||undefined,args:['--no-sandbox']});
const url=process.env.AFTER_URL??'http://127.0.0.1:4173/';
const js=ts.transpileModule(readFileSync(new URL('../src/features/tests/data.ts',import.meta.url),'utf8'),{compilerOptions:{target:ts.ScriptTarget.ES2022,module:ts.ModuleKind.ESNext}}).outputText;
const {questionsForTest}=await import(`data:text/javascript;base64,${Buffer.from(js).toString('base64')}`);
function sdk(mode,fullscreen){return `
 window.backCallbacks=new Set();window.sdkEvents=new Map();window.transitions=0;
 const push=history.pushState.bind(history);history.pushState=(...args)=>{transitions++;return push(...args)};
 window.backFail=${mode==='show-fails'};window.knownVisibility=${mode!=='unknown-visible'};
 const back={isVisible:false,showCount:0,show(){if(backFail)throw Error('show rejected');this.showCount++;if(knownVisibility)this.isVisible=true},hide(){if(knownVisibility)this.isVisible=false},onClick(cb){backCallbacks.add(cb)},offClick(cb){backCallbacks.delete(cb)}};
 window.pendingApi={initData:'test',platform:'ios',version:'8.0',isFullscreen:${fullscreen},viewportHeight:744,viewportStableHeight:744,safeAreaInset:{top:${fullscreen?59:0},bottom:34,left:0,right:0},contentSafeAreaInset:{top:${fullscreen?45:0},bottom:0,left:0,right:0},ready(){},expand(){},onEvent(e,c){if(!sdkEvents.has(e))sdkEvents.set(e,new Set());sdkEvents.get(e).add(c)},offEvent(e,c){sdkEvents.get(e)?.delete(c)},BackButton:back};
 if(!knownVisibility)delete back.isVisible;
 if(${mode==='late-back'})delete back.offClick;
 if(${!['browser','late-sdk'].includes(mode)})window.Telegram={WebApp:pendingApi};
 if(${mode==='browser-sdk'}){pendingApi.initData='';pendingApi.platform='unknown';}
 `;}
async function openQuestion(mode,fullscreen,target=url){
 const p=await browser.newPage({viewport:{width:390,height:744},reducedMotion:'reduce'});
 await p.route('https://telegram.org/**',r=>r.fulfill({contentType:'application/javascript',body:sdk(mode,fullscreen)}));
 await p.goto(target);await p.locator('.nav-item').nth(1).click();for(let nav=0;nav<3 && await p.locator('.test-mode-picker').count()===0;nav++) await p.locator('.test-card').first().click();await p.locator('.test-mode-card').first().click();return p;
}
try{
 for(const fullscreen of [false,true])for(const mode of ['native','late-back','late-sdk','show-fails','unknown-visible','browser','browser-sdk']){
  const p=await openQuestion(mode,fullscreen);
  const initiallyNative=!['browser','browser-sdk','late-sdk'].includes(mode);
  await p.waitForFunction(expected=>document.querySelectorAll('.test-session__close').length===expected,initiallyNative?0:1);
  if(mode==='show-fails'){
   assert.equal(await p.evaluate(()=>backCallbacks.size),0);
   await p.evaluate(()=>dispatchEvent(new PopStateEvent('popstate')));
   await p.locator('.tests-page').waitFor();
   for(let nav=0;nav<3 && await p.locator('.test-mode-picker').count()===0;nav++) await p.locator('.test-card').first().click();await p.locator('.test-mode-card').first().click();
   assert.equal(await p.locator('.test-session__close').count(),0);
  }
  if(['late-back','late-sdk','show-fails'].includes(mode)){
   await p.evaluate(mode=>{if(mode==='late-sdk')window.Telegram={WebApp:pendingApi};if(mode==='late-back'){pendingApi.BackButton.offClick=cb=>backCallbacks.delete(cb);pendingApi.BackButton.isVisible=true;}if(mode==='show-fails')backFail=false;},mode);
   await p.waitForFunction(()=>document.querySelectorAll('.test-session__close').length===0&&backCallbacks.size===1);
  }
  const native=!['browser','browser-sdk'].includes(mode);
  assert.equal(await p.evaluate(()=>backCallbacks.size),['browser','browser-sdk'].includes(mode)?0:1);
  if(native&&mode!=='unknown-visible')assert.ok(await p.evaluate(()=>pendingApi.BackButton.isVisible===true&&pendingApi.BackButton.showCount>0));
  await p.locator('.test-choice').first().click();let dialogs=0;
  p.on('dialog',dialog=>{dialogs++;return dialog.dismiss()});
  if(native)await p.evaluate(()=>{for(const cb of [...backCallbacks]){cb();cb();}dispatchEvent(new PopStateEvent('popstate'));});
  else await p.locator('.test-session__close').click();
  assert.equal(dialogs,1);assert.equal(await p.locator('.test-session').count(),1);
  p.removeAllListeners('dialog');p.on('dialog',dialog=>dialog.accept());
  const before=await p.evaluate(()=>transitions);
  if(native)await p.evaluate(()=>{for(const cb of [...backCallbacks])cb();});else await p.locator('.test-session__close').click();
  await p.locator('.tests-page').waitFor();assert.equal(await p.evaluate(()=>transitions),before+1);assert.equal(await p.evaluate(()=>backCallbacks.size),['browser','browser-sdk'].includes(mode)?0:1);
  for(let nav=0;nav<3 && await p.locator('.test-mode-picker').count()===0;nav++) await p.locator('.test-card').first().click();await p.locator('.test-mode-card').first().click();
  assert.equal(await p.evaluate(()=>backCallbacks.size),['browser','browser-sdk'].includes(mode)?0:1);
  // Finish via skips, then leave result with exactly one transition.
  for(let i=0;i<questionsForTest('anatomy').length;i++)await p.locator('.test-session__skip').click();
  await p.locator('.test-result').waitFor();const resultBefore=await p.evaluate(()=>transitions);
  if(native)await p.evaluate(()=>{for(const cb of [...backCallbacks]){cb();cb();}});else await p.getByRole('button',{name:'К тестам',exact:true}).click();
  await p.locator('.tests-page').waitFor();assert.equal(await p.evaluate(()=>transitions),resultBefore+1);assert.equal(await p.evaluate(()=>backCallbacks.size),['browser','browser-sdk'].includes(mode)?0:1);
  console.log(`PASS Back lifecycle ${mode}/${fullscreen?'fullscreen':'expanded'}: fallback/reactivity, cancel, one exit, re-entry, result cleanup`);await p.close();
 }
 for(const score of [0,1,2,4,5]){
  const p=await openQuestion('browser',false);const questions=questionsForTest('anatomy');
  for(let i=0;i<questions.length;i++){
   if(score===0||score===4&&i===4){await p.locator('.test-session__skip').click();continue;}
   const choice=i<score?questions[i].correctAnswer:(questions[i].correctAnswer+1)%questions[i].answers.length;
   await p.locator('.test-choice').nth(choice).click();await p.locator('.test-session__action').click();
  }
  await p.locator('.test-result').waitFor();assert.equal(await p.locator('.test-result__badge strong').innerText(),`${score*20}%`);
  const stats=await p.locator('.test-result__stats strong').allTextContents();
  assert.deepEqual(stats,[String(score),String(score===0||score===4||score===5?0:5-score),String(score===0?5:score===4?1:0)]);
  assert.equal(await p.getByRole('button',{name:'Разобрать ошибки',exact:true}).count(),score===5?0:1);
  await p.locator('.test-result__test').evaluate(el=>el.textContent='Длинное название медицинской дисциплины. '.repeat(15));
  await p.getByRole('button',{name:'К тестам',exact:true}).scrollIntoViewIfNeeded();
  assert.ok(await p.getByRole('button',{name:'К тестам',exact:true}).evaluate(el=>el.getBoundingClientRect().bottom<=innerHeight));
  assert.ok(await p.locator('.test-result').evaluate(el=>el.scrollWidth<=el.clientWidth));
  console.log(`PASS result ${score*20}%: stats, skips, review/no review, long title, accessible actions`);await p.close();
 }
}finally{await browser.close();}
