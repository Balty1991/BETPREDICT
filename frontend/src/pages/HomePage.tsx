import { Link } from 'react-router';
import { useSettledTickets, usePersistMySettlement, useTodayBoard, useMeta, useNow } from '@/lib/hooks';
import { useAsync } from '@/lib/fetcher';
import { loadTicketsHistory } from '@/lib/data';
import { useStore } from '@/lib/store';
import { longDay, odds as fo, roTime, todayRo } from '@/lib/format';
import type { Ticket } from '@/lib/types';
import { BudgetBar } from '@/components/BudgetBar';
import { Skeleton } from '@/components/kit';

const BANDS: Array<[string, string]> = [
  ['4', '4 meciuri'],
  ['6', '6 meciuri'],
  ['500', '500+'],
  ['1000', '1000+'],
  ['10000', '10000+'],
];

function Slip({ t, label, stake }: { t: Ticket; label: string; stake: string }) {
  return (
    <Link to={`/bilete?bilet=${t.id}`} className="desk-slip">
      <span className="min-w-0">
        <span className="desk-kicker">{label}</span>
        <span className="mt-0.5 block text-[15px] font-bold tracking-tight">{t.legs.length} meciuri · {stake}</span>
      </span>
      <span className="desk-odds">{fo(t.total_odds)}</span>
    </Link>
  );
}

/** Acasă: un birou, nu o listă. Biletele de jucat sus, cele rare dedesubt. */
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

  return (
    <div className="desk space-y-6">
      <header className="desk-hero">
        <p className="eyebrow">Superbet · {meta.data?.generated_at ? `actualizat ${roTime(meta.data.generated_at)}` : 'pe hârtie'}</p>
        <h1 className="capitalize">{longDay(today).split(',')[0]}</h1>
        <p className="mt-1 text-[15px] text-muted-foreground">{longDay(today).split(',').slice(1).join(',').trim() || 'Cornere'}</p>
        <dl className="desk-meter">
          <div><dt>Neîncepute</dt><dd>{loading ? '…' : waiting.length}</dd></div>
          <div><dt>Câștigate</dt><dd className="text-win">{won}<span className="text-muted-foreground">/{past.length}</span></dd></div>
          <div><dt>ROI</dt><dd className={roi == null ? '' : roi >= 0 ? 'text-win' : 'text-loss'}>{roi == null ? '—' : `${roi >= 0 ? '+' : '−'}${Math.abs(Math.round(roi * 100))}%`}</dd></div>
        </dl>
      </header>

      <BudgetBar />

      <section className="space-y-2.5">
        <div className="flex items-end justify-between">
          <h2>De jucat</h2>
          <span className="text-[12px] text-muted-foreground">3 lei</span>
        </div>
        {loading ? <Skeleton className="h-24 w-full rounded-2xl" /> : play.length === 0 ? (
          <p className="desk-empty">Niciun bilet de 4 sau de 6 meciuri neînceput.</p>
        ) : play.map((t) => <Slip key={t.id} t={t} label={name(t)} stake="3 lei" />)}
      </section>

      <section className="space-y-2.5">
        <div className="flex items-end justify-between">
          <h2>Rar</h2>
          <span className="text-[12px] text-muted-foreground">2 lei · alegi unul</span>
        </div>
        {loading ? null : rare.length === 0 ? (
          <p className="desk-empty">Niciun bilet mare neînceput.</p>
        ) : (
          <div className="desk-rail">
            {rare.map((t) => (
              <Link key={t.id} to={`/bilete?bilet=${t.id}`} className="desk-rare">
                <span className="desk-kicker">{name(t)}</span>
                <span className="desk-odds">{fo(t.total_odds)}</span>
                <span className="text-[11px] text-muted-foreground">{t.legs.length} meciuri</span>
              </Link>
            ))}
          </div>
        )}
      </section>

      <nav className="desk-links" aria-label="În continuare">
        <Link to="/bilete">Toate biletele</Link>
        <Link to="/statistici">Rezultate</Link>
        <Link to="/istoric">Istoric</Link>
      </nav>
    </div>
  );
}
