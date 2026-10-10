import { useMemo, useState } from 'react';
import type { Ticket, PyramidHistoryRow } from '@/lib/types';
import { Badge, Empty } from './kit';
import { pct, signed, odds as fo } from '@/lib/format';
import { cn } from '@/lib/utils';

type F = 'all' | 'pending' | 'won' | 'lost' | 'void';
const ST: Record<string, string> = { pending: 'în curs', won: 'câștigat', lost: 'pierdut', void: 'anulat' };

export function ticketProfit(t: Ticket): number {
  if (t.status === 'won') return (t.effective_odds ?? t.total_odds_published ?? t.total_odds) - 1;
  if (t.status === 'lost') return -1;
  return 0;
}

export function ticketBlock(ts: Ticket[]) {
  const won = ts.filter((t) => t.status === 'won').length;
  const lost = ts.filter((t) => t.status === 'lost').length;
  const voids = ts.filter((t) => t.status === 'void').length;
  const pending = ts.length - won - lost - voids;
  const profit = ts.reduce((a, t) => a + ticketProfit(t), 0);
  const avgOdds = ts.length ? ts.reduce((a, t) => a + (t.total_odds_published ?? t.total_odds), 0) / ts.length : null;
  return { n: ts.length, won, lost, void: voids, pending, profit, roi: won + lost ? (profit / (won + lost)) * 100 : null, win: won + lost ? won / (won + lost) : null, avgOdds };
}

export function sourceLabel(t: Ticket): string {
  if (t.created_by === 'user' || t.kind === 'manual') return 'Manual';
  return String(t.id).startsWith('local-') ? 'Robot (în aplicație)' : 'Robot';
}

const pretty = (v: string) => { const x = v.replace(/[_-]+/g, ' ').trim(); return x ? x[0].toUpperCase() + x.slice(1) : x; };

/** Tip de bilet în română, fără termeni interni (ex. „Loterie ~500”, „Multi-zi ~100”, „Bilet sigur ~2”). */
export function ticketType(t: Pick<Ticket, 'kind' | 'variant' | 'variant_label' | 'target_odds' | 'lottery' | 'safe' | 'created_by' | 'legs'> & { total_odds?: number }): string {
  const tgt = t.target_odds ?? (t.kind.startsWith('acca_') && /^\d+$/.test(t.kind.slice(5)) ? Number(t.kind.slice(5)) : null);
  const n = t.legs?.length ?? 0;
  const v = (t.variant ?? '').toLowerCase();
  if (t.kind === 'pyramid') return n ? `Piramida · ${n} ${n === 1 ? 'meci' : 'meciuri'}` : 'Piramida';
  if (t.created_by === 'user' || t.kind === 'manual') return 'Biletul meu';
  if (t.kind === 'acca_value') return n ? `Valoare ${n} ${n === 1 ? 'selecție' : 'selecții'}` : 'Bilet de valoare';
  if (t.kind === 'acca_double') return 'Dublu de valoare';
  if (t.lottery || v.includes('loter')) return `Loterie ~${tgt ?? ''}`;
  if (t.safe || t.kind === 'acca_safe' || v === 'sigur') return `Bilet sigur ~${tgt ?? ''}`;
  if (v.includes('multi')) return `Multi-zi ~${tgt ?? ''}`;
  const lbl = t.variant_label && !/pipeline/i.test(t.variant_label) ? t.variant_label : v ? pretty(v) : '';
  return `Bilet ~${tgt ?? ''}${lbl ? ` · ${lbl}` : ''}`;
}

const tone = (s?: string) => (s === 'won' ? 'win' : s === 'lost' ? 'loss' : s === 'void' ? 'warn' : 'pending') as 'win' | 'loss' | 'warn' | 'pending';
const legMark = (r?: string | null) => (r === 'won' || r === 'half_won' ? '✓' : r === 'lost' || r === 'half_lost' ? '✗' : r === 'void' ? '–' : '•');
const legCls = (r?: string | null) => (r === 'won' || r === 'half_won' ? 'text-win' : r === 'lost' || r === 'half_lost' ? 'text-loss' : 'text-muted-foreground');
const shortDate = (d?: string) => (d ? d.slice(8, 10) + '.' + d.slice(5, 7) : '');

function Counter({ label, value, cls, sub }: { label: string; value: React.ReactNode; cls?: string; sub?: React.ReactNode }) {
  return <div className="card p-3 text-center"><div className={cn('num text-[28px] font-extrabold leading-none', cls)}>{value}</div><div className="mt-1 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">{label}</div>{sub && <div className="text-[11px] text-muted-foreground">{sub}</div>}</div>;
}

