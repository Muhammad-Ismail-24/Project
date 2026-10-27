import { useEffect, useRef } from 'react';

/**
 * Focus management for overlays: moves focus into the dialog when it opens,
 * returns it to the trigger when it closes, and closes on Escape.
 */
export default function useDialog(open, onClose) {
  const ref = useRef(null);
  const onCloseRef = useRef(onClose);
  onCloseRef.current = onClose;

  useEffect(() => {
    if (!open) return undefined;
    const previous = document.activeElement;
    const node = ref.current;
    const target = node?.querySelector('[data-autofocus]') || node?.querySelector('button, a[href], input, select, textarea');
    target?.focus({ preventScroll: true });

    const onKey = (e) => {
      if (e.key === 'Escape') {
        e.stopPropagation();
        onCloseRef.current?.();
      }
      if (e.key === 'Tab' && node) {
        const items = Array.from(node.querySelectorAll('button:not([disabled]), a[href], input:not([disabled]), select, textarea'))
          .filter((el) => el.offsetParent !== null);
        if (!items.length) return;
        const first = items[0];
        const last = items[items.length - 1];
        if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
        else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
      }
    };
    node?.addEventListener('keydown', onKey);
    return () => {
      node?.removeEventListener('keydown', onKey);
      if (previous && typeof previous.focus === 'function') previous.focus({ preventScroll: true });
    };
  }, [open]);

  return ref;
}
