import { useMemo, useState } from 'react';
import { Link } from 'react-router';
import { Flame, Sparkles } from 'lucide-react';
import { useSettledTickets, usePersistMySettlement, useTodayBoard, useMeta } from '@/lib/hooks';
import { getJSON, useAsync } from '@/lib/fetcher';
import { loadTickets, loadJournalRows, loadPyramid, loadPyramid140, loadPyramidMici } from '@/lib/data';
import { useStore } from '@/lib/store';
import { addDays, longDay, odds as fo, roTime, todayRo } from '@/lib/format';
import { pickBoard } from '@/lib/board';
import type { Ticket } from '@/lib/types';
import { perfByDay } from '@/lib/dashboard';
import { Panel } from '@/components/dash';
import { IconPyramid } from '@/components/icons';
import { Skeleton } from '@/components/kit';
import { cn } from '@/lib/utils';
import { BudgetBar } from '@/components/BudgetBar';
import { budgetLei, weekSpent } from '@/lib/stake';

type Boost = { match_id: number; home: string; away: string; kickoff_utc: string; label: string; price: number; ev?: number | null; reliable?: boolean; suspect?: boolean };
const shortName = (t: Ticket) => (t.variant_label ?? 'Bilet').replace(/^Stil Supersocial\s*·\s*/, '').replace(/^Pe val\s*·\s*/, '') || 'Stil Supersocial';

/** „Azi de jucat”: maximum 3 bilete — cel mai bun 100+, cel mai bun 500+/1000+ și Pontul zilei. Dacă cel de azi a început,
 *  se arată următorul neînceput (azi) sau cel de mâine. Plus o singură cotă mărită. */
function TodayPicks({ board, loading }: { board: Ticket[]; loading: boolean }) {
  const today = todayRo();
  const tomorrow = addDays(today, 1);
  const boosts = useAsync(() => getJSON<{ boosts: Boost[] }>('api/boosts/today.json'), []);
  const all = useAsync(() => loadTickets(today), [today]);
  const next = useAsync(() => loadTickets(tomorrow), [tomorrow]);
  const budget = useStore((st) => st.settings.weeklyBudget ?? 50);
  const spent = useStore((st) => weekSpent(st.myTickets));
  const [now] = useState(() => Date.now());
  const notStarted = (t: Ticket) => t.status === 'pending' && t.legs.every((l) => !l.kickoff_utc || Date.parse(l.kickoff_utc) > now);
  const playable = (t: Ticket) => notStarted(t) && !/fără cotă mărită/i.test(t.variant_label ?? '') && !(t as { informational?: boolean }).informational;
  const boardNext = useMemo(() => pickBoard(next.data?.tickets ?? []), [next.data]);
  const bestIn = (xs: Ticket[], lo: number, hi: number) => xs.filter((t) => playable(t) && (t.total_odds ?? 0) >= lo && (t.total_odds ?? 0) < hi)
    .sort((a, b) => (b.p_ticket ?? 0) * (b.total_odds ?? 0) - (a.p_ticket ?? 0) * (a.total_odds ?? 0))[0];
  const pontOf = (xs: Ticket[]) => xs.find((t) => t.kind === 'acca_pont' && notStarted(t));
  const slot = (a?: Ticket, b?: Ticket) => (a ? { t: a, tm: false } : b ? { t: b, tm: true } : null);
  const picks = [
    slot(bestIn(board, 100, 500), bestIn(boardNext, 100, 500)),
    slot(bestIn(board, 500, 1e9), bestIn(boardNext, 500, 1e9)),
    slot(pontOf(all.data?.tickets ?? []), pontOf(next.data?.tickets ?? [])),
  ].filter(Boolean) as Array<{ t: Ticket; tm: boolean }>;
  const best = (boosts.data?.boosts ?? []).filter((b) => (b.ev ?? -1) > 0 && b.reliable && !b.suspect && Date.parse(b.kickoff_utc) > now)
    .sort((a, b) => (b.ev ?? 0) - (a.ev ?? 0))[0];
  return (
    <Panel title="Azi de jucat" icon={<Sparkles className="h-4 w-4" />} right={<Link to="/bilete" className="text-xs font-semibold text-primary">Vezi toate</Link>}>
      {loading ? <Skeleton className="h-40 w-full rounded-2xl" /> : (
        <div className="space-y-2.5">
          {!picks.length && <p className="text-sm text-muted-foreground">Niciun bilet neînceput acum.</p>}
          {picks.map(({ t, tm }) => { const lei = budgetLei(t, budget || 50, budget ? spent : 0); return (
            <Link key={t.id} to="/bilete" className="hot-ticket press">
              <span className="min-w-0 flex-1">
                <span className="block break-words text-[15px] font-bold leading-snug">{t.kind === 'acca_pont' ? 'Pontul zilei' : shortName(t)}{tm && <span className="ml-1.5 text-[11px] font-semibold text-muted-foreground">mâine</span>}</span>
                <span className="mt-1 flex items-center gap-1.5 text-[11px] text-muted-foreground">{t.legs.length} {t.legs.length === 1 ? 'meci' : 'meciuri'} <span className="stake-chip">{lei ? `${lei} lei` : 'buget consumat'}</span></span>
              </span>
              <span className="big-num neon-text text-[26px]">{fo(t.total_odds)}</span>
            </Link>); })}
          {best && (
            <Link to="/statistici?tab=boosts" className="flex min-h-11 items-center gap-2 text-sm">
              <Flame className="h-4 w-4 shrink-0 text-[hsl(var(--glow-3))]" aria-hidden />
              <span className="min-w-0 flex-1 truncate"><b>Cotă mărită:</b> {best.label}</span>
              <span className="num font-extrabold">{fo(best.price)}</span>
            </Link>
          )}
        </div>
      )}
    </Panel>
  );
}

