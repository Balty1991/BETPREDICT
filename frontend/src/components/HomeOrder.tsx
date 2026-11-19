import { useState } from 'react';
import { ArrowUp, ArrowDown, SlidersHorizontal, RotateCcw } from 'lucide-react';
import { Sheet } from './kit';

/** Secțiunile de pe Acasă (brief-ul zilei). */
export type HomeSection = 'brief' | 's10' | 'pyramid' | 'long' | 'bank';
const DEFAULT: HomeSection[] = ['brief', 's10', 'pyramid', 'long', 'bank'];
const LABEL: Record<HomeSection, string> = {
  brief: 'Rezumatul analistului', s10: 'Biletul de cotă ~10', pyramid: 'Piramida cotă 2', long: 'Bilete lungi', bank: 'Banca',
};
const KEY = 'bp.home.order.v3'; // v3: Acasă = brief-ul zilei (cele trei produse de bază)

function read(): HomeSection[] {
  try {
    const v = JSON.parse(localStorage.getItem(KEY) || 'null') as HomeSection[] | null;
    if (!Array.isArray(v)) return DEFAULT;
    const ok = v.filter((x) => DEFAULT.includes(x));
    return [...ok, ...DEFAULT.filter((x) => !ok.includes(x))];
  } catch { return DEFAULT; }
}

export function useHomeOrder() {
  const [order, set] = useState<HomeSection[]>(read);
  const setOrder = (o: HomeSection[]) => { set(o); try { localStorage.setItem(KEY, JSON.stringify(o)); } catch { /* stocare indisponibilă */ } };
  return [order, setOrder] as const;
}

export function HomeOrderButton({ order, onChange }: { order: HomeSection[]; onChange: (o: HomeSection[]) => void }) {
  const [open, setOpen] = useState(false);
  const mv = (i: number, d: number) => { const o = [...order]; const j = i + d; if (j < 0 || j >= o.length) return; [o[i], o[j]] = [o[j], o[i]]; onChange(o); };
  return (
    <>
      <button type="button" className="home-order-btn" onClick={() => setOpen(true)}><SlidersHorizontal className="h-3.5 w-3.5" />Ordinea secțiunilor</button>
      <Sheet open={open} onClose={() => setOpen(false)} title="Ordinea secțiunilor" subtitle="Se salvează pe acest dispozitiv.">
        <ol className="space-y-1.5">
          {order.map((k, i) => (
            <li key={k} className="flex items-center gap-2 rounded-xl border bg-[hsl(var(--elevated))] px-3 py-1.5">
              <span className="num w-5 text-xs text-muted-foreground">{i + 1}</span>
              <span className="flex-1 text-sm font-semibold">{LABEL[k]}</span>
              <button type="button" className="btn btn-ghost h-10 w-10 p-0" disabled={i === 0} onClick={() => mv(i, -1)} aria-label={`Mută „${LABEL[k]}” mai sus`}><ArrowUp className="h-4 w-4" /></button>
              <button type="button" className="btn btn-ghost h-10 w-10 p-0" disabled={i === order.length - 1} onClick={() => mv(i, 1)} aria-label={`Mută „${LABEL[k]}” mai jos`}><ArrowDown className="h-4 w-4" /></button>
            </li>
          ))}
        </ol>
        <button type="button" className="btn btn-ghost mt-3 text-xs" onClick={() => onChange(DEFAULT)}><RotateCcw className="h-4 w-4" />Ordinea implicită</button>
      </Sheet>
    </>
  );
}
