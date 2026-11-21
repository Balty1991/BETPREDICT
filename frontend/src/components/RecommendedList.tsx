import { useMemo, useState } from 'react';
import { Link } from 'react-router';
import { useAsync, getJSON } from '@/lib/fetcher';
import { dayLabel, roTime } from '@/lib/format';
import { Segmented, Loading, Empty } from '@/components/kit';
import { cn } from '@/lib/utils';
import { Plus, Check } from 'lucide-react';
import { toast } from 'sonner';
import { useStore, actions } from '@/lib/store';
import type { TicketLeg } from '@/lib/types';

type Row = {
  match_id: number; kickoff_utc: string; day: string | null; home: string; away: string; league?: string | null;
  label: string; odds: number; p: number; bonus_ok: boolean; kind: 'tipar' | 'liga' | 'pinnacle' | 'nou'; why: string;
  market?: string | null; sel?: string | null; line?: number | null;
};
type Market = { label: string; n: number; won: number; roi: number | null; hit: number | null; off: boolean; days: number };
type Disc = { key: string; label: string; status: 'proba' | 'activ' | 'scos'; band_lo: number; band_hi: number; n: number; roi: number | null; fwd_n: number | null; fwd_roi: number | null };
type Doc = { generated_at: string; count: number; rows: Row[]; note: string; markets?: Market[]; discovery?: Disc[] };

const KIND: Record<Row['kind'], string> = { tipar: 'Tipar Superbet', liga: 'Tipar pe ligă', pinnacle: 'Preț Pinnacle', nou: 'Piață nouă' };
// pe biletul manual doar piețele pe care aplicația le poate deconta singură (ca în generator)
const SLIP_MARKETS = new Set(['ss', '1x2', 'over_under', 'btts', 'double_chance']);
const slipLine = (r: Row) => r.line ?? (r.market === 'over_under' ? 1.5 : null);
// „Peste 0.5 goluri; Peste 7.5 cornere” (Bet Builder Superbet) = cheia BB_G05_C75, decontată pe server
function bbKey(r: Row): string | null {
  const m = /peste 0\.5 goluri; peste ([678])\.5 cornere/i.exec(r.sel ?? '');
  return m ? `BB_G05_C${m[1]}5` : null;
}
function toLeg(r: Row): TicketLeg | null {
  const bb = r.market === 'bb' ? bbKey(r) : null;
  const market = bb ? 'ss' : r.market;
  const sel = bb ?? r.sel;
  if (!market || !sel || !SLIP_MARKETS.has(market)) return null;
  return { match_id: r.match_id, kickoff_utc: r.kickoff_utc, league: r.league ?? undefined, home: r.home, away: r.away, market,
    line: bb ? null : slipLine(r), selection: sel, label: r.label, odds: r.odds, p: r.p, p_market: 1 / r.odds, odds_source: 'superbet', reasons: [r.why] };
}
// aceeași regulă ca în Robot (super_tickets.INTL): internaționalele și amicalele au ieșit −8% față de +6% la cluburi
const INTL = /international|nations league|world cup|qualif|friendl|euro 20|copa am|gold cup|africa cup/i;
const hourRo = (iso: string) => Number(new Intl.DateTimeFormat('ro-RO', { timeZone: 'Europe/Bucharest', hour: '2-digit', hour12: false }).format(new Date(iso)));
const isNight = (iso: string) => hourRo(iso) < 10;
const isIntl = (r: Row) => INTL.test(r.league ?? '');

