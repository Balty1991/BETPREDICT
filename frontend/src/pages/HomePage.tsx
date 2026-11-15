import { Link } from 'react-router';
import { ChevronRight } from 'lucide-react';
import { useSettledTickets, usePersistMySettlement, useTodayBoard, useMeta, useNow } from '@/lib/hooks';
import { useAsync } from '@/lib/fetcher';
import { loadPyramidSafe, loadTicketsHistory } from '@/lib/data';
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

function Row({ t, label, stake }: { t: Ticket; label: string; stake: string }) {
  return (
    <Link to={`/bilete?bilet=${t.id}`} className="play-row">
      <span className="min-w-0">
        <span className="play-name">{label}</span>
        <span className="play-meta">{t.legs.length} meciuri · {stake}</span>
      </span>
      <span className="play-odd">{fo(t.total_odds)}</span>
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
  const { full, loading } = useTodayBoard(today);
  const history = useAsync(loadTicketsHistory, []);
  const pyr = useAsync(() => loadPyramidSafe('1.20'), []);
  const waiting = full.filter((t) => t.kind === 'acca_corners' && t.status === 'pending' && t.legs.every((l) => !l.kickoff_utc || Date.parse(l.kickoff_utc) > now));
  const past = (history.data ?? []).filter((t) => t.kind === 'acca_corners' && (t.status === 'won' || t.status === 'lost'));
  const won = past.filter((t) => t.status === 'won').length;
  const play = waiting.filter((t) => t.variant === '4' || t.variant === '6');
  const rare = waiting.filter((t) => t.variant === '500' || t.variant === '1000' || t.variant === '10000');
  const name = (t: Ticket) => BANDS.find(([v]) => v === t.variant)?.[1] ?? 'Cornere';
  const when = longDay(today);
  const start = pyr.data?.run?.start_date || null;
  const step = (pyr.data?.history ?? []).find((r) => r.date === today && (!start || r.date >= start));
  const pyrMain = pyr.loading ? '…' : !step ? 'fără pas' : step.status !== 'pick' ? 'pauză' : step.result === 'won' ? 'câștigat' : step.result === 'lost' ? 'pierdut' : 'în joc';
  const pyrOdd = step?.odds ? fo(step.odds) : '—';

  return (
    <div className="dash space-y-5">
      <header className="dash-head">
        <p className="dash-kicker">{when}{meta.data?.generated_at ? ` · ${roTime(meta.data.generated_at)}` : ''}</p>
        <h1>Azi</h1>
        <p className="mt-1 max-w-xl text-[14px] text-muted-foreground">Se joacă cornerele scurte și piramida de cotă 2. Restul se urmărește, nu se vinde ca pont.</p>
      </header>

      <dl className="kpi-row">
        <div><dt>Piramida</dt><dd>{pyrMain}</dd></div>
        <div><dt>Cotă</dt><dd>{pyrOdd}</dd></div>
        <div><dt>Scurte de jucat</dt><dd>{loading ? '…' : play.length}</dd></div>
      </dl>
      <p className="text-[12px] text-muted-foreground">Cornere decontate până acum: {won}/{past.length}. Nu e o margine dovedită. Urmărirea pe zile e în Istoric, fără lista de bilete.</p>

      <div className="promo-grid">
        <Link to="/predictii" className="promo">
          <span className="dash-kicker">Model</span>
          <strong>Toate predicțiile</strong>
          <span className="promo-d">Meciurile zilei, pe piețe.</span>
          <ChevronRight className="promo-go" />
        </Link>
        <Link to="/piramida" className="promo promo-pyr">
          <span className="dash-kicker">Jumătate din bancă</span>
          <strong>Piramida cotă 2</strong>
          <span className="promo-d">{pyrMain}{step?.odds ? ` · cotă ${pyrOdd}` : ''}. Un meci sau două, doar din ziua asta.</span>
          <ChevronRight className="promo-go" />
        </Link>
      </div>

      <section className="space-y-2.5">
        <div className="sec-h">
          <h2>Cornere de jucat</h2>
          <span>3 lei</span>
        </div>
        {loading ? <p className="play-empty">Se încarcă biletele…</p> : play.length === 0 ? (
          <p className="play-empty">Niciun bilet de 4 sau de 6 meciuri neînceput.</p>
        ) : play.map((t) => <Row key={t.id} t={t} label={name(t)} stake="3 lei" />)}
        <Link to="/bilete" className="sec-link">Toate cornerele <ChevronRight className="h-4 w-4" /></Link>
      </section>

      {rare.length > 0 && (
        <section className="space-y-2.5">
          <div className="sec-h">
            <h2>Cote mari</h2>
            <span>informativ · nu e pont</span>
          </div>
          {rare.map((t) => <Row key={t.id} t={t} label={name(t)} stake="2 lei" />)}
        </section>
      )}

      <BudgetBar />
    </div>
  );
}
