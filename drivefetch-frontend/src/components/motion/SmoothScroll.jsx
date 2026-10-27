import { createContext, useContext, useEffect, useRef, useState, useCallback, useMemo } from 'react';
import Lenis from 'lenis';

/**
 * Smooth scrolling with Lenis, plus the scroll-driven bits that hang off it:
 *  - --df-progress on <html> (0..1) for the header progress bar
 *  - [data-parallax="0.2"] elements drift at a fraction of the scroll speed
 *
 * Lenis is skipped when the user prefers reduced motion; scrollTo() then falls
 * back to the browser's own scrolling so callers never need to care.
 */
const LenisContext = createContext({ lenis: null, lock: () => {}, unlock: () => {} });

export function useLenis() {
  return useContext(LenisContext).lenis;
}

/**
 * Named scroll locks (menu, dialogs, page transition). Scrolling is paused while
 * any lock is held, so overlapping overlays can't re-enable it early.
 */
export function useScrollLock() {
  const { lock, unlock } = useContext(LenisContext);
  return { lock, unlock };
}

/** scrollTo(target, { offset, immediate }) that works with or without Lenis. */
export function useScrollTo() {
  const lenis = useLenis();
  return useCallback((target, opts = {}) => {
    const { offset = 0, immediate = false } = opts;
    if (lenis) {
      lenis.scrollTo(target, { offset, immediate, duration: immediate ? 0 : 1.3, force: true });
      return;
    }
    let top = 0;
    if (typeof target === 'number') top = target;
    else {
      const el = typeof target === 'string' ? document.querySelector(target) : target;
      if (!el) return;
      top = el.getBoundingClientRect().top + window.scrollY;
    }
    window.scrollTo({ top: top + offset, behavior: immediate ? 'auto' : 'smooth' });
  }, [lenis]);
}

function prefersReducedMotion() {
  return typeof window !== 'undefined' && window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;
}

export default function SmoothScroll({ children }) {
  const [lenis, setLenis] = useState(null);
  const rafRef = useRef(0);
  const locks = useRef(new Set());
  const lenisRef = useRef(null);

  const apply = useCallback(() => {
    const locked = locks.current.size > 0;
    document.body.style.overflow = locked ? 'hidden' : '';
    if (lenisRef.current) {
      if (locked) lenisRef.current.stop();
      else lenisRef.current.start();
    }
  }, []);
  const lock = useCallback((id) => { locks.current.add(id); apply(); }, [apply]);
  const unlock = useCallback((id) => { locks.current.delete(id); apply(); }, [apply]);

  useEffect(() => {
    const root = document.documentElement;
    let instance = null;

    if (!prefersReducedMotion()) {
      instance = new Lenis({
        duration: 1.15,
        easing: (t) => Math.min(1, 1.001 - Math.pow(2, -10 * t)),
        smoothWheel: true,
        wheelMultiplier: 1,
        touchMultiplier: 1.4,
      });
      const loop = (time) => {
        instance.raf(time);
        rafRef.current = requestAnimationFrame(loop);
      };
      rafRef.current = requestAnimationFrame(loop);
      lenisRef.current = instance;
      setLenis(instance);
      apply();
    }

    // Scroll-linked effects. Native scroll events fire with or without Lenis.
    let ticking = false;
    const update = () => {
      ticking = false;
      const max = Math.max(1, root.scrollHeight - window.innerHeight);
      const y = window.scrollY;
      root.style.setProperty('--df-progress', String(Math.min(1, Math.max(0, y / max))));
      if (prefersReducedMotion()) return;
      const vh = window.innerHeight;
      document.querySelectorAll('[data-parallax]').forEach((el) => {
        const speed = parseFloat(el.getAttribute('data-parallax')) || 0;
        const rect = el.getBoundingClientRect();
        if (rect.bottom < -200 || rect.top > vh + 200) return;
        const center = rect.top + rect.height / 2 - vh / 2;
        const prev = parseFloat(el.dataset.parallaxY || '0');
        // rect includes the transform applied last frame, so take it back out first.
        const next = -(center - prev) * speed;
        el.dataset.parallaxY = String(next);
        el.style.transform = `translate3d(0, ${next.toFixed(1)}px, 0)`;
      });
    };
    const onScroll = () => {
      if (!ticking) {
        ticking = true;
        requestAnimationFrame(update);
      }
    };
    window.addEventListener('scroll', onScroll, { passive: true });
    window.addEventListener('resize', onScroll);
    update();

    return () => {
      cancelAnimationFrame(rafRef.current);
      window.removeEventListener('scroll', onScroll);
      window.removeEventListener('resize', onScroll);
      instance?.destroy();
      lenisRef.current = null;
      setLenis(null);
    };
  }, []);

  const value = useMemo(() => ({ lenis, lock, unlock }), [lenis, lock, unlock]);
  return <LenisContext.Provider value={value}>{children}</LenisContext.Provider>;
}
