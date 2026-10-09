import { useEffect, useRef, useState, type ReactNode } from 'react';
import { useRecharts, type Recharts } from '@/lib/useRecharts';
import { Skeleton } from './kit';

/** Hook: devine `true` când elementul intră (aproape) în ecran. */
export function useInView<T extends HTMLElement>(rootMargin = '200px'): [React.RefObject<T | null>, boolean] {
  const ref = useRef<T>(null);
  const [vis, setVis] = useState(false);
  useEffect(() => {
    const el = ref.current;
    if (!el || vis) return;
    if (typeof IntersectionObserver === 'undefined') { setVis(true); return; }
    const io = new IntersectionObserver((es) => { if (es.some((e) => e.isIntersecting)) { setVis(true); io.disconnect(); } }, { rootMargin });
    io.observe(el);
    return () => io.disconnect();
  }, [rootMargin, vis]);
  return [ref, vis];
}

/** Grafic încărcat leneș: recharts se descarcă și se randează doar când graficul ajunge în ecran. */
export function LazyChart({ className, children }: { className?: string; children: (R: Recharts) => ReactNode }) {
  const [ref, vis] = useInView<HTMLDivElement>();
  const R = useRecharts(vis);
  return <div ref={ref} className={className}>{R && vis ? children(R) : <Skeleton className="h-full w-full" />}</div>;
}
