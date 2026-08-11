import { useEffect, useRef } from 'react';

// Observes the returned ref and toggles the `.is-visible` class directly on
// the DOM node when it crosses ~15% into view. Never touches React state, so
// it never triggers a re-render of the observed subtree.
export default function useReveal({ once = true, threshold = 0.15 } = {}) {
  const ref = useRef(null);

  useEffect(() => {
    const node = ref.current;
    if (!node) return;

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
