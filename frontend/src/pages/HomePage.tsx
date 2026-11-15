import { Link } from 'react-router';
import { useState } from 'react';
import { toast } from 'sonner';
import { useSettledTickets, usePersistMySettlement, useTodayBoard, useMeta, useNow } from '@/lib/hooks';
import { useAsync } from '@/lib/fetcher';
import { loadPyramidSafe } from '@/lib/data';
import { useStore } from '@/lib/store';
import { weekSpent } from '@/lib/stake';
import { longDay, odds as fo, roTime, todayRo } from '@/lib/format';
import type { Ticket } from '@/lib/types';

const BANDS: Array<[string, string]> = [
  ['4', '4 meciuri'],
  ['6', '6 meciuri'],
  ['500', '500+'],
  ['1000', '1000+'],
  ['10000', '10000+'],
];

function evTxt(ev: number) {
  const n = ev * 100;
  const sign = n < 0 ? '−' : n > 0 ? '+' : '';
  return `${sign}${Math.abs(n).toFixed(1).replace('.', ',')}%`;
}

function Row({ t, label, level }: { t: Ticket; label: string; level: 'watch' | 'paper' }) {
  const a = t.legs[0];
  const b = t.legs[1];
  const stake = level === 'paper' ? '2 lei' : '3 lei';
  return (
    <Link to={`/bilete?bilet=${t.id}`} className={`ck-row ck-${level}`}>
      <span className={`ck-lvl ck-lvl-${level}`}>{level === 'paper' ? 'Hârtie' : 'Urmărește'}</span>
      <span className="min-w-0 flex-1">
        <span className="ck-name">{a && b ? `${a.home} · ${b.home}` : label}</span>
        <span className="ck-meta">{label} · {t.legs.length} selecții · pierdere max. {stake}</span>
      </span>
      <span className="ck-odd">{fo(t.total_odds)}</span>
    </Link>
  );
}

