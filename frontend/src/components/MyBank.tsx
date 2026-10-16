import { useMemo } from 'react';
import { Spark } from '@/components/dash';
import type { Ticket } from '@/lib/types';

const lei = (x: number) => `${x > 0 ? '+' : ''}${x.toLocaleString('ro-RO', { maximumFractionDigits: 0 })} lei`;
const tone = (x: number) => (x > 0 ? 'text-win' : x < 0 ? 'text-loss' : '');

type Row = { day: string; stake: number; full: number };

/** Statistici › Bilete: evoluția banilor din biletele jucate de mine („Îl joc”, generator), zi de zi,
 *  la miza ta. */
export function MyBank({ tickets }: { tickets: Ticket[] }) {
  const rows = useMemo(() => {
    const out: Row[] = [];
    for (const t of tickets) {
      const stake = t.stake ?? 0;
      if (!stake || (t.status !== 'won' && t.status !== 'lost' && t.status !== 'void')) continue;
      const day = t.date ?? t.created_at?.slice(0, 10) ?? '';
      const full = t.status === 'won' ? stake * t.total_odds - stake : t.status === 'lost' ? -stake : 0;
      out.push({ day, stake, full });
    }
    return out.sort((a, b) => a.day.localeCompare(b.day));
  }, [tickets]);
  if (!rows.length) return <p className="text-sm text-muted-foreground">Încă nu ai bilete jucate decontate. Apasă „Îl joc” pe un bilet ca să-l urmărim.</p>;
  const days = [...new Set(rows.map((r) => r.day))];
  let acc = 0;
  const curve = days.map((d) => (acc += rows.filter((r) => r.day === d).reduce((a, r) => a + r.full, 0)));
  const staked = rows.reduce((a, r) => a + r.stake, 0);
  const profit = rows.reduce((a, r) => a + r.full, 0);
  return (
    <div className="space-y-3">
      <div className="grid grid-cols-3 gap-2 text-center">
        <div className="card p-2"><div className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground">Profit</div><div className={`num text-lg font-extrabold ${tone(profit)}`}>{lei(profit)}</div></div>
        <div className="card p-2"><div className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground">Mizat</div><div className="num text-lg font-extrabold">{staked.toLocaleString('ro-RO', { maximumFractionDigits: 0 })} lei</div></div>
        <div className="card p-2"><div className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground">ROI</div><div className={`num text-lg font-extrabold ${tone(profit)}`}>{staked ? `${((profit / staked) * 100).toFixed(0)}%` : '—'}</div></div>
      </div>
      <Spark values={curve} height={72} label={`Banca mea: ${lei(profit)} în ${days.length} zile`} />
      <p className="text-[11px] text-muted-foreground">{rows.length} bilete în {days.length} zile, profit cumulat la miza ta.</p>
    </div>
  );
}
