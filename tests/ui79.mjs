import assert from 'node:assert/strict';
import { mkdirSync } from 'node:fs';
import { chromium } from 'playwright';

// Serve the previous PR #21 dist separately to compare protected Home regions.
const url = process.env.AFTER_URL || 'http://127.0.0.1:4696';
const beforeUrl = process.env.BEFORE_URL || 'http://127.0.0.1:4697';
const screenshots = 'docs/screenshots/home-layout-8.0';
mkdirSync(screenshots, { recursive: true });
const browser = await chromium.launch({
  executablePath: process.env.CHROMIUM_EXECUTABLE_PATH || '/usr/bin/chromium',
  args: ['--no-sandbox'],
});

async function open(target, width, height, mode, delayed = false) {
  const page = await browser.newPage({
    viewport: { width, height }, hasTouch: true, reducedMotion: 'reduce',
  });
  const errors = [];
  page.on('pageerror', e => errors.push(e.message));
  await page.route('https://telegram.org/**', r => r.fulfill({
    contentType: 'application/javascript',
    body: mode === 'browser' ? '' : `
      window.callbacks=new Set();
      window.Telegram={WebApp:{initData:'test',platform:'ios',version:'8.0',
        isFullscreen:${mode === 'fullscreen'},viewportHeight:${height},viewportStableHeight:${height},
        safeAreaInset:{top:${mode === 'fullscreen' ? 59 : 0},bottom:34},
        contentSafeAreaInset:{top:${mode === 'fullscreen' ? 45 : 0},bottom:0},
        ready(){},expand(){},onEvent(){},offEvent(){},
        BackButton:{isVisible:false,show(){this.isVisible=true},hide(){this.isVisible=false},
          onClick(cb){callbacks.add(cb)},offClick(cb){callbacks.delete(cb)}}}};`,
  }));
  let release;
  if (delayed) {
    const gate = new Promise(resolve => { release = resolve; });
    await page.route('**/promos/*.webp', async route => { await gate; await route.continue(); });
  }
  await page.goto(target, { waitUntil: 'domcontentloaded' });
  await page.locator('.hero').waitFor();
  await page.evaluate(() => document.fonts.ready);
  return { page, release, errors };
}

async function swipe(page, x1, y1, x2, y2) {
  const cdp = await page.context().newCDPSession(page);
  await cdp.send('Input.dispatchTouchEvent', { type: 'touchStart', touchPoints: [{ x: x1, y: y1 }] });
  for (let i = 1; i <= 8; i++) {
    await cdp.send('Input.dispatchTouchEvent', {
      type: 'touchMove', touchPoints: [{ x: x1 + (x2 - x1) * i / 8, y: y1 + (y2 - y1) * i / 8 }],
    });
    await page.waitForTimeout(20);
  }
  await cdp.send('Input.dispatchTouchEvent', { type: 'touchEnd', touchPoints: [] });
  await page.waitForTimeout(350);
  await cdp.detach();
}

