import { useState } from 'react';
import { Link } from 'react-router';
import { getJSON, useAsync } from '@/lib/fetcher';
import { roTime } from '@/lib/format';
import { cn } from '@/lib/utils';
import { SbPickButton } from '@/components/SuperbetLink';

interface Mh { key: string; label: string; status: 'active' | 'paused'; since: string; n: number; hit: number; p: number; roi: number }
interface MhDoc { days: number; min_n: number; rule: string; markets: Mh[] }
interface Va { match_id: number; kickoff_utc: string; home: string; away: string; league?: string; label: string; superbet: number; fair: number; value: number }
interface VaDoc { generated_at: string; alerts: Va[]; record: { settled: number; won: number; expected: number; roi: number | null }; push_enabled: boolean; push_rule: string }

const pct = (v: number, d = 0) => `${(v * 100).toFixed(d)}%`;

/** Piețele Stil: active / pauzate automat (modelul promite peste ce intră și pierd). */
export function MarketHealth() {
  const { data } = useAsync(() => getJSON<MhDoc>('api/stats/market_health.json'), []);
  if (!data?.markets?.length) return null;
  const paused = data.markets.filter((m) => m.status === 'paused');
  const active = data.markets.filter((m) => m.status === 'active').sort((a, b) => b.roi - a.roi);
  const Row = ({ m }: { m: Mh }) => (
    <li className="flex items-center justify-between gap-2 py-1.5 text-xs">
      <span className="min-w-0 truncate">{m.label}</span>
      <span className="num shrink-0 text-muted-foreground">{m.n} · {pct(m.hit)} vs {pct(m.p)} · <b className={m.roi >= 0 ? 'text-win' : 'text-loss'}>{m.roi >= 0 ? '+' : ''}{pct(m.roi, 1)}</b></span>
    </li>
  );
  return (
    <section className="card p-3.5" aria-label="Piețe active și pauzate">
      <div className="flex items-center justify-between">
        <h2 className="text-[15px] font-bold">Piețe active / pauzate</h2>
        <span className="text-[11px] text-muted-foreground">ultimele {data.days} zile</span>
      </div>
      <div className="mt-2 grid grid-cols-2 gap-2 text-center">
        <div className="rounded-xl bg-muted/50 py-2"><div className="big-num text-[22px] text-win">{active.length}</div><div className="label">active</div></div>
        <div className="rounded-xl bg-muted/50 py-2"><div className={cn('big-num text-[22px]', paused.length ? 'text-loss' : '')}>{paused.length}</div><div className="label">pauzate</div></div>
      </div>
      {paused.length > 0 && <ul className="mt-2 divide-y divide-border/50">{paused.map((m) => <Row key={m.key} m={m} />)}</ul>}
      <details className="mt-1 text-xs">
        <summary className="inline-flex min-h-9 cursor-pointer items-center font-semibold text-primary">Toate piețele active ▾</summary>
        <ul className="divide-y divide-border/50">{active.map((m) => <Row key={m.key} m={m} />)}</ul>
        <p className="mt-1 text-[11px] text-muted-foreground">Rândul: selecții · intrate vs promise · ROI. {data.rule}.</p>
      </details>
    </section>
  );
}

