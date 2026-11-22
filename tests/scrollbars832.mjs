import assert from 'node:assert/strict';
import {chromium} from 'playwright';
const url=process.env.AFTER_URL||'http://127.0.0.1:5096';
const fixtureUrl=process.env.FIXTURE_URL||'http://127.0.0.1:5098/tests/fixtures/question-review.html';
const browser=await chromium.launch({executablePath:'/usr/bin/chromium',args:['--no-sandbox']});
const owners=new Set();
async function open(width,mode){
 const p=await browser.newPage({viewport:{width,height:812},reducedMotion:'reduce'});
 await p.route('https://telegram.org/**',r=>r.fulfill({body:mode==='browser'?'':`window.callbacks=new Set();window.Telegram={WebApp:{initData:'test',platform:'ios',version:'8.0',isFullscreen:${mode==='fullscreen'},viewportHeight:812,viewportStableHeight:812,safeAreaInset:{top:${mode==='fullscreen'?59:0},bottom:34},contentSafeAreaInset:{top:${mode==='fullscreen'?45:0},bottom:0},ready(){},expand(){},onEvent(){},offEvent(){},BackButton:{show(){},hide(){},onClick(cb){callbacks.add(cb)},offClick(cb){callbacks.delete(cb)}}}};`}));
 const errors=[];p.on('pageerror',e=>errors.push(e.message));await p.goto(url);return {p,errors};
}
async function audit(p,label){
 const found=await p.evaluate(()=>[...document.querySelectorAll('.shell,.shell *')].filter(e=>{const s=getComputedStyle(e);return [s.overflowX,s.overflowY].some(v=>v==='auto'||v==='scroll');}).map(e=>{const s=getComputedStyle(e);return {name:e.className||e.tagName,x:s.overflowX,y:s.overflowY,standard:s.scrollbarWidth,webkit:getComputedStyle(e,'::-webkit-scrollbar').display};}));
 assert.ok(found.length>0,label);
 for(const el of found){assert.equal(el.standard,'none',`${label}: ${el.name}`);assert.equal(el.webkit,'none',`${label} WebKit: ${el.name}`);owners.add(el.name);}
 assert.ok(await p.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),`${label}: document overflow`);
}
async function resize(p,width,height){
 await p.setViewportSize({width,height});
 await p.waitForFunction(h=>Math.abs(document.querySelector('.shell').getBoundingClientRect().height-h)<1,height);
 await p.evaluate(()=>new Promise(requestAnimationFrame));
}
async function wheel(p,selector){
 const el=p.locator(selector);await el.evaluate(e=>{e.scrollTop=0;});
 assert.ok(await el.evaluate(e=>e.scrollHeight>e.clientHeight),`No overflow to test: ${selector}`);
 const box=await el.boundingBox();await p.mouse.move(box.x+box.width/2,box.y+Math.min(box.height/2,80));await p.mouse.wheel(0,200);
 await p.waitForFunction(selector=>document.querySelector(selector).scrollTop>0,selector);
}
async function back(p,mode,selector){if(mode==='browser')await p.locator(selector).click();else{assert.equal(await p.evaluate(()=>callbacks.size),1);await p.evaluate(()=>[...callbacks][0]());}}
try{
 for(const width of [375,390,430])for(const mode of ['browser','expanded','fullscreen']){
  const {p,errors}=await open(width,mode);await audit(p,'Home');await wheel(p,'.shell__content');
  const navigation=await p.locator('.bottom-nav').boundingBox();assert.equal(navigation.y+navigation.height,812-(mode==='browser'?8:34));
  await p.locator('.shell__content').evaluate(e=>{e.scrollTop=e.scrollHeight;});const tip=await p.locator('.tip').boundingBox();assert.ok(tip.y+tip.height<=navigation.y-8);
  await p.locator('.study-promos').scrollIntoViewIfNeeded();const carousel=await p.locator('.study-promos').boundingBox();await p.mouse.move(carousel.x+carousel.width/2,carousel.y+carousel.height/2);await p.mouse.wheel(200,0);await p.waitForFunction(()=>document.querySelector('.study-promos').scrollLeft>0);await audit(p,'horizontal carousel');
  await p.getByRole('button',{name:'Подробнее',exact:true}).click();await p.locator('.statistics-page').waitFor();
  await p.locator('.statistics-disclosure>summary').first().click();assert.equal(await p.locator('.rp-achievement:visible').count(),9);await audit(p,'Statistics/disclosure');await wheel(p,'.statistics-page');await p.goBack();await p.locator('.topbar').waitFor({state:'visible'});
  await p.locator('.nav-item').nth(1).click();await p.locator('.tests-search input').fill('анатомия');assert.equal(await p.locator('.test-card').count(),1);await audit(p,'Tests/search');await p.locator('.tests-search input').fill('');
  await resize(p,width,400);await wheel(p,'.shell__content');await resize(p,width,812);
  await p.locator('.test-card').first().click();await p.locator('.topic-page').waitFor({state:'visible'});await audit(p,'Topic');await resize(p,width,300);await p.waitForFunction(()=>document.querySelector('.shell').getBoundingClientRect().height<=300);await wheel(p,'.topic-page');await resize(p,width,812);
  await p.getByRole('button',{name:/Ответы и разбор/}).click();await p.locator('.question-review').waitFor();await audit(p,'Answers');await wheel(p,'.question-review__scroll');
  await p.getByRole('searchbox').fill('рёбер');assert.equal(await p.locator('.question-review__card').count(),1);await p.getByRole('searchbox').fill('');
  await p.locator('.question-review__topic').evaluate(e=>{e.textContent='Длинное название темы '.repeat(40);});await audit(p,'nested title');await wheel(p,'.question-review__topic');
  await back(p,mode,'.question-review__back');await p.locator('.topic-page').waitFor({state:'visible'});await p.getByRole('button',{name:'Обучение',exact:true}).click();await p.locator('.test-choice').first().click();
  await p.locator('.test-question h2').evaluate(e=>{e.textContent='Длинный вопрос '.repeat(100);});await p.locator('.test-choice__text').first().evaluate(e=>{e.textContent='Длинный вариант ответа '.repeat(50);});
  const fixed=await p.locator('.test-session__footer').boundingBox();await audit(p,'Question');await wheel(p,'.test-session__content');const footer=await p.locator('.test-session__footer').boundingBox();assert.deepEqual(footer,fixed);assert.ok(footer.y+footer.height<=812-(mode==='browser'?8:34));
  await p.locator('.test-session__action').click();for(let i=0;i<4;i++)await p.locator('.test-session__skip').click();await p.locator('.test-result').waitFor();await p.getByRole('button',{name:'Разобрать ошибки',exact:true}).click();assert.equal(await p.locator('.test-review__item').count(),5);await audit(p,'Result/errors');await wheel(p,'.test-result');
  await p.getByRole('button',{name:'К тестам',exact:true}).click();await p.locator('.tests-page').waitFor();
  await p.locator('.nav-item').nth(2).click();await p.locator('.notes-list').waitFor({state:'visible'});await audit(p,'Notes');await resize(p,width,400);await wheel(p,'.shell__content');await resize(p,width,812);await p.locator('.notes-card').first().click();await p.locator('.notes-detail').waitFor();await audit(p,'Notes detail');await back(p,mode,'.notes-back');await p.locator('.notes-list').waitFor();
  await p.locator('.nav-item').nth(3).click();await p.locator('.profile-page').waitFor({state:'visible'});await audit(p,'Profile');await resize(p,width,400);await wheel(p,'.shell__content');
  await p.locator('.profile-premium-row').click();await p.getByRole('dialog').waitFor();await audit(p,'Modal');
  // A normal short dialog need not overflow on every viewport. Exercise its
  // existing overflow:auto with a test-only long description, not product data.
  await p.locator('#premium-description').evaluate(e=>{e.textContent+=' Длинный тестовый информационный текст.'.repeat(50);});
  await wheel(p,'.premium-dialog');await p.getByRole('button',{name:'Понятно'}).click();await p.getByRole('dialog').waitFor({state:'detached'});await resize(p,width,812);
  // A future scroller with no known page-specific class is covered too.
  await p.evaluate(()=>{const e=document.createElement('div');e.className='future-scroll-owner';e.style.cssText='position:absolute;width:120px;height:60px;overflow:auto';const child=document.createElement('div');child.style.cssText='width:300px;height:200px';e.append(child);document.querySelector('.shell').append(e);});await audit(p,'future nested scroller');
  assert.deepEqual(await p.locator('.future-scroll-owner').evaluate(e=>{e.scrollTop=20;e.scrollLeft=20;return{x:e.scrollLeft,y:e.scrollTop};}),{x:20,y:20});await p.locator('.future-scroll-owner').evaluate(e=>e.remove());
  assert.deepEqual(errors,[]);await p.close();console.log(`PASS ${width} ${mode}: all scroll owners/indicators, wheel + horizontal carousel, search, disclosure, Back, pinned footer, nested/modal/future scrollers`);
 }
 // Large lists use the same AppShell stylesheet even outside the production entry.
 for(const width of [375,390,430]){
  const p=await browser.newPage({viewport:{width,height:400},reducedMotion:'reduce'});await p.goto(`${fixtureUrl}?case=long`);await p.locator('.question-review').waitFor();await audit(p,'long bank fixture');await wheel(p,'.question-review__scroll');await p.getByRole('button',{name:/Показать ещё/}).click();assert.equal(await p.locator('.question-review__card').count(),60);await audit(p,'expanded batch');await p.close();
 }
 console.log('PASS long banks/short screens: 30→60, wheel scrolling, shared fixture import');console.log('AUDITED OWNERS: '+[...owners].sort().join('; '));
}finally{await browser.close();}
