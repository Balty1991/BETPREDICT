import { useMemo, useState } from 'react';
import type { Ticket } from '@/lib/types';
import { ticketType } from '@/components/MyBank';
import { cn } from '@/lib/utils';

const MONTHS = ['ian', 'feb', 'mar', 'apr', 'mai', 'iun', 'iul', 'aug', 'sep', 'oct', 'nov', 'dec'];

/** Statistici: strategiile Robotului comparate lună de lună, la 1 unitate pe bilet. */
export function MonthlyCompare({ tickets }: { tickets: Ticket[] }) {
  const { months, rows } = useMemo(() => {
    const g = new Map<string, Map<string, { n: number; won: number; pl: number }>>();
    const ms = new Set<string>();
    for (const t of tickets) {
      if (t.status !== 'won' && t.status !== 'lost') continue;
      const m = (t.date ?? t.created_at ?? '').slice(0, 7);
      if (!m) continue;
      ms.add(m);
      const k = ticketType(t);
      const row = g.get(k) ?? new Map();
      const x = row.get(m) ?? { n: 0, won: 0, pl: 0 };
      x.n += 1; x.won += t.status === 'won' ? 1 : 0; x.pl += t.status === 'won' ? (t.total_odds ?? 1) - 1 : -1;
      row.set(m, x); g.set(k, row);
    }
    return { months: [...ms].sort(), rows: [...g.entries()] };
  }, [tickets]);
  const [m, setM] = useState<string | null>(null);
  if (!months.length) return null;
  const cur = m ?? months[months.length - 1];
  const list = rows.map(([k, r]) => [k, r.get(cur)] as const).filter(([, v]) => v).sort((a, b) => b[1]!.pl / b[1]!.n - a[1]!.pl / a[1]!.n);
  const label = (s: string) => `${MONTHS[Number(s.slice(5, 7)) - 1]} ${s.slice(2, 4)}`;
  return (
    <section className="card p-3.5" aria-label="Strategii pe luni">
      <div className="flex items-center justify-between gap-2">
        <h2 className="text-[15px] font-bold">Strategii pe luni</h2>
        <div className="flex gap-1 overflow-x-auto scrollbar-none">
          {months.map((x) => <button key={x} aria-pressed={x === cur} onClick={() => setM(x)} className={cn('press min-h-9 rounded-full border px-3 text-xs font-semibold', x === cur ? 'pill-on' : 'bg-card')}>{label(x)}</button>)}
        </div>
      </div>
      <ul className="mt-2 space-y-1.5">
        {list.map(([k, v]) => {
          const roi = v!.pl / v!.n;
          const w = Math.min(100, Math.abs(roi) * 100);
          return (
            <li key={k} className="text-xs">
              <div className="flex justify-between"><span className="font-semibold">{k}</span><span className="num text-muted-foreground">{v!.won}/{v!.n} · <b className={roi >= 0 ? 'text-win' : 'text-loss'}>{roi >= 0 ? '+' : ''}{(roi * 100).toFixed(0)}%</b></span></div>
              <div className="mt-0.5 h-1.5 overflow-hidden rounded-full bg-muted"><div className="bar-grow h-full rounded-full" style={{ width: `${Math.max(2, w)}%`, background: roi >= 0 ? 'hsl(var(--win))' : 'hsl(var(--loss))' }} /></div>
            </li>
          );
        })}
      </ul>
      <p className="mt-2 text-[11px] text-muted-foreground">Bilete decontate ale Robotului, ROI la 1 unitate pe bilet. Bara: mărimea ROI (până la ±100%).</p>
    </section>
  );
}
