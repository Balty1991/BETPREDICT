import { useMemo } from 'react';
import { useAsync } from '@/lib/fetcher';
import { loadTickets, loadTicketsHistory } from '@/lib/data';
import { todayRo, pct, signed } from '@/lib/format';
import { Pyramid140Stats } from '@/components/Pyramid140View';
import { Loading } from '@/components/kit';
import { BankrollPanel } from '@/components/BankrollPanel';
import type { Ticket } from '@/lib/types';
import { STATS_SINCE } from '@/lib/rules';

const BANDS: Array<[string, string]> = [
  ['4', '4 meciuri'],
  ['6', '6 meciuri'],
  ['500', '500+'],
  ['1000', '1000+'],
  ['10000', '10000+'],
];

function row(list: Ticket[]) {
  const done = list.filter((t) => t.status === 'won' || t.status === 'lost');
  const won = done.filter((t) => t.status === 'won').length;
  const profit = done.reduce((a, t) => a + (t.status === 'won' ? (t.total_odds_published ?? t.total_odds) - 1 : -1), 0);
  return { n: list.length, settled: done.length, won, lost: done.length - won, profit, roi: done.length ? profit / done.length : null };
}

/** Performanța celor trei produse (bancă, ROI, calibrare, simulator), apoi piramida live și urmărirea cornerelor. */
export default function StatsPage() {
  const hist = useAsync(loadTicketsHistory, []);
  const today = useAsync(() => loadTickets(todayRo()), []);
  const tickets = useMemo(() => {
    const map = new Map<string, Ticket>();
    for (const t of [...(today.data?.tickets ?? []), ...(hist.data ?? [])]) {
      if (t.kind !== 'acca_corners') continue;
      if ((t.date ?? '') < STATS_SINCE) continue;
      map.set(String(t.id), t);
    }
    return [...map.values()];
  }, [hist.data, today.data]);
  const loadingCorners = (hist.loading && !hist.data) || (today.loading && !today.data);
  const all = row(tickets);
  const bands = BANDS.map(([v, label]) => ({ label, ...row(tickets.filter((t) => t.variant === v)) })).filter((r) => r.n);
  return (
    <div className="space-y-6">
      <header className="desk-hero">
        <p className="dash-kicker">Performanță și bancă</p>
        <h1>Rezultate</h1>
        <p className="mt-1 text-sm text-muted-foreground">Biletul de ~10, biletele lungi și piramida de cotă 2: cât au câștigat față de cât se aștepta, ROI cu SuperBonus, prețuri față de închidere și unde poate ajunge banca.</p>
      </header>

      <BankrollPanel />

      <section className="space-y-2" aria-label="Piramidă cotă 2">
        <h2 className="text-base font-semibold">Piramida cotă 2 · seria în curs</h2>
        <Pyramid140Stats track="1.20" />
      </section>

      <section className="space-y-2" aria-label="Cornere">
        <div>
          <h2 className="text-base font-semibold">Cornere · urmărire</h2>
          <p className="text-xs text-muted-foreground">De la {STATS_SINCE.split('-').reverse().join('.')}, ROI la 1 unitate pe bilet.</p>
        </div>
        {loadingCorners ? <Loading rows={1} /> : (
          <div className="band-grid">
            <article className="band-card band-all">
              <span className="door-k">Toate cornerele</span>
              <strong className={all.roi == null ? '' : all.roi >= 0 ? 'text-win' : 'text-loss'}>{all.roi == null ? '—' : signed(all.roi * 100, 0, '%')}</strong>
              <span>{all.settled ? `${all.won} din ${all.settled} · ${signed(all.profit, 1)} u` : `${all.n} bilete, nimic decontat`}</span>
            </article>
            {bands.map((b) => (
              <article key={b.label} className="band-card">
                <span className="door-k">{b.label}</span>
                <strong className={b.roi == null ? '' : b.roi >= 0 ? 'text-win' : 'text-loss'}>{b.roi == null ? '—' : signed(b.roi * 100, 0, '%')}</strong>
                <span>{b.settled ? `${b.won}/${b.settled} · ${pct(b.won / b.settled)}` : `${b.n} în listă`}</span>
              </article>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
