import { useEffect, useRef, useState, type RefObject } from 'react';

export const reducedMotion = () => typeof window !== 'undefined' && !!window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;

/** Vibrație scurtă (dacă există și nu e redus mișcarea). */
export function haptic(ms = 12) { try { if (!reducedMotion()) navigator.vibrate?.(ms); } catch { /* */ } }

/**
 * Swipe pe orizontală pe un element (doar touch). Nu blochează derularea verticală:
 * gestul se „blochează” pe X doar după ce mișcarea e clar orizontală.
 */
export function useSwipeX(ref: RefObject<HTMLElement | null>, onSwipe: (dir: 1 | -1) => void, threshold = 72) {
  const cb = useRef(onSwipe); useEffect(() => { cb.current = onSwipe; });
  useEffect(() => {
    const el = ref.current; if (!el) return;
    let x0 = 0, y0 = 0, dx = 0, lock: 'x' | 'y' | null = null;
    const start = (e: TouchEvent) => { x0 = e.touches[0].clientX; y0 = e.touches[0].clientY; dx = 0; lock = null; };
    const move = (e: TouchEvent) => {
      const mx = e.touches[0].clientX - x0, my = e.touches[0].clientY - y0;
      if (!lock && (Math.abs(mx) > 10 || Math.abs(my) > 10)) lock = Math.abs(mx) > Math.abs(my) * 1.4 ? 'x' : 'y';
      if (lock !== 'x') return;
      dx = mx;
      el.style.transform = `translateX(${Math.max(-110, Math.min(110, dx)) * 0.6}px)`;
      el.style.transition = 'none';
      el.dataset.swipe = dx > threshold ? 'right' : dx < -threshold ? 'left' : '';
    };
    const end = () => {
      if (lock === 'x' && Math.abs(dx) > threshold) { haptic(); cb.current(dx > 0 ? 1 : -1); }
      el.style.transition = 'transform .25s cubic-bezier(.2,1.2,.4,1)'; el.style.transform = ''; el.dataset.swipe = '';
      lock = null;
    };
    el.addEventListener('touchstart', start, { passive: true });
    el.addEventListener('touchmove', move, { passive: true });
    el.addEventListener('touchend', end); el.addEventListener('touchcancel', end);
    return () => { el.removeEventListener('touchstart', start); el.removeEventListener('touchmove', move); el.removeEventListener('touchend', end); el.removeEventListener('touchcancel', end); };
  }, [ref, threshold]);
}

/** Trage în jos pentru a închide (sheet). Se activează doar când conținutul e derulat sus. */
export function useSwipeDownClose(ref: RefObject<HTMLElement | null>, scrollRef: RefObject<HTMLElement | null>, onClose: () => void) {
  const cb = useRef(onClose); useEffect(() => { cb.current = onClose; });
  useEffect(() => {
    const el = ref.current; if (!el) return;
    let y0 = 0, dy = 0, active = false;
    const start = (e: TouchEvent) => { y0 = e.touches[0].clientY; dy = 0; active = (scrollRef.current?.scrollTop ?? 0) <= 0; };
    const move = (e: TouchEvent) => {
      if (!active) return;
      dy = e.touches[0].clientY - y0;
      if (dy <= 0) { el.style.transform = ''; return; }
      el.style.transition = 'none'; el.style.transform = `translateY(${dy}px)`;
    };
    const end = () => {
      if (!active) return;
      el.style.transition = 'transform .22s ease-out';
      if (dy > 110) { el.style.transform = 'translateY(100%)'; haptic(); setTimeout(() => cb.current(), reducedMotion() ? 0 : 180); }
      else el.style.transform = '';
      active = false;
    };
    el.addEventListener('touchstart', start, { passive: true });
    el.addEventListener('touchmove', move, { passive: true });
    el.addEventListener('touchend', end);
    return () => { el.removeEventListener('touchstart', start); el.removeEventListener('touchmove', move); el.removeEventListener('touchend', end); };
  }, [ref, scrollRef]);
}

/** Pull-to-refresh pe containerul de derulare (#bp-scroll). */
export function usePullToRefresh(ref: RefObject<HTMLElement | null>, onRefresh: () => void) {
  const [pull, setPull] = useState(0);
  const cb = useRef(onRefresh); useEffect(() => { cb.current = onRefresh; });
  useEffect(() => {
    const el = ref.current; if (!el) return;
    let y0 = 0, x0 = 0, active = false, d = 0;
    const start = (e: TouchEvent) => { active = el.scrollTop <= 0; y0 = e.touches[0].clientY; x0 = e.touches[0].clientX; d = 0; };
    const move = (e: TouchEvent) => {
      if (!active) return;
      const dy = e.touches[0].clientY - y0, dx = Math.abs(e.touches[0].clientX - x0);
      if (dy <= 0 || dx > dy) { if (d) { d = 0; setPull(0); } return; }
      d = Math.min(120, dy * 0.5); setPull(d);
    };
    const end = () => { if (active && d >= 70) { haptic(18); cb.current(); } active = false; d = 0; setPull(0); };
    el.addEventListener('touchstart', start, { passive: true });
    el.addEventListener('touchmove', move, { passive: true });
    el.addEventListener('touchend', end);
    return () => { el.removeEventListener('touchstart', start); el.removeEventListener('touchmove', move); el.removeEventListener('touchend', end); };
  }, [ref]);
  return pull;
}

/** Număr animat (count-up), fără animație la reduced-motion. */
export function useCountUp(target: number, ms = 700) {
  const [v, setV] = useState(target);
  const from = useRef(target);
  useEffect(() => {
    if (reducedMotion() || !Number.isFinite(target)) { from.current = target; const id = requestAnimationFrame(() => setV(target)); return () => cancelAnimationFrame(id); }
    const a = from.current, t0 = performance.now();
    let id = 0;
    const tick = (t: number) => {
      const k = Math.min(1, (t - t0) / ms), e = 1 - Math.pow(1 - k, 3);
      setV(a + (target - a) * e);
      if (k < 1) id = requestAnimationFrame(tick); else from.current = target;
    };
    id = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(id);
  }, [target, ms]);
  return v;
}
