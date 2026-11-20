import assert from 'node:assert/strict';
import {mkdirSync,readFileSync} from 'node:fs';
import ts from 'typescript';
import {chromium} from 'playwright';
const url=process.env.AFTER_URL||'http://127.0.0.1:4996';
const dir='docs/screenshots/ui-8.3';mkdirSync(dir,{recursive:true});
const js=ts.transpileModule(readFileSync(new URL('../src/features/tests/data.ts',import.meta.url),'utf8'),{compilerOptions:{target:ts.ScriptTarget.ES2022,module:ts.ModuleKind.ESNext}}).outputText;
const {questionsForTest}=await import(`data:text/javascript;base64,${Buffer.from(js).toString('base64')}`);
const questions=questionsForTest('anatomy');
const browser=await chromium.launch({executablePath:'/usr/bin/chromium',args:['--no-sandbox']});
async function open(width,mode){
 const p=await browser.newPage({viewport:{width,height:812},timezoneId:'Asia/Bishkek',reducedMotion:'reduce'});
 await p.clock.setFixedTime(new Date('2026-11-20T06:00:00Z'));
 await p.route('https://telegram.org/**',r=>r.fulfill({body:mode==='browser'?'':`window.callbacks=new Set();window.Telegram={WebApp:{initData:'test',platform:'ios',version:'8.0',isFullscreen:${mode==='fullscreen'},viewportHeight:812,viewportStableHeight:812,safeAreaInset:{top:${mode==='fullscreen'?59:0},bottom:34},contentSafeAreaInset:{top:${mode==='fullscreen'?45:0},bottom:0},ready(){},expand(){},onEvent(){},offEvent(){},BackButton:{show(){},hide(){},onClick(cb){callbacks.add(cb)},offClick(cb){callbacks.delete(cb)}}}};`}));
 const errors=[];p.on('pageerror',e=>errors.push(e.message));await p.goto(url);return {p,errors};
}
async function shot(p,width,mode,name){if(mode==='fullscreen')await p.screenshot({path:`${dir}/${name}-${width}.png`});}
async function back(p,mode,selector){if(mode==='browser')await p.locator(selector).click();else{assert.equal(await p.evaluate(()=>callbacks.size),1);await p.evaluate(()=>[...callbacks][0]());}}
async function noExplanations(p){assert.equal(await p.locator('.test-explanation,.question-review__explanation').count(),0);for(const q of questions)if(q.explanation)assert.equal(await p.getByText(q.explanation,{exact:true}).count(),0);}
try{
 for(const width of [375,390,430])for(const mode of ['browser','expanded','fullscreen']){
  const {p,errors}=await open(width,mode);const home=p.locator('.page-view').first();
  assert.equal(await home.getByRole('heading',{name:'Вопросы дня',exact:true}).count(),0);
  assert.equal(await home.getByRole('button',{name:/^Вопросы дня:/}).count(),1);
  const daily=p.locator('.daily-questions');const recommendation=await daily.innerText();
  const bounds=await daily.boundingBox();assert.ok(bounds.height>=75&&bounds.height<=90);
  assert.ok(await daily.evaluate(e=>e.scrollWidth<=e.clientWidth&&e.scrollHeight<=e.clientHeight));
  await p.reload();assert.equal(await daily.innerText(),recommendation);
  await shot(p,width,mode,'home-top');
  await p.locator('.shell__content').evaluate(e=>{e.scrollTop=e.scrollHeight;});
  const tip=await p.locator('.tip').boundingBox(),nav=await p.locator('.bottom-nav').boundingBox();assert.ok(tip.y+tip.height<=nav.y-8);await shot(p,width,mode,'home-bottom');
  await daily.click();await p.locator('.question-review').waitFor();
  assert.ok(await p.locator('.question-review__answer--correct').count()>0);assert.equal(await p.locator('.question-review details').count(),0);await noExplanations(p);
  await shot(p,width,mode,'daily-answers');
  await back(p,mode,'.question-review__back');await p.locator('.topbar').waitFor({state:'visible'});
  assert.equal(await daily.innerText(),recommendation);
  await p.locator('.nav-item').nth(1).click();await p.locator('.test-card').first().click();
  await p.getByRole('button',{name:'Обучение',exact:true}).click();
  for(let i=0;i<questions.length;i++){
   if(i===2){await p.locator('.test-session__skip').click();continue;}
   const answer=i===1?(questions[i].correctAnswer+1)%questions[i].answers.length:questions[i].correctAnswer;
   await p.locator('.test-choice').nth(answer).click();
   assert.equal(await p.locator('.test-choice.correct').count(),1);
   assert.equal(await p.locator('.test-choice.wrong').count(),i===1?1:0);
   assert.equal(await p.locator('.test-choice:disabled').count(),questions[i].answers.length);
   assert.ok(await p.locator('.test-answer-status').innerText());await noExplanations(p);
   const footer=await p.locator('.test-session__footer').boundingBox();assert.ok(footer.y+footer.height<=812-(mode==='browser'?8:34));
   if(i===1)await shot(p,width,mode,'learning-answer');
   await p.locator('.test-session__action').click();
  }
  await p.locator('.test-result').waitFor();assert.deepEqual(await p.locator('.test-result__stats strong').allTextContents(),['3','1','1']);assert.equal(await p.locator('.test-result__badge strong').innerText(),'60%');
  await p.getByRole('button',{name:'Разобрать ошибки',exact:true}).click();assert.equal(await p.locator('.test-review__item').count(),2);await noExplanations(p);
  await shot(p,width,mode,'result-review');
  await p.getByRole('button',{name:'Повторить',exact:true}).click();await p.locator('.topic-page').waitFor({state:'visible'});
  await p.getByRole('button',{name:'Экзамен',exact:true}).click();
  for(let i=0;i<questions.length;i++){
   if(i===2){await p.locator('.test-session__skip').click();continue;}
   const answer=i===1?(questions[i].correctAnswer+1)%questions[i].answers.length:questions[i].correctAnswer;
   await p.locator('.test-choice').nth(answer).click();assert.equal(await p.locator('.test-choice.correct,.test-choice.wrong,.test-answer-status').count(),0);await noExplanations(p);
   if(i===1)await shot(p,width,mode,'exam-answer');
   await p.locator('.test-session__action').click();
  }
  await p.locator('.test-result').waitFor();assert.deepEqual(await p.locator('.test-result__stats strong').allTextContents(),['3','1','1']);
  await p.getByRole('button',{name:'К тестам',exact:true}).click();await p.locator('.tests-page').waitFor();
  await p.locator('.test-card').first().click();await p.getByRole('button',{name:/Ответы и разбор/}).click();await p.locator('.question-review').waitFor();
  assert.equal(await p.locator('.question-review__answer--correct').count(),5);assert.equal(await p.locator('.question-review details').count(),0);await noExplanations(p);
  await p.getByRole('searchbox').fill('рёбер');assert.equal(await p.locator('.question-review__card').count(),1);await p.getByRole('searchbox').fill('');await shot(p,width,mode,'topic-answers');
  await back(p,mode,'.question-review__back');await p.locator('.topic-page').waitFor({state:'visible'});await back(p,mode,'.study-back');await p.locator('.tests-page').waitFor();
  if(mode!=='browser')assert.equal(await p.evaluate(()=>callbacks.size),0);
  await p.locator('.nav-item').first().click();await p.locator('.shell__content').evaluate(e=>{e.scrollTop=e.scrollHeight;});assert.ok(await p.locator('.shell').evaluate(e=>e.scrollWidth<=e.clientWidth));assert.equal(await p.evaluate(()=>document.scrollingElement.scrollTop),0);
  assert.deepEqual(errors,[]);await p.close();
  console.log(`PASS ${width} ${mode}: compact daily/reload/return; learning feedback and 60% score; skip/errors/retake; exam secrecy; no explanation text; answer reference/search; safe-area`);
 }
 const {p}=await open(375,'browser');await p.setViewportSize({width:375,height:400});
 await p.locator('.daily-questions').scrollIntoViewIfNeeded();await p.locator('.daily-questions__topic').evaluate(e=>{e.textContent='Очень длинное название существующей темы '.repeat(10);});assert.ok(await p.locator('.daily-questions').evaluate(e=>e.scrollHeight<=e.clientHeight&&e.scrollWidth<=e.clientWidth));await p.locator('.daily-questions').click();await p.locator('.question-review').waitFor();assert.ok(await p.locator('.question-review__scroll').evaluate(e=>e.clientHeight>0));await p.close();
 console.log('PASS 375x400 and long daily title: compact bounds, accessible full reference, scrollable content');
}finally{await browser.close();}
