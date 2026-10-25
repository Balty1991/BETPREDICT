import { useMemo, useState } from 'react';
import { actions } from '@/lib/store';
import { Spark } from '@/components/dash';
import type { Ticket } from '@/lib/types';

const lei = (x: number) => `${x > 0 ? '+' : ''}${x.toLocaleString('ro-RO', { maximumFractionDigits: 0 })} lei`;
const tone = (x: number) => (x > 0 ? 'text-win' : x < 0 ? 'text-loss' : '');

type Row = { day: string; stake: number; full: number; type: string; t: Ticket };

export function ticketType(t: Ticket): string {
  if (t.kind === 'acca_pont') return 'Pontul zilei';
  if (t.kind === 'pyramid') return 'Piramidă';
  if (t.created_by && t.created_by !== 'robot') return 'Generator';
  const o = t.total_odds ?? 0;
  return o >= 1000 ? 'Cotă 1000+' : o >= 500 ? 'Cotă 500+' : o >= 100 ? 'Cotă 100+' : o >= 20 ? 'Cotă 20–99' : 'Sub 20';
}

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
      out.push({ day, stake, full, type: ticketType(t), t });
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
      <ByType rows={rows} />
      <Journal rows={rows} />
    </div>
  );
}

function ByType({ rows }: { rows: Row[] }) {
  const g = new Map<string, { n: number; won: number; stake: number; profit: number }>();
  for (const r of rows) {
    const x = g.get(r.type) ?? { n: 0, won: 0, stake: 0, profit: 0 };
    x.n += 1; x.won += r.t.status === 'won' ? 1 : 0; x.stake += r.stake; x.profit += r.full;
    g.set(r.type, x);
  }
  const list = [...g.entries()].sort((a, b) => b[1].profit - a[1].profit);
  return (
    <div>
      <div className="label mb-1">Pe tip de bilet</div>
      <ul className="divide-y divide-border/50 text-xs">
        {list.map(([k, v]) => (
          <li key={k} className="flex items-center justify-between gap-2 py-1.5">
            <span className="font-semibold">{k}</span>
            <span className="num text-muted-foreground">{v.won}/{v.n} · {v.stake.toLocaleString('ro-RO')} lei · <b className={tone(v.profit)}>{lei(v.profit)}</b> · {v.stake ? `${((v.profit / v.stake) * 100).toFixed(0)}%` : '—'}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

/** Jurnalul: fiecare bilet jucat, cu miza reală (editabilă) și rezultatul. */
function Journal({ rows }: { rows: Row[] }) {
  const [all, setAll] = useState(false);
  const list = [...rows].reverse().slice(0, all ? rows.length : 10);
  return (
    <div>
      <div className="label mb-1">Jurnal</div>
      <ul className="divide-y divide-border/50 text-xs">
        {list.map((r) => (
          <li key={String(r.t.id)} className="flex items-center justify-between gap-2 py-1.5">
            <span className="min-w-0"><span className="block truncate font-semibold">{r.type} · cota {(r.t.total_odds ?? 0).toLocaleString('ro-RO', { maximumFractionDigits: 2 })}</span><span className="text-muted-foreground">{r.day} · {r.t.status === 'won' ? 'câștigat' : r.t.status === 'lost' ? 'pierdut' : 'anulat'}</span></span>
            <span className="flex shrink-0 items-center gap-2">
              <label className="sr-only" htmlFor={`st-${r.t.id}`}>Miza reală</label>
              <input id={`st-${r.t.id}`} type="number" min={0} inputMode="decimal" className="input h-9 w-16 px-2 text-right" defaultValue={r.stake}
                onBlur={(e) => { const v = Math.max(0, Number(e.target.value) || 0); if (v !== r.stake) actions.saveTicket({ ...r.t, stake: v, stake_lei: v }); }} />
              <b className={`num w-16 text-right ${tone(r.full)}`}>{lei(r.full)}</b>
            </span>
          </li>
        ))}
      </ul>
      {rows.length > 10 && <button className="btn btn-ghost mt-1 h-9 text-xs" onClick={() => setAll(!all)}>{all ? 'Mai puține' : `Toate (${rows.length})`}</button>}
    </div>
  );
}
