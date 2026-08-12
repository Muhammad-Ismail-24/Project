import { useEffect } from 'react';
import { ScrollTrigger } from 'gsap/ScrollTrigger';

// ─────────────────────────────────────────────────────────────────────────────
// THE SCROLL BRIDGE (Blueprint §6) — the file v1 lacked.
//
// Scroll progress (0→1) is carried by a single module-level ref object. This is
// deliberate: the DOM side (Home) sets up the ScrollTrigger, while the canvas
// side (DrivingRig, mounted once in MainLayout) reads it every frame inside
// useFrame. Those two live in disjoint React subtrees; a shared module ref
// bridges them WITHOUT React context and WITHOUT any state.
//
// CORE PERFORMANCE RULE: this file contains NO useState / NO setState. The
// ScrollTrigger onUpdate writes ONLY to progressRef.current. Scroll progress
// never routes through React state, so it never re-renders the tree.
// ─────────────────────────────────────────────────────────────────────────────

export const progressRef = { current: 0 };

/**
 * Attach a scrubbed ScrollTrigger to `triggerRef` that writes scroll progress
 * (0→1) into the shared `progressRef`. Returns `{ progressRef }`.
 *
 * @param {React.RefObject<HTMLElement>} triggerRef  the Home journey container.
 * @param {{ enabled?: boolean }} [opts]  when `enabled` is false (e.g.
 *        prefers-reduced-motion, or non-Home routes) no trigger is created and
 *        progress is pinned at 0 — the car holds its landing pose.
 */
export function useScrollProgress(triggerRef, { enabled = true } = {}) {
  useEffect(() => {
    if (!enabled) {
      progressRef.current = 0;
      return undefined;
    }
    const el = triggerRef && triggerRef.current;
    if (!el) return undefined;

    const trigger = ScrollTrigger.create({
      trigger: el,
      start: 'top top',
      end: 'bottom bottom',
      scrub: 1,
      onUpdate: (self) => {
        // The ONLY write. No setState anywhere in this path.
        progressRef.current = self.progress;
      },
    });

    return () => {
      trigger.kill();
      progressRef.current = 0;
    };
  }, [triggerRef, enabled]);

  return { progressRef };
}
