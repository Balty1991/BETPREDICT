import { useMemo, useState, type ReactNode } from 'react';
import { Link } from 'react-router';
import { Activity, ArrowDownRight, ArrowUpRight, BarChart3, Blocks, CalendarClock, ChevronRight, Flame, Gauge, LineChart, Radar, ShieldCheck, Sparkles, Star, Ticket as TicketIcon, Timer, Trophy } from 'lucide-react';
import { useDays, useMeta, useSettledTickets, usePersistMySettlement, useTodayBoard } from '@/lib/hooks';
import { getJSON, useAsync } from '@/lib/fetcher';
import { loadJournalRows, loadPyramid, loadPyramid140, loadPyramidMici, loadTicketsHistory } from '@/lib/data';
import { useStore } from '@/lib/store';
import { addDays, longDay, odds as fo, roDay, roKickoff, roTime, todayRo } from '@/lib/format';
import { isRecommended } from '@/lib/rules';
import { isBest, pickBoard } from '@/lib/board';
import type { Ticket } from '@/lib/types';
import { perfByDay, perfOf, sumPerf, ticketsByDay, todayPulse, type DayPerf, type Scope } from '@/lib/dashboard';
import { Bars, Clock, CountUp, Countdown, Donut, donutColor, Panel, ResultBar, Ring, Spark } from '@/components/dash';
import { IconPredict, IconPyramid, IconStats } from '@/components/icons';
import { ProbRing, Segmented, Skeleton, TeamLogo } from '@/components/kit';
import { cn } from '@/lib/utils';
import { BudgetBar } from '@/components/BudgetBar';
import { budgetLei, weekSpent } from '@/lib/stake';

const SCOPES: Array<{ value: Scope; label: string }> = [
  { value: 'toate', label: 'Toate' },
  { value: 'p80', label: '80%+' },
  { value: 'rec', label: 'Recomandate' },
];

const shortDay = new Intl.DateTimeFormat('ro-RO', { timeZone: 'UTC', weekday: 'short', day: 'numeric' });
const dayName = (d: string, today: string) => (d === addDays(today, -1) ? 'Ieri' : d === today ? 'Azi' : shortDay.format(new Date(`${d}T12:00:00Z`)));
const roNum = (n: number, digits: number) => n.toLocaleString('ro-RO', { minimumFractionDigits: digits, maximumFractionDigits: digits });
const pctTxt = (v: number | null, digits = 0) => (v == null ? '—' : `${roNum(v * 100, digits)}%`);
const signedPct = (v: number | null) => (v == null ? '—' : `${v > 0 ? '+' : ''}${roNum(v * 100, 1)}%`);
const tone = (v: number | null) => (v == null ? '' : v >= 0 ? 'text-win' : 'text-loss');

type Boost = { match_id: number; home: string; away: string; kickoff_utc: string; label: string; price: number; ev?: number | null; reliable?: boolean; suspect?: boolean };
const shortName = (t: Ticket) => (t.variant_label ?? 'Bilet').replace(/^Stil Supersocial\s*·\s*/, '').replace(/^Pe val\s*·\s*/, '') || 'Stil Supersocial';

