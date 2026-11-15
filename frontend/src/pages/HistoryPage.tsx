import { useMemo } from 'react';
import { Link, useSearchParams } from 'react-router';
import { useAsync, getJSON } from '@/lib/fetcher';
import { loadJournalRows, loadPyramidSafe, loadTicketsHistory } from '@/lib/data';
import { addDays, longDay, odds as fo, todayRo } from '@/lib/format';
import { STATS_SINCE } from '@/lib/rules';
import { TicketCard } from '@/components/TicketCard';
import { Skeleton } from '@/components/kit';
import { cn } from '@/lib/utils';

const chipWd = new Intl.DateTimeFormat('ro-RO', { timeZone: 'UTC', weekday: 'short' });
const chipDm = new Intl.DateTimeFormat('ro-RO', { timeZone: 'UTC', day: 'numeric', month: 'short' });
const noon = (d: string) => new Date(`${d}T12:00:00Z`);
const MEASURED = 'BB_G05_C75';

type SsMarket = { key: string; label?: string; n: number; won: number; lost: number; pending: number };
type SsDay = { date: string; n: number; won: number; lost: number; pending: number; markets?: SsMarket[] };
type SsHist = { days?: SsDay[] };
type ExpLine = { odds?: number | null; result?: 'won' | 'lost' | null };
type ExpDay = { matches?: Array<{ markets?: ExpLine[] }> };

function counts(rows: Array<{ result?: string | null }>) {
  let won = 0, lost = 0, pending = 0;
  for (const r of rows) {
    if (r.result === 'won') won += 1;
    else if (r.result === 'lost') lost += 1;
    else if (r.result === 'void' || r.result === 'half_won' || r.result === 'half_lost') continue;
    else pending += 1;
  }
  return { won, lost, pending, n: rows.length };
}
function countLine(won: number, lost: number, pending: number) {
  const bits = [`${won} câștigate`, `${lost} pierdute`];
  if (pending) bits.push(`${pending} în joc`);
  return bits.join(' · ');
}

