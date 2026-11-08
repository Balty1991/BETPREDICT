import { useState } from 'react';
import { Link } from 'react-router';
import { Scale } from 'lucide-react';
import { odds as fo, pct, roDateTime, roTime, signed } from '@/lib/format';
import { SbPickButton, SuperbetLink } from '@/components/SuperbetLink';
import { useLateValue, type LvAlert } from '@/components/LateValueCard';
import { cn } from '@/lib/utils';

const until = (iso: string, now: number) => {
  const m = Math.round((new Date(iso).getTime() - now) / 60000);
  if (m < 0) return 'a început';
  return m >= 60 ? `în ${Math.floor(m / 60)} h ${m % 60} min` : `în ${m} min`;
};
const resTone = (r?: string | null) => (r === 'won' ? 'text-win' : r === 'lost' ? 'text-loss' : 'text-muted-foreground');
const resTxt = (r?: string | null) => (r === 'won' ? 'intrat' : r === 'lost' ? 'pierdut' : r === 'void' ? 'anulat' : 'în așteptare');

function Row({ a, now }: { a: LvAlert; now: number }) {
  const live = new Date(a.kickoff_utc).getTime() > now;
  return (
    <li className="flex items-center justify-between gap-2 py-2.5 text-xs">
      <Link to={`/meci/${a.match_id}`} className="min-w-0">
        <span className="block truncate font-semibold">{a.home} – {a.away}</span>
        <span className="text-muted-foreground">{live ? `${roTime(a.kickoff_utc)} (${until(a.kickoff_utc, now)})` : roDateTime(a.kickoff_utc)} · <b className="text-foreground">{a.label}</b></span>
        <span className="block text-[11px] text-muted-foreground">
          Pinnacle {fo(a.pin_price)} · corect {fo(a.fair)} · Superbet {fo(a.superbet)} · <b className="text-win">+{pct(a.edge, 1)}</b>
          {a.clv != null ? ` · CLV ${signed(a.clv * 100, 1, '%')}` : ''}
        </span>
      </Link>
      <span className="flex shrink-0 flex-col items-end gap-0.5">
        {live ? (
          <>
            <span className="big-num text-[17px] text-primary">{fo(a.superbet)}</span>
            {a.sb_pick && a.sb_event_id ? <SbPickButton eventId={a.sb_event_id} picks={[a.sb_pick]} webUrl={a.superbet_url} />
              : a.superbet_url ? <SuperbetLink url={a.superbet_url} eventId={a.sb_event_id} className="inline-flex items-center gap-1 text-[11px] font-semibold text-[hsl(0_75%_62%)]" /> : null}
          </>
        ) : (
          <span className={cn('font-bold', resTone(a.result))}>{resTxt(a.result)}{a.score ? ` ${a.score}` : ''}</span>
        )}
      </span>
    </li>
  );
}

/** Testul: un singur meci, doar când Superbet plătește peste prețul corect Pinnacle. */
export default function PestePage() {
  const { data, loading, error } = useLateValue();
  const [now] = useState(() => Date.now());
  const live = (data?.alerts ?? []).filter((a) => new Date(a.kickoff_utc).getTime() > now);
  const r = data?.record;
  return (
    <div className="space-y-4">
      <header className="page-hero">
        <div className="eyebrow">Test · pariuri simple</div>
        <h1 className="flex items-center gap-2"><Scale className="h-6 w-6 text-primary" />Peste Pinnacle</h1>
        <p className="text-sm text-muted-foreground">Un singur meci, doar când Superbet plătește mai mult decât prețul corect. Fără acumulatoare.</p>
      </header>

      {loading && !data && <p className="text-sm text-muted-foreground">Se încarcă…</p>}
      {error && !data && <p className="text-sm text-loss">Nu am putut citi lista.</p>}
      {data && r && (
        <>
          <section className="card p-3.5">
            <p className="text-[11px] leading-snug text-muted-foreground">{data.rule.text} Miză de urmărire: {data.rule.stake} leu, pe hârtie.</p>
            <div className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-4">
              {[
                ['Decontate', String(r.settled), `${r.pending} în așteptare`],
                ['Intrate', r.hit_rate == null ? '—' : pct(r.hit_rate, 0), r.settled ? `${r.won} din ${r.settled}` : 'încă nimic'],
                ['ROI', r.roi == null ? '—' : signed(r.roi * 100, 0, '%'), r.settled ? `${signed(r.profit, 1)} lei` : 'la 1 leu'],
                ['CLV', r.avg_clv == null ? '—' : signed(r.avg_clv * 100, 1, '%'), r.clv_n ? `${r.clv_n} închise` : 'după start'],
              ].map(([l, v, s]) => (
                <div key={l} className="rounded-xl bg-[hsl(var(--elevated))] px-2.5 py-2">
                  <div className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">{l}</div>
                  <div className={cn('big-num mt-0.5 text-[18px]', v.startsWith('+') && 'text-win', v.startsWith('-') && 'text-loss')}>{v}</div>
                  <div className="text-[10px] text-muted-foreground">{s}</div>
                </div>
              ))}
            </div>
            <p className="mt-2 text-[11px] text-muted-foreground">21 de pariuri nu sunt o dovadă. Pagina există ca să crească eșantionul. CLV pozitiv înseamnă că prețul s-a mișcat în favoarea noastră până la start.</p>
          </section>

          <section className="card px-3.5 py-2">
            <h2 className="pt-2 text-sm font-semibold">De pus acum {live.length ? `· ${live.length}` : ''}</h2>
            {live.length === 0 ? (
              <p className="py-3 text-xs text-muted-foreground">Nimic în fereastra de 3 ore. Lista se uită la fiecare rulare. Ultima: {roTime(data.generated_at)}.</p>
            ) : (
              <ul className="divide-y divide-border/50">{live.map((a) => <Row key={`${a.match_id}-${a.market}-${a.outcome}`} a={a} now={now} />)}</ul>
            )}
          </section>

          <section className="card px-3.5 py-2">
            <h2 className="pt-2 text-sm font-semibold">Cele deja semnalate</h2>
            {data.recent.length === 0 ? <p className="py-3 text-xs text-muted-foreground">Încă nu e niciunul decontat.</p> : (
              <ul className="divide-y divide-border/50">{data.recent.map((a) => <Row key={`${a.match_id}-${a.market}-${a.outcome}`} a={a} now={now} />)}</ul>
            )}
          </section>
        </>
      )}
    </div>
  );
}
