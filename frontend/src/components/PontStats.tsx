import { useState } from 'react';
import { Card, Stat, ResultBadge } from '@/components/kit';
import { signed, odds as fo } from '@/lib/format';
import type { Ticket } from '@/lib/types';

/** Pontul zilei: câștigate/pierdute, rată de reușită, ROI la miza publicată și istoric. */
export function PontStats({ tickets, fullHistory = false, title = 'Pontul zilei' }: { tickets: Ticket[]; fullHistory?: boolean; title?: string }) {
  const [limit, setLimit] = useState(30);
  const ps = tickets.filter((t) => t.kind === 'acca_pont').sort((a, b) => (b.date ?? '').localeCompare(a.date ?? ''));
  const won = ps.filter((t) => t.status === 'won'), lost = ps.filter((t) => t.status === 'lost');
  const voided = ps.filter((t) => t.status === 'void').length;
  const settled = won.length + lost.length, pending = ps.filter((t) => !t.status || t.status === 'pending').length;
  const staked = [...won, ...lost].reduce((a, t) => a + (t.stake_units ?? 0), 0);
  const profit = won.reduce((a, t) => a + (t.payout ?? (t.stake_units ?? 0) * (t.effective_odds ?? t.total_odds)) - (t.stake_units ?? 0), 0) - lost.reduce((a, t) => a + (t.stake_units ?? 0), 0);
  const visible = fullHistory ? limit : 30;
  return (
    <Card className="p-3.5 md:p-4">
      <h2 className="text-base font-bold">{title}</h2>
      <p className="text-xs text-muted-foreground">Selecțiile zilnice păstrate de la publicare, cu rezultatul și bilanțul lor.</p>
      <div className="mt-3 grid grid-cols-2 gap-3 md:grid-cols-4">
        <Stat label="Câștigate / pierdute" value={`${won.length} / ${lost.length}`} sub={`${pending} în curs${voided ? ` · ${voided} anulate` : ''}`} />
        <Stat label="Rată de reușită" value={settled ? `${Math.round((won.length / settled) * 100)}%` : '—'} />
        <Stat label="Profit" value={settled ? `${signed(profit, 2)}u` : '—'} />
        <Stat label="ROI" value={staked ? `${signed((profit / staked) * 100, 1)}%` : '—'} />
      </div>
      {ps.length ? (
        <>
          <ul className="mt-3 divide-y text-sm">
            {ps.slice(0, visible).map((t) => (
              <li key={`${t.date ?? t.created_at ?? ''}:${t.id}`} className="flex items-center gap-2 py-2">
                <span className="w-12 shrink-0 text-xs tabular-nums text-muted-foreground">{(t.date ?? '').slice(5).split('-').reverse().join('.')}</span>
                <span className="min-w-0 flex-1 truncate">{t.legs.map((l) => l.label ?? l.selection).join(' + ')}</span>
                <b className="num shrink-0">{fo(t.total_odds)}</b>
                <ResultBadge r={t.status ?? 'pending'} />
              </li>
            ))}
          </ul>
          {fullHistory && ps.length > visible && <button type="button" className="btn btn-outline mt-3 min-h-11 w-full" onClick={() => setLimit((n) => Math.min(ps.length, n + 30))}>Mai multe din istoric ({ps.length - visible} rămase)</button>}
        </>
      ) : <p className="mt-3 text-sm text-muted-foreground">Primul Pont al zilei urmărit apare aici după publicare.</p>}
    </Card>
  );
}