/** Acasă: o singură decizie. Jucabil doar dacă pasul de piramidă are EV nenegativ. */
export default function HomePage() {
  const now = useNow();
  const today = todayRo();
  const meta = useMeta();
  const myTickets = useStore((s) => s.myTickets);
  const budget = useStore((s) => s.settings.weeklyBudget ?? 50);
  const spent = useStore((s) => weekSpent(s.myTickets, new Date(), s.settings.weeklyBudget ?? 50));
  const mySettled = useSettledTickets(myTickets);
  usePersistMySettlement(mySettled.tickets, myTickets);
  const { full, loading } = useTodayBoard(today, false);
  const pyr = useAsync(() => loadPyramidSafe('1.20'), []);
  const [watching, setWatching] = useState(false);
  const waiting = full.filter((t) => t.kind === 'acca_corners' && t.status === 'pending' && t.legs.every((l) => !l.kickoff_utc || Date.parse(l.kickoff_utc) > now));
  const play = waiting.filter((t) => t.variant === '4' || t.variant === '6');
  const rare = waiting.filter((t) => t.variant === '500' || t.variant === '1000' || t.variant === '10000');
  const name = (t: Ticket) => BANDS.find(([v]) => v === t.variant)?.[1] ?? 'Cornere';
  const when = longDay(today);
  const start = pyr.data?.run?.start_date || null;
  const step = (pyr.data?.history ?? []).find((r) => r.date === today && (!start || r.date >= start));
  const pyrMain = pyr.loading ? '…' : !step ? 'fără pas' : step.status !== 'pick' ? 'pauză' : step.result === 'won' ? 'câștigat' : step.result === 'lost' ? 'pierdut' : 'în joc';
  const board = pyr.data?.today?.status === 'pick' ? pyr.data.today.main : null;
  const pyrOdd = board?.total_odds ? fo(board.total_odds) : step?.odds ? fo(step.odds) : '—';
  const ev = board?.ev;
  const playableN = board && typeof ev === 'number' && ev >= 0 ? 1 : 0;
  const left = Math.max(0, budget - spent);
  const neg = typeof ev === 'number' && ev < 0;

  return (
    <div className="ck space-y-4">
      <header className="ck-head">
        <p>Azi · {when}{meta.data?.generated_at ? ` · ${roTime(meta.data.generated_at)}` : ''}</p>
        <h1>{playableN ? 'Un pas cu EV nenegativ' : 'Fără valoare confirmată'}</h1>
      </header>

      <ul className="ck-strip" aria-label="Starea zilei">
        <li><b>{loading || pyr.loading ? '…' : playableN}</b><span>jucabile</span></li>
        <li><b>{loading ? '…' : play.length}</b><span>de urmărit</span></li>
        <li><b>{loading ? '…' : rare.length}</b><span>hârtie</span></li>
        <li><Link to="/setari"><b>{left.toLocaleString('ro-RO')}</b><span>lei rămași{spent > 0 ? ` · expunere ${spent.toLocaleString('ro-RO')}` : ''}</span></Link></li>
      </ul>

      {pyr.loading ? (
        <section className="ck-hero" role="status"><h2>Citim pasul zilei…</h2><p>Piramida și bugetul apar imediat ce fișierul e citit.</p></section>
      ) : board ? (
        <section className={`ck-hero ${neg || playableN === 0 ? 'ck-watch' : 'ck-play'}`} aria-label="Recomandarea zilei">
          <div className="ck-hero-k">
            <span className={`ck-lvl ${neg || playableN === 0 ? 'ck-lvl-watch' : 'ck-lvl-play'}`}>{neg || playableN === 0 ? 'Urmărește' : 'Jucabil'}</span>
            <span>Piramidă cotă 2 · {pyrMain} · cotă {pyrOdd}</span>
          </div>
          <h2>{neg ? 'Nu recomand jocul' : 'Pasul zilei'}</h2>
          <p className="ck-why">
            {neg
              ? `EV estimat ${evTxt(ev!)}. Cota ${pyrOdd} e sub șansa modelului. Jumătate din banca simulată ar fi miza, dar nu o marchez ca plasată.`
              : `Cotă ${pyrOdd}. Jumătate din banca simulată. Nu e marcat ca plasat până apeși tu, pe bilet.`}
          </p>
          <ul className="ck-legs">
            {board.legs.slice(0, 2).map((l) => (
              <li key={l.match_id}>
                <b>{l.home}</b>
                <span>{l.away}{l.league ? ` · ${l.league}` : ''}</span>
                <i>{fo(l.odds)}</i>
              </li>
            ))}
          </ul>
          <div className="ck-acts">
            <Link to={`/bilete?bilet=${board.id}`} className="ck-btn ck-btn-main">Vezi biletul</Link>
            <button type="button" className="ck-btn ck-btn-ghost" aria-pressed={watching} onClick={() => { setWatching(true); toast.message('Urmărești pasul pe hârtie. Nu e marcat ca plasat și nu ia din buget.'); }}>
              {watching ? 'Urmărești' : 'Urmăresc'}
            </button>
          </div>
        </section>
      ) : (
        <section className="ck-hero ck-paper" aria-label="Recomandarea zilei">
          <span className="ck-lvl ck-lvl-paper">Fără joc</span>
          <h2>Nu există valoare confirmată azi</h2>
          <p className="ck-why">Niciun pas de piramidă cu meciuri pentru ziua asta. Cornerele scurte, dacă apar, rămân de urmărit.</p>
          <Link to="/predictii" className="ck-btn ck-btn-main">Vezi predicțiile</Link>
        </section>
      )}

      <p className="ck-one">Cornerele de 4 și de 6 nu sunt o margine dovedită. Bugetul rămas e limita ta săptămânală, nu miza piramidei.</p>

      <section className="space-y-2">
        <div className="ck-sec"><h2>De urmărit</h2><span>nu e pont</span></div>
        {loading ? <p className="ck-empty">Citim biletele…</p> : play.length === 0 ? (
          <p className="ck-empty">Niciun bilet de 4 sau de 6 meciuri neînceput.</p>
        ) : play.map((t) => <Row key={t.id} t={t} label={name(t)} level="watch" />)}
      </section>

      <section className="space-y-2">
        <div className="ck-sec"><h2>Hârtie</h2><span>analiză</span></div>
        {loading ? <p className="ck-empty">Citim biletele…</p> : rare.length === 0 ? (
          <p className="ck-empty">Niciun bilet de cotă mare neînceput.</p>
        ) : rare.map((t) => <Row key={t.id} t={t} label={name(t)} level="paper" />)}
      </section>
    </div>
  );
}
