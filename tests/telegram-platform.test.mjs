import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import ts from 'typescript';

const source = readFileSync(new URL('../src/platform/telegram/TelegramPlatformAdapter.ts', import.meta.url), 'utf8');
const js = ts.transpileModule(source, { compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ESNext } }).outputText;
const { createTelegramPlatformAdapter } = await import(`data:text/javascript;base64,${Buffer.from(js).toString('base64')}`);

function environment(overrides = {}) {
  const root = { dataset: {}, style: new Map() };
  root.style.setProperty = root.style.set.bind(root.style);
  root.style.removeProperty = root.style.delete.bind(root.style);
  const events = new Map(), back = new Set();
  const api = {
    initData: 'test', platform: 'ios', version: '8.0', ready() {}, expand() {},
    viewportHeight: 600, viewportStableHeight: 667,
    safeAreaInset: { top: 59, bottom: 34 }, contentSafeAreaInset: { top: 45 },
    onEvent(name, callback) { if (!events.has(name)) events.set(name, new Set()); events.get(name).add(callback); },
    offEvent(name, callback) { events.get(name)?.delete(callback); },
    requestFullscreen() {},
    BackButton: { show() {}, hide() {}, onClick(cb) { back.add(cb); }, offClick(cb) { back.delete(cb); } },
    ...overrides,
  };
  globalThis.window = Object.assign(new EventTarget(), { innerHeight: 667, visualViewport: Object.assign(new EventTarget(), { height: 500 }), Telegram: { WebApp: api } });
  globalThis.document = Object.assign(new EventTarget(), { documentElement: root });
  return { root, events, back, api, emit(name, data) { for (const cb of events.get(name) ?? []) cb(data); } };
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

test('fullscreen success is event driven; failure is recorded; UI 4.5 clearance retained', () => {
  const e = environment(); const a = createTelegramPlatformAdapter(); a.init();
  assert.equal(a.requestFullscreen(), true);
  assert.equal(e.root.dataset.telegramFullscreen, 'false');
  e.api.isFullscreen = true; e.emit('fullscreenChanged');
  assert.equal(e.root.style.get('--anatomai-top-clearance'), '104px');
  assert.equal(e.root.style.get('--tg-safe-top'), '59px');
  e.emit('fullscreenFailed', { error: 'UNSUPPORTED' });
  assert.equal(e.root.dataset.telegramFullscreenError, 'UNSUPPORTED');
  e.api.isFullscreen = false; e.emit('fullscreenChanged');
  assert.equal(e.root.style.get('--anatomai-top-clearance'), '0px');
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
