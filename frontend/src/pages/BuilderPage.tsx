import { useMemo, useState } from 'react';
import { Link } from 'react-router';
import { Blocks, FlaskConical } from 'lucide-react';
import { Card, Segmented, Badge, Loading, Empty, Notice } from '@/components/kit';
import { useAsync } from '@/lib/fetcher';
import { getJSON } from '@/lib/fetcher';
import { addDays, todayRo, dayLabel, pct, odds as fo, roKickoff, signed } from '@/lib/format';
import type { BuilderDay, BuilderMatch } from '@/lib/types';
import { cn } from '@/lib/utils';

const GROUPS: Record<string, string> = {
  team_total_home: 'Goluri gazde', team_total_away: 'Goluri oaspeți', ht_over_under: 'Goluri repriza 1', h2_over_under: 'Goluri repriza 2',
  half_most_goals: 'Repriza cu cele mai multe goluri', corners_over_under: 'Cornere', ht_corners_over_under: 'Cornere repriza 1',
};

function Stat({ k, v, hi, tone }: { k: string; v: string; hi?: boolean; tone?: string }) {
  return (
    <div className={cn('rounded-lg px-1 py-1', hi && 'bg-primary/10')}>
      <div className={cn('num text-base font-extrabold leading-tight', hi && 'text-primary', tone)}>{v}</div>
      <div className="text-[9.5px] uppercase leading-tight tracking-wide text-muted-foreground">{k}</div>
    </div>
  );
}
const esc = (x: string) => x.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
/** „Vasco da Gama câștigă; Peste 1.5 goluri” → ['Gazde câștigă', 'Peste 1.5 goluri'] */
function legsOf(label: string, home: string, away: string) {
  return label.split(/\s*;\s*/).filter(Boolean).map((l) => l.replace(new RegExp(esc(home), 'g'), 'Gazde').replace(new RegExp(esc(away), 'g'), 'Oaspeți'));
}

export function MatchBuilder({ m, only }: { m: BuilderMatch; only: boolean }) {
  const combos = (m.combos ?? []).filter((c) => !only || c.value);
  const extras = (m.extra_markets ?? []).filter((x) => !only || (x.ev ?? -1) > 0);
  if (only && !combos.length && !extras.length) return null;
  const byGroup = new Map<string, typeof extras>();
  for (const x of extras) byGroup.set(x.market, [...(byGroup.get(x.market) ?? []), x]);
  return (
    <Card className="overflow-hidden">
      <header className="flex flex-wrap items-center gap-2 px-4 pt-3">
        <Link to={`/meci/${m.match_id}`} className="font-extrabold hover:text-primary">{m.home} – {m.away}</Link>
        <span className="text-xs text-muted-foreground">{roKickoff(m.kickoff_utc)}</span>
        {m.lambda_home != null && <span className="num ml-auto text-xs text-muted-foreground">xG {m.lambda_home.toFixed(2)} – {m.lambda_away?.toFixed(2)}{m.corners ? ` · cornere ~${m.corners.mu.toFixed(1)}` : ''}</span>}
      </header>
      {m.superavantaj?.note && <p className="px-4 pt-1 text-[11px] text-muted-foreground">SuperAvantaj: {m.superavantaj.note}</p>}
      {!!combos.length && (
        <>
        <ul className="mt-2 space-y-2 px-3 pb-3 md:hidden">{combos.map((c, i) => (
          <li key={i} className={cn('rounded-xl border p-2.5', c.value && 'border-[hsl(var(--win)/0.5)]')}>
            <div className="flex flex-wrap items-center gap-1">
              {legsOf(c.label, m.home, m.away).map((l, j) => <span key={j} className="rounded-md bg-accent/50 px-1.5 py-0.5 text-[12px] font-semibold leading-tight">{l}</span>)}
              {c.value && <Badge tone="win">valoare</Badge>}
            </div>
            <div className="mt-2 grid grid-cols-4 gap-1 text-center">
              <Stat k="Șansă" v={pct(c.p, 0)} />
              <Stat k="Cotă corectă" v={fo(c.fair_odds)} />
              <Stat k="Joacă peste" v={fo(c.min_odds)} hi />
              <Stat k="Superbet" v={c.sb_odds ? fo(c.sb_odds) : '—'} tone={c.ev == null ? undefined : c.ev >= 0 ? 'text-win' : 'text-loss'} />
            </div>
            {(c.source === 'model' || c.ev != null) && <p className="mt-1 text-[10px] text-muted-foreground">{[c.source === 'model' && 'combinație proprie', c.correlation_lift && `corelație ×${c.correlation_lift.toFixed(2)}`, c.ev != null && `EV ${signed(c.ev * 100, 1, '%')}`].filter(Boolean).join(' · ')}</p>}
          </li>
        ))}</ul>
        <div className="hidden overflow-x-auto md:block"><table className="pro-table mt-2 w-full text-sm">
          <thead><tr><th className="text-left">Combinație</th><th>Șansă</th><th>Cotă corectă</th><th>Joacă doar peste</th><th>Superbet</th><th>EV</th></tr></thead>
          <tbody>{combos.map((c, i) => (
            <tr key={i}><td className="text-left"><span className="font-semibold">{c.label}</span>{c.value && <> <Badge tone="win">valoare</Badge></>}{c.source === 'model' && <span className="block text-[10px] text-muted-foreground">combinație proprie{c.correlation_lift ? ` · corelație ×${c.correlation_lift.toFixed(2)}` : ''}</span>}</td>
              <td>{pct(c.p, 1)}</td><td>{fo(c.fair_odds)}</td><td className="font-bold text-primary">{fo(c.min_odds)}</td><td>{c.sb_odds ? fo(c.sb_odds) : '—'}</td>
              <td className={cn(c.ev == null ? '' : c.ev >= 0 ? 'text-win' : 'text-loss')}>{c.ev == null ? '—' : signed(c.ev * 100, 1, '%')}</td></tr>
          ))}</tbody></table></div></>
      )}
      {!!extras.length && (
        <details className="border-t px-4 py-2 text-sm">
          <summary className="cursor-pointer text-xs font-semibold text-primary">Piețe experimentale ({extras.length})</summary>
          <div className="mt-2 grid gap-3 md:grid-cols-2">{[...byGroup.entries()].map(([g, xs]) => (
            <div key={g}><div className="mb-1 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">{GROUPS[g] ?? g}</div>
              <ul className="divide-y">{xs.map((x) => <li key={x.key} className="flex items-center gap-2 py-1"><span className="flex-1 truncate">{x.label}</span><span className="num text-xs text-muted-foreground">{pct(x.p)}</span><span className="num w-12 text-right">{fo(x.fair_odds)}</span><span className="num w-12 text-right text-xs">{x.sb_odds ? fo(x.sb_odds) : '—'}</span></li>)}</ul></div>
          ))}</div>
        </details>
      )}
    </Card>
  );
}

