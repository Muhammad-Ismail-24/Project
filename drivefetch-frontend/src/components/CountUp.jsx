import React, { useEffect, useRef, useState } from 'react';

// Animated count-up stat. Starts when it scrolls into view (IntersectionObserver,
// one-shot), eases out over `duration`, and respects prefers-reduced-motion by
// snapping straight to the final value. Ref/rAF driven — no per-frame React
// state above the canvas is involved (this lives in normal page DOM).
export default function CountUp({
  end,
  duration = 1600,
  prefix = '',
  suffix = '',
  decimals = 0,
  className = '',
}) {
  const ref = useRef(null);
  const started = useRef(false);
  const [val, setVal] = useState(0);

  useEffect(() => {
    const node = ref.current;
    if (!node) return undefined;

    const reduce =
      typeof window !== 'undefined' &&
      window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;
    if (reduce) {
      setVal(end);
      return undefined;
    }

    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (!entry.isIntersecting || started.current) return;
          started.current = true;
          const t0 = performance.now();
          const tick = (t) => {
            const p = Math.min((t - t0) / duration, 1);
            const eased = 1 - Math.pow(1 - p, 3); // easeOutCubic
            setVal(end * eased);
            if (p < 1) requestAnimationFrame(tick);
            else setVal(end);
          };
          requestAnimationFrame(tick);
          observer.unobserve(entry.target);
        });
      },
      { threshold: 0.4 }
    );

    observer.observe(node);
    return () => observer.disconnect();
  }, [end, duration]);

  const display = decimals > 0 ? val.toFixed(decimals) : Math.round(val).toLocaleString();

  return (
    <span ref={ref} className={className}>
      {prefix}{display}{suffix}
    </span>
  );
}
