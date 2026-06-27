/**
 * useHasHover — returns true when the primary pointer device supports genuine
 * hover (mouse / trackpad).  Returns false for touch-only devices.
 *
 * Uses the CSS4 `(hover: hover)` media feature, which the browser resolves per
 * pointer capability, not per current interaction mode.  Defaults to true for
 * SSR environments or browsers that don't expose matchMedia (e.g. jsdom in
 * tests), so desktop hover behaviour is the safe fallback.
 */
import { useState, useEffect } from 'react';

export function useHasHover(): boolean {
  const [hasHover, setHasHover] = useState<boolean>(() => {
    if (typeof window === 'undefined' || !window.matchMedia) return true;
    return window.matchMedia('(hover: hover)').matches;
  });

  useEffect(() => {
    if (!window.matchMedia) return;
    const mq = window.matchMedia('(hover: hover)');
    const handler = (e: MediaQueryListEvent) => setHasHover(e.matches);
    mq.addEventListener('change', handler);
    return () => mq.removeEventListener('change', handler);
  }, []);

  return hasHover;
}