/** Istoric: ziua, piramida de cotă 2 (doar seria nouă), cornerele și rubricile de predicții. */
export default function HistoryPage() {
  const today = todayRo();
  const [sp, setSp] = useSearchParams();
  const q = sp.get('zi');
  const day = q && q <= today && q >= STATS_SINCE ? q : today;
  const setDay = (d: string) => { sp.set('zi', d); setSp(sp, { replace: true }); };
  const history = useAsync(loadTicketsHistory, []);
  const pyr = useAsync(() => loadPyramidSafe('1.20'), []);
  const journal = useAsync(() => loadJournalRows(1, 21), []);
  const stil = useAsync(() => getJSON<SsHist>('api/supersocial/history.json'), []);
  const exp = useAsync(() => getJSON<ExpDay>(`api/experimental/${day}.json`), [day]);
  const days = useMemo(() => {
    const out: string[] = [];
    for (let d = today; d >= STATS_SINCE && out.length < 14; d = addDays(d, -1)) out.push(d);
    return out;
  }, [today]);
  const corners = useMemo(() => (history.data ?? []).filter((t) => t.kind === 'acca_corners' && (t.date ?? '') === day), [history.data, day]);
  const won = corners.filter((t) => t.status === 'won').length;
  const lost = corners.filter((t) => t.status === 'lost').length;
  const start = pyr.data?.run?.start_date || null;
  const step = (pyr.data?.history ?? []).find((r) => r.date === day && (!start || r.date >= start));
  const before = !!start && day < start;
  const stepTxt = pyr.loading ? '…' : before ? 'înainte de serie' : !step ? 'fără pas' : step.status !== 'pick' ? 'pauză' : step.result === 'won' ? 'câștigat' : step.result === 'lost' ? 'pierdut' : 'în joc';
  const stepSub = pyr.loading ? '…' : before ? `Seria a început pe ${longDay(start!)}. Pașii de dinainte nu mai sunt ai ei.` : step?.odds ? `cotă ${fo(step.odds)}` : 'jumătate din bancă';

  const jRows = (journal.data?.rows ?? []).filter((r) => r.date === day && (r.source === 'recomandată' || r.source === 'principală'));
  const rec = counts(jRows.filter((r) => r.source === 'recomandată'));
  const pont = counts(jRows.filter((r) => r.source === 'principală'));
  const toate = counts(jRows);
  const ssDay = stil.data?.days?.find((d) => d.date === day);
  const measured = ssDay?.markets?.find((m) => m.key === MEASURED);
  const expLines = (exp.data?.matches ?? []).flatMap((m) => m.markets ?? []).filter((x) => x.odds != null);
  const expC = counts(expLines);

  const toateMain = journal.loading ? '…' : toate.n ? countLine(toate.won, toate.lost, toate.pending) : 'nimic de monitorizat';
  const toateSub = journal.loading ? '' : toate.n
    ? `${rec.n} recomandate · ${pont.n} pont. Fără restul listei de predicții.`
    : 'Niciun pont sau recomandare în jurnal pentru ziua asta.';
  const stilMain = stil.loading ? '…' : !ssDay || !ssDay.n ? 'fără decontare salvată' : countLine(ssDay.won, ssDay.lost, ssDay.pending);
  const stilSub = stil.loading ? '' : !ssDay || !ssDay.n
    ? 'Stil nu are rezultate salvate pentru ziua asta. Nu inventez un procent.'
    : measured
      ? (ssDay.n > measured.n
        ? `Combinația măsurată: ${countLine(measured.won, measured.lost, measured.pending)}. Alte piețe: ${ssDay.n - measured.n}.`
        : `Doar combinația măsurată: ${countLine(measured.won, measured.lost, measured.pending)}.`)
      : 'Nicio selecție din combinația măsurată în decontarea salvată.';
  const expMain = exp.loading ? '…' : !exp.data ? 'fără jurnal' : expLines.length ? countLine(expC.won, expC.lost, expC.pending) : 'nicio linie cu cotă';
  const expSub = exp.loading ? '' : !exp.data
    ? 'Nu există fișier de hârtie pentru ziua asta.'
    : expLines.length
      ? `${expLines.length} linii cu cotă Superbet. Hârtie, nu pont, nu intră pe bilete.`
      : 'Hârtie. Liniile fără cotă Superbet nu se numără.';

  const rubrici = [
    { k: 'Toate', main: toateMain, sub: toateSub },
    { k: 'Stil Supersocial', main: stilMain, sub: stilSub },
    { k: 'Experimental', main: expMain, sub: expSub },
  ];

  return (
    <div className="space-y-5">
      <header className="desk-hero">
        <p className="dash-kicker">Zi de zi</p>
        <h1>Istoric</h1>
        <p className="mt-1 text-[15px] text-muted-foreground">{longDay(day)}</p>
      </header>

      <div className="scrollbar-none -mx-4 flex gap-2 overflow-x-auto px-4 pb-1" role="group" aria-label="Alege ziua">
        {days.map((d) => (
          <button key={d} type="button" aria-pressed={d === day} onClick={() => setDay(d)}
            className={cn('day-chip', d === day && 'day-chip-on')}>
            <span className="block capitalize">{d === today ? 'Azi' : d === addDays(today, -1) ? 'Ieri' : chipWd.format(noon(d)).replace(/[.,]/g, '')}</span>
            <span className="block text-[13px]">{chipDm.format(noon(d)).replace(/\.$/, '')}</span>
          </button>
        ))}
      </div>

      <Link to="/piramida" className={cn('pyr-day', !before && step?.result === 'won' && 'pyr-day-won', !before && step?.result === 'lost' && 'pyr-day-lost')}>
        <span className="door-k">Piramida cotă 2</span>
        <strong>{stepTxt}</strong>
        <span>{stepSub}</span>
      </Link>

      <section className="space-y-2.5" aria-label="Predicții">
        <div>
          <h2>Predicții</h2>
          <p className="text-[12px] text-muted-foreground">Aceleași rubrici ca pe pagina de predicții. Numără rezultatele, nu un pont nou.</p>
        </div>
        <div className="card divide-y overflow-hidden">
          {rubrici.map((r) => (
            <div key={r.k} className="px-3 py-3">
              <div className="flex items-baseline justify-between gap-3">
                <span className="text-sm font-bold">{r.k}</span>
                <span className="text-right text-[13px] font-semibold">{r.main}</span>
              </div>
              {r.sub ? <p className="mt-1 text-[12px] leading-snug text-muted-foreground">{r.sub}</p> : null}
            </div>
          ))}
        </div>
      </section>

      <section className="space-y-2.5" aria-label="Cornerele zilei">
        <div className="flex items-end justify-between">
          <h2>Cornere</h2>
          <span className="text-[12px] text-muted-foreground">{history.loading ? '…' : `${won} câștigate · ${lost} pierdute`}</span>
        </div>
        {history.loading ? <Skeleton className="h-32 w-full rounded-2xl" /> : corners.length ? (
          <div className="stagger space-y-3">{corners.map((t) => <TicketCard key={t.id} t={t} compact />)}</div>
        ) : <p className="desk-empty">Niciun bilet de cornere în ziua asta.</p>}
      </section>
    </div>
  );
}