function Chip({ on, onClick, children }: { on: boolean; onClick: () => void; children: React.ReactNode }) {
  return <button type="button" onClick={onClick} className={cn('press shrink-0 rounded-full border px-3 py-1.5 text-xs font-semibold', on ? 'border-transparent bg-primary text-primary-foreground' : 'bg-[hsl(var(--elevated))] text-muted-foreground')}>{children}</button>;
}

function HistoryCard({ t }: { t: Ticket }) {
  const [open, setOpen] = useState(false);
  const st = t.status ?? 'pending';
  const done = t.legs.filter((l) => l.result === 'won' || l.result === 'half_won').length;
  const odds = (st === 'won' && t.effective_odds && t.effective_odds > 1 ? t.effective_odds : null) ?? t.total_odds_published ?? t.total_odds ?? t.legs.reduce((a, l) => a * (l.odds || 1), 1);
  const stake = t.stake_units || t.stake || 0;
  const p = ticketProfit(t);
  return (
    <div className={cn('card overflow-hidden border-l-4', st === 'won' ? 'border-l-[hsl(var(--win))]' : st === 'lost' ? 'border-l-[hsl(var(--loss))]' : 'border-l-primary/40')}>
      <button type="button" className="w-full p-3 text-left" onClick={() => setOpen(!open)} aria-expanded={open}>
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0"><div className="truncate text-[15px] font-bold">{ticketType(t)}</div>
            <div className="text-xs text-muted-foreground">{shortDate(t.date)} · {t.legs.length} {t.legs.length === 1 ? 'meci' : 'meciuri'} · {sourceLabel(t)}</div></div>
          <Badge tone={tone(st)}>{ST[st] ?? st}</Badge>
        </div>
        <div className="mt-2 grid grid-cols-3 gap-2 text-center">
          <div><div className="num text-lg font-extrabold text-primary">{odds >= 100 ? Math.round(odds) : fo(odds)}</div><div className="text-[10px] uppercase text-muted-foreground">cotă</div></div>
          <div><div className="num text-lg font-extrabold">{stake ? `${stake}u` : '—'}</div><div className="text-[10px] uppercase text-muted-foreground">{stake ? 'miză' : 'informativ'}</div></div>
          <div><div className={cn('num text-lg font-extrabold', st === 'pending' ? '' : p >= 0 ? 'text-win' : 'text-loss')}>{st === 'pending' ? `${done}/${t.legs.length}` : `${signed(p, 2)}u`}</div><div className="text-[10px] uppercase text-muted-foreground">{st === 'pending' ? 'câștigate' : `${done}/${t.legs.length} sel.`}</div></div>
        </div>
        <div className="mt-2 text-center text-[11px] text-primary">{open ? 'Ascunde selecțiile ▲' : 'Vezi selecțiile ▼'}</div>
      </button>
      {open && <ul className="divide-y border-t text-sm">{t.legs.map((l, i) => (
        <li key={i} className="flex items-center gap-2 px-3 py-2"><span className={cn('w-4 text-center font-bold', legCls(l.result))}>{legMark(l.result)}</span>
          <div className="min-w-0 flex-1"><div className="truncate font-semibold">{l.label}</div><div className="truncate text-xs text-muted-foreground">{l.home} – {l.away}{l.score ? ` · ${l.score}` : ''}</div></div>
          <span className="num font-bold">{fo(l.odds)}</span></li>))}</ul>}
    </div>
  );
}

export type TypeSummary = { key: string; n: number; won: number; lost: number; roi: number | null; profit?: number | null };

export function TypeCards({ title, rows }: { title: string; rows: TypeSummary[] }) {
  if (!rows.length) return null;
  return (
    <div><h2 className="mb-2 text-sm font-semibold">{title}</h2>
      <div className="grid grid-cols-2 gap-2 md:grid-cols-3">{rows.map((g) => (
        <div key={g.key} className="card p-3"><div className="truncate text-sm font-bold">{g.key}</div>
          <div className="mt-1 flex items-baseline justify-between"><span className="text-xs"><b className="text-win">{g.won}</b> / <b className="text-loss">{g.lost}</b> <span className="text-muted-foreground">din {g.n}</span></span>
            <span className={cn('num text-sm font-extrabold', (g.roi ?? 0) >= 0 ? 'text-win' : 'text-loss')}>{signed(g.roi, 0, '%')}</span></div>
          <div className="mt-1.5 h-1.5 overflow-hidden rounded-full bg-[hsl(var(--loss)/0.35)]"><div className="h-full bg-[hsl(var(--win))]" style={{ width: `${g.won + g.lost ? (g.won / (g.won + g.lost)) * 100 : 0}%` }} /></div>
        </div>))}</div>
    </div>
  );
}

