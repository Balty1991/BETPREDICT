import { useEffect, useState, type ReactNode } from 'react';

type IdleWin = Window & { requestIdleCallback?: (cb: () => void, o?: { timeout: number }) => number; cancelIdleCallback?: (id: number) => void };

/** Randează conținutul sub fold după primul paint (când browserul e liber): împarte munca în sarcini mici. */
export function Deferred({ children, minHeight = 600 }: { children: ReactNode; minHeight?: number }) {
  const [ready, setReady] = useState(false);
  useEffect(() => {
    const w = window as IdleWin;
    if (w.requestIdleCallback && w.cancelIdleCallback) {
      const id = w.requestIdleCallback(() => setReady(true), { timeout: 1000 });
      return () => w.cancelIdleCallback!(id);
    }
    const t = window.setTimeout(() => setReady(true), 120);
    return () => window.clearTimeout(t);
  }, []);
  return ready ? <>{children}</> : <div style={{ minHeight }} aria-hidden="true" />;
}
