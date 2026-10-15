import { useMemo, useState } from 'react';
import { Link, useSearchParams } from 'react-router';
import { CalendarDays, CheckCircle2, ChevronRight, Ticket as TicketIcon, XCircle, MinusCircle, Clock } from 'lucide-react';
import { useAsync, getJSON } from '@/lib/fetcher';
import { loadJournalRows, loadPyramid, loadPyramid140, loadPyramidMici, loadTicketsHistory } from '@/lib/data';
import { useStore } from '@/lib/store';
import { addDays, longDay, odds as fo, todayRo } from '@/lib/format';
import { pickBoard } from '@/lib/board';
import { inScope, perfOf, type Scope } from '@/lib/dashboard';
import { STATS_SINCE } from '@/lib/rules';
import { TicketCard } from '@/components/TicketCard';
import { CountUp, Panel, ResultBar, Ring } from '@/components/dash';
import { Badge, Empty, Segmented, Skeleton } from '@/components/kit';
import { IconPyramid } from '@/components/icons';
import type { JournalRow, PyramidState } from '@/lib/types';
import { cn } from '@/lib/utils';

const SCOPES: Array<{ value: Scope; label: string }> = [
  { value: 'rec', label: 'Recomandate' },
  { value: 'p80', label: '80%+' },
  { value: 'toate', label: 'Toate' },
];
const chipWd = new Intl.DateTimeFormat('ro-RO', { timeZone: 'UTC', weekday: 'short' });
const chipDm = new Intl.DateTimeFormat('ro-RO', { timeZone: 'UTC', day: 'numeric', month: 'short' });
const noon = (d: string) => new Date(`${d}T12:00:00Z`);
const roPct = (v: number | null, d = 0) => (v == null ? '—' : `${(v * 100).toFixed(d).replace('.', ',')}%`);

function ResultIcon({ r }: { r: JournalRow['result'] }) {
  if (r === 'won' || r === 'half_won') return <CheckCircle2 className="h-5 w-5 shrink-0 text-win" aria-label="Câștigat" />;
  if (r === 'lost' || r === 'half_lost') return <XCircle className="h-5 w-5 shrink-0 text-loss" aria-label="Pierdut" />;
  if (r === 'void') return <MinusCircle className="h-5 w-5 shrink-0 text-muted-foreground" aria-label="Anulat" />;
  return <Clock className="h-5 w-5 shrink-0 text-muted-foreground" aria-label="În joc" />;
}

