import { useMemo, useState } from 'react';
import type { Ticket, PyramidHistoryRow } from '@/lib/types';
import { Card, Stat, Badge, Segmented, Empty } from './kit';
import { TicketCard } from './TicketCard';
import { pct, signed, odds as fo } from '@/lib/format';
import { cn } from '@/lib/utils';

type F = 'all' | 'pending' | 'won' | 'lost' | 'void';
const ST: Record<string, string> = { pending: 'în curs', won: 'câștigat', lost: 'pierdut', void: 'anulat' };

export function ticketProfit(t: Ticket): number {
  if (t.status === 'won') return (t.effective_odds ?? t.total_odds) - 1;
  if (t.status === 'lost') return -1;
  return 0;
}

export function ticketBlock(ts: Ticket[]) {
  const won = ts.filter((t) => t.status === 'won').length;
  const lost = ts.filter((t) => t.status === 'lost').length;
  const voids = ts.filter((t) => t.status === 'void').length;
  const pending = ts.length - won - lost - voids;
  const profit = ts.reduce((a, t) => a + ticketProfit(t), 0);
  const avgOdds = ts.length ? ts.reduce((a, t) => a + t.total_odds, 0) / ts.length : null;
  return { n: ts.length, won, lost, void: voids, pending, profit, roi: won + lost ? (profit / (won + lost)) * 100 : null, win: won + lost ? won / (won + lost) : null, avgOdds };
}

export function sourceLabel(t: Ticket): string {
  if (t.created_by === 'user' || t.kind === 'manual') return 'Manual';
  return String(t.id).startsWith('local-') ? 'Robot (aplicație)' : 'Robot (pipeline)';
}

/** Secțiune cu KPI, tabel pe grupuri și istoric pe bilet (status: în curs/câștigat/pierdut/anulat). */
export function TicketSection({ tickets, groupKey, groupTitle, empty, extra }: {
  tickets: Ticket[]; groupKey: (t: Ticket) => string; groupTitle: string; empty: string; extra?: React.ReactNode;
}) {
  const [f, setF] = useState<F>('all');
  const [limit, setLimit] = useState(20);
  const b = ticketBlock(tickets);
  const groups = useMemo(() => {
    const g = new Map<string, Ticket[]>();
    for (const t of tickets) { const k = groupKey(t); g.set(k, [...(g.get(k) ?? []), t]); }
    return [...g.entries()].map(([k, ts]) => ({ key: k, ...ticketBlock(ts) })).sort((a, c) => c.n - a.n);
  }, [tickets, groupKey]);
  const list = useMemo(() => tickets.filter((t) => f === 'all' || (f === 'pending' ? !t.status || t.status === 'pending' : t.status === f))
    .sort((a, c) => (c.date ?? '').localeCompare(a.date ?? '') || String(c.id).localeCompare(String(a.id))), [tickets, f]);
  if (!tickets.length) return <Empty title={empty}>Se salvează automat de la prima generare și se decontează după meciuri.</Empty>;
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-2 sm:gap-3 lg:grid-cols-5">
        <Stat label="Total" value={b.n} sub={`${b.pending} în curs${b.void ? ` · ${b.void} anulate` : ''}`} />
        <Stat label="Rată de câștig" value={pct(b.win, 1)} sub={`${b.won}V / ${b.lost}Î`} />
        <Stat label="ROI (1u/bilet)" value={signed(b.roi, 1, '%')} tone={(b.roi ?? 0) >= 0 ? 'win' : 'loss'} />
        <Stat label="Profit" value={`${signed(b.profit, 2)} u`} tone={b.profit >= 0 ? 'win' : 'loss'} />
        <Stat label="Cotă medie" value={fo(b.avgOdds)} />
      </div>
      {extra}
      <Card className="overflow-x-auto"><h2 className="p-3 text-sm font-semibold">{groupTitle}</h2>
        <table className="w-full text-sm"><thead className="text-xs text-muted-foreground"><tr><th className="px-3 py-1 text-left">Grup</th><th className="text-right">N</th><th className="text-right">V/Î</th><th className="text-right">Rată</th><th className="px-3 text-right">ROI</th></tr></thead>
          <tbody>{groups.map((g) => <tr key={g.key} className="border-t"><td className="px-3 py-2">{g.key}</td><td className="text-right">{g.n}</td><td className="text-right">{g.won}/{g.lost}</td><td className="text-right">{pct(g.win)}</td><td className={cn('px-3 text-right', (g.roi ?? 0) >= 0 ? 'text-win' : 'text-loss')}>{signed(g.roi, 1, '%')}</td></tr>)}</tbody></table>
      </Card>
      <div className="flex items-center justify-between gap-2">
        <h2 className="text-sm font-semibold">Istoric ({list.length})</h2>
        <Segmented size="sm" value={f} onChange={(v) => { setF(v); setLimit(20); }} options={[{ value: 'all', label: 'Toate' }, { value: 'pending', label: 'În curs' }, { value: 'won', label: 'Câștigate' }, { value: 'lost', label: 'Pierdute' }, { value: 'void', label: 'Anulate' }]} />
      </div>
      <div className="grid gap-3 md:grid-cols-2">
        {list.slice(0, limit).map((t) => (
          <div key={String(t.id)} className="space-y-1">
            <div className="flex items-center gap-1.5 text-[11px] text-muted-foreground"><span>{t.date}</span><Badge tone="outline">{sourceLabel(t)}</Badge><Badge tone={t.status === 'won' ? 'win' : t.status === 'lost' ? 'loss' : t.status === 'void' ? 'warn' : 'pending'}>{ST[t.status ?? 'pending'] ?? t.status}</Badge></div>
            <TicketCard t={t} compact saved />
          </div>
        ))}
      </div>
      {list.length > limit && <button className="btn btn-outline w-full" onClick={() => setLimit(limit + 20)}>Arată mai multe</button>}
    </div>
  );
}

export function pyramidDaysSummary(rows: PyramidHistoryRow[]) {
  return { days: rows.length, picks: rows.filter((r) => r.status === 'pick').length, noBet: rows.filter((r) => r.status !== 'pick').length };
}
