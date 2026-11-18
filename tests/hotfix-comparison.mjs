import assert from 'node:assert/strict';
import {mkdirSync,writeFileSync,readFileSync} from 'node:fs';
import ts from 'typescript';
import {chromium} from 'playwright';
const before=process.env.BEFORE_URL;
if(!before)throw Error('BEFORE_URL must serve production a853c99');
const after=process.env.AFTER_URL??'http://127.0.0.1:4173/';
const output=process.env.COMPARISON_DIR??'/workspace/work/ui611-comparison';mkdirSync(output,{recursive:true});
const js=ts.transpileModule(readFileSync(new URL('../src/features/tests/data.ts',import.meta.url),'utf8'),{compilerOptions:{target:ts.ScriptTarget.ES2022,module:ts.ModuleKind.ESNext}}).outputText;
const {questionsForTest}=await import(`data:text/javascript;base64,${Buffer.from(js).toString('base64')}`);
function fixture(late){return `window.callbacks=new Set();window.events=new Map();const back={isVisible:false,showCount:0,show(){this.showCount++;this.isVisible=true},hide(){this.isVisible=false},onClick(c){callbacks.add(c)},offClick(c){callbacks.delete(c)}};if(${late})delete back.offClick;window.Telegram={WebApp:{initData:'test',platform:'ios',version:'8.0',isFullscreen:true,viewportHeight:812,viewportStableHeight:812,safeAreaInset:{top:59,bottom:34,left:0,right:0},contentSafeAreaInset:{top:45,bottom:0,left:0,right:0},ready(){},expand(){},onEvent(e,c){if(!events.has(e))events.set(e,new Set());events.get(e).add(c)},offEvent(e,c){events.get(e)?.delete(c)},BackButton:back}};`;}
const browser=await chromium.launch({executablePath:process.env.CHROMIUM_EXECUTABLE_PATH||undefined,args:['--no-sandbox']});const report=[];
try{
 for(const width of [320,375,390,430])for(const version of ['before','after']){
  const p=await browser.newPage({viewport:{width,height:812},reducedMotion:'reduce'});await p.route('https://telegram.org/**',r=>r.fulfill({contentType:'application/javascript',body:fixture(false)}));await p.goto(version==='before'?before:after);
  for(const position of ['top','end']){
   await p.locator('.shell__content').evaluate((el,pos)=>{el.scrollTop=pos==='end'?el.scrollHeight:0},position);
   const content=await p.locator('.shell__content').evaluate(el=>({scrollTop:el.scrollTop,scrollHeight:el.scrollHeight,padding:getComputedStyle(el).paddingBottom}));
   await p.screenshot({path:`${output}/${width}-${position}-${version}.png`});report.push({width,position,version,content});
  }await p.close();
 }
 for(const version of ['before','after']){
  const p=await browser.newPage({viewport:{width:390,height:812},reducedMotion:'reduce'});await p.route('https://telegram.org/**',r=>r.fulfill({contentType:'application/javascript',body:fixture(true)}));await p.goto(version==='before'?before:after);
  await p.locator('.nav-item').nth(1).click();await p.locator('.test-card').first().click();await p.locator('.test-mode-card').first().click();assert.equal(await p.locator('.test-session__close').count(),1);
  await p.evaluate(()=>{Telegram.WebApp.BackButton.offClick=c=>callbacks.delete(c);Telegram.WebApp.BackButton.isVisible=true;});
  if(version==='after')await p.waitForFunction(()=>document.querySelectorAll('.test-session__close').length===0);
  else assert.equal(await p.locator('.test-session__close').count(),1);
  if(version==='after')assert.equal(await p.evaluate(()=>callbacks.size),1);
  await p.mouse.move(0,0);await p.screenshot({path:`docs/screenshots/ui-6.1.1/question-${version}.jpg`,type:'jpeg',quality:88});await p.close();
  const result=await browser.newPage({viewport:{width:390,height:812},reducedMotion:'reduce'});await result.route('https://telegram.org/**',r=>r.fulfill({contentType:'application/javascript',body:fixture(false)}));await result.goto(version==='before'?before:after);
  await result.locator('.nav-item').nth(1).click();await result.locator('.test-card').first().click();await result.locator('.test-mode-card').first().click();
  const q=questionsForTest('anatomy');for(let i=0;i<q.length;i++){const answer=i===0?q[i].correctAnswer:(q[i].correctAnswer+1)%q[i].answers.length;await result.locator('.test-choice').nth(answer).click();await result.locator('.test-session__action').click();}
  await result.locator('.test-result').waitFor();const height=await result.locator('.test-result').evaluate(el=>el.querySelector('.test-result__actions').getBoundingClientRect().bottom-el.querySelector('.eyebrow').getBoundingClientRect().top);
  report.push({version,resultHeight:height});await result.mouse.move(0,0);await result.screenshot({path:`docs/screenshots/ui-6.1.1/result-${version}.jpg`,type:'jpeg',quality:88});await result.close();
 }
 writeFileSync(`${output}/geometry.json`,JSON.stringify(report,null,2));
 const a=report.find(r=>r.version==='before'&&r.resultHeight).resultHeight;const b=report.find(r=>r.version==='after'&&r.resultHeight).resultHeight;assert.ok(b<a);console.log(`PASS result group ${a.toFixed(1)} -> ${b.toFixed(1)}px`);
}catch(error){throw error;}finally{await browser.close();}