/** „Azi de jucat”: cele mai bune bilete din listă (cotă, sistem recomandat), cea mai bună cotă mărită +EV și auditul. */
function TodayPicks({ board, loading }: { board: Ticket[]; loading: boolean }) {
  const boosts = useAsync(() => getJSON<{ boosts: Boost[] }>('api/boosts/today.json'), []);
  const [now] = useState(() => Date.now());
  const open = board.filter((t) => t.status === 'pending' && t.legs.every((l) => !l.kickoff_utc || Date.parse(l.kickoff_utc) > now));
  const top = [...open].sort((a, b) => Number(isBest(b)) - Number(isBest(a)) || (b.ev ?? -9) - (a.ev ?? -9)).slice(0, 3);
  const budget = useStore((st) => st.settings.weeklyBudget ?? 50);
  const spent = useStore((st) => weekSpent(st.myTickets));
  const big = open.filter((t) => (t.total_odds ?? 0) >= 100 && !(t as { informational?: boolean }).informational)
    .sort((a, b) => (a.total_odds ?? 0) - (b.total_odds ?? 0)).slice(0, 4);
  const best = (boosts.data?.boosts ?? []).filter((b) => (b.ev ?? -1) > 0 && b.reliable && !b.suspect && Date.parse(b.kickoff_utc) > now)
    .sort((a, b) => (b.ev ?? 0) - (a.ev ?? 0))[0];
  return (
    <Panel glow="b" title="Azi de jucat" icon={<Sparkles className="h-4 w-4" />} right={<Link to="/bilete" className="text-xs font-semibold text-primary">Toate biletele</Link>}>
      {loading ? <Skeleton className="h-24 w-full rounded-2xl" /> : (
        <div className="space-y-2">
          <p className="text-xs text-muted-foreground">{open.length ? `${open.length} bilete neîncepute în listă.` : 'Niciun bilet neînceput acum.'}</p>
          {big.length > 0 && <div className="text-[11px] font-bold uppercase tracking-wider text-primary">Cote mari 100+ / 500+ / 1000+ · miză mică</div>}
          {big.map((t) => { const lei = budgetLei(t, budget || 50, budget ? spent : 0); return (
            <Link key={`big-${t.id}`} to="/bilete" className="hot-ticket press">
              <Flame className="h-5 w-5 shrink-0 text-primary" aria-hidden />
              <span className="min-w-0 flex-1">
                <span className="block break-words text-sm font-bold leading-snug">{shortName(t)}</span>
                <span className="mt-1 flex flex-wrap items-center gap-1.5 text-[11px] text-muted-foreground">{t.legs.length} meciuri <span className="stake-chip">{lei ? `joacă ${lei} lei` : 'buget consumat'}</span></span>
              </span>
              <span className="big-num neon-text text-[26px]">{fo(t.total_odds)}</span>
            </Link>); })}
          {top.filter((t) => !big.includes(t)).map((t) => (
            <Link key={t.id} to="/bilete" className="dash-strip press">
              <TicketIcon className="h-4 w-4 shrink-0 text-primary" aria-hidden />
              <span className="min-w-0 flex-1">
                <span className="block break-words text-sm font-bold leading-snug">{isBest(t) ? '⭐ ' : ''}{shortName(t)}</span>
                <span className="block text-[11px] text-muted-foreground">{t.legs.length} meciuri</span>
              </span>
              <span className="num text-lg font-extrabold text-primary">{fo(t.total_odds)}</span>
            </Link>
          ))}
          {best && (
            <Link to="/statistici?tab=boosts" className="dash-strip press">
              <Flame className="h-4 w-4 shrink-0 text-[hsl(var(--glow-3))]" aria-hidden />
              <span className="min-w-0 flex-1">
                <span className="block text-[11px] font-bold uppercase tracking-wider text-muted-foreground">Cea mai bună cotă mărită · <span className="num">{roKickoff(best.kickoff_utc)}</span></span>
                <span className="block break-words text-sm font-bold leading-snug">{best.label}</span>
                <span className="block break-words text-[11px] text-muted-foreground">{best.home} – {best.away} · EV {signedPct(best.ev ?? null)} · se retrag repede</span>
              </span>
              <span className="num text-lg font-extrabold">{fo(best.price)}</span>
            </Link>
          )}
          <Link to="/statistici?tab=audit" className="press flex min-h-[40px] items-center gap-2 text-xs font-semibold text-primary"><BarChart3 className="h-4 w-4" />Audit piețe: ce câștigă și ce pierde pe cotele reale<ChevronRight className="ml-auto h-4 w-4" /></Link>
        </div>
      )}
    </Panel>
  );
}

