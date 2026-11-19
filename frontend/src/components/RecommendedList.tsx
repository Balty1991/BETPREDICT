import { useMemo, useState } from 'react';
import { Link } from 'react-router';
import { useAsync, getJSON } from '@/lib/fetcher';
import { dayLabel, roTime } from '@/lib/format';
import { Segmented, Loading, Empty } from '@/components/kit';
import { cn } from '@/lib/utils';

type Row = {
  match_id: number; kickoff_utc: string; day: string | null; home: string; away: string; league?: string | null;
  label: string; odds: number; p: number; bonus_ok: boolean; kind: 'tipar' | 'liga' | 'pinnacle'; why: string;
};
type Market = { label: string; n: number; won: number; roi: number | null; hit: number | null; off: boolean; days: number };
type Doc = { generated_at: string; count: number; rows: Row[]; note: string; markets?: Market[] };

const KIND: Record<Row['kind'], string> = { tipar: 'Tipar Superbet', liga: 'Tipar pe ligă', pinnacle: 'Preț Pinnacle' };
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
              <Link to={`/meci/${r.match_id}${r.day ? `?zi=${r.day}` : ''}`} className="flex items-start gap-3 py-3">
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
            </div>
          ))}
        </div>
      )}
      {rows.length > limit && <button type="button" className="btn btn-outline min-h-11 w-full" onClick={() => setLimit((l) => l + 40)}>Încă {Math.min(40, rows.length - limit)}</button>}
    </div>
  );
}
