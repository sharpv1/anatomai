import assert from 'node:assert/strict';
import {chromium} from 'playwright';
import {mkdirSync,writeFileSync} from 'node:fs';

const before=process.env.BEFORE_URL;
const after=process.env.AFTER_URL ?? 'http://127.0.0.1:4173/';
if(!before) throw new Error('Set BEFORE_URL to a server hosting UI 5.2 at commit 8d1e922');
const output=process.env.COMPARISON_DIR ?? '/workspace/work/ui521-comparison';
mkdirSync(output,{recursive:true});
const browser=await chromium.launch({executablePath:process.env.CHROMIUM_EXECUTABLE_PATH||undefined,args:['--no-sandbox']});
const report=[];
try {
  for(const width of [375,390,430]) {
    for(const version of ['before','after']) {
      const page=await browser.newPage({viewport:{width,height:844},reducedMotion:'reduce'});
      await page.route('https://telegram.org/**',r=>r.fulfill({contentType:'application/javascript',body:`window.Telegram={WebApp:{initData:'test',platform:'ios',version:'8.0',isFullscreen:true,viewportHeight:844,viewportStableHeight:844,safeAreaInset:{top:59,bottom:34,left:0,right:0},contentSafeAreaInset:{top:45,bottom:0,left:0,right:0},ready(){},expand(){},onEvent(){},offEvent(){},BackButton:{show(){},hide(){},onClick(){},offClick(){}}}};`}));
      await page.goto(version==='before'?before:after);
      for(const position of ['top','end']) {
        await page.locator('.shell__content').evaluate((el,pos)=>{el.scrollTop=pos==='end'?el.scrollHeight:0},position);
        const nav=await page.locator('.bottom-nav').boundingBox();
        const content=await page.locator('.shell__content').evaluate(el=>({scrollTop:el.scrollTop,scrollHeight:el.scrollHeight,padding:getComputedStyle(el).paddingBottom}));
        await page.screenshot({path:`${output}/${width}-${position}-${version}.png`});
        report.push({width,position,version,nav,content});
      }
      if(width===390) {
        await page.locator('.shell__content').evaluate(el=>{el.scrollTop=0});
        await page.screenshot({path:`docs/screenshots/ui-5.2.1/home-${version}.jpg`,type:'jpeg',quality:88});
      }
      await page.locator('.nav-item').nth(1).click();await page.locator('.test-card').first().click();await page.locator('.test-mode-card').first().click();
      const block=await page.locator('.test-session').evaluate(el=>{
        const head=el.querySelector('.test-session__top').getBoundingClientRect();
        const options=el.querySelector('.test-session__options').getBoundingClientRect();
        return {height:options.bottom-head.top,questionFont:getComputedStyle(el.querySelector('h2')).fontSize,choiceHeight:el.querySelector('.test-choice').getBoundingClientRect().height,backButtons:el.querySelectorAll('.test-session__close').length};
      });
      if(version==='after') {assert.equal(block.backButtons,0);assert.ok(block.choiceHeight>=48);}
      report.push({width,version,test:block});
      if(width===390) await page.screenshot({path:`docs/screenshots/ui-5.2.1/test-${version}.jpg`,type:'jpeg',quality:88});
      await page.close();
    }
  }
  writeFileSync(`${output}/geometry.json`,JSON.stringify(report,null,2));
  for(const width of [375,390,430]) {
    for(const position of ['top','end']) {
      const a=report.find(r=>r.width===width&&r.position===position&&r.version==='before');
      const b=report.find(r=>r.width===width&&r.position===position&&r.version==='after');
      assert.deepEqual(a.content,b.content,`${width}/${position}: home scroll geometry changed`);
    }
    const a=report.find(r=>r.width===width&&r.test&&r.version==='before').test;
    const b=report.find(r=>r.width===width&&r.test&&r.version==='after').test;
    assert.equal(a.questionFont,b.questionFont);
    assert.ok(1-b.height/a.height>=.15 && 1-b.height/a.height<=.20,'Test density must improve by 15–20% on the comparison fixture');
    console.log(`${width}px: test block ${a.height.toFixed(1)} -> ${b.height.toFixed(1)}px (${((1-b.height/a.height)*100).toFixed(1)}% smaller); home scroll unchanged`);
  }
} finally {await browser.close();}
