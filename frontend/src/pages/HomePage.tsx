import { Link } from 'react-router';
import { CalendarDays, ChevronRight, Layers, Target, Ticket as TicketIcon } from 'lucide-react';
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

function Row({ t, label, stake, badge }: { t: Ticket; label: string; stake: string; badge: string }) {
  return (
    <Link to={`/bilete?bilet=${t.id}`} className="play-row">
      <span className="min-w-0">
        <span className="play-name">{label}</span>
        <span className="play-meta">{t.legs.length} meciuri · {stake}</span>
      </span>
      <span className="play-side">
        <span className="play-badge">{badge}</span>
        <span className="play-odd">{fo(t.total_odds)}</span>
      </span>
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

  return (
    <div className="dash space-y-4">
      <header className="dash-head">
        <p className="dash-kicker">Overview · {when}{meta.data?.generated_at ? ` · ${roTime(meta.data.generated_at)}` : ''}</p>
        <h1>Situația zilei</h1>
        <p className="dash-lead">Cornere scurte și piramida de cotă 2. Restul se urmărește. Nimic de aici nu e un câștig garantat.</p>
      </header>

      <dl className="kpi-row">
        <div><dt>Piramida</dt><dd>{pyrMain}</dd></div>
        <div><dt>Cotă</dt><dd>{pyrOdd}</dd></div>
        <div><dt>Scurte de jucat</dt><dd>{loading ? '…' : play.length}</dd></div>
      </dl>
      <p className="dash-note">Cornerele scurte nu sunt o margine dovedită. Urmărirea pe zile e în Istoric, fără lista de bilete.</p>

      <section className="mod-grid" aria-label="Module">
        <Link to="/predictii" className="mod">
          <span className="mod-ico"><Target /></span>
          <span className="mod-k">Predicții</span>
          <strong>Măsurat, prima</strong>
          <span className="mod-d">Gol + 7,5 cornere. ~75% e pe selecție, nu pe bilet.</span>
        </Link>
        <Link to="/piramida" className="mod mod-on">
          <span className="mod-ico"><Layers /></span>
          <span className="mod-k">Piramidă</span>
          <strong>{pyrMain}{step?.odds ? ` · ${pyrOdd}` : ''}</strong>
          <span className="mod-d">Jumătate din bancă. Un meci sau două, doar din ziua asta.</span>
        </Link>
        <Link to="/bilete" className="mod">
          <span className="mod-ico"><TicketIcon /></span>
          <span className="mod-k">Cornere</span>
          <strong>{loading ? '…' : `${play.length} de jucat`}</strong>
          <span className="mod-d">Bilete scurte, 4 sau 6 meciuri. Cotele mari stau separat, informative.</span>
        </Link>
        <Link to="/istoric" className="mod">
          <span className="mod-ico"><CalendarDays /></span>
          <span className="mod-k">Istoric</span>
          <strong>Numărători</strong>
          <span className="mod-d">Piramida și rubricile de predicții. Fără lista de bilete.</span>
        </Link>
      </section>

      <section className="space-y-2.5">
        <div className="sec-h">
          <h2>Cornere de jucat</h2>
          <span>3 lei</span>
        </div>
        {loading ? <p className="play-empty">Se încarcă biletele…</p> : play.length === 0 ? (
          <p className="play-empty">Niciun bilet de 4 sau de 6 meciuri neînceput.</p>
        ) : play.map((t) => <Row key={t.id} t={t} label={name(t)} stake="3 lei" badge="neînceput" />)}
        <Link to="/bilete" className="sec-link">Toate cornerele <ChevronRight className="h-4 w-4" /></Link>
      </section>

      {rare.length > 0 && (
        <section className="space-y-2.5">
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
