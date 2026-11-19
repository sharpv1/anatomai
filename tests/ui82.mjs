import assert from 'node:assert/strict';
import {mkdirSync,writeFileSync} from 'node:fs';
import {chromium} from 'playwright';
const after=process.env.AFTER_URL||'http://127.0.0.1:4896';
const before=process.env.BEFORE_URL||'http://127.0.0.1:4897';
const dir='docs/screenshots/ui-8.2';mkdirSync(dir,{recursive:true});
const browser=await chromium.launch({executablePath:'/usr/bin/chromium',args:['--no-sandbox']});
async function open(width,mode,url=after){
 const p=await browser.newPage({viewport:{width,height:812},timezoneId:'Asia/Bishkek',reducedMotion:'reduce'});
 await p.clock.setFixedTime(new Date('2026-11-19T06:00:00Z'));
 await p.route('https://telegram.org/**',r=>r.fulfill({body:mode==='browser'?'':`window.callbacks=new Set();window.Telegram={WebApp:{initData:'test',platform:'ios',version:'8.0',isFullscreen:${mode==='fullscreen'},viewportHeight:812,viewportStableHeight:812,safeAreaInset:{top:${mode==='fullscreen'?59:0},bottom:34},contentSafeAreaInset:{top:${mode==='fullscreen'?45:0},bottom:0},ready(){},expand(){},onEvent(){},offEvent(){},BackButton:{show(){},hide(){},onClick(cb){callbacks.add(cb)},offClick(cb){callbacks.delete(cb)}}}};`}));
 const errors=[];p.on('pageerror',e=>errors.push(e.message));await p.goto(url);return {p,errors};
}
async function back(p,mode,selector){if(mode==='browser')await p.locator(selector).click();else{assert.equal(await p.evaluate(()=>callbacks.size),1);await p.evaluate(()=>[...callbacks][0]());}}
async function home(p){await p.locator('.topbar').waitFor({state:'visible'});}
async function shot(p,width,mode,name){if(mode==='fullscreen')await p.screenshot({path:`${dir}/${name}-${width}.png`});}
async function topic(p){await p.locator('.nav-item').nth(1).click();await p.locator('.test-card').first().click();await p.locator('.topic-page').waitFor({state:'visible'});}
try{
 for(const width of [375,390,430])for(const mode of ['browser','expanded','fullscreen']){
  const {p,errors}=await open(width,mode);const root=p.locator('.page-view').first();
  assert.deepEqual(await root.locator('.stats--compact dd').allTextContents(),['0','—','—']);
  assert.equal(await root.locator('.stats--compact>div').count(),3);
  assert.equal(await root.locator('.activity').count(),0);
  const recommendation=await p.locator('.daily-questions').innerText();
  assert.ok(!recommendation.includes('12 карточек'));
  await p.reload();assert.equal(await p.locator('.daily-questions').innerText(),recommendation);
  await shot(p,width,mode,'home-top');
  await p.locator('.shell__content').evaluate(e=>{e.scrollTop=e.scrollHeight;});
  const tip=await p.locator('.tip').boundingBox(),nav=await p.locator('.bottom-nav').boundingBox();assert.ok(tip.y+tip.height<=nav.y-8);
  await shot(p,width,mode,'home-bottom');
  for(const [index,title] of ['Анатомия','Физиология','Неврология'].entries()){
   await p.locator('.subject').nth(index).click();await p.locator('.notes-detail').waitFor();
   assert.equal(await p.locator('.notes-detail h2').innerText(),title);
   if(index===0)await shot(p,width,mode,'notes-discipline');
   assert.equal(await p.locator('.notes-back:visible').count(),mode==='browser'?1:0);
   await back(p,mode,'.notes-back:visible');await home(p);
   if(mode!=='browser')assert.equal(await p.evaluate(()=>callbacks.size),0);
  }
  await root.getByRole('button',{name:'Все',exact:true}).click();await p.locator('.notes-list').waitFor();
  assert.equal(await p.locator('.notes-card').count(),4);
  await shot(p,width,mode,'notes-catalog');
  await p.locator('.notes-card').first().click();await p.locator('.notes-detail').waitFor();
  await back(p,mode,'.notes-back:visible');await p.locator('.notes-list').waitFor();
  await back(p,mode,'.notes-back:visible');await home(p);
  await p.locator('.daily-questions').click();await p.locator('.question-review').waitFor();
  assert.equal(await p.locator('.question-review h1').innerText(),'Ответы и разбор');
  assert.equal(await p.locator('.topic-page').count(),0);
  const dailyTitle=await p.locator('.question-review__topic').innerText();
  await shot(p,width,mode,'daily-answers');
  await back(p,mode,'.question-review__back');await home(p);
  assert.equal(await p.locator('.daily-questions').innerText(),recommendation);
  await p.goForward();await p.locator('.question-review').waitFor();
  assert.equal(await p.locator('.question-review__topic').innerText(),dailyTitle);
  await p.reload();await p.locator('.question-review').waitFor();
  assert.equal(await p.locator('.question-review__topic').innerText(),dailyTitle);
  await back(p,mode,'.question-review__back');await home(p);
  await topic(p);
  const {p:base}=await open(width,mode,before);await topic(base);
  assert.deepEqual(await p.locator('.topic-modes button').evaluateAll(es=>es.map(e=>{const r=e.getBoundingClientRect();return{x:r.x,y:r.y,width:r.width,height:r.height};})),await base.locator('.topic-modes button').evaluateAll(es=>es.map(e=>{const r=e.getBoundingClientRect();return{x:r.x,y:r.y,width:r.width,height:r.height};})));
  await p.mouse.move(0,0);await base.mouse.move(0,0);
  await p.evaluate(()=>document.activeElement?.blur());await base.evaluate(()=>document.activeElement?.blur());
  const styles=page=>page.locator('.topic-modes button').evaluateAll(es=>es.map(el=>{const s=getComputedStyle(el);return Object.fromEntries(['backgroundColor','color','font','padding','border','borderRadius','minHeight','display'].map(key=>[key,s[key]]));}));
  assert.deepEqual(await styles(p),await styles(base));
  // Rectangles above must match at the actual screen positions. Normalize the
  // pixel capture only, avoiding a fractional screenshot clip after navigation.
  const saved=[];
  for(const page of [p,base])saved.push(await page.locator('.topic-modes').evaluate(el=>{
    const old={row:el.style.cssText,content:document.querySelector('.shell__content').style.cssText};
    const width=el.getBoundingClientRect().width;document.querySelector('.shell__content').style.visibility='hidden';
    Object.assign(el.style,{position:'fixed',left:'0px',top:'0px',width:`${width}px`,margin:'0px',zIndex:'999',visibility:'visible'});return old;
  }));
  const actualModes=await p.locator('.topic-modes').screenshot(),previousModes=await base.locator('.topic-modes').screenshot();
  if(!actualModes.equals(previousModes)){writeFileSync(`/tmp/ui82-controls-${width}-${mode}-actual.png`,actualModes);writeFileSync(`/tmp/ui82-controls-${width}-${mode}-before.png`,previousModes);}
  assert.deepEqual(actualModes,previousModes,'Learning/exam controls changed');
  for(const [index,page] of [p,base].entries())await page.locator('.topic-modes').evaluate((el,old)=>{el.style.cssText=old.row;document.querySelector('.shell__content').style.cssText=old.content;},saved[index]);
  await base.close();
  assert.equal(await p.locator('.topic-questions,.topic-show-all').count(),0);
  assert.equal(await p.locator('.topic-metrics dd').count(),3);
  await shot(p,width,mode,'topic');
  await p.getByRole('button',{name:/Ответы и разбор/}).click();await p.locator('.question-review').waitFor();
  await p.getByRole('searchbox').fill('рёбер');assert.equal(await p.locator('.question-review__card').count(),1);
  await p.getByRole('searchbox').fill('');await p.locator('.question-review__explanation summary').first().click();
  await shot(p,width,mode,'topic-answers');
  await back(p,mode,'.question-review__back');await p.locator('.topic-page').waitFor({state:'visible'});
  await p.getByRole('button',{name:'Экзамен',exact:true}).click();await p.locator('.test-choice').first().click();
  assert.equal(await p.locator('.question-review,.test-choice.correct,.test-explanation').count(),0);
  p.once('dialog',d=>d.accept());await back(p,mode,'.test-session__close');await p.locator('.topic-page').waitFor({state:'visible'});
  await p.getByRole('button',{name:'Обучение',exact:true}).click();await p.locator('.test-choice').first().click();assert.equal(await p.locator('.test-choice.correct').count(),1);
  p.once('dialog',d=>d.accept());await back(p,mode,'.test-session__close');await p.locator('.topic-page').waitFor({state:'visible'});
  await back(p,mode,'.study-back');await p.locator('.tests-page').waitFor();
  await p.locator('.nav-item').nth(3).click();await shot(p,width,mode,'profile');
  assert.equal(await p.locator('.premium-card').count(),0);
  await p.locator('.profile-premium-row').click();await p.getByRole('dialog').waitFor();
  assert.equal(await p.getByRole('dialog').locator('h2').innerText(),'Premium скоро появится');
  assert.equal(await p.getByRole('dialog').getByRole('button').count(),1);await shot(p,width,mode,'premium-info');
  await p.getByRole('button',{name:'Понятно'}).click();await p.getByRole('dialog').waitFor({state:'detached'});
  await p.locator('.nav-item').first().click();await home(p);
  await p.getByRole('button',{name:'Подробнее',exact:true}).click();await p.locator('.statistics-page').waitFor();
  await p.goBack();await home(p);
  assert.ok(await p.locator('.shell').evaluate(e=>e.scrollWidth<=e.clientWidth));
  assert.equal(await p.evaluate(()=>document.scrollingElement.scrollTop),0);assert.deepEqual(errors,[]);
  await p.close();console.log(`PASS ${width} ${mode}: honest compact stats; all subjects/Notes/catalog/back; daily reload/forward; topic control pixel/geometry parity; answers/search; exam/learning; Premium; clearance`);
 }
 // Complete an actual existing test; opening reference pages must not record attempts.
 const {p}=await open(390,'browser');await topic(p);await p.getByRole('button',{name:'Обучение',exact:true}).click();
 for(let i=0;i<5;i++)await p.locator('.test-session__skip').click();
 await p.getByRole('button',{name:'К тестам',exact:true}).click();await p.locator('.nav-item').first().click();
 const values=await p.locator('.stats--compact dd').allTextContents();assert.equal(values[0],'1');assert.equal(values[1],'0%');assert.match(values[2],/^\d+ (сек|мин)$/);
 await p.locator('.daily-questions').click();await p.locator('.question-review').waitFor();await back(p,'browser','.question-review__back');await home(p);
 assert.deepEqual(await p.locator('.stats--compact dd').allTextContents(),values);await p.close();
 console.log('PASS statistics use an actual completion; reference browsing does not alter history/results');
 const fixture=await browser.newPage();await fixture.goto('http://127.0.0.1:4898/tests/fixtures/question-review.html?case=daily-empty');
 await fixture.locator('.daily-questions').waitFor();assert.equal(await fixture.locator('.daily-questions button,button.daily-questions').count(),0);assert.ok((await fixture.locator('.daily-questions').innerText()).includes('Пока нет доступных вопросов'));await fixture.close();
 console.log('PASS empty daily bank has no unavailable action');
}finally{await browser.close();}
