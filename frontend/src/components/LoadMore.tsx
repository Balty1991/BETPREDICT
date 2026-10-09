import { useEffect, useRef } from 'react';
import { useInView } from './LazyChart';

/** Paginare incrementală: încarcă automat următoarea pagină când butonul ajunge în ecran (remontat cu `key` la fiecare pagină). */
export function LoadMore({ onMore, label = 'Arată mai multe' }: { onMore: () => void; label?: string }) {
  const [ref, vis] = useInView<HTMLDivElement>('400px');
  const cb = useRef(onMore);
  useEffect(() => { cb.current = onMore; });
  useEffect(() => { if (vis) cb.current(); }, [vis]);
  return <div ref={ref} className="text-center"><button className="btn btn-outline w-full md:w-auto" onClick={() => cb.current()}>{label}</button></div>;
}
