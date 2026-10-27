import { useEffect } from 'react';

/**
 * Watches the whole document for [data-reveal] / [data-stagger] / .df-split
 * elements and adds .is-in once each scrolls into view. The CSS in index.css
 * does the actual animation, so pages only need to add the attribute.
 *
 * Motion is opt-in at runtime: html.df-motion is only added here, so if JS
 * fails or the user prefers reduced motion, content is simply visible.
 */
const SELECTOR = '[data-reveal], [data-stagger], .df-split';

export default function useAutoReveal() {
  useEffect(() => {
    const root = document.documentElement;
    const reduce = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;
    if (reduce || !('IntersectionObserver' in window)) {
      root.classList.remove('df-motion');
      return undefined;
    }
    root.classList.add('df-motion');

    // Elements waiting to be revealed. While a page transition holds reveals
    // (html.df-hold), visible elements stay pending and are re-checked on release.
    const pending = new Set();
    const io = new IntersectionObserver(
      (entries) => {
        if (root.classList.contains('df-hold')) return;
        for (const entry of entries) {
          if (entry.isIntersecting) {
            entry.target.classList.add('is-in');
            pending.delete(entry.target);
            io.unobserve(entry.target);
          }
        }
      },
      { rootMargin: '0px 0px -8% 0px', threshold: 0 },
    );
    let holding = root.classList.contains('df-hold');
    const holdWatcher = new MutationObserver(() => {
      const now = root.classList.contains('df-hold');
      if (holding && !now) {
        pending.forEach((el) => {
          if (!el.isConnected) { pending.delete(el); return; }
          io.unobserve(el);
          io.observe(el);
        });
      }
      holding = now;
    });
    holdWatcher.observe(root, { attributes: true, attributeFilter: ['class'] });

    const seen = new WeakSet();
    const prepStagger = (el) => {
      Array.from(el.children).forEach((child, i) => child.style.setProperty('--si', String(i)));
    };
    const track = (el) => {
      if (seen.has(el)) return;
      seen.add(el);
      if (el.hasAttribute('data-stagger')) prepStagger(el);
      pending.add(el);
      io.observe(el);
    };
    const scan = (node) => {
      if (node.nodeType !== 1) return;
      if (node.matches(SELECTOR)) track(node);
      node.querySelectorAll(SELECTOR).forEach(track);
    };

    scan(document.body);
    const mo = new MutationObserver((mutations) => {
      for (const m of mutations) {
        m.addedNodes.forEach(scan);
        // Stagger lists that gain children later (results streaming in)
        if (m.target.nodeType === 1 && m.target.hasAttribute?.('data-stagger')) prepStagger(m.target);
      }
    });
    mo.observe(document.body, { childList: true, subtree: true });

    return () => {
      io.disconnect();
      mo.disconnect();
      holdWatcher.disconnect();
    };
  }, []);
}
