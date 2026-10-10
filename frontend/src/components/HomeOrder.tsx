import { useState } from 'react';
import { ArrowUp, ArrowDown, SlidersHorizontal, RotateCcw } from 'lucide-react';
import { Sheet } from './kit';

export type HomeSection = 'hero' | 'tools' | 'pyramid' | 'tickets' | 'horizon' | 'rec' | 'mine' | 'generator' | 'past';
const DEFAULT: HomeSection[] = ['hero', 'tools', 'pyramid', 'tickets', 'horizon', 'rec', 'mine', 'generator', 'past'];
const LABEL: Record<HomeSection, string> = {
  hero: 'Pontul zilei', tools: 'Instrumente pro', pyramid: 'Piramida', tickets: 'Biletele Robotului (azi)', horizon: 'Bilete pe 7 zile',
  rec: 'Recomandările zilei', mine: 'Biletele mele', generator: 'Generator cu regulile tale', past: 'Bilete din zilele trecute',
};
const KEY = 'bp.home.order';

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
  const setOrder = (o: HomeSection[]) => { set(o); try { localStorage.setItem(KEY, JSON.stringify(o)); } catch { /* */ } };
  return [order, setOrder] as const;
}

export function HomeOrderButton({ order, onChange }: { order: HomeSection[]; onChange: (o: HomeSection[]) => void }) {
  const [open, setOpen] = useState(false);
  const mv = (i: number, d: number) => { const o = [...order]; const j = i + d; if (j < 0 || j >= o.length) return; [o[i], o[j]] = [o[j], o[i]]; onChange(o); };
  return (
    <>
      <button className="btn btn-outline text-xs" onClick={() => setOpen(true)}><SlidersHorizontal className="h-4 w-4" />Personalizează Acasă</button>
      <Sheet open={open} onClose={() => setOpen(false)} title="Ordinea secțiunilor" subtitle="Mută secțiunile în ordinea preferată. Se salvează pe acest dispozitiv.">
        <ol className="space-y-1.5">
          {order.map((k, i) => (
            <li key={k} className="flex items-center gap-2 rounded-xl border bg-[hsl(var(--elevated))] px-3 py-1.5">
              <span className="num w-5 text-xs text-muted-foreground">{i + 1}</span>
              <span className="flex-1 text-sm font-semibold">{LABEL[k]}</span>
              <button className="btn btn-ghost h-10 w-10 p-0" disabled={i === 0} onClick={() => mv(i, -1)} aria-label={`Mută „${LABEL[k]}” mai sus`}><ArrowUp className="h-4 w-4" /></button>
              <button className="btn btn-ghost h-10 w-10 p-0" disabled={i === order.length - 1} onClick={() => mv(i, 1)} aria-label={`Mută „${LABEL[k]}” mai jos`}><ArrowDown className="h-4 w-4" /></button>
            </li>
          ))}
        </ol>
        <button className="btn btn-ghost mt-3 text-xs" onClick={() => onChange(DEFAULT)}><RotateCcw className="h-4 w-4" />Ordinea implicită</button>
      </Sheet>
    </>
  );
}