/** Istoric: alegi o zi trecută și vezi ce a dat Robotul și ce a ieșit. */
export default function HistoryPage() {
  const today = todayRo();
  const [sp, setSp] = useSearchParams();
  const day = sp.get('zi') && sp.get('zi')! < today && sp.get('zi')! >= STATS_SINCE ? sp.get('zi')! : addDays(today, -1);
  const setDay = (d: string) => { sp.set('zi', d); setSp(sp, { replace: true }); };
  const [scope, setScope] = useState<Scope>('rec');
  const [limit, setLimit] = useState(30);

  const minOdds = useStore((s) => s.settings.minOdds);
  const journal = useAsync(() => loadJournalRows(minOdds, 120), [minOdds]);
  const history = useAsync(loadTicketsHistory, []);
  const pyr = useAsync(async () => Promise.all([loadPyramid(), loadPyramid140(), loadPyramidMici()]), []);

  const days = useMemo(() => {
    const out: string[] = [];
    for (let d = addDays(today, -1); d >= STATS_SINCE && out.length < 14; d = addDays(d, -1)) out.push(d);
    return out;
  }, [today]);
  const rows = useMemo(() => (journal.data?.rows ?? []).filter((r) => r.date === day), [journal.data, day]);
  const scoped = useMemo(() => rows.filter((r) => inScope(r, scope)).sort((a, b) => (b.p ?? 0) - (a.p ?? 0)), [rows, scope]);
  const perf = useMemo(() => perfOf(day, scoped), [day, scoped]);
  const board = useMemo(() => pickBoard((history.data ?? []).filter((t) => t.date === day)), [history.data, day]);
  const bw = board.filter((t) => t.status === 'won').length, bl = board.filter((t) => t.status === 'lost').length;

  return (
    <div className="space-y-4">
      <header>
        <div className="eyebrow">Ce a dat Robotul și ce a ieșit</div>
        <h1>Istoric</h1>
      </header>

      <div className="scrollbar-none -mx-4 flex gap-2 overflow-x-auto px-4 pb-1" role="group" aria-label="Alege ziua">
        {days.map((d) => (
          <button key={d} type="button" aria-pressed={d === day} onClick={() => { setDay(d); setLimit(30); }}
            className={cn('press shrink-0 rounded-2xl border px-3 py-2 text-center text-xs font-bold', d === day ? 'border-primary/60 bg-primary text-primary-foreground' : 'bg-card text-muted-foreground')}>
            <span className="block capitalize">{d === addDays(today, -1) ? 'Ieri' : chipWd.format(noon(d)).replace(/[.,]/g, '')}</span>
            <span className="block text-[13px]">{chipDm.format(noon(d)).replace(/\.$/, '')}</span>
          </button>
        ))}
      </div>

      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="flex items-center gap-2 text-base"><CalendarDays className="h-4 w-4 text-primary" />{longDay(day)}</h2>
        <Segmented size="sm" value={scope} onChange={(v) => { setScope(v); setLimit(30); }} options={SCOPES} />
      </div>

      {journal.loading ? <Skeleton className="h-40 w-full rounded-3xl" /> : (
        <Panel glow="a">
          {perf.n === 0 ? <p className="py-6 text-center text-sm text-muted-foreground">Nicio predicție în această selecție în ziua asta.</p> : (
            <>
              <div className="flex items-center gap-4">
                <Ring value={perf.winRate} size={112} stroke={10} tone={(perf.winRate ?? 0) >= 0.5 ? 'win' : 'warn'} label="Rată de câștig">
                  <div><div className="dash-ring-v text-[20px]"><CountUp value={perf.winRate == null ? null : perf.winRate * 100} digits={1} suffix="%" /></div><div className="text-[9px] font-bold uppercase tracking-widest text-muted-foreground">winrate</div></div>
                </Ring>
                <dl className="grid min-w-0 flex-1 grid-cols-2 gap-x-3 gap-y-2">
                  <div><dt className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground">Predicții</dt><dd className="text-[20px] font-extrabold"><CountUp value={perf.n} /></dd></div>
                  <div><dt className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground">ROI</dt><dd className={cn('text-[20px] font-extrabold', (perf.roi ?? 0) >= 0 ? 'text-win' : 'text-loss')}><CountUp value={perf.roi == null ? null : perf.roi * 100} digits={1} suffix="%" signed /></dd></div>
                  <div><dt className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground">Câștigate</dt><dd className="text-[20px] font-extrabold text-win"><CountUp value={perf.won} /></dd></div>
                  <div><dt className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground">Pierdute</dt><dd className="text-[20px] font-extrabold text-loss"><CountUp value={perf.lost} /></dd></div>
                </dl>
              </div>
              <ResultBar className="mt-3" won={perf.won} lost={perf.lost} void={perf.void} pending={perf.pending} />
              <p className="mt-2 text-xs text-muted-foreground">Profit {perf.profit >= 0 ? '+' : ''}{perf.profit.toFixed(2).replace('.', ',')} u la 1 unitate pe selecție{perf.void ? ` · ${perf.void} anulate` : ''}{perf.pending ? ` · ${perf.pending} nedecontate` : ''}.</p>
            </>
          )}
        </Panel>
      )}

      <Pyramids day={day} states={pyr.data ?? null} loading={pyr.loading} />

      <section aria-label="Bilete jucate" className="space-y-2">
        <h2 className="flex items-center gap-2 text-base"><TicketIcon className="h-4 w-4 text-primary" />Biletele zilei
          {board.length > 0 && <span className="text-xs font-semibold text-muted-foreground"><span className="text-win">{bw} câștigate</span> · <span className="text-loss">{bl} pierdute</span>{board.length - bw - bl ? ` · ${board.length - bw - bl} în joc` : ''}</span>}
        </h2>
        {history.loading ? <Skeleton className="h-32 w-full rounded-2xl" /> : board.length ? (
          <details className="card group">
            <summary className="flex min-h-[52px] cursor-pointer list-none items-center gap-2 px-4 font-bold">{board.length} {board.length === 1 ? 'bilet' : 'bilete'} din listă<ChevronRight className="ml-auto h-4 w-4 text-muted-foreground transition-transform group-open:rotate-90" /></summary>
            <div className="space-y-3 px-2 pb-3">{board.map((t) => <TicketCard key={t.id} t={t} compact />)}</div>
          </details>
        ) : <p className="text-sm text-muted-foreground">Niciun bilet în listă în ziua asta.</p>}
      </section>

      <SsDay day={day} />

      <section aria-label="Selecțiile zilei" className="space-y-2">
        <h2 className="text-base">Selecțiile zilei <span className="text-xs font-semibold text-muted-foreground">după șansă</span></h2>
        {journal.loading ? <Skeleton className="h-60 w-full rounded-2xl" /> : !scoped.length ? <Empty title="Nimic aici" icon={<CalendarDays className="h-6 w-6" />}>Alege „Toate” sau altă zi.</Empty> : (
          <>
            <ul className="card divide-y px-3">
              {scoped.slice(0, limit).map((r, i) => (
                <li key={`${r.match_id}-${r.market}-${r.label}-${i}`}>
                  <Link to={`/meci/${r.match_id}?zi=${r.date}`} className="flex items-center gap-3 py-2.5">
                    <ResultIcon r={r.result} />
                    <span className="min-w-0 flex-1">
                      <span className="block break-words text-[11px] text-muted-foreground">{r.league}</span>
                      <span className="block break-words text-sm font-bold leading-snug">{r.match}{r.score ? <b className="num ml-1.5 text-foreground">{r.score}</b> : null}</span>
                      <span className="block text-xs font-semibold text-primary">{r.label}</span>
                    </span>
                    <span className="flex shrink-0 flex-col items-end gap-0.5">
                      <span className="num text-sm font-extrabold">{fo(r.odds)}</span>
                      <span className="num text-[11px] text-muted-foreground">{roPct(r.p)}</span>
                    </span>
                  </Link>
                </li>
              ))}
            </ul>
            {scoped.length > limit && <button type="button" className="btn btn-outline w-full" onClick={() => setLimit((n) => n + 30)}>Mai multe ({scoped.length - limit} rămase)</button>}
          </>
        )}
      </section>
    </div>
  );
}

