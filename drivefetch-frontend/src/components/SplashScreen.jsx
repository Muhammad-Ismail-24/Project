import { useEffect } from 'react';

/**
 * SplashScreen
 *
 * The red splash itself is plain HTML in index.html (#df-splash) so it paints
 * before any JavaScript has loaded. This component runs once the layout and the
 * first page have rendered, waits for the web fonts (so the page doesn't reflow
 * under the reveal), then plays the exit: the logo lifts away and the red panel
 * wipes upward to reveal the page.
 *
 * First visit in a tab: the splash stays for at least ~1.1s so it reads as a
 * deliberate moment. Later full reloads in the same tab: ~0.35s.
 */
const FIRST_VISIT_MS = 1100;
const REPEAT_VISIT_MS = 350;
const FONT_WAIT_CAP_MS = 1500;
const EXIT_MS = 800;

function readSeen() {
  try { return sessionStorage.getItem('df-splash-seen') === '1'; } catch { return false; }
}
function markSeen() {
  try { sessionStorage.setItem('df-splash-seen', '1'); } catch { /* storage blocked */ }
}

/** Remove the splash immediately (used when the app hits a fatal error). */
export function dismissSplash() {
  const el = typeof document !== 'undefined' ? document.getElementById('df-splash') : null;
  if (el) el.remove();
}

export default function SplashScreen() {
  useEffect(() => {
    const el = document.getElementById('df-splash');
    if (!el) return undefined;

    let cancelled = false;
    const timers = [];
    const minMs = readSeen() ? REPEAT_VISIT_MS : FIRST_VISIT_MS;
    const elapsed = typeof performance !== 'undefined' ? performance.now() : 0;
    const wait = Math.max(0, minMs - elapsed);

    const delay = (ms) => new Promise((resolve) => { timers.push(setTimeout(resolve, ms)); });
    const fontsReady = typeof document !== 'undefined' && document.fonts && document.fonts.ready
      ? Promise.race([document.fonts.ready, delay(FONT_WAIT_CAP_MS)])
      : Promise.resolve();

    Promise.all([fontsReady, delay(wait)]).then(() => {
      if (cancelled) return;
      el.classList.add('df-out');
      markSeen();
      timers.push(setTimeout(() => { el.remove(); }, EXIT_MS));
    });

    return () => {
      cancelled = true;
      timers.forEach(clearTimeout);
    };
  }, []);

  return null;
}
