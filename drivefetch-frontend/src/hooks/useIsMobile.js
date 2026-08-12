import { useState, useEffect } from 'react';

// Blueprint §9 — the mobile/desktop branch switch.
//
// matchMedia at the < 768px breakpoint (767.98px avoids the fractional-viewport
// gap). SSR-safe: guards `window` and assumes desktop on the server. This DOES
// use React state — deliberately: the boolean must flip a real render so the
// experience can branch (different camera config / quality), per §9. It is NOT
// a per-frame value, so it does not violate the Core Performance Rule. The
// matchMedia `change` event only fires when the query result actually flips, so
// there is no resize render-storm.
const QUERY = '(max-width: 767.98px)';

function getMatch() {
  if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') {
    return false;
  }
  return window.matchMedia(QUERY).matches;
}

export default function useIsMobile() {
  const [isMobile, setIsMobile] = useState(getMatch);

  useEffect(() => {
    if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') {
      return undefined;
    }
    const mql = window.matchMedia(QUERY);
    const onChange = (e) => setIsMobile(e.matches);
    // Reconcile in case the viewport changed between initial render and effect.
    setIsMobile(mql.matches);
    mql.addEventListener('change', onChange);
    return () => mql.removeEventListener('change', onChange);
  }, []);

  return isMobile;
}