function Pyramids({ day, states, loading }: { day: string; states: Array<PyramidState | null> | null; loading: boolean }) {
  const names = ['Piramida 2.00', 'Piramida 1.40', 'Piramida mici'];
  const qs = ['', '?p=140', '?p=mici'];
  return (
    <section aria-label="Piramidele zilei" className="grid grid-cols-3 gap-2">
      {names.map((name, i) => {
        const h = states?.[i]?.history?.find((r) => r.date === day);
        const res = h?.result;
        const txt = loading ? '…' : !h ? '—' : h.status !== 'pick' ? 'Pauză' : res === 'won' ? 'Câștigat' : res === 'lost' ? 'Pierdut' : res === 'void' ? 'Anulat' : 'În joc';
        return (
          <Link key={name} to={`/piramida${qs[i]}`} className={cn('dash-pyr press', res === 'won' && 'dash-pyr-on')}>
            <IconPyramid className="h-4 w-4 text-primary" />
            <span className="text-[10px] font-extrabold uppercase tracking-wider text-muted-foreground">{name}</span>
            <span className={cn('text-[17px] font-extrabold leading-none', res === 'won' ? 'text-win' : res === 'lost' ? 'text-loss' : 'text-warn')}>{txt}</span>
            <span className="num text-[10px] text-muted-foreground">{h?.odds ? `cota ${fo(h.odds)}` : ' '}</span>
          </Link>
        );
      })}
    </section>
  );
}

type SsAgg = { n: number; won: number; lost: number; void: number; pending: number; win_rate: number | null; implied: number | null; roi: number | null };
type SsHist = { days: Array<SsAgg & { date: string; markets: Array<SsAgg & { key: string; label: string }>;
  top: Array<{ match_id: number; home: string; away: string; key: string; label: string; p: number; odds: number; result: string | null; score: string | null; corners: number | null }> }> };
const pct0 = (v: number | null) => (v == null ? '—' : `${Math.round(v * 100)}%`);
const sgn = (v: number | null) => (v == null ? '—' : `${v > 0 ? '+' : ''}${(v * 100).toFixed(1).replace('.', ',')}%`);

