import { Spark } from './dash';
import type { Ticket } from '@/lib/types';
import { cn } from '@/lib/utils';

/** Profitul cumulat (1u pe bilet) pe tip de bilet, ultimele 14 zile: o linie neon pe fiecare tip. */
export function KindSparks<K extends string>({ tickets, kinds, kindOf }: { tickets: Ticket[]; kinds: ReadonlyArray<readonly [K, string]>; kindOf: (t: Ticket) => K }) {
  const days = [...new Set(tickets.map((t) => t.date ?? '').filter(Boolean))].sort().slice(-14);
  if (days.length < 2) return null;
  const rows = kinds.map(([k, label]) => {
    const ts = tickets.filter((t) => kindOf(t) === k && days.includes(t.date ?? '') && (t.status === 'won' || t.status === 'lost'));
    let cum = 0;
    const vals = days.map((d) => { for (const t of ts.filter((x) => x.date === d)) cum += t.status === 'won' ? (t.total_odds ?? 1) - 1 : -1; return cum; });
    return { k, label, n: ts.length, won: ts.filter((t) => t.status === 'won').length, vals, roi: ts.length ? cum / ts.length : 0 };
  }).filter((r) => r.n >= 3);
  if (!rows.length) return null;
  return (
    <div className="scrollbar-none -mx-4 flex gap-2 overflow-x-auto px-4 pb-1" aria-label="Profit pe tip de bilet, 14 zile">
      {rows.map((r) => (
        <div key={r.k} className="spark-card w-40 shrink-0 rounded-2xl border p-2.5">
          <div className="flex items-baseline justify-between gap-1"><span className="truncate text-[11px] font-bold">{r.label.replace(/^⭐\s*/, '')}</span>
            <span className={cn('num text-[11px] font-extrabold', r.roi >= 0 ? 'text-win' : 'text-loss')}>{r.roi >= 0 ? '+' : ''}{Math.round(r.roi * 100)}%</span></div>
          <Spark values={r.vals} height={36} label={`${r.label}: profit cumulat`} className="mt-1" />
          <div className="text-[10px] text-muted-foreground">{r.won}/{r.n} câștigate</div>
        </div>
      ))}
    </div>
  );
}