/** Superbet peste prețul corect Pinnacle (fără marjă), pe meciuri neîncepute. */
export function ValueAlerts() {
  const { data } = useAsync(() => getJSON<VaDoc>('api/alerts/value.json'), []);
  const [now] = useState(() => Date.now());
  if (!data) return null;
  const list = data.alerts.filter((a) => new Date(a.kickoff_utc).getTime() > now);
  const r = data.record;
  return (
    <details className="card p-3.5" aria-label="Cote cu valoare față de Pinnacle">
      <summary className="flex min-h-9 cursor-pointer list-none items-center justify-between gap-2">
        <span className="text-[15px] font-bold">Valoare vs Pinnacle <span className="ml-1 rounded-full bg-primary/15 px-2 py-0.5 text-xs text-primary">{list.length}</span></span>
        <span className="text-[11px] text-muted-foreground">▾</span>
      </summary>
      <p className="mt-1 text-[11px] text-muted-foreground">
        Superbet plătește cu ≥ 5% peste cota corectă Pinnacle. Istoric: {r.settled} decontate, {r.won} câștigate (așteptat {r.expected.toLocaleString('ro-RO')}){r.roi != null ? `, ROI ${r.roi >= 0 ? '+' : ''}${pct(r.roi, 1)}` : ''}.
        {data.push_enabled ? ' Notificări pornite.' : ` În probă: ${data.push_rule}.`}
      </p>
      {list.length === 0 ? <p className="mt-2 text-xs text-muted-foreground">Nicio cotă cu valoare acum.</p> : (
        <ul className="mt-1 divide-y divide-border/50">
          {list.map((a) => (
            <li key={`${a.match_id}-${a.label}`}>
              <Link to={`/meci/${a.match_id}`} className="flex items-center justify-between gap-2 py-2 text-xs">
                <span className="min-w-0"><span className="block truncate font-semibold">{a.home} – {a.away}</span><span className="text-muted-foreground">{roTime(a.kickoff_utc)} · {a.label}</span></span>
                <span className="shrink-0 text-right"><span className="big-num text-[15px] text-primary">{a.superbet.toFixed(2)}</span><span className="block text-[11px] text-muted-foreground">corect {a.fair.toFixed(2)} · <b className="text-win">+{pct(a.value)}</b></span></span>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </details>
  );
}

interface ClvDoc { days: number; strategies: Array<{ strategy: string; legs: number; clv: number; beat: number }> }

/** CLV pe strategie: cota luată față de cota Superbet de la start. */
export function ClvStrategy() {
  const { data } = useAsync(() => getJSON<ClvDoc>('api/stats/clv_strategy.json'), []);
  if (!data?.strategies?.length) return null;
  return (
    <section className="card p-3.5" aria-label="CLV pe strategie">
      <div className="flex items-center justify-between"><h2 className="text-[15px] font-bold">CLV pe strategie</h2><span className="text-[11px] text-muted-foreground">ultimele {data.days} zile</span></div>
      <ul className="mt-2 divide-y divide-border/50 text-xs">
        {data.strategies.map((r) => (
          <li key={r.strategy} className="flex items-center justify-between gap-2 py-1.5">
            <span className="font-semibold">{r.strategy}</span>
            <span className="num text-muted-foreground">{r.legs} picioare · {pct(r.beat)} peste închidere · <b className={r.clv > 0 ? 'text-win' : r.clv < 0 ? 'text-loss' : ''}>{r.clv > 0 ? '+' : ''}{pct(r.clv, 1)}</b></span>
          </li>
        ))}
      </ul>
      <p className="mt-1 text-[11px] text-muted-foreground">Cota luată ÷ cota Superbet la start − 1. Peste zero = ai prins prețul înainte să scadă.</p>
    </section>
  );
}

interface SegPick { market: string; match_id: number; kickoff_utc: string; home: string; away: string; label: string; key: string;
  odds: number; p: number; profile: string; roi: number; n: number; win_rate: number; profiles: number; clv?: number | null; sb_event_id?: string | null;
  sb_pick?: { market: string; outcome: string; ref?: string } | null }
interface SegDoc { today: SegPick[]; segments: Array<{ key: string; profile: string; n: number; roi: number; win_rate: number; status?: string }>; note: string;
  counts?: { activ: number; suspect: number; 'pauză': number } }

/** Meciurile potrivite pentru piețele pe plus: profilul de meci (cotă, șansă, ligă) în care piața a ieșit pe plus. */
export function SegmentPicks() {
  const { data } = useAsync(() => getJSON<SegDoc>('api/stats/segments.json'), []);
  const [now] = useState(() => Date.now());
  const [all, setAll] = useState(false);
  if (!data) return null;
  const list = data.today.filter((a) => new Date(a.kickoff_utc).getTime() > now);
  const shown = all ? list : list.slice(0, 12);
  return (
    <details className="card p-3.5" aria-label="Meciuri potrivite pentru piețele pe plus">
      <summary className="flex min-h-9 cursor-pointer list-none items-center justify-between gap-2">
        <span className="text-[15px] font-bold">Meciuri potrivite <span className="ml-1 rounded-full bg-emerald-500/15 px-2 py-0.5 text-xs text-win">{list.length}</span></span>
        <span className="text-[11px] text-muted-foreground">▾</span>
      </summary>
      <p className="mt-1 text-[11px] text-muted-foreground">
        Pentru fiecare piață, Robotul caută tipul de meci în care a ieșit pe plus la cota Superbet (nivel de cotă, șansă, ligă), verificat pe
        ambele jumătăți ale istoricului. Aici sunt meciurile de azi și mâine care se potrivesc.{' '}
        {data.counts ? <>Profiluri: <b className="text-win">{data.counts.activ} active</b>{data.counts.suspect ? `, ${data.counts.suspect} suspecte (cota urcă după alegere)` : ''}{data.counts['pauză'] ? `, ${data.counts['pauză']} pe pauză (pe minus în ultimele 7 zile)` : ''}.</> : `${data.segments.length} profiluri găsite până acum.`}
      </p>
      {list.length === 0 ? <p className="mt-2 text-xs text-muted-foreground">Niciun meci potrivit acum.</p> : (
        <ul className="mt-1 divide-y divide-border/50">
          {shown.map((a) => (
            <li key={`${a.match_id}-${a.key}`} className="flex items-center justify-between gap-2 py-2 text-xs">
              <Link to={`/meci/${a.match_id}`} className="min-w-0">
                <span className="block truncate font-semibold">{a.home} – {a.away}</span>
                <span className="text-muted-foreground">{roTime(a.kickoff_utc)} · <b className="text-foreground">{a.label}</b></span>
                <span className="block text-[11px] text-muted-foreground">profil: {a.profile} · {a.n} selecții, {pct(a.win_rate)} intrate, ROI <b className="text-win">+{pct(a.roi, 1)}</b>{a.clv != null ? ` · cota ${a.clv >= 0 ? 'scade' : 'urcă'} după alegere (${a.clv >= 0 ? '+' : ''}${pct(a.clv, 1)})` : ''}{a.profiles > 1 ? ` · ${a.profiles} profiluri` : ''}</span>
              </Link>
              <span className="flex shrink-0 flex-col items-end">
                <span className="big-num text-[15px] text-primary">{a.odds.toFixed(2)}</span>
                <span className="text-[11px] text-muted-foreground">șansă {pct(a.p)}</span>
                <SbPickButton eventId={a.sb_event_id} picks={a.sb_pick ? [a.sb_pick] : null} />
              </span>
            </li>
          ))}
        </ul>
      )}
      {list.length > 12 && <button type="button" className="mt-1 text-xs font-semibold text-primary" onClick={() => setAll(!all)}>{all ? 'Arată mai puține' : `Arată toate (${list.length})`}</button>}
    </details>
  );
}