/** Stil Supersocial în ziua aleasă: toate selecțiile urmărite (cu preț Superbet), nu doar cele de pe bilete. */
function SsDay({ day }: { day: string }) {
  const h = useAsync(() => getJSON<SsHist>('api/supersocial/history.json'), []);
  const [open, setOpen] = useState(false);
  const d = h.data?.days.find((x) => x.date === day);
  if (h.loading) return <Skeleton className="h-32 w-full rounded-2xl" />;
  if (!d) return null;
  return (
    <Panel title="Stil Supersocial" glow="b" right={<span className="text-xs text-muted-foreground">{d.n} selecții urmărite</span>}>
      <div className="grid grid-cols-4 gap-2 text-center">
        <div><div className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground">Intrate</div><div className="num text-lg font-extrabold"><span className="text-win">{d.won}</span><span className="text-muted-foreground">/</span><span className="text-loss">{d.lost}</span></div></div>
        <div><div className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground">Winrate</div><div className="num text-lg font-extrabold">{pct0(d.win_rate)}</div></div>
        <div><div className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground">Cota promitea</div><div className="num text-lg font-extrabold text-muted-foreground">{pct0(d.implied)}</div></div>
        <div><div className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground">ROI</div><div className={cn('num text-lg font-extrabold', (d.roi ?? 0) >= 0 ? 'text-win' : 'text-loss')}>{sgn(d.roi)}</div></div>
      </div>
      <ResultBar className="mt-3" won={d.won} lost={d.lost} void={d.void} pending={d.pending} />
      <div className="mt-3 overflow-x-auto">
        <table className="w-full text-xs">
          <thead className="text-muted-foreground"><tr><th className="py-1 text-left">Piață</th><th className="text-right">✓/✗</th><th className="text-right">Intră</th><th className="text-right">Cota</th><th className="text-right">ROI</th></tr></thead>
          <tbody>{d.markets.filter((m) => m.won + m.lost > 0).map((m) => (
            <tr key={m.key} className="border-t">
              <td className="py-1.5 pr-2">{m.label}</td>
              <td className="num text-right"><span className="text-win">{m.won}</span>/<span className="text-loss">{m.lost}</span></td>
              <td className={cn('num text-right font-bold', m.win_rate != null && m.implied != null && m.win_rate >= m.implied ? 'text-win' : 'text-loss')}>{pct0(m.win_rate)}</td>
              <td className="num text-right text-muted-foreground">{pct0(m.implied)}</td>
              <td className={cn('num text-right', (m.roi ?? 0) >= 0 ? 'text-win' : 'text-loss')}>{sgn(m.roi)}</td>
            </tr>
          ))}</tbody>
        </table>
      </div>
      <p className="mt-2 text-[11px] text-muted-foreground">Verde: piața a intrat mai des decât promitea cota. ROI la 1 unitate pe fiecare selecție, la prețul Superbet de dinainte de start.</p>
      {d.top.length > 0 && (
        <details className="mt-2" onToggle={(e) => setOpen(e.currentTarget.open)}>
          <summary className="cursor-pointer text-sm font-bold text-primary">Cele mai sigure {d.top.length}, cu rezultatul</summary>
          {open && <ul className="mt-2 divide-y">
            {d.top.map((r, i) => (
              <li key={`${r.match_id}-${r.key}-${i}`} className="flex items-center gap-2 py-2">
                <ResultIcon r={(r.result ?? 'pending') as JournalRow['result']} />
                <span className="min-w-0 flex-1">
                  <span className="block break-words text-sm font-semibold leading-snug">{r.home} – {r.away}{r.score ? <b className="num ml-1.5">{r.score}</b> : null}{r.corners != null ? <span className="ml-1.5 text-[11px] text-muted-foreground">· {r.corners} cornere</span> : null}</span>
                  <span className="block text-xs font-semibold text-primary">{r.label}</span>
                </span>
                <span className="flex shrink-0 flex-col items-end"><span className="num text-sm font-extrabold">{fo(r.odds)}</span><Badge tone="muted">{Math.round(r.p * 100)}%</Badge></span>
              </li>
            ))}
          </ul>}
        </details>
      )}
    </Panel>
  );
}
