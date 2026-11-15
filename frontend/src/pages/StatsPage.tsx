import { useMemo } from 'react';
import { useAsync } from '@/lib/fetcher';
import { loadTickets, loadTicketsHistory } from '@/lib/data';
import { todayRo, pct, signed } from '@/lib/format';
import { Pyramid140Stats } from '@/components/Pyramid140View';
import { Loading, Notice } from '@/components/kit';
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

/** Doar cornere și piramida de cotă 2. Restul sistemelor nu se mai încarcă. */
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
  if ((hist.loading && !hist.data) || (today.loading && !today.data)) return <Loading />;
  const all = row(tickets);
  const bands = BANDS.map(([v, label]) => ({ label, ...row(tickets.filter((t) => t.variant === v)) })).filter((r) => r.n);
  return (
    <div className="space-y-4">
      <header className="desk-hero">
        <p className="dash-kicker">Cornere și piramidă</p>
        <h1>Rezultate</h1>
      </header>
      <Notice>Biletele de cornere de la {STATS_SINCE.split('-').reverse().join('.')}. ROI la 1 unitate pe bilet. Piramida de cotă 2 e separat, jos.</Notice>
      <section className="band-grid" aria-label="Cornere pe cotă">
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
      </section>
      <section className="space-y-2">
        <h2 className="text-sm font-semibold">Piramidă cotă 2</h2>
        <Pyramid140Stats track="1.20" />
      </section>
    </div>
  );
}
