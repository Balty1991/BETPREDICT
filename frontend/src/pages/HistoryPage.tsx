import { useMemo } from 'react';
import { Link, useSearchParams } from 'react-router';
import { useAsync, getJSON } from '@/lib/fetcher';
import { loadJournalRows, loadPyramidSafe } from '@/lib/data';
import { addDays, longDay, odds as fo, todayRo } from '@/lib/format';
import { STATS_SINCE } from '@/lib/rules';
import { cn } from '@/lib/utils';

const chipWd = new Intl.DateTimeFormat('ro-RO', { timeZone: 'UTC', weekday: 'short' });
const chipDm = new Intl.DateTimeFormat('ro-RO', { timeZone: 'UTC', day: 'numeric', month: 'short' });
const noon = (d: string) => new Date(`${d}T12:00:00Z`);
const MEASURED = 'BB_G05_C75';

type SsMarket = { key: string; label?: string; n: number; won: number; lost: number; pending: number };
type SsDay = { date: string; n: number; won: number; lost: number; pending: number; markets?: SsMarket[] };
type SsHist = { days?: SsDay[] };
type Cell = { won: number; lost: number; pending: number; n: number };
type JournalDays = { days?: Record<string, { rec?: Cell; pont?: Cell }> };
type ExpCell = { priced: number; won: number; lost: number; pending: number };
type ExpCounts = { days?: Record<string, ExpCell> };
const Z: Cell = { won: 0, lost: 0, pending: 0, n: 0 };

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

/** Istoric: ziua, piramida de cotă 2 și rubricile de predicții. Fără bilete. */
export default function HistoryPage() {
  const today = todayRo();
  const [sp, setSp] = useSearchParams();
  const q = sp.get('zi');
  const day = q && q <= today && q >= STATS_SINCE ? q : today;
  const setDay = (d: string) => { sp.set('zi', d); setSp(sp, { replace: true }); };
  const pyr = useAsync(() => loadPyramidSafe('1.20'), []);
  const journal = useAsync(() => getJSON<JournalDays>('api/stats/journal_days.json'), []);
  const legacy = useAsync(() => (journal.loading || journal.data ? Promise.resolve(null) : loadJournalRows(1, 21)), [journal.loading, !!journal.data]);
  const stil = useAsync(() => getJSON<SsHist>('api/supersocial/history.json'), []);
  const exp = useAsync(() => getJSON<ExpCounts>('api/experimental/counts.json'), []);
  const days = useMemo(() => {
    const out: string[] = [];
    for (let d = today; d >= STATS_SINCE && out.length < 14; d = addDays(d, -1)) out.push(d);
    return out;
  }, [today]);
  const start = pyr.data?.run?.start_date || null;
  const step = (pyr.data?.history ?? []).find((r) => r.date === day && (!start || r.date >= start));
  const before = !!start && day < start;
  const stepTxt = pyr.loading ? '…' : before ? 'înainte de serie' : !step ? 'fără pas' : step.status !== 'pick' ? 'pauză' : step.result === 'won' ? 'câștigat' : step.result === 'lost' ? 'pierdut' : 'în joc';
  const stepSub = pyr.loading ? '…' : before ? `Seria a început pe ${longDay(start!)}. Pașii de dinainte nu mai sunt ai ei.` : step?.odds ? `cotă ${fo(step.odds)}` : 'jumătate din bancă';

  const fromSlim = journal.data?.days?.[day];
  const jRows = fromSlim ? [] : (legacy.data?.rows ?? []).filter((r) => r.date === day && (r.source === 'recomandată' || r.source === 'principală'));
  const rec = fromSlim?.rec ?? (fromSlim ? Z : counts(jRows.filter((r) => r.source === 'recomandată')));
  const pont = fromSlim?.pont ?? (fromSlim ? Z : counts(jRows.filter((r) => r.source === 'principală')));
  const toate = fromSlim
    ? { won: (rec.won || 0) + (pont.won || 0), lost: (rec.lost || 0) + (pont.lost || 0), pending: (rec.pending || 0) + (pont.pending || 0), n: (rec.n || 0) + (pont.n || 0) }
    : counts(jRows);
  const ssDay = stil.data?.days?.find((d) => d.date === day);
  const measured = ssDay?.markets?.find((m) => m.key === MEASURED);
  const expC = exp.data?.days?.[day];
  const jLoading = journal.loading || (!journal.data && legacy.loading);

  const toateMain = jLoading ? '…' : toate.n ? countLine(toate.won, toate.lost, toate.pending) : 'nimic de monitorizat';
  const toateSub = jLoading ? '' : toate.n
    ? `${rec.n} recomandate · ${pont.n} pont. Nu sunt biletele de cornere.`
    : 'Niciun pont sau recomandare în jurnal pentru ziua asta.';
  const stilMain = stil.loading ? '…' : !ssDay || !ssDay.n ? 'fără decontare salvată' : countLine(ssDay.won, ssDay.lost, ssDay.pending);
  const stilSub = stil.loading ? '' : !ssDay || !ssDay.n
    ? 'Stil nu are rezultate salvate pentru ziua asta. Nu inventez un procent.'
    : measured
      ? (ssDay.n > measured.n
        ? `Combinația măsurată: ${countLine(measured.won, measured.lost, measured.pending)}. Alte piețe: ${ssDay.n - measured.n}.`
        : `Doar combinația măsurată: ${countLine(measured.won, measured.lost, measured.pending)}.`)
      : 'Nicio selecție din combinația măsurată în decontarea salvată.';
  const expMain = exp.loading ? '…' : !exp.data ? 'fără numărătoare' : expC?.priced ? countLine(expC.won, expC.lost, expC.pending) : 'nicio linie cu cotă';
  const expSub = exp.loading ? '' : !exp.data
    ? 'Numărătoarea de hârtie nu e încă publicată. Hârtia rămâne în Predicții, nu aici ca fișier mare.'
    : expC?.priced
      ? `${expC.priced} linii cu cotă Superbet. Hârtie, nu pont, nu intră pe bilete.`
      : 'Hârtie. Liniile fără cotă Superbet nu se numără.';

  const rubrici = [
    { k: 'Toate', main: toateMain, sub: toateSub },
    { k: 'Stil Supersocial', main: stilMain, sub: stilSub },
    { k: 'Experimental', main: expMain, sub: expSub },
  ];

  return (
    <div className="space-y-5">
      <header className="desk-hero">
        <p className="dash-kicker">Ce se urmărește</p>
        <h1>Istoric</h1>
        <p className="mt-1 max-w-xl text-[15px] text-muted-foreground">{longDay(day)}. Patru numărători, fără bilete. Un rezultat aici nu e un pont nou.</p>
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

      <Link to="/piramida" className={cn('watch watch-wide', !before && step?.result === 'won' && 'watch-won', !before && step?.result === 'lost' && 'watch-lost')}>
        <span className="watch-k">01 · Piramida cotă 2</span>
        <strong>{stepTxt}</strong>
        <span>{stepSub}</span>
      </Link>

      <section className="watch-grid" aria-label="Predicții">
        <p className="watch-note">Aceleași trei rubrici ca la Predicții. Stil gol arată gol. Hârtia nu se amestecă cu pontul.</p>
        {rubrici.map((r, i) => (
          <article key={r.k} className="watch">
            <span className="watch-k">0{i + 2} · {r.k}</span>
            <strong>{r.main}</strong>
            {r.sub ? <span>{r.sub}</span> : null}
          </article>
        ))}
      </section>
    </div>
  );
}
