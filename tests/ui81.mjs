import assert from 'node:assert/strict';
import {mkdirSync} from 'node:fs';
import {chromium} from 'playwright';
const url=process.env.AFTER_URL||'http://127.0.0.1:4796';
const fixtureUrl=process.env.FIXTURE_URL||'http://127.0.0.1:4798/tests/fixtures/question-review.html';
const dir='docs/screenshots/ui-8.1';mkdirSync(dir,{recursive:true});
const browser=await chromium.launch({executablePath:process.env.CHROMIUM_EXECUTABLE_PATH||'/usr/bin/chromium',args:['--no-sandbox']});
async function open(width,mode){
 const page=await browser.newPage({viewport:{width,height:812},reducedMotion:'reduce'});
 await page.route('https://telegram.org/**',r=>r.fulfill({body:mode==='browser'?'':`window.callbacks=new Set();window.Telegram={WebApp:{initData:'test',platform:'ios',version:'8.0',isFullscreen:${mode==='fullscreen'},viewportHeight:812,viewportStableHeight:812,safeAreaInset:{top:${mode==='fullscreen'?59:0},bottom:34},contentSafeAreaInset:{top:${mode==='fullscreen'?45:0},bottom:0},ready(){},expand(){},onEvent(){},offEvent(){},BackButton:{show(){},hide(){},onClick(cb){callbacks.add(cb)},offClick(cb){callbacks.delete(cb)}}}};`}));
 const errors=[];page.on('pageerror',e=>errors.push(e.message));await page.goto(url);
 return {page,errors};
}
async function back(page,mode){if(mode==='browser')await page.locator('.question-review__back').click();else{assert.equal(await page.evaluate(()=>callbacks.size),1);await page.evaluate(()=>[...callbacks][0]());}await page.locator('.topic-page').waitFor({state:'visible'});}
try{
 for(const width of [375,390,430])for(const mode of ['browser','expanded','fullscreen']){
  const {page,errors}=await open(width,mode);
  await page.locator('.nav-item').nth(1).click();await page.locator('.test-card').first().click();
  await page.getByRole('button',{name:'Показать все (5)'}).click();
  await page.locator('.topic-page').evaluate(e=>{e.scrollTop=80;});
  await page.getByRole('button',{name:/Разбор вопросов/}).click();
  await page.locator('.question-review').waitFor();
  assert.equal(await page.locator('.question-review__back').count(),mode==='browser'?1:0);
  assert.equal(await page.locator('.question-review__card').count(),5);
  assert.equal(await page.locator('.question-review__answer').count(),20);
  assert.equal(await page.locator('.question-review__answer--correct').count(),5);
  assert.equal(await page.locator('.question-review .test-session__action,.question-review .wrong,.topic-favorite').count(),0);
  assert.equal(await page.getByRole('button',{name:/Проверить|Ответить|Следующий вопрос/}).count(),0);
  assert.equal(await page.locator('.question-review__explanation[open]').count(),0);
  assert.equal(await page.locator('.question-review__scroll').evaluate(e=>getComputedStyle(e).overscrollBehaviorY),'none');
  assert.ok(await page.locator('.question-review').evaluate(e=>e.scrollWidth<=e.clientWidth));
  const input=page.getByRole('searchbox');
  await input.fill('  РЕБЕР ');assert.equal(await page.locator('.question-review__card').count(),1);
  assert.equal(await page.locator('.question-review__card h2>span').innerText(),'2.');
  await input.fill('Несуществующий запрос');assert.equal(await page.locator('.question-review__card').count(),0);
  assert.ok(await page.locator('.question-review__empty').isVisible());
  await input.fill('');await page.locator('.question-review__explanation summary').first().click();
  assert.ok(await page.locator('.question-review__explanation p').first().isVisible());
  if(mode==='fullscreen')await page.screenshot({path:`${dir}/review-${width}.png`});
  await page.locator('.question-review__scroll').evaluate(e=>{e.scrollTop=e.scrollHeight;});
  const last=await page.locator('.question-review__card').last().boundingBox();
  assert.ok(last.y+last.height<=812-(mode==='browser'?8:34));
  await back(page,mode);assert.equal(await page.locator('.topic-questions>li').count(),5);
  assert.ok(await page.locator('.topic-page').evaluate(e=>e.scrollTop>0));
  await page.goForward();await page.locator('.question-review').waitFor();
  await page.goBack();await page.locator('.topic-page').waitFor({state:'visible'});
  await page.getByRole('button',{name:'Экзамен',exact:true}).click();
  assert.equal(await page.locator('.question-review').count(),0);
  await page.locator('.test-choice').first().click();
  assert.equal(await page.locator('.test-choice.correct,.test-explanation,.question-review__answer--correct').count(),0);
  page.once('dialog',d=>d.accept());
  if(mode==='browser')await page.locator('.test-session__close').click();else await page.evaluate(()=>[...callbacks][0]());
  await page.locator('.topic-page').waitFor({state:'visible'});
  await page.getByRole('button',{name:'Обучение',exact:true}).click();await page.locator('.test-choice').first().click();
  assert.equal(await page.locator('.test-choice.correct').count(),1);
  assert.deepEqual(errors,[]);await page.close();
  console.log(`PASS ${width} ${mode}: reference answers/search/explanation, topic state, Back/forward/callbacks, safe-area, exam secrecy, learning`);
 }
 // Test-only data: multiple answers, missing explanations, long banks, paging.
 for(const width of [375,390,430]){
  const page=await browser.newPage({viewport:{width,height:812},reducedMotion:'reduce'});
  await page.goto(`${fixtureUrl}?case=multi`);
  assert.equal(await page.locator('.question-review__answer--correct').count(),2);
  assert.equal(await page.locator('.question-review__explanation').count(),0);
  await page.goto(`${fixtureUrl}?case=empty`);assert.equal(await page.locator('.question-review__card').count(),0);assert.ok(await page.locator('.question-review__empty').isVisible());
  await page.goto(`${fixtureUrl}?case=long`);
  assert.equal(await page.locator('.question-review__card').count(),30);
  await page.getByRole('button',{name:/Показать ещё/}).click();assert.equal(await page.locator('.question-review__card').count(),60);
  await page.getByRole('searchbox').fill('формулировка 200.');assert.equal(await page.locator('.question-review__card').count(),1);
  assert.equal(await page.locator('.question-review__card h2>span').innerText(),'200.');
  assert.ok(await page.locator('.question-review__card').evaluate(e=>e.scrollWidth<=e.clientWidth));
  await page.screenshot({path:`${dir}/long-fixture-${width}.png`});
  await page.setViewportSize({width,height:400});
  await page.locator('.question-review__scroll').evaluate(e=>{e.scrollTop=e.scrollHeight;});
  assert.ok(await page.locator('.question-review__scroll').evaluate(e=>e.clientHeight>0));
  await page.close();console.log(`PASS ${width} fixture: multiple correct, absent explanation, empty, 200 questions/paging/search, long answers, short height`);
 }
}finally{await browser.close();}