/** Acasă: panoul zilei. Cifre, grafice și monitorizarea ultimelor zile. Biletele stau în pagina lor. */
export default function HomePage() {
  const today = todayRo();
  const yesterday = addDays(today, -1);
  const last3 = useMemo(() => [addDays(today, -3), addDays(today, -2), yesterday], [today, yesterday]);
  const week = useMemo(() => Array.from({ length: 7 }, (_, i) => addDays(today, i - 7)), [today]);

  const minOdds = useStore((s) => s.settings.minOdds);
  const days = useDays(useMemo(() => [today], [today]));
  const journal = useAsync(() => loadJournalRows(minOdds, 8), [minOdds]);
  const history = useAsync(loadTicketsHistory, []);
  const { board, loading: boardLoading } = useTodayBoard(today);
  const meta = useMeta();

  // biletele mele se decontează și aici, ca rezultatele să rămână salvate (ca înainte pe Acasă)
  const myTickets = useStore((s) => s.myTickets);
  const mySettled = useSettledTickets(myTickets);
  usePersistMySettlement(mySettled.tickets, myTickets);

  const [scope, setScope] = useState<Scope>('toate');
  const matches = useMemo(() => days.data?.[0]?.matches ?? [], [days.data]);
  const pulse = useMemo(() => todayPulse(matches, isRecommended, minOdds), [matches, minOdds]);
  // Stil Supersocial (cornere, reprize, intervale): meciurile de azi încă neîncepute cu o selecție de 80%+
  const ss = useAsync(() => getJSON<{ rows: Array<{ match_id: number; p: number; kickoff_utc: string }> }>('api/supersocial/today.json'), []);
  const ss80 = useMemo(() => {
    const open = new Set(matches.filter((m) => m.status === 'notstarted').map((m) => m.id));
    return new Set((ss.data?.rows ?? []).filter((r) => r.p >= 0.8 && roDay(r.kickoff_utc) === today && open.has(r.match_id)).map((r) => r.match_id)).size;
  }, [ss.data, today, matches]);
  const rows = useMemo(() => journal.data?.rows ?? [], [journal.data]);
  const perf3 = useMemo(() => perfByDay(rows, last3, scope), [rows, last3, scope]);
  const perfWeek = useMemo(() => perfByDay(rows, week, scope), [rows, week, scope]);
  const total3 = useMemo(() => sumPerf(perf3), [perf3]);
  const wrWeek = useMemo(() => perfWeek.map((d) => (d.won + d.lost ? d.winRate : null)), [perfWeek]);
  // scara se strânge pe datele reale (±10 pp), ca diferențele de la o zi la alta să se vadă
  const wrDomain = useMemo((): [number, number] => {
    const v = wrWeek.filter((x): x is number => x != null);
    return v.length ? [Math.max(0, Math.min(...v) - 0.1), Math.min(1, Math.max(...v) + 0.1)] : [0, 1];
  }, [wrWeek]);
  const todayLive = useMemo(() => perfOf(today, rows.filter((r) => r.date === today)), [rows, today]);
  const yPerf = perf3[2];
  const before = perf3[1];

  const pastBoard = useMemo(() => pickBoard((history.data ?? []).filter((t) => (t.date ?? '') < today && (t.date ?? '') >= last3[0])), [history.data, today, last3]);
  const tDays = useMemo(() => ticketsByDay(pastBoard, last3), [pastBoard, last3]);

  const loadingDay = days.loading;
  const loadingJ = journal.loading;

  return (
    <div className="dash space-y-4">
      <TodayPicks board={board} loading={boardLoading} />
      {/* ── HERO ─────────────────────────────────────── */}
      <section className="dash-hero" aria-labelledby="dash-title">
        <div className="dash-aurora" aria-hidden />
        <div className="dash-grid" aria-hidden />
        <div className="dash-scan" aria-hidden />
        <div className="relative">
          <div className="flex flex-wrap items-center gap-2">
            <span className="dash-live"><span className="dash-live-dot" aria-hidden />Live</span>
            <span className="text-xs font-semibold capitalize text-muted-foreground">{longDay(today)}</span>
            <Clock className="ml-auto text-xs font-bold text-muted-foreground" />
          </div>
          <h1 id="dash-title" className="dash-h1 mt-3">Azi, <span className="dash-gradient-text">pe scurt</span></h1>
          <p className="mt-1 text-sm text-muted-foreground">
            {loadingDay ? 'Se citesc meciurile…' : `${pulse.matches} meciuri · ${pulse.upcoming} urmează · ${pulse.live} în joc · ${pulse.finished} terminate`}
            {meta.data?.generated_at && <> · actualizat {roTime(meta.data.generated_at)}</>}
          </p>

          <div className="mt-4 grid grid-cols-2 gap-2.5 md:grid-cols-4">
            <Kpi to="/predictii" icon={<IconPredict className="h-4 w-4" />} label="Predicții azi" value={loadingDay ? null : pulse.preds} sub={`în ${pulse.withPreds} meciuri · ${pulse.available} cu cotă, de jucat`} accent="a" />
            <Kpi to="/predictii" icon={<Flame className="h-4 w-4" />} label="Meciuri 80%+" value={loadingDay ? null : pulse.p80Matches} sub={`${pulse.p80Open} de jucat · ${pulse.p80Cheap} sub ${minOdds}${ss.data ? ` · ${ss80} în Stil Supersocial` : ''}`} accent="b" hot />
            <Kpi to="/predictii" icon={<Star className="h-4 w-4" />} label="Recomandate" value={loadingDay ? null : pulse.rec} sub={`${pulse.value} cu valoare`} accent="c" />
            <Kpi to="/bilete" icon={<TicketIcon className="h-4 w-4" />} label="Bilete azi" value={boardLoading ? null : board.length} sub="în lista de azi" accent="d" />
          </div>
          <BudgetBar />

          <div className="mt-3 grid gap-2.5 sm:grid-cols-2">
            {pulse.next ? (
              <Link to={`/meci/${pulse.next.id}?zi=${roDay(pulse.next.kickoff_utc)}`} className="dash-strip press">
                <Timer className="h-4 w-4 shrink-0 text-primary" aria-hidden />
                <span className="min-w-0 flex-1">
                  <span className="block text-[11px] font-bold uppercase tracking-wider text-muted-foreground">Următorul meci · <span className="num">{roKickoff(pulse.next.kickoff_utc)}</span></span>
                  <span className="block break-words text-sm font-bold leading-snug">{pulse.next.home.name} – {pulse.next.away.name}</span>
                  <span className="block break-words text-[11px] text-muted-foreground">{pulse.next.league.name}</span>
                </span>
                <Countdown iso={pulse.next.kickoff_utc} className="dash-count text-lg font-extrabold" />
              </Link>
            ) : (
              <div className="dash-strip"><Timer className="h-4 w-4 text-muted-foreground" aria-hidden /><span className="text-sm text-muted-foreground">{loadingDay ? 'Se încarcă…' : 'Niciun meci nu mai urmează azi.'}</span></div>
            )}
            <div className="dash-strip">
              <Activity className="h-4 w-4 shrink-0 text-primary" aria-hidden />
              <span className="min-w-0 flex-1">
                <span className="block text-[11px] font-bold uppercase tracking-wider text-muted-foreground">Azi până acum</span>
                <span className="block text-sm font-bold">
                  {loadingJ ? '…' : todayLive.won + todayLive.lost === 0 ? 'Nimic decontat încă' : <><span className="text-win">{todayLive.won} câștigate</span> · <span className="text-loss">{todayLive.lost} pierdute</span></>}
                </span>
              </span>
              <span className={cn('num text-lg font-extrabold', (todayLive.winRate ?? 0) >= 0.5 ? 'text-win' : 'text-warn')}>{pctTxt(todayLive.winRate)}</span>
            </div>
          </div>
        </div>
      </section>


      {/* ── PERFORMANȚĂ ──────────────────────────────── */}
      <div className="flex flex-wrap items-center justify-between gap-2 pt-1">
        <h2 className="dash-section"><Gauge className="h-4 w-4" aria-hidden />Cum au ieșit</h2>
        <Segmented size="sm" value={scope} onChange={setScope} options={SCOPES} />
      </div>

      <div className="grid gap-4 lg:grid-cols-5">
        <Panel className="lg:col-span-2" glow="a" title="Ieri" icon={<Trophy className="h-4 w-4" />} right={<span className="text-xs text-muted-foreground">{longDay(yesterday)}</span>}>
          {loadingJ ? <Skeleton className="h-48 w-full rounded-2xl" /> : yPerf.n === 0 ? <p className="py-10 text-center text-sm text-muted-foreground">Nicio predicție ieri în această selecție.</p> : (
            <>
              <div className="flex items-center gap-4">
                <Ring value={yPerf.winRate} size={132} stroke={11} tone={(yPerf.winRate ?? 0) >= 0.5 ? 'win' : 'warn'} label="Rată de câștig ieri">
                  <div>
                    <div className="dash-ring-v"><CountUp value={yPerf.winRate == null ? null : yPerf.winRate * 100} digits={1} suffix="%" /></div>
                    <div className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground">winrate</div>
                  </div>
                </Ring>
                <dl className="grid min-w-0 flex-1 grid-cols-2 gap-x-3 gap-y-2.5">
                  <Mini k="Predicții" v={<CountUp value={yPerf.n} />} />
                  <Mini k="ROI" v={<CountUp value={yPerf.roi == null ? null : yPerf.roi * 100} digits={1} suffix="%" signed />} cls={tone(yPerf.roi)} />
                  <Mini k="Câștigate" v={<CountUp value={yPerf.won} />} cls="text-win" />
                  <Mini k="Pierdute" v={<CountUp value={yPerf.lost} />} cls="text-loss" />
                </dl>
              </div>
              <ResultBar className="mt-4" won={yPerf.won} lost={yPerf.lost} void={yPerf.void} pending={yPerf.pending} />
              <div className="mt-2 flex flex-wrap items-center justify-between gap-2 text-xs text-muted-foreground">
                <span>Profit <b className={cn('num', tone(yPerf.profit))}>{yPerf.profit > 0 ? '+' : ''}{roNum(yPerf.profit, 2)} u</b> pe {yPerf.staked} cu cotă{yPerf.void ? ` · ${yPerf.void} anulate` : ''}</span>
                <Trend now={yPerf.winRate} prev={before.winRate} />
              </div>
            </>
          )}
        </Panel>

        <Panel className="lg:col-span-3" glow="b" title="Ultimele 3 zile" icon={<CalendarClock className="h-4 w-4" />} right={<Link to="/istoric" className="text-xs font-bold text-primary">Istoric →</Link>}>
          {loadingJ ? <Skeleton className="h-48 w-full rounded-2xl" /> : (
            <>
              <div className="grid grid-cols-3 gap-2">
                {perf3.map((d, i) => <DayCard key={d.date} d={d} label={dayName(d.date, today)} delay={i} />)}
              </div>
              <div className="dash-total mt-3">
                <TotalCell k="Predicții" v={<CountUp value={total3.n} />} />
                <TotalCell k="✓ / ✗" v={<><span className="text-win">{total3.won}</span><span className="text-muted-foreground">/</span><span className="text-loss">{total3.lost}</span></>} />
                <TotalCell k="Winrate" v={<CountUp value={total3.winRate == null ? null : total3.winRate * 100} digits={1} suffix="%" />} />
                <TotalCell k="ROI" v={<CountUp value={total3.roi == null ? null : total3.roi * 100} digits={1} suffix="%" signed />} cls={tone(total3.roi)} />
              </div>
              <div className="mt-3">
                <div className="mb-1 flex items-center justify-between text-[11px] font-bold uppercase tracking-wider text-muted-foreground"><span>Winrate · 7 zile</span><span className="num">{pctTxt(perfWeek.at(-1)?.winRate ?? null)}</span></div>
                <Spark values={wrWeek} height={56} domain={wrDomain} label="Rata de câștig pe ultimele 7 zile" />
                <div className="mt-1 flex justify-between text-[10px] text-muted-foreground">{week.map((d) => <span key={d} className="num">{shortDay.format(new Date(`${d}T12:00:00Z`)).replace('.', '')}</span>)}</div>
              </div>
            </>
          )}
        </Panel>
      </div>

      {/* ── AZI ÎN GRAFICE ───────────────────────────── */}
      <h2 className="dash-section pt-1"><BarChart3 className="h-4 w-4" aria-hidden />Azi în grafice</h2>
      <div className="grid gap-4 md:grid-cols-3">
        <Panel title="Pe piețe" icon={<Radar className="h-4 w-4" />} glow="c">
          {loadingDay ? <Skeleton className="h-36 w-full rounded-2xl" /> : (
            <div className="flex items-center gap-4">
              <Donut parts={pulse.markets.map((m) => ({ label: m.label, n: m.n }))}>
                <div><div className="dash-ring-v"><CountUp value={pulse.preds} /></div><div className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground">predicții</div></div>
              </Donut>
              <ul className="min-w-0 flex-1 space-y-1.5 text-xs">
                {pulse.markets.slice(0, 6).map((m, i) => (
                  <li key={m.key} className="flex items-center gap-2"><i className="h-2.5 w-2.5 shrink-0 rounded-full" style={{ background: donutColor(i), boxShadow: `0 0 8px ${donutColor(i)}` }} /><span className="min-w-0 flex-1 truncate">{m.label}</span><b className="num">{m.n}</b></li>
                ))}
              </ul>
            </div>
          )}
        </Panel>
        <Panel title="Pe șansă" icon={<ShieldCheck className="h-4 w-4" />}>
          {loadingDay ? <Skeleton className="h-36 w-full rounded-2xl" /> : (
            <>
              <Bars data={pulse.bands.map((b) => ({ k: `${b.key}%`.replace('<50%', '<50'), n: b.n }))} height={120} highlight={(k) => k.startsWith('80') || k.startsWith('90')} label="Predicții pe trepte de șansă" />
              <p className="mt-2 text-xs text-muted-foreground"><b className="text-foreground">{pulse.p80}</b> din {pulse.preds} au șansă de cel puțin 80%.</p>
            </>
          )}
        </Panel>
        <Panel title="Pe ore" icon={<Timer className="h-4 w-4" />}>
          {loadingDay ? <Skeleton className="h-36 w-full rounded-2xl" /> : pulse.hours.length ? (
            <>
              <Bars data={pulse.hours.map((h) => ({ k: String(h.h).padStart(2, '0'), n: h.n }))} height={120} highlight={(k) => Number(k) === Number(new Intl.DateTimeFormat('ro-RO', { timeZone: 'Europe/Bucharest', hour: '2-digit', hourCycle: 'h23' }).format(new Date()))} label="Meciuri pe ora de start" />
              <p className="mt-2 text-xs text-muted-foreground">Câte meciuri încep la fiecare oră. Ora curentă e aprinsă.</p>
            </>
          ) : <p className="py-10 text-center text-sm text-muted-foreground">Fără meciuri azi.</p>}
        </Panel>
      </div>

      {/* ── CELE MAI SIGURE + BILETE ─────────────────── */}
      <div className="grid gap-4 lg:grid-cols-5">
        <Panel className="lg:col-span-3" title="Cele mai sigure, încă de jucat" icon={<Sparkles className="h-4 w-4" />} glow="a" right={<Link to="/predictii" className="text-xs font-bold text-primary">Toate →</Link>}>
          {loadingDay ? <Skeleton className="h-56 w-full rounded-2xl" /> : pulse.top.length ? (
            <ol className="stagger space-y-2">
              {pulse.top.map(({ m, p }, i) => (
                <li key={`${m.id}-${p.id}`}>
                  <Link to={`/meci/${m.id}?zi=${roDay(m.kickoff_utc)}`} className="dash-row press">
                    <span className="dash-rank num">{i + 1}</span>
                    <ProbRing p={p.p} size={42} stroke={4} label="Șansă" />
                    <span className="min-w-0 flex-1">
                      <span className="flex items-start gap-1.5 text-[11px] leading-snug text-muted-foreground"><span className="mt-px shrink-0"><TeamLogo src={m.league.logo} name={m.league.name} size={12} /></span><span className="min-w-0 break-words">{m.league.name}</span></span>
                      <span className="block break-words text-sm font-bold leading-snug">{m.home.name} – {m.away.name}</span>
                      <span className="mt-0.5 flex flex-wrap items-center gap-x-2 text-xs"><b className="text-primary">{p.label}</b><span className="num text-muted-foreground">{roKickoff(m.kickoff_utc)}</span></span>
                    </span>
                    <span className="dash-odds num">{fo(p.odds)}</span>
                  </Link>
                </li>
              ))}
            </ol>
          ) : <p className="py-10 text-center text-sm text-muted-foreground">Nicio selecție de minim 70% cu cotă nu mai urmează azi.</p>}
        </Panel>

        <Panel className="lg:col-span-2" title="Bilete" icon={<TicketIcon className="h-4 w-4" />} glow="b" right={<Link to="/bilete" className="text-xs font-bold text-primary">Deschide →</Link>}>
          <Link to="/bilete" className="dash-tickets-big press">
            <span className="dash-ring-v text-[44px]"><CountUp value={boardLoading ? null : board.length} /></span>
            <span className="text-sm text-muted-foreground">bilete în lista de azi<br /><span className="text-xs">cel mult 10, max. 3 meciuri comune</span></span>
            <ChevronRight className="ml-auto h-5 w-5 text-muted-foreground" aria-hidden />
          </Link>
          <div className="mt-3 space-y-2">
            {history.loading ? <Skeleton className="h-24 w-full rounded-2xl" /> : tDays.map((d) => (
              <div key={d.date} className="flex items-center gap-3">
                <span className="w-12 shrink-0 text-xs font-bold capitalize text-muted-foreground">{dayName(d.date, today)}</span>
                <ResultBar className="flex-1" won={d.won} lost={d.lost} void={0} pending={d.pending} />
                <span className="num w-16 shrink-0 text-right text-xs font-bold">{d.n ? <><span className="text-win">{d.won}</span>/<span className="text-loss">{d.lost}</span>{d.pending ? <span className="text-muted-foreground">/{d.pending}</span> : null}</> : <span className="text-muted-foreground">—</span>}</span>
              </div>
            ))}
            <p className="text-[11px] text-muted-foreground">Verde câștigate, roșu pierdute, gri încă în joc.</p>
          </div>
        </Panel>
      </div>

      {/* ── PIRAMIDE + SCURTĂTURI ────────────────────── */}
      <Pyramids today={today} />

      <nav aria-label="Scurtături" className="grid grid-cols-3 gap-2 md:grid-cols-6">
        {[
          { to: '/predictii', t: 'Predicții', i: <IconPredict className="h-5 w-5" /> },
          { to: '/bilete', t: 'Bilete', i: <TicketIcon className="h-5 w-5" /> },
          { to: '/piramida', t: 'Piramida', i: <IconPyramid className="h-5 w-5" /> },
          { to: '/statistici', t: 'Statistici', i: <IconStats className="h-5 w-5" /> },
          { to: '/istoric', t: 'Istoric', i: <CalendarClock className="h-5 w-5" /> },
          { to: '/builder', t: 'Builder', i: <Blocks className="h-5 w-5" /> },
        ].map((x) => (
          <Link key={x.to} to={x.to} className="dash-shortcut press"><span className="dash-ico">{x.i}</span><span className="text-xs font-bold">{x.t}</span></Link>
        ))}
      </nav>
      <p className="flex items-center justify-center gap-1.5 text-center text-[11px] text-muted-foreground"><LineChart className="h-3.5 w-3.5" aria-hidden />ROI la 1 unitate pe fiecare selecție cu cotă. Winrate = câștigate ÷ (câștigate + pierdute).</p>
    </div>
  );
}

