import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { chromium } from 'playwright';

const server = spawn(process.execPath, ['node_modules/vite/bin/vite.js', 'preview', '--host', '127.0.0.1', '--port', '4179', '--strictPort'], { stdio: ['ignore', 'pipe', 'pipe'] });
let browser;
try {
  await new Promise((resolve, reject) => {
    server.stdout.on('data', chunk => { if (String(chunk).includes('4179')) resolve(); });
    server.on('error', reject);
    server.on('exit', code => reject(new Error(`Preview exited: ${code}`)));
  });
  browser = await chromium.launch({ executablePath: process.env.CHROMIUM_EXECUTABLE_PATH || undefined, args: ['--no-sandbox'] });
  for (const [width, height] of [[320,480], [375,400], [390,667], [667,375]]) {
    for (const mode of ['browser', 'telegram', 'fullscreen']) {
      const page = await browser.newPage({ viewport: { width, height } });
      const errors = []; page.on('pageerror', error => errors.push(error.message));
      await page.route('https://telegram.org/**', route => route.fulfill({ contentType: 'application/javascript', body: `
        window.testBackCallbacks = new Set();
        window.testEvents = new Map();
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
      await page.goto('http://127.0.0.1:4179/');
      await page.locator('.nav-item').nth(1).click();
      await page.locator('.test-card').first().click();
      await page.locator('.test-mode-card').first().click();
      await page.locator('.test-choice').first().click();
      const expected = mode === 'browser' ? 0 : 1;
      assert.equal(await page.evaluate(() => testBackCallbacks.size), expected);
      await page.evaluate(() => {
        const content = document.querySelector('.test-session__content');
        const long = document.createElement('div'); long.style.height = '1600px'; content.append(long);
      });
      const before = await page.evaluate(() => {
        const rect = selector => { const r = document.querySelector(selector).getBoundingClientRect(); return {top:r.top, bottom:r.bottom}; };
        return {header:rect('.test-session__top'), footer:rect('.test-session__footer')};
      });
      await page.locator('.test-session__content').evaluate(el => { el.scrollTop = el.scrollHeight; });
      const after = await page.evaluate(() => {
        const content = document.querySelector('.test-session__content');
        const footer = document.querySelector('.test-session__footer').getBoundingClientRect();
        const header = document.querySelector('.test-session__top').getBoundingClientRect();
        return {top:header.top, bottom:footer.bottom, scroll:content.scrollTop, height:content.clientHeight, documentScroll:document.scrollingElement.scrollTop};
      });
      assert.ok(after.height > 0 && after.scroll > 0, `${width}x${height} ${mode}: content cannot scroll`);
      assert.ok(before.header.top >= 0 && after.bottom <= height + 1, `${width}x${height} ${mode}: footer outside viewport: ${after.bottom}`);
      assert.equal(after.top, before.header.top); assert.equal(after.bottom, before.footer.bottom);
      assert.equal(after.documentScroll, 0);
      assert.deepEqual(errors, []);
      console.log(`PASS ${width}x${height} ${mode}: footer=${after.bottom}, inner scroll=${after.scroll}, BackButton=${expected}`);
      await page.close();
    }
  }
} finally {
  await browser?.close(); server.kill();
}
