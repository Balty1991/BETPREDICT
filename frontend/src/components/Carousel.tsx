import { useCallback, useEffect, useRef, useState, type ReactNode } from 'react';
import { ChevronLeft, ChevronRight } from 'lucide-react';
import { cn } from '@/lib/utils';

/**
 * Rând orizontal cu scroll-snap care merge și pe desktop:
 * săgeți ‹ ›, tragere cu mouse-ul, rotița verticală → orizontal (doar cât rândul mai poate derula),
 * iar cu `grid` devine grilă pe ecrane late (lg+). Pe touch rămâne swipe nativ (nu interceptăm atingerile),
 * deci nu interferează cu app shell-ul #bp-scroll.
 */
export function Carousel({ children, className, grid = false, label }: { children: ReactNode; className?: string; grid?: boolean; label?: string }) {
  const ref = useRef<HTMLDivElement>(null);
  const [can, setCan] = useState({ l: false, r: false });

  const update = useCallback(() => {
    const el = ref.current; if (!el) return;
    setCan((p) => {
      const l = el.scrollLeft > 4, r = el.scrollLeft + el.clientWidth < el.scrollWidth - 4;
      return p.l === l && p.r === r ? p : { l, r };
    });
  }, []);

  useEffect(() => {
    const el = ref.current; if (!el) return;
    update();
    const ro = new ResizeObserver(update); ro.observe(el);
    el.addEventListener('scroll', update, { passive: true });
    const onWheel = (e: WheelEvent) => {
      if (e.ctrlKey || Math.abs(e.deltaX) >= Math.abs(e.deltaY)) return; // trackpad orizontal: nativ
      if (el.scrollWidth <= el.clientWidth + 4) return; // grilă / fără overflow → pagina derulează normal
      const max = el.scrollWidth - el.clientWidth;
      if ((e.deltaY < 0 && el.scrollLeft <= 0) || (e.deltaY > 0 && el.scrollLeft >= max - 1)) return; // la capăt → lasă pagina
      e.preventDefault();
      el.scrollBy({ left: e.deltaY * (e.deltaMode === 1 ? 32 : 1), behavior: 'auto' });
    };
    el.addEventListener('wheel', onWheel, { passive: false });
    // tragere cu mouse-ul (doar pointer de tip mouse; touch rămâne nativ)
    let down = false, moved = false, x0 = 0, s0 = 0;
    const onDown = (e: PointerEvent) => {
      if (e.pointerType !== 'mouse' || e.button !== 0 || el.scrollWidth <= el.clientWidth + 4) return;
      down = true; moved = false; x0 = e.clientX; s0 = el.scrollLeft;
    };
    const onMove = (e: PointerEvent) => {
      if (!down) return;
      const dx = e.clientX - x0;
      if (!moved && Math.abs(dx) > 6) { moved = true; el.style.scrollSnapType = 'none'; el.style.cursor = 'grabbing'; el.style.userSelect = 'none'; }
      if (moved) el.scrollLeft = s0 - dx;
    };
    const onUp = () => {
      if (!down) return; down = false;
      if (moved) {
        el.style.cursor = ''; el.style.userSelect = '';
        const left = el.scrollLeft; el.style.scrollSnapType = ''; el.scrollLeft = left;
        // reactivarea scroll-snap aliniază rândul la cel mai apropiat card
      }
    };
    const onClick = (e: MouseEvent) => { if (moved) { e.preventDefault(); e.stopPropagation(); moved = false; } };
    el.addEventListener('pointerdown', onDown);
    window.addEventListener('pointermove', onMove);
    window.addEventListener('pointerup', onUp);
    el.addEventListener('click', onClick, true);
    return () => {
      ro.disconnect(); el.removeEventListener('scroll', update); el.removeEventListener('wheel', onWheel);
      el.removeEventListener('pointerdown', onDown); window.removeEventListener('pointermove', onMove); window.removeEventListener('pointerup', onUp);
      el.removeEventListener('click', onClick, true);
    };
  }, [update]);

  const step = (dir: 1 | -1) => {
    const el = ref.current; if (!el) return;
    const card = el.firstElementChild as HTMLElement | null;
    el.scrollBy({ left: dir * Math.max(200, (card?.offsetWidth ?? el.clientWidth * 0.8) + 12), behavior: 'smooth' });
  };

  const arrow = 'carousel-arrow absolute top-1/2 z-10 hidden h-10 w-10 -translate-y-1/2 items-center justify-center rounded-full border bg-card/90 shadow-lg backdrop-blur transition-opacity hover:bg-card';
  return (
    <div className={cn('group/car relative', grid && 'carousel-grid-wrap')}>
      <div ref={ref} role="region" aria-label={label} className={cn('snap-row', grid && 'carousel-grid', className)}>{children}</div>
      <button type="button" aria-label="Înapoi" onClick={() => step(-1)} className={cn(arrow, '-left-2', !can.l && 'pointer-events-none opacity-0')}><ChevronLeft className="h-5 w-5" /></button>
      <button type="button" aria-label="Înainte" onClick={() => step(1)} className={cn(arrow, '-right-2', !can.r && 'pointer-events-none opacity-0')}><ChevronRight className="h-5 w-5" /></button>
    </div>
  );
}
