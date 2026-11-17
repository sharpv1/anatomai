import assert from 'node:assert/strict';
import {mkdirSync,writeFileSync} from 'node:fs';
import {chromium} from 'playwright';
const before=process.env.BEFORE_URL;
if(!before)throw Error('BEFORE_URL must serve production bda3f72');
const after=process.env.AFTER_URL??'http://127.0.0.1:4173/';
const output=process.env.COMPARISON_DIR??'/workspace/work/ui60-comparison';
mkdirSync(output,{recursive:true});
const browser=await chromium.launch({executablePath:process.env.CHROMIUM_EXECUTABLE_PATH||undefined,args:['--no-sandbox']});
const report=[];
try {
 for(const width of [320,375,390,430])for(const version of ['before','after']){
  const page=await browser.newPage({viewport:{width,height:852},reducedMotion:'reduce'});
  await page.route('https://telegram.org/**',r=>r.fulfill({contentType:'application/javascript',body:`window.Telegram={WebApp:{initData:'test',platform:'ios',version:'8.0',isFullscreen:true,viewportHeight:852,viewportStableHeight:852,safeAreaInset:{top:59,bottom:34,left:0,right:0},contentSafeAreaInset:{top:45,bottom:0,left:0,right:0},ready(){},expand(){},onEvent(){},offEvent(){},BackButton:{show(){},hide(){},onClick(){},offClick(){}}}};`}));
  await page.goto(version==='before'?before:after);
  for(const position of ['top','end']){
   await page.locator('.shell__content').evaluate((el,pos)=>{el.scrollTop=pos==='end'?el.scrollHeight:0},position);
   const nav=await page.locator('.bottom-nav').boundingBox();
   const content=await page.locator('.shell__content').evaluate(el=>({scrollTop:el.scrollTop,scrollHeight:el.scrollHeight,padding:getComputedStyle(el).paddingBottom}));
   await page.screenshot({path:`${output}/${width}-${position}-${version}.png`});report.push({width,position,version,nav,content});
  }
  if(width===390){
   await page.locator('.shell__content').evaluate(el=>{el.scrollTop=0});
   const shot=screen=>page.screenshot({path:`docs/screenshots/ui-6.0/${screen}-${version}.jpg`,type:'jpeg',quality:88});
   await shot('home');
   await page.locator('.nav-item').nth(1).click();await shot('tests');
   await page.locator('.test-card').first().click();await page.locator('.test-mode-card').first().click();await shot('question');
   // Reload to complete a one-question existing test without altering its data.
   await page.reload();await page.locator('.nav-item').nth(1).click();await page.locator('.test-card').nth(3).click();await page.locator('.test-mode-card').first().click();await page.locator('.test-choice').first().click();await page.locator('.test-session__action').click();await page.locator('.test-result').waitFor();await shot('result');
   if(version==='after'){
    assert.equal(await page.locator('.test-result__badge strong').innerText(),'100%');
    assert.equal(await page.getByRole('button',{name:'Разобрать ошибки',exact:true}).count(),0);
    assert.equal(await page.locator('.test-result__progress').getAttribute('aria-valuenow'),'100');
    assert.equal(await page.getByRole('button',{name:'К тестам',exact:true}).getAttribute('class'),'test-session__action');
   }
   await page.getByRole('button',{name:'К тестам',exact:true}).click();await page.locator('.nav-item').nth(3).click();await page.locator('.toast').waitFor({state:'detached'});await shot('profile');
  }
  await page.close();
 }
 writeFileSync(`${output}/geometry.json`,JSON.stringify(report,null,2));
 for(const width of [320,375,390,430])for(const position of ['top','end']){
  const a=report.find(r=>r.width===width&&r.position===position&&r.version==='before');
  const b=report.find(r=>r.width===width&&r.position===position&&r.version==='after');
  assert.deepEqual(a.content,b.content);console.log(`PASS home geometry ${width}/${position}`);
 }
}finally{await browser.close();}
