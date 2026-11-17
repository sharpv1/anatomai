import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { chromium } from 'playwright';
import { readFileSync } from 'node:fs';
import ts from 'typescript';

const server = spawn(process.execPath, ['node_modules/vite/bin/vite.js', 'preview', '--host', '127.0.0.1', '--port', '4179', '--strictPort'], { stdio: ['ignore', 'pipe', 'pipe'] });
let browser;
try {
  await new Promise((resolve, reject) => {
    server.stdout.on('data', chunk => { if (String(chunk).includes('4179')) resolve(); });
    server.on('error', reject);
    server.on('exit', code => reject(new Error(`Preview exited: ${code}`)));
  });
  browser = await chromium.launch({ executablePath: process.env.CHROMIUM_EXECUTABLE_PATH || undefined, args: ['--no-sandbox'] });
  for (const [width, height] of [[375,812], [390,844], [430,932], [375,400], [390,480], [430,400], [667,375]]) {
    for (const mode of ['browser', 'telegram', 'fullscreen']) {
      const page = await browser.newPage({ viewport: { width, height } });
      const errors = []; page.on('pageerror', error => errors.push(error.message));
      await page.route('https://telegram.org/**', route => route.fulfill({ contentType: 'application/javascript', body: `
        window.testBackCallbacks = new Set(); window.testEvents = new Map();
        window.Telegram = {WebApp: {
          initData: ${JSON.stringify(mode === 'browser' ? '' : 'test')}, platform: '${mode === 'browser' ? 'unknown' : 'ios'}', version: '8.0',
          isFullscreen: ${mode === 'fullscreen'}, viewportHeight: ${height}, viewportStableHeight: ${height},
          safeAreaInset: {top: ${mode === 'fullscreen' ? 59 : 0}, bottom: 34, left: 0, right: 0},
          contentSafeAreaInset: {top: ${mode === 'fullscreen' ? 45 : 0}, bottom: 0},
          ready(){}, expand(){}, requestFullscreen(){},
          onEvent(e,c){if(!testEvents.has(e))testEvents.set(e,new Set());testEvents.get(e).add(c)},
          offEvent(e,c){testEvents.get(e)?.delete(c)},
          BackButton:{show(){},hide(){},onClick(c){testBackCallbacks.add(c)},offClick(c){testBackCallbacks.delete(c)}}}};
      ` }));
      const safeTop = mode === 'fullscreen' ? 104 : 0;
      const bottom = mode === 'browser' ? 8 : 34;
      const expectedBack = mode === 'browser' ? 0 : 1;
      await page.goto('http://127.0.0.1:4179/');
      assert.equal(await page.locator('.fullscreen-toggle').isVisible(), mode === 'telegram');
      assert.ok(await page.locator('.shell').evaluate(el => el.scrollWidth <= el.clientWidth));
      assert.equal(await page.locator('.hero svg,.icon-btn .dot').count(),0);
      assert.equal(await page.locator('.hero .streak').innerText(),'🔥 5 дней подряд');
      assert.equal(await page.locator('.hero .micro-badge').innerText(),'✦ +120 XP за сегодня');
      assert.ok(await page.locator('.icon-btn').evaluate(el=>el.getBoundingClientRect().width>=44 && el.getBoundingClientRect().height>=44));
      assert.ok(await page.locator('meta[name="viewport"]').getAttribute('content').then(value=>value.includes('user-scalable=no')));
      const gestures=await page.locator('.shell').evaluate(el=>{
        const fire=(type,touches)=>{const e=new Event(type,{bubbles:true,cancelable:true});if(touches)Object.defineProperty(e,'touches',{value:touches});el.dispatchEvent(e);return e.defaultPrevented;};
        return {gesture:fire('gesturestart'),double:fire('dblclick'),single:fire('touchmove',[{clientX:1,clientY:2}]),multi:fire('touchmove',[{},{}])};
      });
      assert.deepEqual(gestures,{gesture:true,double:true,single:false,multi:true});
      const geometry = await page.evaluate(() => {
        const view = document.querySelector('.shell__viewport').getBoundingClientRect();
        const header = document.querySelector('.topbar').getBoundingClientRect();
        const nav = document.querySelector('.bottom-nav'); const n = nav.getBoundingClientRect();
        return {viewTop:view.top, headerTop:header.top, navTop:n.top, viewBottom:view.bottom, paddingBottom:getComputedStyle(nav).paddingBottom, scrim:getComputedStyle(document.querySelector('.shell'),'::before').height};
      });
      assert.equal(geometry.viewTop, safeTop);
      assert.equal(geometry.headerTop, safeTop + 12);
      assert.equal(geometry.scrim, `${safeTop}px`);
      assert.equal(geometry.paddingBottom, '6px');
      assert.equal(geometry.viewBottom, height);
      assert.equal(await page.locator('.bottom-nav').evaluate(el => el.getBoundingClientRect().bottom), height - bottom);
      assert.equal(await page.locator('.bottom-nav').evaluate(el => el.getBoundingClientRect().height),60);
      assert.ok(await page.locator('.bottom-nav').evaluate(el => el.getBoundingClientRect().width < document.querySelector('.shell').clientWidth));
      // Scroll the real home page: the protected band never receives hero hits.
      await page.locator('.shell__content').evaluate(el => { el.scrollTop = el.scrollHeight; });
      const home = await page.evaluate(() => {
        const c = document.querySelector('.shell__content'); const tip = document.querySelector('.tip').getBoundingClientRect();
        const band = document.elementFromPoint(innerWidth / 2, 10);
        return {scroll:c.scrollTop, tipBottom:tip.bottom, bottom:document.querySelector('.bottom-nav').getBoundingClientRect().top, bandHasHero:!!band?.closest('.hero')};
      });
      assert.ok(home.scroll > 0); assert.ok(home.tipBottom <= home.bottom + 1); if(safeTop > 0) assert.equal(home.bandHasHero, false);
      for(const idx of [2,3,0]) {await page.locator('.nav-item').nth(idx).click();assert.equal(await page.locator('.nav-item').nth(idx).getAttribute('aria-current'),'page');}
      await page.locator('.nav-item').nth(1).click();
      assert.equal(await page.locator('.shell__content').evaluate(el => el.scrollTop), 0);
      // Keyboard simulation: current visual height shrinks while SDK stable height remains stale.
      assert.ok(await page.locator('.tests-search input').evaluate(el => parseFloat(getComputedStyle(el).fontSize) >= 16));
      await page.locator('.tests-search input').focus();
      const keyboardHeight = Math.max(280, height - 260);
      await page.setViewportSize({ width, height: keyboardHeight });
      await page.waitForFunction(h => Math.abs(document.querySelector('.shell').getBoundingClientRect().height - h) < 1, keyboardHeight);
      assert.ok(await page.locator('.bottom-nav').evaluate((el, h) => el.getBoundingClientRect().bottom <= h + 1, keyboardHeight));
      await page.locator('.tests-search input').fill('анатомия');
      assert.equal(await page.locator('.test-card').count(), 1);
      await page.locator('.tests-search input').fill('');
      await page.locator('.tests-search input').blur();
      await page.setViewportSize({ width, height });
      await page.waitForFunction(h => Math.abs(document.querySelector('.shell').getBoundingClientRect().height - h) < 1, height);
      // Long catalog fixture changes only the test DOM, not application data.
      await page.locator('.test-list').evaluate(el => { const card = el.firstElementChild; for(let i=0;i<12;i++){const copy=card.cloneNode(true);copy.dataset.fixture='true';el.append(copy);} });
      await page.locator('.shell__content').evaluate(el => { el.scrollTop = el.scrollHeight; });
      assert.ok(await page.locator('.shell__content').evaluate(el => el.scrollTop > 0));
      await page.locator('[data-fixture]').evaluateAll(els => els.forEach(el=>el.remove()));
      await page.locator('.shell__content').evaluate(el => { el.scrollTop = 0; });
      await page.locator('.test-card').first().click();
      await page.locator('.test-mode-card').first().click();
      assert.equal(await page.locator('.fullscreen-toggle').isVisible(), false);
      assert.equal(await page.locator('.test-session__close').count(),mode === 'browser' ? 1 : 0);
      await page.locator('.test-choice').first().click();
      assert.equal(await page.locator('.test-session__action').innerText(),'Далее');
      assert.equal(await page.locator('.test-choice:disabled').count(),4);
      await page.waitForFunction(() => [...document.querySelectorAll('.test-choice.correct,.test-choice.wrong')].every(el => ['rgb(236, 251, 245)', 'rgb(255, 241, 241)'].includes(getComputedStyle(el).backgroundColor)));
      const colors = await page.locator('.test-choice').evaluateAll(els => els.filter(el=>el.matches('.correct,.wrong')).map(el=>({card:getComputedStyle(el).backgroundColor,text:getComputedStyle(el.querySelector('.test-choice__text')).backgroundColor,radio:getComputedStyle(el.querySelector('.test-choice__radio')).backgroundColor})));
      assert.equal(colors.length, 2);
      assert.deepEqual(colors.map(c=>c.card).sort(), ['rgb(236, 251, 245)','rgb(255, 241, 241)'].sort());
      for(const color of colors) { assert.equal(color.text,'rgba(0, 0, 0, 0)');assert.equal(color.radio,'rgba(0, 0, 0, 0)'); }
      assert.equal(await page.evaluate(() => testBackCallbacks.size), expectedBack);
      await page.evaluate(() => {
        document.querySelector('.test-session__content h2').textContent = 'Длинный вопрос по анатомии. '.repeat(24);
        document.querySelectorAll('.test-choice__text').forEach(el => {el.textContent = 'Длинный вариант ответа с медицинскими терминами. '.repeat(10);});
      });
      assert.ok(await page.locator('.test-session__content').evaluate(el => el.scrollWidth <= el.clientWidth));
      const before = await page.evaluate(() => {
        const rect = selector => { const r = document.querySelector(selector).getBoundingClientRect(); return {top:r.top, bottom:r.bottom}; };
        return {header:rect('.test-session__top'), footer:rect('.test-session__footer')};
      });
      await page.locator('.test-session__content').evaluate(el => { el.scrollTop = el.scrollHeight; });
      const after = await page.evaluate(() => {
        const c = document.querySelector('.test-session__content');
        const f = document.querySelector('.test-session__footer').getBoundingClientRect();
        const h = document.querySelector('.test-session__top').getBoundingClientRect();
        return {top:h.top, bottom:f.bottom, scroll:c.scrollTop, height:c.clientHeight, documentScroll:document.scrollingElement.scrollTop};
      });
      assert.ok(after.height > 0 && after.scroll > 0, `${width}x${height} ${mode}: content cannot scroll`);
      assert.ok(before.header.top >= safeTop && after.bottom <= height - bottom + 1);
      assert.equal(after.top, before.header.top); assert.equal(after.bottom, before.footer.bottom); assert.equal(after.documentScroll, 0);
      // Back and reopen must not leak callbacks.
      page.once('dialog', dialog => dialog.dismiss());
      if(mode !== 'browser') await page.evaluate(() => { for(const cb of [...testBackCallbacks]) cb(); });
      else await page.locator('.test-session__close').click();
      assert.equal(await page.locator('.test-session').count(),1);
      assert.equal(await page.evaluate(() => testBackCallbacks.size),expectedBack);
      page.once('dialog', dialog => dialog.accept());
      if(mode !== 'browser') await page.evaluate(() => { for(const cb of [...testBackCallbacks]) cb(); });
      else await page.locator('.test-session__close').click();
      await page.locator('.tests-head').waitFor();
      assert.equal(await page.evaluate(() => testBackCallbacks.size), 0);
      await page.locator('.nav-item').first().click();
      await page.locator('.topbar').waitFor();
      // Fullscreen/expanded transition must be driven by metrics, not by a fixed minimum.
      if(mode !== 'browser') {
        await page.evaluate(() => {
          const t=Telegram.WebApp;t.isFullscreen=false;t.safeAreaInset.top=0;t.contentSafeAreaInset.top=0;t.safeAreaInset.bottom=0;
          for(const event of ['fullscreenChanged','safeAreaChanged','contentSafeAreaChanged','viewportChanged']) for(const cb of testEvents.get(event)??[])cb();
        });
        assert.equal(await page.locator('.shell__viewport').evaluate(el => el.getBoundingClientRect().top), 0);
        assert.equal(await page.locator('.bottom-nav').evaluate(el=>getComputedStyle(el).paddingBottom),'6px');
        assert.equal(await page.locator('.bottom-nav').evaluate(el=>innerHeight-el.getBoundingClientRect().bottom),8);
      }
      await page.reload();
      assert.equal(await page.evaluate(() => testBackCallbacks.size), 0);
      if(mode !== 'browser') assert.ok(await page.evaluate(() => [...testEvents.values()].every(set=>set.size===1)));
      assert.deepEqual(errors, []);
      console.log(`PASS ${width}x${height} ${mode}: clipping, navigation, search/resize, answer colors, footer, reopen`);
      await page.close();
    }
  }
  // Full learning/exam journeys use the existing immutable question fixtures.
  const js = ts.transpileModule(readFileSync(new URL('../src/features/tests/data.ts', import.meta.url), 'utf8'), {compilerOptions:{target:ts.ScriptTarget.ES2022,module:ts.ModuleKind.ESNext}}).outputText;
  const {questionsForTest}=await import(`data:text/javascript;base64,${Buffer.from(js).toString('base64')}`);
  const questions=questionsForTest('anatomy');
  const page=await browser.newPage({viewport:{width:390,height:667},reducedMotion:'reduce'});
  await page.route('https://telegram.org/**',r=>r.fulfill({contentType:'application/javascript',body:''}));
  await page.goto('http://127.0.0.1:4179/');
  await page.locator('.nav-item').nth(1).click(); await page.locator('.test-card').first().click(); await page.locator('.test-mode-card').first().click();
  assert.equal(await page.locator('.test-session__action').count(),0);
  for(let i=0;i<questions.length;i++) {
    assert.equal(await page.locator('.test-session__track').getAttribute('aria-valuenow'),String(i));
    if(i===2) {await page.locator('.test-session__skip').click();continue;}
    const answer=i===3 ? (questions[i].correctAnswer+1)%questions[i].answers.length : questions[i].correctAnswer;
    await page.locator('.test-choice').nth(answer).click();
    assert.equal(await page.locator('.test-choice.correct').count(),1);
    assert.notEqual(await page.locator('.test-session__action').innerText(),'Проверить ответ');
    const locked = await page.locator('.test-choice[aria-pressed="true"]').innerText();
    const score = await page.locator('.test-session__score').innerText();
    await page.locator('.test-choice').nth((answer+1)%questions[i].answers.length).evaluate(el=>el.click());
    assert.equal(await page.locator('.test-choice[aria-pressed="true"]').innerText(),locked);
    assert.equal(await page.locator('.test-session__score').innerText(),score);
    assert.equal(await page.locator('.test-choice:disabled').count(),questions[i].answers.length);
    assert.equal(await page.locator('.test-choice.correct').count(),1);
    assert.equal(await page.locator('.test-session__track').getAttribute('aria-valuenow'),String(i+1));
    if(i===1) assert.equal(await page.locator('.test-streak').innerText(),'2 подряд');
    if(i===3) assert.equal(await page.locator('.test-streak').count(),0);
    assert.equal(await page.locator('.test-question').evaluate(el=>getComputedStyle(el).animationName),'none');
    await page.locator('.test-session__action').click();
  }
  await page.locator('.test-result').waitFor();
  assert.equal(await page.locator('.test-result__badge strong').innerText(),'60%');
  assert.deepEqual(await page.locator('.test-result__stats strong').allTextContents(),['3','1','1']);
  await page.getByRole('button',{name:'Разобрать ошибки',exact:true}).click();
  assert.equal(await page.locator('.test-review__item').count(),2);
  await page.getByRole('button',{name:'Пройти ещё раз',exact:true}).click();
  await page.locator('.test-mode-card').nth(1).click();
  for(let i=0;i<questions.length;i++) {
    if(i===2){await page.locator('.test-session__skip').click();continue;}
    const answer=i===1 ? (questions[i].correctAnswer+1)%questions[i].answers.length : questions[i].correctAnswer;
    await page.locator('.test-choice').nth((answer+1)%questions[i].answers.length).click();
    await page.locator('.test-choice').nth(answer).click();
    assert.equal(await page.locator('.test-choice[aria-pressed="true"]').count(),1);
    assert.equal(await page.locator('.test-choice.correct,.test-choice.wrong,.test-explanation,.test-streak').count(),0);
    assert.notEqual(await page.locator('.test-session__action').innerText(),'Проверить ответ');
    await page.locator('.test-session__action').click();
  }
  await page.locator('.test-result').waitFor();
  assert.deepEqual(await page.locator('.test-result__stats strong').allTextContents(),['3','1','1']);
  await page.getByRole('button',{name:'К тестам',exact:true}).click();await page.locator('.tests-page').waitFor();
  console.log('PASS learning/exam journeys: instant check/locked answer, streak, skip, results, errors review, retake, reduced motion');
  await page.close();
} finally { await browser?.close(); server.kill(); }
