import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import ts from 'typescript';

const source = readFileSync(new URL('../src/platform/telegram/TelegramPlatformAdapter.ts', import.meta.url), 'utf8');
const js = ts.transpileModule(source, { compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ESNext } }).outputText;
const { createTelegramPlatformAdapter, resolveInset } = await import(`data:text/javascript;base64,${Buffer.from(js).toString('base64')}`);

function environment(overrides = {}) {
  const root = { dataset: {}, style: new Map() };
  root.style.setProperty = root.style.set.bind(root.style);
  root.style.removeProperty = root.style.delete.bind(root.style);
  const events = new Map(), back = new Set(), timers = new Map();
  let timerId = 0;
  const api = {
    initData: 'test', platform: 'ios', version: '8.0', ready() {}, expand() {},
    viewportHeight: 600, viewportStableHeight: 667,
    safeAreaInset: { top: 59, bottom: 34 }, contentSafeAreaInset: { top: 45 },
    onEvent(name, callback) { if (!events.has(name)) events.set(name, new Set()); events.get(name).add(callback); },
    offEvent(name, callback) { events.get(name)?.delete(callback); },
    requestFullscreen() {},
    BackButton: { isVisible: false, show() { this.isVisible = true; }, hide() { this.isVisible = false; }, onClick(cb) { back.add(cb); }, offClick(cb) { back.delete(cb); } },
    ...overrides,
  };
  globalThis.window = Object.assign(new EventTarget(), { innerHeight: 667, setInterval(fn) { timers.set(++timerId,fn);return timerId; }, clearInterval(id) { timers.delete(id); }, visualViewport: Object.assign(new EventTarget(), { height: 500 }), Telegram: { WebApp: api } });
  globalThis.document = Object.assign(new EventTarget(), { documentElement: root });
  return { root, events, back, api, timers, tick() {for(const fn of [...timers.values()]) fn();}, emit(name, data) { for (const cb of events.get(name) ?? []) cb(data); } };
}

test('factory is pure; init/dispose are idempotent and support remount', () => {
  const e = environment(); const a = createTelegramPlatformAdapter();
  assert.equal(e.events.size, 0); a.init(); a.init();
  assert.equal(e.events.size, 5);
  for (const handlers of e.events.values()) assert.equal(handlers.size, 1);
  a.dispose(); a.dispose();
  for (const handlers of e.events.values()) assert.equal(handlers.size, 0);
  assert.deepEqual(e.root.dataset, {}); assert.equal(e.root.style.size, 0);
  a.init(); for (const handlers of e.events.values()) assert.equal(handlers.size, 1);
  a.dispose();
});

test('BackButton invokes only the latest callback and unregisters on hide/dispose', () => {
  const e = environment(); const a = createTelegramPlatformAdapter(); let old = 0, latest = 0;
  a.showBackButton(() => old++); a.init();
  for (let i = 0; i < 20; i++) a.showBackButton(() => latest++);
  assert.equal(e.back.size, 1); for (const cb of e.back) cb();
  assert.equal(old, 0); assert.equal(latest, 1);
  a.hideBackButton(); assert.equal(e.back.size, 0);
  a.showBackButton(() => latest++); a.dispose(); assert.equal(e.back.size, 0);
});

test('fullscreen success is event driven; no fixed clearance is injected', () => {
  const e = environment(); const a = createTelegramPlatformAdapter(); a.init();
  assert.equal(a.requestFullscreen(), true);
  assert.equal(e.root.dataset.telegramFullscreen, 'false');
  e.api.isFullscreen = true; e.emit('fullscreenChanged');
  assert.equal(e.root.style.get('--app-inset-top'), '104px');
  e.api.safeAreaInset.top = 20; e.api.contentSafeAreaInset.top = 32; e.emit('safeAreaChanged');
  assert.equal(e.root.style.get('--app-inset-top'), '52px');
  assert.equal(e.root.style.has('--anatomai-top-clearance'), false);
  assert.equal(e.root.style.get('--tg-safe-top'), '20px');
  e.emit('fullscreenFailed', { error: 'UNSUPPORTED' });
  assert.equal(e.root.dataset.telegramFullscreenError, 'UNSUPPORTED');
  e.api.isFullscreen = false; e.emit('fullscreenChanged');
  e.api.safeAreaInset.top = 0; e.api.contentSafeAreaInset.top = 0; e.emit('contentSafeAreaChanged');
  assert.equal(e.root.style.get('--app-inset-top'), '0px');
  assert.equal(e.root.dataset.telegramFullscreenError, undefined); a.dispose();
});

test('browser SDK object and old Telegram clients do not enable fullscreen', () => {
  let e = environment({ initData: '', platform: 'unknown' }); let a = createTelegramPlatformAdapter(); a.init();
  assert.equal(a.isTelegram, false); assert.equal(a.requestFullscreen(), false);
  window.visualViewport.height = 320; window.visualViewport.dispatchEvent(new Event('resize'));
  assert.equal(e.root.style.get('--tg-viewport-height'), '320px'); a.dispose();
  e = environment({ version: '7.10' }); a = createTelegramPlatformAdapter(); a.init();
  assert.equal(a.isTelegram, true); assert.equal(a.requestFullscreen(), false); a.dispose();
});

