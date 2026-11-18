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
type Doc = { generated_at: string; count: number; rows: Row[]; note: string };

const KIND: Record<Row['kind'], string> = { tipar: 'Tipar Superbet', liga: 'Tipar pe ligă', pinnacle: 'Preț Pinnacle' };

/** Selecțiile recomandate: piețele din care Robotul face biletele, cu motivul din istoric. */
export function RecommendedList({ day, today }: { day: string | null; today: string }) {
  const q = useAsync(() => getJSON<Doc>('api/recommended.json').catch(() => null), []);
  const [sort, setSort] = useState<'time' | 'p'>('time');
  const [limit, setLimit] = useState(40);
  const rows = useMemo(() => {
    const xs = (q.data?.rows ?? []).filter((r) => !day || r.day === day);
    return sort === 'p' ? [...xs].sort((a, b) => b.p - a.p) : xs;
  }, [q.data, day, sort]);
  if (q.loading) return <Loading />;
  if (!q.data) return <Empty title="Lista recomandată nu e încă publicată">Apare după următoarea rulare a Robotului.</Empty>;
  return (
    <div className="space-y-3">
      <p className="text-xs leading-snug text-muted-foreground">{q.data.note}</p>
      <div className="flex items-center justify-between gap-2">
        <span className="text-sm text-muted-foreground"><b className="text-foreground">{rows.length}</b> selecții{day ? ` · ${day === today ? 'azi' : dayLabel(day)}` : ''}</span>
        <Segmented size="sm" value={sort} onChange={setSort} options={[{ value: 'time', label: 'Oră' }, { value: 'p', label: 'Șansă' }]} />
      </div>
      {!rows.length ? <Empty title="Nicio selecție recomandată în ziua asta">Alege altă zi sau „Toate zilele”.</Empty> : (
        <div className="card divide-y px-3">
          {rows.slice(0, limit).map((r, i, arr) => (
            <div key={`${r.match_id}-${r.label}`}>
              {!day && sort === 'time' && (i === 0 || arr[i - 1].day !== r.day) && (
                <div className="pt-3 text-xs font-extrabold uppercase tracking-wide text-primary">{r.day === today ? 'Azi' : dayLabel(r.day ?? '')}</div>
              )}
              <Link to={`/meci/${r.match_id}`} className="flex items-start gap-3 py-3">
                <div className="min-w-0 flex-1">
                  <div className="text-[15px] font-bold leading-tight">{r.label}</div>
                  <div className="truncate text-sm">{r.home} – {r.away}</div>
                  <div className="text-xs text-muted-foreground">{roTime(r.kickoff_utc)}{r.league ? ` · ${r.league}` : ''}</div>
                  <div className="mt-1 flex flex-wrap gap-1">
                    <span className={cn('rounded-full px-2 py-0.5 text-[10px] font-bold', r.kind === 'tipar' ? 'bg-primary/15 text-primary' : 'bg-amber-500/15 text-amber-600 dark:text-amber-400')}>{KIND[r.kind]}</span>
                    {r.bonus_ok && <span className="rounded-full bg-muted px-2 py-0.5 text-[10px] font-bold text-muted-foreground">intră la SuperBonus</span>}
                  </div>
                  <p className="mt-1 text-[11px] leading-snug text-muted-foreground">{r.why}</p>
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
