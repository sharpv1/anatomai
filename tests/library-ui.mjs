import assert from 'node:assert/strict';
import {mkdirSync} from 'node:fs';
import {chromium} from 'playwright';
const before=process.env.BEFORE_URL,after=process.env.AFTER_URL;
if(!before||!after)throw Error('BEFORE_URL must serve 8d216b2 and AFTER_URL current build');
const output='docs/screenshots/ui-7.0';mkdirSync(output,{recursive:true});
const browser=await chromium.launch({executablePath:process.env.CHROMIUM_EXECUTABLE_PATH||undefined,args:['--no-sandbox']});
const fixture=(height,mode='fullscreen',name='Айдана',last='Садыкова')=>`window.callbacks=new Set();window.sdkEvents=new Map();window.Telegram={WebApp:{initData:${JSON.stringify(new URLSearchParams({user:JSON.stringify({first_name:name,last_name:last})}).toString())},platform:'ios',version:'8.0',isFullscreen:${mode==='fullscreen'},viewportHeight:${height},viewportStableHeight:${height},safeAreaInset:{top:${mode==='fullscreen'?59:0},bottom:34,left:0,right:0},contentSafeAreaInset:{top:${mode==='fullscreen'?45:0},bottom:0,left:0,right:0},ready(){},expand(){},onEvent(e,c){if(!sdkEvents.has(e))sdkEvents.set(e,new Set());sdkEvents.get(e).add(c)},offEvent(e,c){sdkEvents.get(e)?.delete(c)},BackButton:{isVisible:false,show(){this.isVisible=true},hide(){this.isVisible=false},onClick(c){callbacks.add(c)},offClick(c){callbacks.delete(c)}}}};`;
async function page(url,width,height=812,mode='fullscreen',long=false){const p=await browser.newPage({viewport:{width,height},reducedMotion:'reduce'});await p.route('https://telegram.org/**',r=>r.fulfill({contentType:'application/javascript',body:mode==='browser'?'':fixture(height,mode,long?'ОченьДлинноеИмя'.repeat(8):'Айдана',long?'ОченьДлиннаяФамилия'.repeat(8):'Садыкова')}));await p.goto(url);return p;}
async function image(p,path){await p.mouse.move(0,0);return p.screenshot(path?{path,type:'jpeg',quality:88}:{});}
async function safe(p,height,mode){assert.ok(await p.locator('.shell').evaluate(el=>el.scrollWidth<=el.clientWidth));await p.locator('.shell__content').evaluate(el=>el.scrollTop=el.scrollHeight);const r=await p.evaluate(()=>{const owner=document.querySelector('.shell__content'),page=document.querySelector('.page-view:not([hidden])'),nav=document.querySelector('.bottom-nav').getBoundingClientRect();return {scroll:owner.scrollTop,bottom:page.getBoundingClientRect().bottom,nav:nav.top,overflow:page.scrollWidth>page.clientWidth};});assert.equal(r.overflow,false);assert.ok(r.bottom<=r.nav+1,JSON.stringify({height,mode,...r}));}
try{
 // Strict whole-image Home diff, including the unchanged Liquid Glass capsule.
 for(const width of [320,375,390,430]){
  const shots=[];for(const url of [before,after]){const p=await page(url,width);const list=[];for(const end of [false,true]){await p.locator('.shell__content').evaluate((el,end)=>el.scrollTop=end?el.scrollHeight:0,end);list.push(await image(p));}shots.push(list);await p.close();}
  for(let i=0;i<2;i++)assert.ok(shots[0][i].equals(shots[1][i]),`Home pixel diff at ${width}/${i}`);console.log(`PASS ${width}px Home: top/end PNG byte-identical, no mask`);
 }
 const flowShots=[];for(const url of [before,after]){const p=await page(url,390);await p.clock.setFixedTime(new Date('2026-11-18T00:00:00Z'));await p.locator('.nav-item').nth(1).click();await p.locator('.test-card').first().click();await p.locator('.test-mode-card').first().click();await p.locator('.test-choice').first().click();const shots=[await image(p)];await p.locator('.test-session__action').click();for(let i=0;i<4;i++)await p.locator('.test-session__skip').click();await p.locator('.test-result').waitFor();shots.push(await image(p));flowShots.push(shots);await p.close();}for(let i=0;i<2;i++)assert.ok(flowShots[0][i].equals(flowShots[1][i]),`Test flow pixel diff ${i}`);console.log('PASS question/result PNG byte-identical to UI 6.1.2');
 for(const [version,url] of [['before',before],['after',after]]){
  const p=await page(url,390);for(const [index,name] of [[1,'tests'],[2,'notes'],[3,'profile']]){await p.locator('.nav-item').nth(index).click();await image(p,`${output}/${name}-${version}.jpg`);if(version==='after'&&name==='profile'){await p.locator('.shell__content').evaluate(el=>el.scrollTop=el.scrollHeight);await image(p,`${output}/profile-bottom-after.jpg`);}}await p.close();
 }
 for(const width of [320,375,390,430])for(const height of [400,812])for(const mode of ['browser','expanded','fullscreen']){
  const p=await page(after,width,height,mode,true);const errors=[];p.on('pageerror',e=>errors.push(e.message));
  await p.locator('.nav-item').nth(1).click();assert.equal(await p.locator('.test-card').count(),4);assert.equal(await p.locator('.test-progress').count(),0);
  assert.match(await p.locator('.test-card-meta').first().innerText(),/Вопросов: 5/);
  await p.getByRole('button',{name:'Легко',exact:true}).click();assert.equal(await p.locator('.test-card').count(),2);
  await p.locator('.tests-search input').fill('НЕВРО');assert.equal(await p.locator('.test-card').count(),0);await p.getByRole('button',{name:'Сбросить поиск',exact:true}).click();assert.equal(await p.locator('.test-card').count(),4);
  await p.locator('.tests-search input').fill('анатомия');await p.locator('.nav-item').nth(2).click();
  assert.equal(await p.locator('.notes-card').count(),4);assert.equal(await p.locator('.notes-card button,.notes-card a').count(),0);
  await p.getByRole('textbox',{name:'Найти дисциплину',exact:true}).fill('гисто');assert.equal(await p.locator('.notes-card').count(),1);
  await p.locator('.nav-item').nth(3).click();assert.equal(await p.locator('.profile-week li').count(),7);assert.equal(await p.locator('.profile-stats dd').allTextContents().then(x=>x.every(v=>v==='—')),true);
  assert.ok((await p.locator('.profile-identity h2').innerText()).includes(mode==='browser'?'Ваш профиль':'ОченьДлинноеИмя'));
  await safe(p,height,mode);
  await p.locator('.nav-item').nth(2).click();assert.equal(await p.getByRole('textbox',{name:'Найти дисциплину',exact:true}).inputValue(),'гисто');
  await p.getByRole('textbox',{name:'Найти дисциплину',exact:true}).fill('zzz');assert.equal(await p.locator('.notes-card').count(),0);await p.getByRole('button',{name:'Сбросить поиск',exact:true}).click();
  // Large library fixture is DOM-only; no invented production articles.
  await p.locator('.notes-list').evaluate(el=>{const first=el.firstElementChild;for(let i=0;i<25;i++)el.append(first.cloneNode(true));});await safe(p,height,mode);
  await p.locator('.nav-item').nth(1).click();assert.equal(await p.locator('.tests-search input').inputValue(),'анатомия');
  await p.locator('.test-card-title').first().evaluate(el=>el.textContent='Очень длинное название медицинской дисциплины '.repeat(12));await safe(p,height,mode);
  await p.locator('.tests-search input').fill('');await p.locator('.library-quick').click();await p.locator('.test-mode-picker').waitFor();await p.getByRole('button',{name:'Вернуться к тестам',exact:true}).click();await p.locator('.tests-page').waitFor();
  assert.equal(await p.locator('.nav-item').count(),4);assert.deepEqual(errors,[]);console.log(`PASS ${width}x${height} ${mode}: search/filter, state, empty profile, long name/title, large library, safe-area, quick practice`);await p.close();
 }
 const state=await page(after,390);await state.locator('.nav-item').nth(1).click();await state.getByRole('button',{name:'Легко',exact:true}).click();await state.locator('.nav-item').first().click();await state.locator('.nav-item').nth(1).click();assert.equal(await state.getByRole('button',{name:'Легко',exact:true}).getAttribute('aria-pressed'),'true');assert.equal(await state.locator('.test-card').count(),2);await state.locator('.nav-item').nth(2).click();await state.locator('.notes-list').evaluate(el=>{const first=el.firstElementChild;for(let i=0;i<25;i++)el.append(first.cloneNode(true));});await state.locator('.shell__content').evaluate(el=>el.scrollTop=200);await state.locator('.nav-item').nth(3).click();await state.locator('.nav-item').nth(2).click();assert.equal(await state.locator('.shell__content').evaluate(el=>el.scrollTop),200);await state.close();console.log('PASS level and library scroll survive tab transitions');
 const motion=await page(after,390);await motion.emulateMedia({reducedMotion:'no-preference'});await motion.locator('.nav-item').nth(1).click();await motion.waitForFunction(()=>document.querySelector('.test-card').getAnimations().every(a=>a.playState==='finished'));assert.equal(await motion.locator('.test-card').first().evaluate(el=>getComputedStyle(el).animationDuration),'0.18s');await motion.emulateMedia({reducedMotion:'reduce'});assert.equal(await motion.locator('.test-card').first().evaluate(el=>getComputedStyle(el).animationName),'none');await motion.close();console.log('PASS scoped animation/reduced-motion');
}finally{await browser.close();}
