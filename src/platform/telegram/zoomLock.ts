/** Best-effort WKWebView zoom lock, scoped to ANATOMAI, never a blanket touch blocker. */
export function attachZoomLock(root: HTMLElement): () => void {
  type Point = { x: number; y: number; target: EventTarget | null };
  let start: Point | undefined;
  let moved = false;
  let lastTap: (Point & { at: number }) | undefined;
  const prevent = (event: Event) => { if (event.cancelable) event.preventDefault(); };
  const point = (touch: Touch, target: EventTarget | null): Point => ({ x: touch.clientX, y: touch.clientY, target });
  const distance = (a: Point, b: Point) => Math.hypot(a.x - b.x, a.y - b.y);
  const reset = () => { start = undefined; lastTap = undefined; moved = false; };
  const touchStart = (event: TouchEvent) => {
    if (event.touches.length > 1) { reset(); prevent(event); return; }
    start = event.touches[0] ? point(event.touches[0], event.target) : undefined;
    moved = false;
  };
  const touchMove = (event: TouchEvent) => {
    if (event.touches.length > 1) { reset(); prevent(event); return; }
    if (start && event.touches[0] && distance(start, point(event.touches[0], event.target)) > 12) moved = true;
  };
  const touchEnd = (event: TouchEvent) => {
    const previousStart = start;
    start = undefined;
    if (!previousStart || moved || event.touches.length || event.changedTouches.length !== 1) { lastTap = undefined; return; }
    const target = event.target as Element | null;
    // Native controls keep their clicks/focus; CSS touch-action handles their double tap.
    if (target?.closest?.('button, a, input, textarea, select, [role="button"], [contenteditable="true"]')) { lastTap = undefined; return; }
    const tap = point(event.changedTouches[0], event.target);
    const now = event.timeStamp;
    if (lastTap && lastTap.target === tap.target && now - lastTap.at < 280 && distance(lastTap, tap) < 24) {
      prevent(event);
      lastTap = undefined;
    } else lastTap = { ...tap, at: now };
  };
  const listeners: Array<[string, EventListener]> = [
    ['gesturestart', prevent], ['gesturechange', prevent], ['dblclick', prevent],
    ['touchstart', touchStart as EventListener], ['touchmove', touchMove as EventListener],
    ['touchend', touchEnd as EventListener], ['touchcancel', reset],
  ];
  for (const [name, listener] of listeners) root.addEventListener(name, listener, { passive: false });
  return () => { for (const [name, listener] of listeners) root.removeEventListener(name, listener); reset(); };
}
