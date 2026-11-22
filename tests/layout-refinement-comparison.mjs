import assert from 'node:assert/strict';
import {mkdirSync,writeFileSync} from 'node:fs';
import {chromium} from 'playwright';
const before=process.env.BEFORE_URL;
if(!before)throw Error('BEFORE_URL must serve production 7363ee4');
const after=process.env.AFTER_URL??'http://127.0.0.1:4173/';
const output=process.env.COMPARISON_DIR??'/workspace/work/ui61-comparison';mkdirSync(output,{recursive:true});
const browser=await chromium.launch({executablePath:process.env.CHROMIUM_EXECUTABLE_PATH||undefined,args:['--no-sandbox']});
const report=[];
try{
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
  const shot=async screen=>{await page.mouse.move(0,0);await page.screenshot({path:`docs/screenshots/ui-6.1/${screen}-${version}.jpg`,type:'jpeg',quality:88});};
  if(width===390){await page.locator('.shell__content').evaluate(el=>{el.scrollTop=0});await shot('home');}
  await page.locator('.nav-item').nth(1).click();
  const cards=await page.locator('.test-card').evaluateAll(els=>els.map(el=>el.getBoundingClientRect().height));
  report.push({width,version,cards});
  if(width===390)await shot('catalog');
  await page.locator('.test-card').first().click();await page.locator('.test-mode-card').first().click();
  const question=await page.locator('.test-session').evaluate(el=>{
   const header=el.querySelector('.test-session__top').getBoundingClientRect();const options=el.querySelector('.test-session__options').getBoundingClientRect();const footer=el.querySelector('.test-session__footer').getBoundingClientRect();
   return{headerHeight:header.height,optionsBottom:options.bottom,footerTop:footer.top,gap:footer.top-options.bottom,questionFont:getComputedStyle(el.querySelector('h2')).fontSize};
  });report.push({width,version,question});
  if(version==='after'){assert.equal(await page.locator('.test-session__close').count(),0);assert.ok(question.gap<=32,'No flex-created empty gap before actions');assert.ok(await page.locator('.test-session__skip').evaluate(el=>el.getBoundingClientRect().height>=44));}
  if(width===390){await shot('question');
   await page.reload();await page.locator('.nav-item').nth(1).click();await page.locator('.test-card').nth(3).click();await page.locator('.test-mode-card').first().click();await page.locator('.test-choice').first().click();await page.locator('.test-session__action').click();await page.locator('.test-result').waitFor();await shot('result');
   if(version==='after'){assert.equal(await page.getByRole('button',{name:'К тестам',exact:true}).getAttribute('class'),'test-result__back');assert.equal(await page.getByRole('button',{name:'Разобрать ошибки',exact:true}).count(),0);}
  }
  await page.close();
 }
 writeFileSync(`${output}/geometry.json`,JSON.stringify(report,null,2));
 for(const width of [320,375,390,430]){
  for(const position of ['top','end']){const a=report.find(r=>r.width===width&&r.position===position&&r.version==='before');const b=report.find(r=>r.width===width&&r.position===position&&r.version==='after');assert.deepEqual(a.content,b.content);}
  const a=report.find(r=>r.width===width&&r.cards&&r.version==='before').cards;const b=report.find(r=>r.width===width&&r.cards&&r.version==='after').cards;
  assert.ok(a.every((h,i)=>1-b[i]/h>=.1 && 1-b[i]/h<=.15),'Catalog reduction must stay within 10–15%');
  console.log(`${width}px cards: ${a.map((h,i)=>`${h.toFixed(1)}→${b[i].toFixed(1)} (${((1-b[i]/h)*100).toFixed(1)}%)`).join(', ')}`);
  assert.equal(report.find(r=>r.width===width&&r.question&&r.version==='before').question.questionFont,report.find(r=>r.width===width&&r.question&&r.version==='after').question.questionFont);
 }
}finally{await browser.close();}
