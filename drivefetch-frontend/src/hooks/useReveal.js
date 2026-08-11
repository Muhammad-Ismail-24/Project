import { useEffect, useRef } from 'react';

// Blueprint §5/§14 reveal hook.
//
// Observes the returned ref with an IntersectionObserver and toggles the
// `.is-visible` class directly on the DOM node when it crosses ~15% into view.
// One-shot by default (unobserves after first reveal). It NEVER stores
// visibility in React state, so revealing an element never re-renders its
// parent — no per-element state, per §14.
export default function useReveal({ once = true, threshold = 0.15 } = {}) {
  const ref = useRef(null);

  useEffect(() => {
    const node = ref.current;
    if (!node) return undefined;

    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            entry.target.classList.add('is-visible');
            if (once) observer.unobserve(entry.target);
          } else if (!once) {
            entry.target.classList.remove('is-visible');
          }
        });
      },
      { threshold }
    );

    observer.observe(node);
    return () => observer.disconnect();
  }, [once, threshold]);

  return ref;
}