test('distinct system/content areas compose once; explicit zero suppresses browser fallback', () => {
  assert.equal(resolveInset(59, 45, 59), 104);
  assert.equal(resolveInset(0, 0, 34), 0);
  assert.equal(resolveInset(34, 0, 34), 34);
  assert.equal(resolveInset(undefined, 12, 34), 46);
  assert.equal(resolveInset(NaN, -10, 34), 34);
  assert.equal(resolveInset(-1, Infinity, 0), 0);
});

test('viewport uses current visible height, not stable height; resize listeners are removed', () => {
  const e = environment(); const a = createTelegramPlatformAdapter(); a.init();
  assert.equal(e.root.style.get('--tg-viewport-height'), '500px');
  assert.equal(e.root.style.get('--tg-viewport-stable-height'), '667px');
  window.visualViewport.height = 280;
  window.visualViewport.offsetTop = 12;
  window.visualViewport.dispatchEvent(new Event('resize'));
  assert.equal(e.root.style.get('--tg-viewport-height'), '280px');
  assert.equal(e.root.style.get('--app-viewport-offset-top'), '12px');
  e.api.safeAreaInset.bottom = 0; e.emit('safeAreaChanged');
  assert.equal(e.root.style.get('--app-inset-bottom'), '0px');
  a.dispose();
  window.dispatchEvent(new Event('resize'));
  window.visualViewport.dispatchEvent(new Event('scroll'));
  document.dispatchEvent(new Event('visibilitychange'));
  assert.equal(e.root.style.size, 0);
  a.init(); assert.equal(e.root.style.get('--app-inset-bottom'), '0px'); a.dispose();
});

