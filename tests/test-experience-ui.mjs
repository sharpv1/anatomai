import assert from 'node:assert/strict';
import {mkdirSync,readFileSync,writeFileSync} from 'node:fs';
import ts from 'typescript';
import {chromium} from 'playwright';
const before=process.env.BEFORE_URL,after=process.env.AFTER_URL;
if(!before||!after)throw Error('Serve UI 6.1.2 via BEFORE_URL and current build via AFTER_URL');
const output='docs/screenshots/ui-6.2';mkdirSync(output,{recursive:true});
const js=ts.transpileModule(readFileSync(new URL('../src/features/tests/data.ts',import.meta.url),'utf8'),{compilerOptions:{target:ts.ScriptTarget.ES2022,module:ts.ModuleKind.ESNext}}).outputText;
const {questionsForTest}=await import(`data:text/javascript;base64,${Buffer.from(js).toString('base64')}`);
const sdk=height=>`window.callbacks=new Set();window.Telegram={WebApp:{initData:'demo',platform:'ios',version:'8.0',isFullscreen:true,viewportHeight:${height},viewportStableHeight:${height},safeAreaInset:{top:59,bottom:34,left:0,right:0},contentSafeAreaInset:{top:45,bottom:0,left:0,right:0},ready(){},expand(){},onEvent(){},offEvent(){},BackButton:{isVisible:false,show(){this.isVisible=true},hide(){this.isVisible=false},onClick(c){callbacks.add(c)},offClick(c){callbacks.delete(c)}}}};`;
const browser=await chromium.launch({executablePath:process.env.CHROMIUM_EXECUTABLE_PATH||undefined,args:['--no-sandbox']});
async function page(url,width=390,height=812){const p=await browser.newPage({viewport:{width,height},reducedMotion:'reduce'});await p.route('https://telegram.org/**',r=>r.fulfill({contentType:'application/javascript',body:sdk(height)}));await p.goto(url);return p;}
async function enter(p,mode='learning'){await p.locator('.nav-item').nth(1).click();await p.locator('.test-card').first().click();await p.locator('.test-mode-card').nth(mode==='exam'?1:0).click();}
async function shot(p){await p.mouse.move(0,0);return p.screenshot();}
const report=[];
try{
 for(const width of [320,375,390,430]){
  const snapshots=[];
  for(const url of [before,after]){
   const p=await page(url,width);const shots=[];
   for(const bottom of [false,true]){await p.locator('.shell__content').evaluate((el,end)=>el.scrollTop=end?el.scrollHeight:0,bottom);shots.push(await shot(p));}
   await p.locator('.nav-item').nth(1).click();shots.push(await shot(p));await p.locator('.test-card').first().click();shots.push(await shot(p));snapshots.push(shots);await p.close();
  }
  for(let i=0;i<4;i++)assert.ok(snapshots[0][i].equals(snapshots[1][i]),`${width}px regression on home/catalog/mode picker ${i}`);
  console.log(`PASS ${width}px: home top/end, catalog, mode picker PNG unchanged`);
 }
 for(const [version,url] of [['before',before],['after',after]]){
  const p=await page(url);await enter(p);await p.locator('.test-choice').first().click();
  await p.mouse.move(0,0);await p.screenshot({path:`${output}/question-${version}.jpg`,type:'jpeg',quality:88});
  report.push({version,question:await p.locator('.test-session').evaluate(el=>({content:el.querySelector('.test-session__content').getBoundingClientRect().height,footer:el.querySelector('.test-session__footer').getBoundingClientRect().bottom}))});
  await p.locator('.test-session__action').click();const q=questionsForTest('anatomy');for(let i=1;i<q.length;i++){await p.locator('.test-choice').nth(q[i].correctAnswer).click();await p.locator('.test-session__action').click();}
  assert.equal(await p.locator('.test-result__badge strong').innerText(),'80%');
  await p.mouse.move(0,0);await p.screenshot({path:`${output}/result-${version}.jpg`,type:'jpeg',quality:88});
  report.push({version,resultGroup:await p.locator('.test-result').evaluate(el=>el.querySelector('.test-result__actions').getBoundingClientRect().bottom-el.querySelector('.test-result__summary').getBoundingClientRect().top)});
  await p.getByRole('button',{name:'Разобрать ошибки',exact:true}).click();assert.equal(await p.locator('.test-review__item').count(),1);await p.close();
 }
 for(const width of [375,390,430])for(const height of [400,812])for(const mode of ['learning','exam']){
  const p=await page(after,width,height);await enter(p,mode);await p.locator('.test-choice').first().click();
  if(mode==='exam')assert.equal(await p.locator('.test-choice.correct,.test-choice.wrong,.test-explanation').count(),0);
  await p.locator('.test-session').evaluate(el=>{
   el.querySelector('.test-session__meta>span').textContent='Длинное название медицинской дисциплины '.repeat(15);
   el.querySelector('h2').textContent='Длинный вопрос с медицинскими терминами. '.repeat(30);
   el.querySelectorAll('.test-choice__text').forEach(e=>e.textContent='Длинный вариант ответа '.repeat(20));
   const explanation=el.querySelector('.test-explanation p');if(explanation)explanation.textContent='Подробное объяснение ответа. '.repeat(80);
  });
  const rect=()=>{const h=document.querySelector('.test-session__top').getBoundingClientRect(),f=document.querySelector('.test-session__footer').getBoundingClientRect(),c=document.querySelector('.test-session__content');return {top:h.top,bottom:f.bottom,height:c.clientHeight,scroll:c.scrollTop,overflow:c.scrollWidth>c.clientWidth||document.documentElement.scrollWidth>innerWidth};};
  const initial=await p.evaluate(rect);await p.locator('.test-session__content').evaluate(el=>el.scrollTop=el.scrollHeight);const end=await p.evaluate(rect);
  assert.equal(end.top,initial.top);assert.equal(end.bottom,initial.bottom);assert.ok(end.top>=104&&end.bottom<=height-34&&end.height>0&&end.scroll>0);assert.equal(end.overflow,false);
  assert.ok(await p.locator('.test-session__action').isVisible());assert.ok(await p.locator('.test-choice').evaluateAll(els=>els.every(el=>el.getBoundingClientRect().height>=44)));
  if(width===375&&height===400&&mode==='learning'){await p.mouse.move(0,0);await p.screenshot({path:`${output}/question-long-short-screen.jpg`,type:'jpeg',quality:88});}
  console.log(`PASS ${width}x${height} ${mode}: long title/question/answers/explanation, scroll, stable footer, safe-area, no overflow`);await p.close();
 }
 writeFileSync(`${output}/geometry.json`,JSON.stringify(report,null,2));console.log(JSON.stringify(report));
}finally{await browser.close();}
