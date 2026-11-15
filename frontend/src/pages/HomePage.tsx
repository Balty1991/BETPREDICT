import { Link } from 'react-router';
import { ChevronRight } from 'lucide-react';
import { useSettledTickets, usePersistMySettlement, useTodayBoard, useMeta, useNow } from '@/lib/hooks';
import { useAsync } from '@/lib/fetcher';
import { loadPyramidSafe } from '@/lib/data';
import { useStore } from '@/lib/store';
import { longDay, odds as fo, roTime, todayRo } from '@/lib/format';
import type { Ticket } from '@/lib/types';
import { BudgetBar } from '@/components/BudgetBar';

const BANDS: Array<[string, string]> = [
  ['4', '4 meciuri'],
  ['6', '6 meciuri'],
  ['500', '500+'],
  ['1000', '1000+'],
  ['10000', '10000+'],
];

function ini(name: string) {
  const clean = name.normalize('NFD').replace(/[\u0300-\u036f]/g, '').replace(/[^A-Za-z]/g, '');
  return (clean.slice(0, 2) || '•').toUpperCase();
}

function Row({ t, label, stake, badge }: { t: Ticket; label: string; stake: string; badge: string }) {
  const a = t.legs[0];
  const b = t.legs[1];
  return (
    <Link to={`/bilete?bilet=${t.id}`} className="cap-row">
      <span className="ball">{a ? ini(a.home) : 'C'}</span>
      <span className="min-w-0 flex-1">
        <span className="play-name">{a && b ? `${a.home} · ${b.home}` : label}</span>
        <span className="play-meta">{label} · {t.legs.length} meciuri · {stake} · {badge}</span>
      </span>
      <span className="cap-odd">{fo(t.total_odds)}</span>
    </Link>
  );
}

/** Acasă: biletele de azi, predicțiile și piramida. */
export default function HomePage() {
  const now = useNow();
  const today = todayRo();
  const meta = useMeta();
  const myTickets = useStore((s) => s.myTickets);
  const mySettled = useSettledTickets(myTickets);
  usePersistMySettlement(mySettled.tickets, myTickets);
  const { full, loading } = useTodayBoard(today, false);
  const pyr = useAsync(() => loadPyramidSafe('1.20'), []);
  const waiting = full.filter((t) => t.kind === 'acca_corners' && t.status === 'pending' && t.legs.every((l) => !l.kickoff_utc || Date.parse(l.kickoff_utc) > now));
  const play = waiting.filter((t) => t.variant === '4' || t.variant === '6');
  const rare = waiting.filter((t) => t.variant === '500' || t.variant === '1000' || t.variant === '10000');
  const name = (t: Ticket) => BANDS.find(([v]) => v === t.variant)?.[1] ?? 'Cornere';
  const when = longDay(today);
  const start = pyr.data?.run?.start_date || null;
  const step = (pyr.data?.history ?? []).find((r) => r.date === today && (!start || r.date >= start));
  const pyrMain = pyr.loading ? '…' : !step ? 'fără pas' : step.status !== 'pick' ? 'pauză' : step.result === 'won' ? 'câștigat' : step.result === 'lost' ? 'pierdut' : 'în joc';
  const pyrOdd = step?.odds ? fo(step.odds) : '—';

  const board = pyr.data?.today?.status === 'pick' ? pyr.data.today.main : null;

  return (
    <div className="feed space-y-4">
      <header className="dash-head">
        <p className="dash-kicker">Live · {when}{meta.data?.generated_at ? ` · ${roTime(meta.data.generated_at)}` : ''}</p>
        <h1>Azi</h1>
      </header>

      <Link to="/piramida" className="score-card">
        <div className="score-top">
          <span>Piramidă cotă 2</span>
          <span className="score-pill">{pyrMain}</span>
        </div>
        {(board?.legs ?? []).slice(0, 2).map((l) => (
          <div className="score-row" key={l.match_id}>
            <span className="ball">{ini(l.home)}</span>
            <span className="min-w-0 flex-1">
              <b>{l.home}</b>
              <i>{l.away} · {l.league || 'Fotbal'}</i>
            </span>
            <span className="cap-odd">{fo(l.odds)}</span>
          </div>
        ))}
        {!board && <p className="score-empty">{pyr.loading ? 'Se încarcă pasul…' : 'Niciun pas cu meciuri pentru ziua asta.'}</p>}
        <div className="score-foot">
          <span>combinat · jumătate din bancă</span>
          <b>{pyrOdd}</b>
        </div>
      </Link>

      <dl className="stat-grid">
        <div><dt>Piramida</dt><dd>{pyrMain}</dd></div>
        <div><dt>Cotă</dt><dd>{pyrOdd}</dd></div>
        <div><dt>Scurte</dt><dd>{loading ? '…' : play.length}</dd></div>
      </dl>
      <p className="dash-note">Cornerele scurte nu sunt o margine dovedită. Istoricul numără, nu listează bilete.</p>

      <section className="space-y-2">
        <div className="sec-h">
          <h2>Cornere</h2>
          <span>3 lei</span>
        </div>
        {loading ? <p className="play-empty">Se încarcă biletele…</p> : play.length === 0 ? (
          <p className="play-empty">Niciun bilet de 4 sau de 6 meciuri neînceput.</p>
        ) : play.map((t) => <Row key={t.id} t={t} label={name(t)} stake="3 lei" badge="neînceput" />)}
        <Link to="/bilete" className="sec-link">Toate cornerele <ChevronRight className="h-4 w-4" /></Link>
      </section>

      {rare.length > 0 && (
        <section className="space-y-2">
          <div className="sec-h">
            <h2>Cote mari</h2>
            <span>informativ · nu e pont</span>
          </div>
          {rare.map((t) => <Row key={t.id} t={t} label={name(t)} stake="2 lei" badge="informativ" />)}
        </section>
      )}

      <BudgetBar />
    </div>
  );
}