function Kpi({ to, icon, label, value, sub, accent, hot }: { to: string; icon: ReactNode; label: string; value: number | null; sub: string; accent: 'a' | 'b' | 'c' | 'd'; hot?: boolean }) {
  return (
    <Link to={to} className={cn('dash-kpi press', `dash-kpi-${accent}`)}>
      <span className="flex items-center gap-1.5 text-[11px] font-bold uppercase tracking-wider text-muted-foreground"><span className="dash-kpi-ico">{icon}</span>{label}</span>
      <span className={cn('dash-kpi-v', hot && 'dash-gradient-text')}>{value == null ? <span className="skeleton inline-block h-8 w-14 rounded-lg align-middle" /> : <CountUp value={value} />}</span>
      <span className="text-[11px] leading-snug text-muted-foreground">{sub}</span>
    </Link>
  );
}

function Mini({ k, v, cls }: { k: string; v: ReactNode; cls?: string }) {
  return (
    <div className="min-w-0">
      <dt className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground">{k}</dt>
      <dd className={cn('text-[22px] font-extrabold leading-tight', cls)}>{v}</dd>
    </div>
  );
}

function TotalCell({ k, v, cls }: { k: string; v: ReactNode; cls?: string }) {
  return (
    <div className="min-w-0 text-center">
      <div className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground">{k}</div>
      <div className={cn('num text-base font-extrabold', cls)}>{v}</div>
    </div>
  );
}

