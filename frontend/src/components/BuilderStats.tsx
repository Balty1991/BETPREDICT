import { useState } from 'react';
import { Link } from 'react-router';
import { Card, Loading, Empty, Notice, Segmented, Badge } from './kit';
import { useAsync, getJSON } from '@/lib/fetcher';
import { pct, odds as fo, signed, roKickoff } from '@/lib/format';
import { cn } from '@/lib/utils';

type Agg = { n: number; won: number; lost: number; pending: number; hit_rate: number | null; expected_won: number; priced_n: number; profit: number; roi_pct: number | null };
type Row = { id: number; match_id: number; home?: string; away?: string; kickoff_utc?: string; label: string; type: string; p: number; fair_odds: number; min_odds: number; sb_price?: number | null; source: string; result: 'won' | 'lost' | 'pending'; score?: string | null };
type BBStats = { overall?: Agg; superbet?: Agg; model?: Agg; by_type?: Array<Agg & { type: string }>; recent?: Row[]; generated_at?: string };

function Big({ k, v, tone, sub }: { k: string; v: string | number; tone?: string; sub?: string }) {
  return (
    <Card className="p-3 text-center">
      <div className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground">{k}</div>
      <div className={cn('num text-2xl font-extrabold', tone)}>{v}</div>
      {sub && <div className="text-[11px] text-muted-foreground">{sub}</div>}
    </Card>
  );
}

/** Statistici › Bet Builder: toate combinațiile publicate, decontate doar după final. */
export function BuilderStats() {
  const res = useAsync(() => getJSON<BBStats>('api/builder/stats.json'), []);
  const [f, setF] = useState<'all' | 'won' | 'lost' | 'pending'>('all');
  if (res.loading) return <Loading />;
  const d = res.data;
  if (!d?.overall) return <Empty title="Încă nu există statistici Bet Builder">Apar după prima rulare a Robotului care publică fișierul de statistici.</Empty>;
  const o = d.overall;
  const rows = (d.recent ?? []).filter((r) => f === 'all' || r.result === f);
  return (
    <div className="space-y-4">
      <Notice><b>Experimental.</b> Se decontează doar după finalul meciului. ROI-ul e calculat la cota Superbet, 1u pe combinație, doar unde Superbet a avut preț.</Notice>
      <div className="grid grid-cols-3 gap-2">
        <Big k="Câștigate" v={o.won} tone="text-win" />
        <Big k="Pierdute" v={o.lost} tone="text-loss" />
        <Big k="În curs" v={o.pending} />
      </div>
      <div className="grid grid-cols-2 gap-2">
        <Big k="Rată de câștig" v={o.hit_rate != null ? pct(o.hit_rate, 1) : '—'} sub={`așteptat ${o.expected_won} din ${o.won + o.lost}`} />
        <Big k="ROI la Superbet" v={o.roi_pct != null ? signed(o.roi_pct, 1, '%') : '—'} tone={o.roi_pct == null ? undefined : o.roi_pct >= 0 ? 'text-win' : 'text-loss'} sub={`${o.priced_n} cu preț · ${signed(o.profit, 2)} u`} />
      </div>
      {!!d.by_type?.length && (
        <Card className="overflow-hidden">
          <h3 className="px-4 pt-3 text-sm font-bold">Pe tip de combinație</h3>
          <ul className="divide-y px-4 pb-2">
            {d.by_type.map((t) => (
              <li key={t.type} className="flex items-center gap-2 py-2.5 text-sm">
                <span className="min-w-0 flex-1"><span className="block truncate font-semibold">{t.type}</span><span className="text-[11px] text-muted-foreground">{t.won}V / {t.lost}Î · {t.pending} în curs</span></span>
                <span className="num w-14 text-right">{t.hit_rate != null ? pct(t.hit_rate, 0) : '—'}</span>
                <span className={cn('num w-16 text-right font-bold', t.roi_pct == null ? 'text-muted-foreground' : t.roi_pct >= 0 ? 'text-win' : 'text-loss')}>{t.roi_pct != null ? signed(t.roi_pct, 1, '%') : '—'}</span>
              </li>
            ))}
          </ul>
        </Card>
      )}
      <div>
        <div className="mb-2 flex items-center justify-between gap-2"><h3 className="text-sm font-bold">Combinații recente</h3></div>
        <Segmented size="sm" value={f} onChange={setF} options={[{ value: 'all', label: 'Toate' }, { value: 'won', label: 'Câștigate' }, { value: 'lost', label: 'Pierdute' }, { value: 'pending', label: 'În curs' }]} />
        {!rows.length ? <p className="mt-3 text-sm text-muted-foreground">Nicio combinație în această categorie.</p> : (
          <ul className="mt-3 space-y-2">
            {rows.slice(0, 80).map((r) => (
              <li key={r.id} className={cn('card p-3', r.result === 'won' && 'border-[hsl(var(--win)/0.5)]', r.result === 'lost' && 'border-[hsl(var(--loss)/0.4)]')}>
                <div className="flex items-start gap-2">
                  <div className="min-w-0 flex-1">
                    <Link to={`/meci/${r.match_id}`} className="block break-words text-[13px] font-bold hover:text-primary">{r.home} – {r.away}</Link>
                    <div className="text-[11px] text-muted-foreground">{r.kickoff_utc ? roKickoff(r.kickoff_utc) : ''}{r.score ? ` · ${r.score}` : ''} · {r.type}</div>
                  </div>
                  <Badge tone={r.result === 'won' ? 'win' : r.result === 'lost' ? 'loss' : 'pending'}>{r.result === 'won' ? '✓ câștigat' : r.result === 'lost' ? '✗ pierdut' : 'în curs'}</Badge>
                </div>
                <div className="mt-1 text-[13px]">{r.label}</div>
                <div className="mt-1 flex gap-3 text-[11px] text-muted-foreground"><span>șansă <b className="text-foreground">{pct(r.p, 0)}</b></span><span>cotă corectă <b className="text-foreground">{fo(r.fair_odds)}</b></span><span>Superbet <b className="text-foreground">{r.sb_price ? fo(r.sb_price) : '—'}</b></span></div>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