/** Selecțiile recomandate: piețele din care Robotul face biletele, cu motivul din istoric. Filtre: piață, doar cluburi. */
export function RecommendedList({ day, today }: { day: string | null; today: string }) {
  const q = useAsync(() => getJSON<Doc>('api/recommended.json').catch(() => null), []);
  const [sort, setSort] = useState<'time' | 'p'>('time');
  const [market, setMarket] = useState('');
  const [clubs, setClubs] = useState(true);
  const [limit, setLimit] = useState(40);
  const ofDay = useMemo(() => (q.data?.rows ?? []).filter((r) => !day || r.day === day), [q.data, day]);
  const labels = useMemo(() => {
    const n = new Map<string, number>();
    for (const r of ofDay) if (!clubs || !isIntl(r)) n.set(r.label, (n.get(r.label) ?? 0) + 1);
    return [...n.entries()].sort((a, b) => b[1] - a[1]);
  }, [ofDay, clubs]);
  const hiddenIntl = useMemo(() => (clubs ? ofDay.filter((r) => isIntl(r) && (!market || r.label === market)).length : 0), [ofDay, clubs, market]);
  const slip = useStore((s) => s.slip);
  const inSlip = (r: Row) => { const g = toLeg(r); return !!g && slip.some((l) => l.match_id === g.match_id && l.market === g.market && l.line === g.line && l.selection === g.selection); };
  const rows = useMemo(() => {
    const xs = ofDay.filter((r) => (!clubs || !isIntl(r)) && (!market || r.label === market));
    return sort === 'p' ? [...xs].sort((a, b) => b.p - a.p) : xs;
  }, [ofDay, clubs, market, sort]);
  if (q.loading) return <Loading />;
  if (!q.data) return <Empty title="Lista recomandată nu e încă publicată">Apare după următoarea rulare a Robotului.</Empty>;
  const activeMarket = market && labels.some(([l]) => l === market) ? market : '';
  return (
    <div className="space-y-3">
      <p className="text-xs leading-snug text-muted-foreground">{q.data.note}</p>
      <details className="card px-3 py-2">
        <summary className="cursor-pointer text-sm font-bold">🔎 Piețe noi găsite de Robot ({(q.data.discovery ?? []).filter((d) => d.status !== 'scos').length})</summary>
        <div className="mt-2 space-y-1.5 text-sm">
          {!(q.data.discovery ?? []).length && <p className="text-xs text-muted-foreground">Încă niciuna. Robotul verifică zilnic toate piețele Superbet (cluburi, ziua, cote de închidere); una nouă intră în probă la ≥150 selecții, ROI ≥ +3% și pe plus în ambele jumătăți ale ultimelor 60 de zile.</p>}
          {(q.data.discovery ?? []).map((d) => (
            <div key={`${d.key}-${d.band_lo}`} className="flex items-center justify-between gap-2">
              <span className="min-w-0 flex-1 truncate">{d.label} <span className="text-xs text-muted-foreground">{d.band_lo.toFixed(2)}–{d.band_hi.toFixed(2)}</span></span>
              <span className={cn('rounded-full px-2 py-0.5 text-[10px] font-bold', d.status === 'activ' ? 'bg-primary/15 text-primary' : d.status === 'proba' ? 'bg-amber-500/15 text-amber-600 dark:text-amber-400' : 'bg-muted text-muted-foreground')}>{d.status === 'activ' ? 'pe bilete' : d.status === 'proba' ? `în probă ${d.fwd_n ?? 0}/80` : 'scoasă'}</span>
              <span className="w-12 text-right text-xs font-bold tabular-nums">{d.roi == null ? '–' : `${d.roi >= 0 ? '+' : ''}${Math.round(d.roi * 100)}%`}</span>
            </div>
          ))}
        </div>
      </details>
      {!!q.data.markets?.length && (
        <details className="card px-3 py-2">
          <summary className="flex min-h-11 cursor-pointer items-center text-sm font-bold">Cum merg piețele pe Superbet (ultimele {q.data.markets[0].days} de zile)</summary>
          <div className="mt-2 divide-y text-sm">
            {[...q.data.markets].sort((a, b) => (b.roi ?? -9) - (a.roi ?? -9)).map((m) => (
              <div key={m.label} className="flex items-center justify-between gap-2 py-1.5">
                <span className="min-w-0 flex-1 truncate">{m.label}{m.off && <span className="ml-1 text-[11px] font-bold text-destructive">· scoasă de pe bilete</span>}</span>
                <span className="text-xs text-muted-foreground tabular-nums">{m.won}/{m.n}</span>
                <span className={cn('w-14 text-right font-bold tabular-nums', (m.roi ?? 0) >= 0 ? 'text-primary' : 'text-destructive')}>{m.roi == null ? '–' : `${m.roi >= 0 ? '+' : ''}${Math.round(m.roi * 100)}%`}</span>
              </div>
            ))}
          </div>
          <p className="mt-1 text-[11px] text-muted-foreground">La cota de închidere Superbet. O piață care pierde peste 6% pe cel puțin 150 de selecții iese singură de pe bilete până își revine.</p>
        </details>
      )}
      <div className="space-y-2" role="group" aria-label="Filtre selecții recomandate">
        <div className="-mx-4 flex gap-1.5 overflow-x-auto px-4 scrollbar-none" role="group" aria-label="Piață">
          <button type="button" aria-pressed={!activeMarket} className={cn('chip shrink-0', !activeMarket && 'chip-on')} onClick={() => setMarket('')}>Toate piețele</button>
          {labels.map(([l, n]) => (
            <button key={l} type="button" aria-pressed={activeMarket === l} className={cn('chip shrink-0', activeMarket === l && 'chip-on')} onClick={() => setMarket(activeMarket === l ? '' : l)}>{l} <span className="tabular-nums opacity-70">{n}</span></button>
          ))}
        </div>
        <div className="flex items-center justify-between gap-2">
          <button type="button" aria-pressed={clubs} onClick={() => setClubs(!clubs)} className={cn('press flex min-h-11 items-center gap-2 rounded-2xl border px-3 text-sm font-bold', clubs ? 'border-primary/60 bg-primary/10 text-primary' : 'bg-card')}>
            <span aria-hidden className={cn('relative h-5 w-8 shrink-0 rounded-full transition-colors', clubs ? 'bg-primary' : 'bg-muted')}><span className={cn('absolute left-0 top-0.5 h-4 w-4 rounded-full bg-white shadow transition-transform', clubs ? 'translate-x-[14px]' : 'translate-x-0.5')} /></span>
            Doar cluburi
          </button>
          <Segmented size="sm" value={sort} onChange={setSort} options={[{ value: 'time', label: 'Oră' }, { value: 'p', label: 'Șansă' }]} />
        </div>
      </div>
      <div className="flex flex-wrap items-baseline gap-x-2 text-sm text-muted-foreground">
        <span><b className="text-foreground">{rows.length}</b> selecții{day ? ` · ${day === today ? 'azi' : dayLabel(day)}` : ''}</span>
        {hiddenIntl > 0 && <span className="text-xs">· {hiddenIntl} din meciuri internaționale/amicale ascunse (−8% pe Superbet, față de +6% la cluburi)</span>}
      </div>
      {!rows.length ? <Empty title="Nicio selecție recomandată cu filtrele astea">Alege altă zi, altă piață sau „Toate zilele”.</Empty> : (
        <div className="card divide-y px-3">
          {rows.slice(0, limit).map((r, i, arr) => (
            <div key={`${r.match_id}-${r.label}`}>
              {!day && sort === 'time' && (i === 0 || arr[i - 1].day !== r.day) && (
                <div className="pt-3 text-xs font-extrabold uppercase tracking-wide text-primary">{r.day === today ? 'Azi' : dayLabel(r.day ?? '')}</div>
              )}
              <div className="flex items-start gap-2">
              <Link to={`/meci/${r.match_id}${r.day ? `?zi=${r.day}` : ''}`} className="flex min-w-0 flex-1 items-start gap-3 py-3">
                <div className="min-w-0 flex-1">
                  <div className="text-[15px] font-bold leading-tight">{r.label}</div>
                  <div className="truncate text-sm">{r.home} – {r.away}</div>
                  <div className="text-xs text-muted-foreground">{roTime(r.kickoff_utc)}{r.league ? ` · ${r.league}` : ''}</div>
                  <div className="mt-1 flex flex-wrap gap-1">
                    <span className={cn('rounded-full px-2 py-0.5 text-[10px] font-bold', r.kind === 'tipar' ? 'bg-primary/15 text-primary' : 'bg-amber-500/15 text-amber-600 dark:text-amber-400')}>{KIND[r.kind]}</span>
                    {r.bonus_ok && <span className="rounded-full bg-muted px-2 py-0.5 text-[10px] font-bold text-muted-foreground">intră la SuperBonus</span>}
                    {isNight(r.kickoff_utc) && <span className="rounded-full bg-warn px-2 py-0.5 text-[10px] font-bold text-warn" title="Selecțiile de noapte au intrat 43% față de 69% așteptat">noaptea</span>}
                    {isIntl(r) && <span className="rounded-full bg-loss px-2 py-0.5 text-[10px] font-bold text-loss">internațional</span>}
                  </div>
                  <p className="mt-1 text-[11px] leading-snug text-muted-foreground">{r.why}</p>
                  <span className="mt-1 inline-block text-[11px] font-bold text-primary">Analiza meciului →</span>
                </div>
                <div className="flex shrink-0 flex-col items-end">
                  <span className="rounded-xl border bg-card px-2.5 py-1 text-base font-extrabold tabular-nums">{r.odds.toFixed(2)}</span>
                  <span className="mt-1 text-xs text-muted-foreground">șansă {Math.round(r.p * 100)}%</span>
                </div>
              </Link>
              {(() => {
                const leg = toLeg(r);
                const on = inSlip(r);
                const started = Date.parse(r.kickoff_utc) <= Date.now();
                if (!leg || started) return null;
                return (
                  <button type="button" aria-pressed={on} aria-label={on ? 'Scoate de pe bilet' : 'Adaugă pe bilet'}
                    onClick={() => { actions.toggleSlip(leg); toast(on ? 'Scos de pe bilet' : `Pe bilet: ${r.label}`); }}
                    className={cn('press mt-3 flex h-10 w-10 shrink-0 items-center justify-center rounded-xl border', on ? 'border-[hsl(var(--win))] bg-[hsl(var(--win)/0.15)] text-win' : 'border-primary/40 bg-primary/10 text-primary')}>
                    {on ? <Check className="h-5 w-5" /> : <Plus className="h-5 w-5" />}
                  </button>
                );
              })()}
              </div>
            </div>
          ))}
        </div>
      )}
      {rows.length > limit && <button type="button" className="btn btn-outline min-h-11 w-full" onClick={() => setLimit((l) => l + 40)}>Încă {Math.min(40, rows.length - limit)}</button>}
    </div>
  );
}