/** Acasă: data, bugetul, ce e de jucat, rezultatele pe scurt și piramidele. Restul stă în paginile lor. */
export default function HomePage() {
  const today = todayRo();
  const yesterday = addDays(today, -1);
  const last3 = useMemo(() => [addDays(today, -3), addDays(today, -2), yesterday], [today, yesterday]);
  const minOdds = useStore((s) => s.settings.minOdds);
  const journal = useAsync(() => loadJournalRows(minOdds, 8), [minOdds]);
  const { board, loading: boardLoading } = useTodayBoard(today);
  const meta = useMeta();
  // biletele mele se decontează și aici, ca rezultatele să rămână salvate
  const myTickets = useStore((s) => s.myTickets);
  const mySettled = useSettledTickets(myTickets);
  usePersistMySettlement(mySettled.tickets, myTickets);
  const rows = useMemo(() => journal.data?.rows ?? [], [journal.data]);
  const perf3 = useMemo(() => perfByDay(rows, last3, 'toate'), [rows, last3]);
  const loadingJ = journal.loading;

  return (
    <div className="dash space-y-4">
      <div className="flex items-center gap-2 px-1 text-xs text-muted-foreground">
        <span className="font-semibold capitalize text-foreground">{longDay(today)}</span>
        {meta.data?.generated_at && <span>· actualizat {roTime(meta.data.generated_at)}</span>}
      </div>
      <BudgetBar />
      <TodayPicks board={board} loading={boardLoading} />
      <Link to="/istoric" className="card press block p-4" aria-label="Rezultatele ultimelor 3 zile">
        <div className="mb-2 flex items-center justify-between"><span className="text-sm font-bold">Rezultate</span><span className="text-xs font-semibold text-primary">Istoric →</span></div>
        {loadingJ ? <Skeleton className="h-14 w-full rounded-xl" /> : (
          <div className="grid grid-cols-3 gap-2">
            {perf3.map((d) => (
              <div key={d.date} className="rounded-xl bg-[hsl(var(--elevated))] px-2 py-2 text-center">
                <div className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">{d.date === yesterday ? 'ieri' : d.date.slice(8, 10) + '.' + d.date.slice(5, 7)}</div>
                <div className={cn('big-num mt-1 text-[20px]', (d.winRate ?? 0) >= 0.5 ? 'text-win' : 'text-warn')}>{d.winRate == null ? '—' : `${Math.round(d.winRate * 100)}%`}</div>
                <div className={cn('num text-[11px] font-bold', (d.roi ?? 0) >= 0 ? 'text-win' : 'text-loss')}>{d.roi == null ? '' : `ROI ${d.roi >= 0 ? '+' : ''}${(d.roi * 100).toFixed(1)}%`}</div>
              </div>
            ))}
          </div>
        )}
      </Link>

      {/* ── PIRAMIDE + SCURTĂTURI ────────────────────── */}
      <details className="group">
        <summary className="flex min-h-11 cursor-pointer list-none items-center justify-center gap-1 text-xs font-semibold text-muted-foreground">Mai mult: piramidele <span className="transition-transform group-open:rotate-180">▾</span></summary>
        <div className="pt-2"><Pyramids today={today} /></div>
      </details>

    </div>
  );
}

function Pyramids({ today }: { today: string }) {
  const a = useAsync(loadPyramid, []);
  const b = useAsync(loadPyramid140, []);
  const c = useAsync(loadPyramidMici, []);
  const tiles = [
    { name: 'Piramida 2.00', st: a, q: '' },
    { name: 'Piramida 1.40', st: b, q: '?p=140' },
    { name: 'Piramida mici', st: c, q: '?p=mici' },
  ];
  return (
    <section aria-label="Piramide" className="grid grid-cols-3 gap-2">
      {tiles.map(({ name, st, q }) => {
        const s = st.data;
        const main = s?.date === today && s.today?.status === 'pick' ? s.today.main : null;
        return (
          <Link key={name} to={`/piramida${q}`} className={cn('dash-pyr press', main && 'dash-pyr-on')}>
            <IconPyramid className="h-4 w-4 text-primary" />
            <span className="text-[10px] font-extrabold uppercase tracking-wider text-muted-foreground">{name}</span>
            <span className={cn('num text-[20px] font-extrabold leading-none', main ? 'text-primary' : 'text-warn')}>{st.loading ? '…' : main ? fo(main.total_odds) : 'Pauză'}</span>
            <span className="max-w-full truncate text-[10px] text-muted-foreground">{main ? `${main.legs.length} meciuri` : s?.action?.short ?? 'nu se joacă'}</span>
          </Link>
        );
      })}
    </section>
  );
}
