import { useEffect } from 'react';

/**
 * Intro loader.
 *
 * The red screen, counter and logo are plain HTML in index.html (#df-splash) so
 * they paint before any JavaScript runs; CSS counts up to ~86% on its own.
 * Once the app and the first page have rendered (and fonts are in), this:
 *   1. finishes the count to 100,
 *   2. flies the logo from the centre into the header logo's exact spot,
 *      cross-fading white to red as it lands,
 *   3. lifts the red panel away, and switches page reveals on (html.df-ready).
 *
 * First visit in a tab holds the intro for at least ~1.4s so it reads as a
 * deliberate moment; later reloads in the same tab keep it short.
 */
const FIRST_VISIT_MS = 1400;
const REPEAT_VISIT_MS = 300;
const FONT_WAIT_CAP_MS = 1500;
const COUNT_FINISH_MS = { first: 520, repeat: 260 };
const FLIGHT_MS = { first: 1050, repeat: 850 };

function readSeen() {
  try { return sessionStorage.getItem('df-splash-seen') === '1'; } catch { return false; }
}
function markSeen() {
  try { sessionStorage.setItem('df-splash-seen', '1'); } catch { /* storage blocked */ }
}

function finishIntro() {
  const root = document.documentElement;
  root.classList.add('df-ready');
  root.classList.remove('df-loading');
}

/** Remove the splash immediately (used when the app hits a fatal error). */
export function dismissSplash() {
  if (typeof document === 'undefined') return;
  document.getElementById('df-splash')?.remove();
  finishIntro();
}

const easeOutCubic = (t) => 1 - Math.pow(1 - t, 3);

export default function SplashScreen() {
  useEffect(() => {
    const el = document.getElementById('df-splash');
    if (!el) {
      finishIntro();
      return undefined;
    }

    let cancelled = false;
    let raf = 0;
    const timers = [];
    const delay = (ms) => new Promise((resolve) => { timers.push(setTimeout(resolve, ms)); });
    const reduce = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;

    const seen = readSeen();
    const minMs = seen ? REPEAT_VISIT_MS : FIRST_VISIT_MS;
    const countMs = seen ? COUNT_FINISH_MS.repeat : COUNT_FINISH_MS.first;
    const flightMs = seen ? FLIGHT_MS.repeat : FLIGHT_MS.first;
    const elapsed = performance.now();
    const fontsReady = document.fonts?.ready
      ? Promise.race([document.fonts.ready, delay(FONT_WAIT_CAP_MS)])
      : Promise.resolve();

    // Take the counter over from CSS and run it to 100.
    const finishCount = () => new Promise((resolve) => {
      const current = parseInt(getComputedStyle(el).getPropertyValue('--p'), 10) || 0;
      el.style.animation = 'none';
      el.style.setProperty('--p', String(current));
      if (reduce) {
        el.style.setProperty('--p', '100');
        resolve();
        return;
      }
      const start = performance.now();
      const step = (now) => {
        const t = Math.min(1, (now - start) / countMs);
        el.style.setProperty('--p', String(Math.round(current + (100 - current) * easeOutCubic(t))));
        if (t < 1) raf = requestAnimationFrame(step);
        else resolve();
      };
      raf = requestAnimationFrame(step);
    });

    const fly = () => {
      const logo = el.querySelector('.df-s-logo');
      const target = document.getElementById('df-header-logo');
      const targetRect = target?.getBoundingClientRect();
      const canFly = !reduce && logo && targetRect && targetRect.width > 0 && targetRect.bottom > 0;

      if (canFly) {
        // Pin the logo where it is in plain pixels, then transform it onto the header logo.
        const from = logo.getBoundingClientRect();
        logo.style.animation = 'none';
        logo.style.left = `${from.left}px`;
        logo.style.top = `${from.top}px`;
        logo.style.width = `${from.width}px`;
        logo.style.transform = 'none';
        void logo.offsetWidth; // commit the pinned position before animating
        const scale = targetRect.width / from.width;
        logo.style.transition = `transform ${flightMs}ms cubic-bezier(.76, 0, .24, 1)`;
        el.querySelector('.df-s-bg')?.style.setProperty('transition-duration', `${flightMs - 50}ms`);
        logo.style.transform = `translate3d(${targetRect.left - from.left}px, ${targetRect.top - from.top}px, 0) scale(${scale})`;
      } else if (logo) {
        logo.style.transition = 'opacity .4s ease';
        logo.style.opacity = '0';
      }

      el.classList.add('df-out');
      document.documentElement.classList.add('df-ready'); // page reveals start as the panel lifts
      markSeen();
      timers.push(setTimeout(() => {
        // Swap the flown logo for the real header logo in the same frame, with no fade.
        const headerLogo = document.getElementById('df-header-logo');
        if (headerLogo) headerLogo.style.transition = 'none';
        document.documentElement.classList.remove('df-loading');
        el.remove();
        requestAnimationFrame(() => requestAnimationFrame(() => { if (headerLogo) headerLogo.style.transition = ''; }));
      }, canFly ? flightMs + 30 : 650));
    };

    Promise.all([fontsReady, delay(Math.max(0, minMs - elapsed))])
      .then(() => (cancelled ? null : finishCount()))
      .then(() => (cancelled ? null : delay(reduce ? 0 : seen ? 60 : 160)))
      .then(() => { if (!cancelled) fly(); });

    return () => {
      cancelled = true;
      cancelAnimationFrame(raf);
      timers.forEach(clearTimeout);
    };
  }, []);

  return null;
}
