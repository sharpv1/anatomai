import assert from 'node:assert/strict';
import {chromium} from 'playwright';
const before=process.env.BEFORE_URL,after=process.env.AFTER_URL;
if(!before||!after)throw Error('BEFORE_URL (31466a8 build) and AFTER_URL required');
const browser=await chromium.launch({executablePath:process.env.CHROMIUM_EXECUTABLE_PATH||undefined,args:['--no-sandbox']});
const sdk=`window.callbacks=new Set();window.Telegram={WebApp:{initData:'demo',platform:'ios',version:'8.0',ready(){},expand(){},viewportHeight:744,viewportStableHeight:744,safeAreaInset:{top:0,bottom:34},contentSafeAreaInset:{top:0,bottom:0},onEvent(){},offEvent(){},BackButton:{show(){},hide(){},onClick(cb){callbacks.add(cb)},offClick(cb){callbacks.delete(cb)}}}};`;
try{
 for(const width of [320,375,390,430]){
  const images=[];
  for(const url of [before,after]){
   const p=await browser.newPage({viewport:{width,height:744},reducedMotion:'reduce'});
   await p.route('https://telegram.org/**',r=>r.fulfill({contentType:'application/javascript',body:sdk}));await p.goto(url);
   const shots=[];for(const end of [false,true]){await p.locator('.shell__content').evaluate((el,end)=>el.scrollTop=end?el.scrollHeight:0,end);shots.push(await p.screenshot());}images.push(shots);
   await p.locator('.nav-item').nth(1).click();await p.locator('.test-card').first().click();await p.locator('.test-mode-card').first().click();
   assert.equal(await p.locator('.test-session__close').count(),url===after?0:1);
   if(url===after){
    const geometry=await p.locator('.test-session').evaluate(el=>{const box=el.querySelector('.test-session__top').getBoundingClientRect(),meta=el.querySelector('.test-session__meta').getBoundingClientRect(),track=el.querySelector('.test-session__track').getBoundingClientRect();return {left:box.left,meta:meta.left,track:track.left,overflow:document.documentElement.scrollWidth>innerWidth};});
    assert.equal(geometry.left,geometry.meta);assert.equal(geometry.left,geometry.track);assert.equal(geometry.overflow,false);
   }
   await p.close();
  }
  for(let i=0;i<2;i++)assert.ok(images[0][i].equals(images[1][i]),`home changed ${width}/${i}`);
  console.log(`PASS ${width}px: home PNG identical at top/end; unknown SDK visibility hides arrow and removes reserved column`);
 }
}finally{await browser.close();}
