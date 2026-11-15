import { Link } from 'react-router';
import { useSettledTickets, usePersistMySettlement, useTodayBoard, useMeta, useNow } from '@/lib/hooks';
import { useAsync } from '@/lib/fetcher';
import { loadTicketsHistory } from '@/lib/data';
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
    <Link to={`/bilete?bilet=${t.id}`} className="bilet-row">
      <span className="bilet-name">{label}</span>
      <span className="bilet-meta">{t.legs.length} meciuri · {stake}</span>
      <span className="bilet-odd">{fo(t.total_odds)}</span>
    </Link>
  );
}

/** Acasă: două bilete tipărite. Cornerele de jucat și piramida de cotă 2. */
export default function HomePage() {
  const now = useNow();
  const today = todayRo();
  const meta = useMeta();
  const myTickets = useStore((s) => s.myTickets);
  const mySettled = useSettledTickets(myTickets);
  usePersistMySettlement(mySettled.tickets, myTickets);
  const { full, loading } = useTodayBoard(today);
  const history = useAsync(loadTicketsHistory, []);
  const waiting = full.filter((t) => t.kind === 'acca_corners' && t.status === 'pending' && t.legs.every((l) => !l.kickoff_utc || Date.parse(l.kickoff_utc) > now));
  const past = (history.data ?? []).filter((t) => t.kind === 'acca_corners' && (t.status === 'won' || t.status === 'lost'));
  const won = past.filter((t) => t.status === 'won').length;
  const roi = past.length ? past.reduce((a, t) => a + (t.status === 'won' ? (t.total_odds_published ?? t.total_odds) - 1 : -1), 0) / past.length : null;
  const play = waiting.filter((t) => t.variant === '4' || t.variant === '6');
  const rare = waiting.filter((t) => t.variant === '500' || t.variant === '1000' || t.variant === '10000');
  const name = (t: Ticket) => BANDS.find(([v]) => v === t.variant)?.[1] ?? 'Cornere';
  const when = longDay(today);
  const [dayName, ...rest] = when.split(',');

  return (
    <div className="casa-home">
      <header className="casa-day">
        <p className="casa-kicker">Casa de bilete · {meta.data?.generated_at ? roTime(meta.data.generated_at) : 'pe hârtie'}</p>
        <h1 className="capitalize">{dayName}</h1>
        <p className="casa-when">{rest.join(',').trim() || 'Două mese'}</p>
      </header>

      <section className="bilet bilet-corn">
        <div className="bilet-head">
          <span className="bilet-idx">01</span>
          <div className="min-w-0">
            <h2>Cornere</h2>
            <p>Peste 0,5 goluri · peste 7,5 cornere</p>
          </div>
          <span className="bilet-stake">3 lei</span>
        </div>
        {loading ? <p className="bilet-empty">Se încarcă biletele…</p> : play.length === 0 ? (
          <p className="bilet-empty">Niciun bilet de 4 sau de 6 meciuri neînceput.</p>
        ) : play.map((t) => <Row key={t.id} t={t} label={name(t)} stake="3 lei" />)}
        <Link to="/bilete" className="bilet-go">Deschide masa de cornere</Link>
      </section>

      <section className="bilet bilet-cota">
        <div className="bilet-head">
          <span className="bilet-idx">02</span>
          <div className="min-w-0">
            <h2>Cotă 2</h2>
            <p>Un meci sau două. Jumătate din bancă. Fără pereche, ziua e pauză.</p>
          </div>
          <span className="bilet-stake">½</span>
        </div>
        <Link to="/piramida" className="bilet-go">Pasul de azi</Link>
      </section>

      {(loading || rare.length > 0) && (
        <section className="bilet bilet-rare">
          <div className="bilet-head">
            <span className="bilet-idx">03</span>
            <div className="min-w-0">
              <h2>Rar</h2>
              <p>Cote mari. Alegi unul.</p>
            </div>
            <span className="bilet-stake">2 lei</span>
          </div>
          {rare.map((t) => <Row key={t.id} t={t} label={name(t)} stake="2 lei" />)}
        </section>
      )}

      <dl className="casa-line">
        <div><dt>Neîncepute</dt><dd>{loading ? '…' : waiting.length}</dd></div>
        <div><dt>Câștigate</dt><dd>{won}<span>/{past.length}</span></dd></div>
        <div><dt>ROI cornere</dt><dd className={roi == null ? '' : roi >= 0 ? 'is-win' : 'is-loss'}>{roi == null ? '—' : `${roi >= 0 ? '+' : '−'}${Math.abs(Math.round(roi * 100))}%`}</dd></div>
      </dl>

      <BudgetBar />
    </div>
  );
}
