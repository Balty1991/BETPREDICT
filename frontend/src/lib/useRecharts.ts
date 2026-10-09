import { useEffect, useState } from 'react';

export type Recharts = typeof import('recharts');
let mod: Recharts | null = null;
let pending: Promise<Recharts> | null = null;

/** Încarcă recharts doar când e nevoie (`enabled`), când browserul e liber. */
export function useRecharts(enabled = true): Recharts | null {
  const [m, setM] = useState<Recharts | null>(mod);
  useEffect(() => {
    if (m || !enabled) return;
    let alive = true;
    const start = () => { pending ??= import('recharts'); pending.then((x) => { mod = x; if (alive) setM(x); }); };
    const w = window as Window & { requestIdleCallback?: (cb: () => void, o?: { timeout: number }) => number; cancelIdleCallback?: (id: number) => void };
    const id = w.requestIdleCallback ? w.requestIdleCallback(start, { timeout: 800 }) : window.setTimeout(start, 50);
    return () => { alive = false; if (w.cancelIdleCallback) w.cancelIdleCallback(id); else window.clearTimeout(id); };
  }, [m, enabled]);
  return m;
}
