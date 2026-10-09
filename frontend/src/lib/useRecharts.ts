import { useEffect, useState } from 'react';

type Recharts = typeof import('recharts');
let mod: Recharts | null = null;
let pending: Promise<Recharts> | null = null;

/** Încarcă recharts după primul render: textul și KPI-urile apar imediat, graficele vin după. */
export function useRecharts(): Recharts | null {
  const [m, setM] = useState<Recharts | null>(mod);
  useEffect(() => {
    if (m) return;
    let alive = true;
    // graficele sunt sub fold: le încărcăm după ce pagina e afișată și browserul e liber
    const start = () => { pending ??= import('recharts'); pending.then((x) => { mod = x; if (alive) setM(x); }); };
    const w = window as Window & { requestIdleCallback?: (cb: () => void, o?: { timeout: number }) => number };
    const t = window.setTimeout(() => (w.requestIdleCallback ? w.requestIdleCallback(start, { timeout: 1500 }) : start()), 1200);
    return () => { alive = false; window.clearTimeout(t); };
  }, [m]);
  return m;
}