try {
  for (const width of [375, 390, 430]) {
    for (const mode of ['browser', 'expanded', 'fullscreen']) {
      const { page, release, errors } = await open(url, width, 812, mode, true);
      const home = page.locator('.page-view').first();
      assert.deepEqual(await home.evaluate(el => {
        const blocks=['topbar','hero','subjects','review','stats','study-promos','tip'];
        return [...el.children].flatMap(child=>blocks.filter(name=>child.classList.contains(name)));
      }), ['topbar','hero','subjects','review','stats','study-promos','tip']);
      assert.equal(await home.locator('.hero + .section h3').innerText(),'Предметы');
      assert.equal(await home.locator('.subjects + .section h3').innerText(),'Повтори сегодня');
      assert.equal(await home.locator('.review + .section h3').innerText(),'Твоя статистика');
      assert.equal(await home.locator('.activity,.chart,.days').count(),0);
      assert.equal(await home.locator('.stat').count(),2);
      assert.equal(await home.locator('.stat b').first().innerText(),'—');
      assert.equal(await home.locator('.stat b').nth(1).innerText(),'0 сек');
      assert.equal(await home.evaluate(el=>el.lastElementChild.classList.contains('tip')),true);
      const carousel = page.locator('.study-promos');
      await carousel.scrollIntoViewIfNeeded();
      const cards = carousel.locator('button');
      assert.equal(await cards.count(), 4);
      assert.deepEqual(await carousel.locator('.study-promo__artwork').evaluateAll(images => images.map(el => el.src.split('/').pop())),
        ['exam-preparation.webp', 'medical-notes.webp', 'mistake-review.webp', 'anatomai-premium.webp']);
      assert.equal(await carousel.locator('strong,span,svg').count(), 0);
      const before = await carousel.boundingBox();
      const nextSectionBefore = await page.locator('.tip').boundingBox();
      release();
      // A fourth lazy image may intentionally remain unfetched until scrolled
      // into view. Check initial stability with the first visible image only.
      await carousel.locator('img').first().evaluate(image => image.decode());
      const after = await carousel.boundingBox();
      assert.equal(before.height, after.height, 'Images must reserve height before decoding');
      assert.ok(after.height >= 105 && after.height <= 115);
      assert.equal(nextSectionBefore.y, (await page.locator('.tip').boundingBox()).y);

      const geometry = await carousel.evaluate(el => {
        const box = el.getBoundingClientRect();
        return {
          snap: getComputedStyle(el).scrollSnapType,
          touch: getComputedStyle(el).touchAction,
          overscroll: getComputedStyle(el).overscrollBehaviorY,
          peek: box.right - el.children[1].getBoundingClientRect().left,
        };
      });
      assert.equal(geometry.snap, 'x mandatory');
      assert.equal(geometry.touch, 'pan-x pan-y');
      assert.equal(geometry.overscroll, 'auto');
      assert.ok(geometry.peek > 8, 'Next banner must be partially visible');

      for (let i = 0; i < 4; i++) {
        const img = cards.nth(i).locator('.study-promo__artwork');
        await cards.nth(i).scrollIntoViewIfNeeded();
        await img.evaluate(image => image.decode());
        assert.equal(await img.getAttribute('loading'), 'lazy');
        assert.equal(await img.getAttribute('alt'), ''); // The button carries the accessible label.
        const dimensions = await img.evaluate(el => ({
          width: el.clientWidth, height: el.clientHeight, naturalWidth: el.naturalWidth,
          naturalHeight: el.naturalHeight, fit: getComputedStyle(el).objectFit,
        }));
        assert.equal(dimensions.naturalWidth, 1536);
        assert.equal(dimensions.naturalHeight, 768);
        assert.equal(dimensions.fit, 'cover');
        // Bounds in the unchanged 1536x768 artwork: all headings plus the
        // main illustration, including the pencil and the raised crown.
        const protectedArea = [
          {left:95, top:130, right:1460, bottom:665},
          {left:95, top:130, right:1430, bottom:665},
          {left:95, top:130, right:1470, bottom:665},
          {left:100, top:55, right:1430, bottom:650},
        ][i];
        const visibleSource = await img.evaluate(el => {
          const image=el.getBoundingClientRect(), card=el.parentElement.getBoundingClientRect();
          const [px,py]=getComputedStyle(el).objectPosition.split(' ').map(v=>parseFloat(v)/100);
          const scale=Math.max(image.width/el.naturalWidth,image.height/el.naturalHeight);
          const left=image.left+(image.width-el.naturalWidth*scale)*px;
          const top=image.top+(image.height-el.naturalHeight*scale)*py;
          return {left:(card.left-left)/scale,top:(card.top-top)/scale,right:(card.right-left)/scale,bottom:(card.bottom-top)/scale};
        });
        assert.ok(visibleSource.left <= protectedArea.left && visibleSource.top <= protectedArea.top && visibleSource.right >= protectedArea.right && visibleSource.bottom >= protectedArea.bottom, `Artwork clipped: ${i} ${JSON.stringify(visibleSource)}`);
        const frame = await cards.nth(i).evaluate(el => ({height:el.getBoundingClientRect().height,overflow:getComputedStyle(el).overflow,radius:getComputedStyle(el).borderRadius,padding:getComputedStyle(el).padding,border:getComputedStyle(el).borderWidth}));
        assert.ok(frame.height >= 105 && frame.height <= 115);
        assert.equal(frame.overflow, 'hidden');
        assert.equal(frame.radius, '16px');
        assert.equal(frame.padding, '0px');
        assert.equal(frame.border, '0px');
        const cleanFrame = await cards.nth(i).evaluate(el => {
          const card=getComputedStyle(el), image=getComputedStyle(el.querySelector('img')), row=getComputedStyle(el.parentElement);
          return {fraction:el.getBoundingClientRect().width/el.parentElement.getBoundingClientRect().width,gap:parseFloat(row.gap),shadows:[card.boxShadow,image.boxShadow,row.boxShadow],borders:[card.borderWidth,image.borderWidth,row.borderWidth],pseudo:[getComputedStyle(el,'::before').content,getComputedStyle(el,'::after').content,getComputedStyle(el.parentElement,'::before').content,getComputedStyle(el.parentElement,'::after').content]};
        });
        assert.ok(cleanFrame.fraction >= .779 && cleanFrame.fraction <= .821);
        assert.ok(cleanFrame.gap >= 8 && cleanFrame.gap <= 10);
        assert.deepEqual(cleanFrame.shadows,['none','none','none']);
        assert.deepEqual(cleanFrame.borders,['0px','0px','0px']);
        assert.ok(cleanFrame.pseudo.every(content=>content==='none'));
        if (i===3) {
          assert.equal(await cards.nth(i).locator('.study-promo__headroom').getAttribute('aria-hidden'),'true');
          assert.equal(await cards.nth(i).locator('.study-promo__headroom').evaluate(el=>getComputedStyle(el).mixBlendMode),'darken');
        }
        assert.ok((await cards.nth(i).getAttribute('aria-label')).length > 10);
        if (mode === 'fullscreen') {
          await carousel.evaluate((el, index) => { el.scrollLeft = el.children[index].offsetLeft - el.offsetLeft; }, i);
          await page.waitForTimeout(150);
          const cardBounds = await cards.nth(i).boundingBox();
          const carouselBounds = await carousel.boundingBox();
          assert.ok(cardBounds.x >= carouselBounds.x - 1 && cardBounds.x + cardBounds.width <= carouselBounds.x + carouselBounds.width + 1);
          await carousel.screenshot({ path: `${screenshots}/carousel-${width}-${i + 1}.png` });
        }
      }
      if (mode === 'fullscreen') {
        await carousel.evaluate(el => { el.scrollLeft = 0; });
        await page.locator('.shell__content').evaluate(el => { el.scrollTop = 0; });
        await page.screenshot({ path: `${screenshots}/home-carousel-${width}.png` });
      }

      await page.locator('.shell__content').evaluate(el=>{el.scrollTop=el.scrollHeight;});
      const tip=await page.locator('.tip').boundingBox(), navigation=await page.locator('.bottom-nav').boundingBox();
      assert.ok(tip.y+tip.height <= navigation.y-8,'Last Home block must clear the navigation');
      if(mode==='fullscreen')await page.screenshot({path:`${screenshots}/home-bottom-${width}.png`});
      await carousel.scrollIntoViewIfNeeded();

      // Actual touch input: horizontal carousel gesture and vertical parent scrolling.
      await carousel.evaluate(el => { el.scrollLeft = 0; });
      const box = await carousel.boundingBox();
      const topBefore = await page.locator('.shell__content').evaluate(el => el.scrollTop);
      await swipe(page, box.x + box.width - 25, box.y + box.height / 2, box.x + 25, box.y + box.height / 2);
      assert.ok(await carousel.evaluate(el => el.scrollLeft > 0));
      assert.ok(Math.abs(await page.locator('.shell__content').evaluate(el => el.scrollTop) - topBefore) < 2);
      const moved = await carousel.boundingBox();
      await swipe(page, moved.x + 120, moved.y + moved.height / 2, moved.x + 120, moved.y - 100);
      assert.ok(await page.locator('.shell__content').evaluate(el => el.scrollTop > 0));
      assert.equal(await page.evaluate(() => document.scrollingElement.scrollTop), 0);
      assert.ok(await page.locator('.shell').evaluate(el => el.scrollWidth <= el.clientWidth));
      assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
      assert.equal(await page.locator('.shell__content').evaluate(el => getComputedStyle(el).overscrollBehaviorY), 'none');
      const nav = await page.locator('.bottom-nav').boundingBox();
      assert.equal(nav.y + nav.height, 812 - (mode === 'browser' ? 8 : 34));

      // First two banners retain real destinations. The other two reuse the
      // existing accessible dialog, including history and native Back cleanup.
      for (let i = 0; i < 2; i++) {
        await cards.nth(i).click();
        await page.locator(i === 1 ? '.notes-page' : '.tests-page').waitFor({ state: 'visible' });
        assert.equal(await page.getByRole('dialog').count(), 0);
        await page.locator('.nav-item').first().click();
      }
      for (const i of [2, 3, 3]) {
        await cards.nth(i).click();
        const dialog = page.getByRole('dialog');
        await dialog.waitFor({ state: 'visible' });
        assert.equal(await dialog.locator('h2').innerText(), i === 2 ? 'Повторение ошибок пока недоступно' : 'Premium скоро появится');
        assert.equal(await dialog.getByRole('button').count(), 1);
        assert.equal(new URL(page.url()).hash, i === 2 ? '#home-mistakes' : '#home-premium');
        if (mode === 'browser') await page.goBack();
        else {
          assert.equal(await page.evaluate(() => callbacks.size), 1);
          await page.evaluate(() => [...callbacks][0]());
        }
        await dialog.waitFor({ state: 'detached' });
        assert.equal(new URL(page.url()).hash, '');
        if (mode !== 'browser') assert.equal(await page.evaluate(() => callbacks.size), 0);
      }
      await cards.last().click();
      await page.getByRole('button', { name: 'Понятно' }).click();
      await page.getByRole('dialog').waitFor({ state: 'detached' });
      await home.getByRole('button',{name:'Подробнее',exact:true}).click();
      await page.locator('.statistics-page').waitFor({state:'visible'});
      assert.equal(await page.locator('.statistics-page .profile-week li').count(),7);
      await page.goBack();
      await home.waitFor({state:'visible'});
      assert.equal(await home.locator('.activity').count(),0);
      assert.deepEqual(errors, []);
      await page.close();
      console.log(`PASS ${width} ${mode}: Home block order, statistics retained, no Home week, tip clearance, compact promos/touch/routes, Details statistics week retained`);
    }
  }

  // Compare protected regions at the same viewport and scroll position independently.
  const previous = (await open(beforeUrl, 390, 812, 'browser')).page;
  const current = (await open(url, 390, 812, 'browser')).page;
  for (const p of [previous, current]) await p.locator('.shell__content').evaluate(el => { el.style.visibility = 'hidden'; });
  for (const selector of ['.topbar', '.hero', '.subjects', '.review', '.stats', '.bottom-nav']) {
    // The new image aspect ratio moves later sections. Compare their own rendering
    // at identical integer coordinates, without a different glass-nav backdrop.
    for (const p of [previous, current]) {
      if (selector === '.bottom-nav') {
        await p.locator('.shell__content').evaluate(el => { el.style.visibility = 'hidden'; });
      } else {
        await p.locator(selector).evaluate(el => {
          const width = el.getBoundingClientRect().width;
          Object.assign(el.style, { position: 'fixed', left: '0px', top: '0px', width: `${width}px`, zIndex: '999', visibility: 'visible' });
        });
      }
    }
    const a = await previous.locator(selector).screenshot();
    const b = await current.locator(selector).screenshot();
    assert.deepEqual(b, a, `Protected region changed: ${selector}`);
    if (selector !== '.bottom-nav') {
      for (const p of [previous, current]) await p.locator(selector).evaluate(el => { el.style.visibility = 'hidden'; });
    }
  }
  await previous.close();
  await current.close();
  console.log('PASS pixel-identical protected regions at normalized positions/backdrop vs previous PR #21');

  const { page } = await open(url, 375, 400, 'fullscreen');
  await page.locator('.study-promos').scrollIntoViewIfNeeded();
  await page.getByRole('button', { name: 'Подготовка к экзаменам — открыть тесты' }).click();
  await page.locator('.tests-page').waitFor({ state: 'visible' });
  await page.locator('.nav-item').nth(3).click();
  await page.locator('.premium-card button').click();
  await page.getByRole('dialog').waitFor({ state: 'visible' });
  await page.getByRole('button', { name: 'Понятно' }).click();
  await page.getByRole('dialog').waitFor({ state: 'detached' });
  await page.close();
  console.log('PASS 375x400 fullscreen: carousel reachable, exam route, existing Profile Premium dialog');
} finally {
  await browser.close();
}