/** Bilete: contoare mari, filtre (status + tip), carduri expandabile, sumar pe tip în carduri. */
export function TicketSection({ tickets, groupKey = ticketType, groupTitle, empty, extra }: {
  tickets: Ticket[]; groupKey?: (t: Ticket) => string; groupTitle: string; empty: string; extra?: React.ReactNode;
}) {
  const [f, setF] = useState<F>('all');
  const [type, setType] = useState('');
  const [limit, setLimit] = useState(20);
  const b = ticketBlock(tickets);
  const groups = useMemo(() => {
    const g = new Map<string, Ticket[]>();
    for (const t of tickets) { const k = groupKey(t); g.set(k, [...(g.get(k) ?? []), t]); }
    return [...g.entries()].map(([k, ts]) => ({ key: k, ...ticketBlock(ts) })).sort((a, c) => c.n - a.n);
  }, [tickets, groupKey]);
  const list = useMemo(() => tickets.filter((t) => (f === 'all' || (f === 'pending' ? !t.status || t.status === 'pending' : t.status === f)) && (!type || groupKey(t) === type))
    .sort((a, c) => (c.date ?? '').localeCompare(a.date ?? '') || String(c.id).localeCompare(String(a.id))), [tickets, f, type, groupKey]);
  if (!tickets.length) return <Empty title={empty}>Se salvează automat de la prima generare și se decontează după meciuri.</Empty>;
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-3 gap-2">
        <Counter label="Câștigate" value={b.won} cls="text-win" />
        <Counter label="Pierdute" value={b.lost} cls="text-loss" />
        <Counter label="În curs" value={b.pending} cls="text-primary" />
      </div>
      <div className="card grid grid-cols-3 divide-x p-0 text-center">
        <div className="p-2.5"><div className="num text-lg font-extrabold">{b.n}</div><div className="text-[10px] uppercase text-muted-foreground">total{b.void ? ` · ${b.void} anulate` : ''}</div></div>
        <div className="p-2.5"><div className={cn('num text-lg font-extrabold', b.profit >= 0 ? 'text-win' : 'text-loss')}>{signed(b.profit, 2)}u</div><div className="text-[10px] uppercase text-muted-foreground">profit</div></div>
        <div className="p-2.5"><div className={cn('num text-lg font-extrabold', (b.roi ?? 0) >= 0 ? 'text-win' : 'text-loss')}>{signed(b.roi, 1, '%')}</div><div className="text-[10px] uppercase text-muted-foreground">ROI · rată {pct(b.win)}</div></div>
      </div>
      <div className="space-y-2">
        <div className="flex gap-1.5 overflow-x-auto scrollbar-none">{([['all', 'Toate'], ['won', 'Câștigate'], ['lost', 'Pierdute'], ['pending', 'În curs']] as [F, string][]).map(([v, l]) => <Chip key={v} on={f === v} onClick={() => { setF(v); setLimit(20); }}>{l}</Chip>)}</div>
        {groups.length > 1 && <div className="flex gap-1.5 overflow-x-auto scrollbar-none"><Chip on={!type} onClick={() => setType('')}>Toate tipurile</Chip>{groups.map((g) => <Chip key={g.key} on={type === g.key} onClick={() => { setType(type === g.key ? '' : g.key); setLimit(20); }}>{g.key}</Chip>)}</div>}
      </div>
      <h2 className="text-sm font-semibold">Istoric ({list.length})</h2>
      {list.length ? <div className="stagger grid gap-2.5 md:grid-cols-2">{list.slice(0, limit).map((t) => <HistoryCard key={String(t.id)} t={t} />)}</div> : <p className="text-sm text-muted-foreground">Niciun bilet pentru filtrul ales.</p>}
      {list.length > limit && <button className="btn btn-outline w-full" onClick={() => setLimit(limit + 20)}>Arată mai multe</button>}
      <TypeCards title={groupTitle} rows={groups.map((g) => ({ key: g.key, n: g.n, won: g.won, lost: g.lost, roi: g.roi }))} />
      {extra}
    </div>
  );
}

export function pyramidDaysSummary(rows: PyramidHistoryRow[]) {
  return { days: rows.length, picks: rows.filter((r) => r.status === 'pick').length, noBet: rows.filter((r) => r.status !== 'pick').length };
}
