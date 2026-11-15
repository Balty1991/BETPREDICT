import { Link } from 'react-router';
import { useSettledTickets, usePersistMySettlement, useTodayBoard, useMeta, useNow } from '@/lib/hooks';
import { useAsync } from '@/lib/fetcher';
import { loadTicketsHistory } from '@/lib/data';
import { useStore } from '@/lib/store';
import { longDay, roTime, todayRo } from '@/lib/format';
import { BudgetBar } from '@/components/BudgetBar';
import { TicketCard } from '@/components/TicketCard';
import { Skeleton } from '@/components/kit';

const BANDS: Array<[string, string, string]> = [
  ['4', 'De jucat', '4 meciuri'],
  ['6', 'De jucat', '6 meciuri'],
  ['500', 'Rar', '500+'],
  ['1000', 'Rar', '1000+'],
  ['10000', 'Rar', '10000+'],
];

/** Acasă: biletele de cornere, pe cotă, și unde stau. Restul e în meniu. */
export default function HomePage() {
  const now = useNow();
  const today = todayRo();
  const meta = useMeta();
  const myTickets = useStore((s) => s.myTickets);
  const mySettled = useSettledTickets(myTickets);
  usePersistMySettlement(mySettled.tickets, myTickets);
  const { full, loading } = useTodayBoard(today);
  const history = useAsync(loadTicketsHistory, []);
  const corners = full.filter((t) => t.kind === 'acca_corners');
  const waiting = corners.filter((t) => t.status === 'pending' && t.legs.every((l) => !l.kickoff_utc || Date.parse(l.kickoff_utc) > now));
  const past = (history.data ?? []).filter((t) => t.kind === 'acca_corners' && (t.status === 'won' || t.status === 'lost'));
  const won = past.filter((t) => t.status === 'won').length;
  const roi = past.length ? past.reduce((a, t) => a + (t.status === 'won' ? (t.total_odds_published ?? t.total_odds) - 1 : -1), 0) / past.length : null;

  return (
    <div className="space-y-5">
      <header className="flex items-end justify-between gap-3">
        <div>
          <div className="eyebrow">Cornere · Superbet</div>
          <h1 className="capitalize">{longDay(today)}</h1>
          {meta.data?.generated_at && <p className="mt-1 text-[12px] text-muted-foreground">Actualizat {roTime(meta.data.generated_at)}</p>}
        </div>
        <Link to="/bilete" className="btn btn-primary h-10 min-h-0 px-4 text-[13px]">Biletele</Link>
      </header>

      <section className="grid grid-cols-3 gap-2">
        <div className="card p-3"><div className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">Neîncepute</div><div className="num mt-1 text-[26px] font-extrabold leading-none">{loading ? '…' : waiting.length}</div></div>
        <div className="card p-3"><div className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">Decontate</div><div className="num mt-1 text-[26px] font-extrabold leading-none"><span className="text-win">{won}</span><span className="text-muted-foreground">–</span><span className="text-loss">{past.length - won}</span></div></div>
        <div className="card p-3"><div className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">ROI</div><div className={`num mt-1 text-[26px] font-extrabold leading-none ${roi == null ? 'text-muted-foreground' : roi >= 0 ? 'text-win' : 'text-loss'}`}>{roi == null ? '—' : `${roi >= 0 ? '+' : '−'}${Math.abs(Math.round(roi * 100))}%`}</div></div>
      </section>

      <BudgetBar />

      <section className="space-y-3">
        <div className="flex items-baseline justify-between">
          <h2>De pus azi</h2>
          <span className="text-[12px] text-muted-foreground">3 lei pe 4 și pe 6 · 2 lei pe cele mari</span>
        </div>
        {loading ? <Skeleton className="h-28 w-full rounded-2xl" /> : waiting.length === 0 ? (
          <p className="card p-4 text-sm text-muted-foreground">Niciun bilet de cornere neînceput. Următoarea actualizare le pune aici.</p>
        ) : BANDS.map(([v, group, label]) => {
          const xs = waiting.filter((t) => t.variant === v);
          if (!xs.length) return null;
          return (
            <div key={v} className="space-y-2">
              <div className="flex items-baseline gap-2 px-0.5">
                <h3 className="text-[13px]">{label}</h3>
                <span className="text-[11px] text-muted-foreground">{group}</span>
              </div>
              {xs.map((t) => <TicketCard key={t.id} t={t} compact />)}
            </div>
          );
        })}
      </section>

      <section className="grid grid-cols-2 gap-2 text-sm">
        <Link to="/statistici" className="card press p-3 font-bold">Rezultate<span className="mt-1 block text-[12px] font-medium text-muted-foreground">ROI pe fiecare cotă</span></Link>
        <Link to="/istoric" className="card press p-3 font-bold">Istoric<span className="mt-1 block text-[12px] font-medium text-muted-foreground">Zi de zi</span></Link>
      </section>
      <p className="text-[12px] leading-relaxed text-muted-foreground">Singurul plus măsurat e peste 0,5 goluri cu peste 7,5 cornere, cam +6% pe selecție. Predicțiile, piramida și restul uneltelor sunt în Mai mult.</p>
    </div>
  );
}