function Trend({ now, prev }: { now: number | null; prev: number | null }) {
  if (now == null || prev == null) return null;
  const d = now - prev;
  const up = d >= 0;
  return (
    <span className={cn('inline-flex items-center gap-0.5 font-bold', up ? 'text-win' : 'text-loss')}>
      {up ? <ArrowUpRight className="h-3.5 w-3.5" aria-hidden /> : <ArrowDownRight className="h-3.5 w-3.5" aria-hidden />}
      {up ? '+' : ''}{roNum(d * 100, 1)} pp față de alaltăieri
    </span>
  );
}

function DayCard({ d, label, delay }: { d: DayPerf; label: string; delay: number }) {
  return (
    <Link to={`/istoric?zi=${d.date}`} className="dash-day press" style={{ animationDelay: `${delay * 90}ms` }} aria-label={`${label}: deschide istoricul zilei`}>
      <div className="text-[11px] font-extrabold uppercase tracking-wider text-muted-foreground">{label}</div>
      <Ring value={d.winRate} size={68} stroke={6} tone={d.winRate == null ? 'primary' : d.winRate >= 0.5 ? 'win' : 'warn'} label={`Rată de câștig ${label}`}>
        <span className="num text-[13px] font-extrabold">{pctTxt(d.winRate)}</span>
      </Ring>
      <div className="num text-xs font-bold"><span className="text-win">{d.won}</span><span className="text-muted-foreground"> / </span><span className="text-loss">{d.lost}</span></div>
      <div className={cn('num text-sm font-extrabold', tone(d.roi))}>{signedPct(d.roi)}</div>
      <div className="text-[10px] text-muted-foreground">{d.n} predicții</div>
    </Link>
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