test('SDK absent, old event API, and missing insets fall back without exceptions', () => {
  let e = environment(); delete window.Telegram;
  let a = createTelegramPlatformAdapter(); a.init();
  assert.equal(a.isTelegram, false);
  assert.match(e.root.style.get('--app-inset-top'), /env\(safe-area-inset-top/); a.dispose();
  e = environment({ version: '7.10' }); a = createTelegramPlatformAdapter(); a.init();
  assert.deepEqual([...e.events.keys()], ['viewportChanged']); a.dispose();
  e = environment({ safeAreaInset: undefined, contentSafeAreaInset: undefined }); a = createTelegramPlatformAdapter(); a.init();
  assert.match(e.root.style.get('--app-inset-bottom'), /env\(safe-area-inset-bottom/); a.dispose();
});

test('intentional pinch zoom does not reflow shell as if a keyboard opened', () => {
  const e = environment(); const a = createTelegramPlatformAdapter(); a.init();
  assert.equal(e.root.style.get('--tg-viewport-height'), '500px');
  window.visualViewport.scale = 2; window.visualViewport.height = 250; window.visualViewport.offsetTop = 120;
  window.visualViewport.dispatchEvent(new Event('resize'));
  assert.equal(e.root.style.get('--tg-viewport-height'), '500px');
  assert.equal(e.root.style.get('--app-viewport-offset-top'), '0px');
  window.visualViewport.scale = 1; window.visualViewport.height = 320; window.visualViewport.offsetTop = 0;
  window.visualViewport.dispatchEvent(new Event('resize'));
  assert.equal(e.root.style.get('--tg-viewport-height'), '320px'); a.dispose();
});

test('native BackButton capability requires a supported client and removable callback', () => {
  let e = environment(); let a = createTelegramPlatformAdapter();
  assert.equal(a.canUseBackButton,false); a.init(); assert.equal(a.canUseBackButton,true); a.dispose();
  assert.equal(a.canUseBackButton,false);
  for(const overrides of [{BackButton:undefined},{version:'6.0'},{BackButton:{show(){},hide(){},onClick(){}}},{initData:'',platform:'unknown'}]){
    e=environment(overrides);a=createTelegramPlatformAdapter();a.init();assert.equal(a.canUseBackButton,false);a.dispose();
  }
});

test('native visibility is reactive, screen owned, and stale release cannot clear a newer screen',()=>{
 const e=environment();const a=createTelegramPlatformAdapter();a.init();let notices=0;
 const unsubscribe=a.subscribeBackButton(()=>notices++);const releaseA=a.bindBackButton(()=>{});
 assert.equal(a.getBackButtonSnapshot(),true);assert.equal(e.back.size,1);
 const releaseB=a.bindBackButton(()=>{});releaseA();
 assert.equal(a.getBackButtonSnapshot(),true);assert.equal(e.back.size,1);
 releaseB();assert.equal(a.getBackButtonSnapshot(),false);assert.equal(e.back.size,0);assert.equal(e.timers.size,0);assert.equal(notices,2);
 unsubscribe();a.dispose();
});

test('late SDK and late BackButton support update visibility without React unrelated state changes',()=>{
 const e=environment();const a=createTelegramPlatformAdapter();delete window.Telegram;a.init();
 const release=a.bindBackButton(()=>{});assert.equal(a.getBackButtonSnapshot(),false);assert.equal(e.timers.size,1);
 window.Telegram={WebApp:e.api};e.tick();assert.equal(a.getBackButtonSnapshot(),true);assert.equal(e.back.size,1);
 release();a.dispose();assert.equal(e.timers.size,0);
 const f=environment();delete f.api.BackButton.offClick;const b=createTelegramPlatformAdapter();b.init();const cleanup=b.bindBackButton(()=>{});
 assert.equal(b.getBackButtonSnapshot(),false);f.api.BackButton.offClick=cb=>f.back.delete(cb);f.tick();assert.equal(b.getBackButtonSnapshot(),true);assert.equal(f.back.size,1);cleanup();b.dispose();
});

test('unknown visibility or rejected show does not change host context or leak callbacks',()=>{
 const e=environment();delete e.api.BackButton.isVisible;e.api.BackButton.show=()=>{};
 const a=createTelegramPlatformAdapter();a.init();const release=a.bindBackButton(()=>{});
 assert.equal(a.canUseBackButton,true);assert.equal(a.getBackButtonSnapshot(),false);assert.equal(e.back.size,1);
 e.api.BackButton.show=()=>{throw Error('client rejected')};e.tick();assert.equal(a.getBackButtonSnapshot(),false);assert.equal(e.back.size,0);
 e.api.BackButton.show=()=>{e.api.BackButton.isVisible=true};e.tick();assert.equal(a.getBackButtonSnapshot(),true);assert.equal(e.back.size,1);
 release();a.dispose();assert.equal(e.back.size,0);assert.equal(e.timers.size,0);
});

test('duplicate native dispatch in the same turn calls exit once and permits a later retry',async()=>{
 const e=environment();const a=createTelegramPlatformAdapter();a.init();let count=0;const release=a.bindBackButton(()=>count++);
 const callback=[...e.back][0];callback();callback();assert.equal(count,1);await Promise.resolve();callback();assert.equal(count,2);release();a.dispose();
});

test('replaced BackButton is rebound, old button is released, unowned client button is not assumed managed',()=>{
 const e=environment();e.api.BackButton.isVisible=true;const a=createTelegramPlatformAdapter();a.init();
 assert.equal(a.getBackButtonSnapshot(),false);assert.equal(e.api.BackButton.isVisible,true);
 const release=a.bindBackButton(()=>{});assert.equal(a.getBackButtonSnapshot(),true);
 const old=e.api.BackButton;const replacementCallbacks=new Set();
 e.api.BackButton={isVisible:false,show(){this.isVisible=true},hide(){this.isVisible=false},onClick(cb){replacementCallbacks.add(cb)},offClick(cb){replacementCallbacks.delete(cb)}};
 e.tick();assert.equal(e.back.size,0);assert.equal(old.isVisible,false);assert.equal(replacementCallbacks.size,1);assert.equal(a.getBackButtonSnapshot(),true);
 release();a.dispose();assert.equal(replacementCallbacks.size,0);
});

 test('Telegram context is reactive and independent of native Back visibility',()=>{
  const e=environment();delete window.Telegram;const a=createTelegramPlatformAdapter();a.init();let notices=0;
  const unsub=a.subscribeBackButton(()=>notices++);const release=a.bindBackButton(()=>{});
  assert.equal(a.getTelegramContextSnapshot(),false);
  delete e.api.BackButton.isVisible;e.api.BackButton.show=()=>{};window.Telegram={WebApp:e.api};e.tick();
  assert.equal(a.getTelegramContextSnapshot(),true);assert.equal(a.getBackButtonSnapshot(),false);assert.equal(notices,1);
  delete window.Telegram;e.tick();assert.equal(a.getTelegramContextSnapshot(),false);assert.equal(notices,2);
  release();unsub();a.dispose();assert.equal(e.timers.size,0);
 });
 test('SDK presence and unknown/malformed platform do not imply Telegram launch',()=>{
  for(const overrides of [{initData:'',platform:'unknown'},{initData:'',platform:'invented'},{initData:' ',platform:undefined},{ready:undefined}]){
   environment(overrides);const a=createTelegramPlatformAdapter();a.init();assert.equal(a.getTelegramContextSnapshot(),false);a.dispose();
  }
  for(const overrides of [{initData:'',platform:'ios'},{platform:'unknown',initData:'query_id=demo'},{BackButton:undefined},{version:'6.0'}]){
   environment(overrides);const a=createTelegramPlatformAdapter();a.init();assert.equal(a.getTelegramContextSnapshot(),true);a.dispose();assert.equal(a.getTelegramContextSnapshot(),false);
  }
 });