export default function BuilderPage() {
  const t = todayRo();
  const dates = useMemo(() => [0, 1, 2].map((i) => addDays(t, i)), [t]);
  const [day, setDay] = useState(dates[0]);
  const [only, setOnly] = useState<'value' | 'all'>('all');
  const res = useAsync(() => getJSON<BuilderDay>(`api/builder/${day}.json`), [day]);
  const ms = (res.data?.matches ?? []).slice().sort((a, b) => a.kickoff_utc.localeCompare(b.kickoff_utc));
  return (
    <div className="space-y-4">
      <div>
        <h1 className="flex items-center gap-2"><Blocks className="h-7 w-7 text-primary" aria-hidden />Bet Builder</h1>
        <p className="text-sm text-muted-foreground">Combinații în același meci, cu cota corectă calculată de Robot.</p>
      </div>
      <Notice><FlaskConical className="mr-1 inline h-4 w-4" aria-hidden /><b>Experimental.</b> {res.data?.rule ?? 'Joacă doar dacă Superbet dă cel puțin cota minimă (1/șansă × 1.05).'} Nu intră în recomandări sau bilete până nu se dovedește pe ≥ 300 de selecții.</Notice>
      <div className="flex flex-wrap gap-2">
        <Segmented size="sm" value={day} onChange={setDay} options={dates.map((d) => ({ value: d, label: dayLabel(d) }))} />
        <Segmented size="sm" value={only} onChange={setOnly} options={[{ value: 'all', label: 'Toate' }, { value: 'value', label: 'Doar cu valoare' }]} />
      </div>
      {res.loading ? <Loading /> : !ms.length ? <Empty title="Încă nu există sugestii Bet Builder pentru această zi" /> : (
        <div className="grid gap-4 xl:grid-cols-2">{ms.map((m) => <MatchBuilder key={m.match_id} m={m} only={only === 'value'} />)}</div>
      )}
    </div>
  );
}
