import { useMemo, useState } from 'react';
import { useAsync, getJSON } from '@/lib/fetcher';
import { SuperbetLink } from '@/components/SuperbetLink';
import { useDays } from '@/lib/hooks';
import { dayLabel, roDay, roTime } from '@/lib/format';
import { TeamLogo } from '@/components/kit';
import type { Match } from '@/lib/types';
import { cn } from '@/lib/utils';

type Row = { match_id: number; key: string; label: string; p: number; odds?: number | null; fair_odds?: number | null; edge?: number | null;
  kickoff_utc: string; home: string; away: string; src: string; bb: boolean; est?: boolean; corner_mean?: number | null; group?: string };
type Doc = { count: number; matches: number; note: string; rows: Row[] };

const GROUPS: Array<[string, string, string[]]> = [
  ['all', 'Toate', []],
  ['reprize', 'Reprize', ['H13x2', 'R1R2', 'BB_H13x2_O15']],
  ['combo', 'R1 0.5 & 1.5', ['R1O15']],
  ['interval', 'Intervale', ['G13', 'G24', 'G25']],
  ['r1_cornere', 'R1 cornere', ['H1CLT5', 'H1C56', 'H1C7P', 'H1C25', 'H1C35', 'H1U65', 'BB_H1C25_U65']],
  ['cornere', 'Cornere meci', ['C65', 'C75', 'C85', 'C95', 'CU145', 'BB_C65_U145']],
];
const ICON: Record<string, string> = { all: '◎', reprize: '⏱', combo: '🔗', interval: '↔', r1_cornere: '⚑', cornere: '⛳' };
const SHORT: Record<string, string> = { H13x2: '1-3 fiecare repriză', R1R2: 'Gol ambele reprize', BB_H13x2_O15: '1-3 reprize & 1.5',
  R1O15: 'R1 0.5 & 1.5', G13: '1-3', G24: '2-4', G25: '2-5', H1CLT5: 'sub 5', H1C56: '5-6', H1C7P: '7+',
  H1C25: 'Peste 2.5', H1C35: 'Peste 3.5', H1U65: 'Sub 6.5', BB_H1C25_U65: 'Interval 3-6',
  C65: 'Peste 6.5', C75: 'Peste 7.5', C85: 'Peste 8.5', C95: 'Peste 9.5', CU145: 'Sub 14.5', BB_C65_U145: '6.5 & sub 14.5' };
/** Pe românește ce înseamnă + unde e în Superbet (tab › piață › selecție), după numele pieței din oferta Superbet. */
const SB: Record<string, { what: string; where: string }> = {
  C65: { what: 'Cel puțin 7 cornere în meci', where: 'Cornere › Total cornere › Peste 6.5' },
  C75: { what: 'Cel puțin 8 cornere în meci', where: 'Cornere › Total cornere › Peste 7.5' },
  C85: { what: 'Cel puțin 9 cornere în meci', where: 'Cornere › Total cornere › Peste 8.5' },
  C95: { what: 'Cel puțin 10 cornere în meci', where: 'Cornere › Total cornere › Peste 9.5' },
  CU145: { what: 'Cel mult 14 cornere în meci', where: 'Cornere › Total cornere › Sub 14.5' },
  BB_C65_U145: { what: 'Între 7 și 14 cornere în meci', where: 'Bet Builder: Total cornere Peste 6.5 + Sub 14.5' },
  H1C25: { what: 'Cel puțin 3 cornere în prima repriză', where: 'Cornere › Prima repriză - Total cornere › Peste 2.5' },
  H1C35: { what: 'Cel puțin 4 cornere în prima repriză', where: 'Cornere › Prima repriză - Total cornere › Peste 3.5' },
  H1U65: { what: 'Cel mult 6 cornere în prima repriză', where: 'Cornere › Prima repriză - Total cornere › Sub 6.5' },
  H1CLT5: { what: 'Cel mult 4 cornere în prima repriză', where: 'Cornere › Prima repriză - Interval cornere › <5' },
  H1C56: { what: '5 sau 6 cornere în prima repriză', where: 'Cornere › Prima repriză - Interval cornere › 5-6' },
  H1C7P: { what: 'Cel puțin 7 cornere în prima repriză', where: 'Cornere › Prima repriză - Interval cornere › 7+' },
  BB_H1C25_U65: { what: 'Între 3 și 6 cornere în prima repriză', where: 'Bet Builder: Prima repriză - Total cornere Peste 2.5 + Sub 6.5' },
  G13: { what: 'Între 1 și 3 goluri în meci', where: 'Goluri › Interval goluri › 1-3' },
  G24: { what: 'Între 2 și 4 goluri în meci', where: 'Goluri › Interval goluri › 2-4' },
  G25: { what: 'Între 2 și 5 goluri în meci', where: 'Goluri › Interval goluri › 2-5' },
  R1R2: { what: 'Se marchează în ambele reprize', where: 'Reprize › Gol marcat în ambele reprize › Da' },
  R1O15: { what: 'Gol în prima repriză și cel puțin 2 în meci', where: 'Total goluri prima repriză & Total goluri › Peste 0.5 & Peste 1.5' },
  H13x2: { what: 'Între 1 și 3 goluri în fiecare repriză', where: 'Reprize › Interval goluri în fiecare repriză › 1-3' },
  BB_H13x2_O15: { what: '1-3 goluri în fiecare repriză și cel puțin 2 în meci', where: 'Bet Builder: Interval goluri în fiecare repriză 1-3 + Total goluri Peste 1.5' },
};
const NAME: Record<string, string> = { CU145: 'Cornere Sub 14.5', H1U65: 'R1 Cornere Sub 6.5' };

/** Predicții „Stil Supersocial” (cornere, reprize, intervale, BB) sortate după șansă, cu prețul Superbet și EV. */
export function SupersocialList() {
  const q = useAsync(() => getJSON<Doc>('api/supersocial/today.json'), []);
  const [g, setG] = useState('all');
  const [k, setK] = useState('');
  const [minP, setMinP] = useState(0);
  const [info, setInfo] = useState(false);
  const [limit, setLimit] = useState(40);
  const keys = GROUPS.find((x) => x[0] === g)![2];
  const all = useMemo(() => q.data?.rows ?? [], [q.data]);
  // linkul Superbet al fiecărui meci vine din fișierele zilelor (lista acoperă azi și mâine)
  const dates = useMemo(() => [...new Set(all.map((r) => roDay(r.kickoff_utc)))].filter(Boolean).sort(), [all]);
  const days = useDays(dates);
  // meciul întreg (ligă, sigle, link Superbet) din fișierele zilelor
  const byId = useMemo(() => {
    const m = new Map<number, Match>();
    for (const d of days.data ?? []) for (const x of d?.matches ?? []) m.set(x.id, x);
    return m;
  }, [days.data]);
  const cnt = (f: (r: Row) => boolean) => all.filter((r) => f(r) && r.p >= minP).length;
  const rows = useMemo(() => all.filter((r) => (k ? r.key === k : !keys.length || keys.includes(r.key)) && r.p >= minP),
    [all, keys, k, minP]);
  // un card pe meci (ca în „Toate predicțiile”), meciurile în ordinea celei mai sigure selecții
  const cards = useMemo(() => {
    const g = new Map<number, Row[]>();
    for (const r of rows) g.set(r.match_id, [...(g.get(r.match_id) ?? []), r]);
    return [...g.values()];
  }, [rows]);
  if (q.loading) return <div className="card p-4 text-sm text-muted-foreground">Se încarcă…</div>;
  if (!q.data) return <div className="card p-4 text-sm text-muted-foreground">Predicțiile Stil Supersocial nu sunt publicate încă.</div>;
  return (
    <div className="space-y-2 overflow-x-hidden">
      <div className="scrollbar-none -mx-1 flex snap-x gap-1.5 overflow-x-auto px-1 pb-0.5">
        {GROUPS.map(([id, l, ks]) => (
          <button key={id} className={cn('chip shrink-0 snap-start whitespace-nowrap min-h-[40px]', g === id && 'chip-on')} aria-pressed={g === id}
            onClick={() => { setG(id); setK(''); setLimit(40); }}>
            <span aria-hidden>{ICON[id]}</span> {l}
            <span className="num ml-1 rounded-full bg-white/10 px-1.5 text-[10px]">{cnt((r) => !ks.length || ks.includes(r.key))}</span>
          </button>
        ))}
      </div>
      {keys.length > 1 && (
        <div className="scrollbar-none -mx-1 flex gap-1 overflow-x-auto px-1">
          <button className={cn('chip shrink-0 whitespace-nowrap px-2.5 py-1 text-[11px] min-h-[34px]', !k && 'chip-on')} onClick={() => setK('')}>Toate</button>
          {keys.map((x) => <button key={x} className={cn('chip shrink-0 whitespace-nowrap px-2.5 py-1 text-[11px] min-h-[34px]', k === x && 'chip-on')} aria-pressed={k === x}
            onClick={() => { setK(x); setLimit(40); }}>{SHORT[x] ?? x} <span className="num opacity-70">{cnt((r) => r.key === x)}</span></button>)}
        </div>
      )}
      <div className="flex items-center gap-2 text-xs">
        <span className="num font-semibold">{rows.length}</span><span className="text-muted-foreground">selecții în {cards.length} meciuri</span>
        <select aria-label="Șansă minimă" value={minP} onChange={(e) => setMinP(Number(e.target.value))}
          className="ml-auto min-h-[36px] rounded-lg border border-white/10 bg-card px-2 text-xs">
          {[0, 0.5, 0.6, 0.7, 0.8].map((x) => <option key={x} value={x}>{x ? `Șansă ≥${x * 100}%` : 'Orice șansă'}</option>)}
        </select>
        <button aria-label="Informații" aria-expanded={info} onClick={() => setInfo(!info)}
          className={cn('grid h-9 w-9 shrink-0 place-items-center rounded-full border border-white/10 text-sm', info && 'chip-on')}>ⓘ</button>
      </div>
      {info && (
        <div className="fixed inset-0 z-50 flex items-end bg-black/60" onClick={() => setInfo(false)}>
          <div className="card w-full rounded-b-none p-4 pb-8 text-sm" onClick={(e) => e.stopPropagation()}>
            <div className="mb-2 flex items-center justify-between"><b>Despre Stil Supersocial</b>
              <button className="chip min-h-[36px]" onClick={() => setInfo(false)}>Închide</button></div>
            <p className="text-xs text-muted-foreground">Sortate după șansă. EV = șansa modelului × cota Superbet − 1. {q.data.note}</p>
          </div>
        </div>
      )}
      <div className="stagger grid gap-3 md:grid-cols-2">
        {cards.slice(0, limit).map((rs) => <SsCard key={rs[0].match_id} rows={rs} m={byId.get(rs[0].match_id)} />)}
      </div>
      {cards.length > limit && (
        <button type="button" className="btn btn-outline w-full" onClick={() => setLimit((n) => n + 40)}>
          Mai multe meciuri ({cards.length - limit} rămase)
        </button>
      )}
    </div>
  );
}

/** Card de meci în stilul „Toate predicțiile”: ligă, echipe cu sigle, ora; apoi selecțiile Supersocial, cea mai sigură sus. */
function SsCard({ rows, m }: { rows: Row[]; m?: Match }) {
  const [more, setMore] = useState(false);
  const r0 = rows[0];
  const shown = more ? rows : rows.slice(0, 2);
  const iso = r0.kickoff_utc;
  return (
    <article className="card card-hover mcard overflow-hidden">
      <div className="flex items-start gap-3 px-3.5 pb-2 pt-3">
        <div className="min-w-0 flex-1">
          <div className="mb-1.5 flex items-center gap-1.5 text-[11px] text-muted-foreground">
            {m && <TeamLogo src={m.league.logo} name={m.league.name} size={14} />}
            <span className="min-w-0 break-words">{m?.league.name ?? 'Fotbal'}</span>
          </div>
          <div className="space-y-1">
            {[[r0.home, m?.home.logo], [r0.away, m?.away.logo]].map(([name, logo]) => (
              <div key={name as string} className="flex items-center gap-2.5">
                <TeamLogo src={logo as string | null | undefined} name={name as string} size={28} />
                <span className="min-w-0 flex-1 break-words text-[16px] font-semibold leading-tight">{name}</span>
              </div>
            ))}
          </div>
        </div>
        <span className="m-status shrink-0 rounded-lg bg-primary/15 px-2 py-1 text-[12px] font-bold tabular-nums text-primary">{dayLabel(roDay(iso))} · {roTime(iso)}</span>
      </div>
      {r0.corner_mean && rows.some((r) => /C/.test(r.key)) && <div className="px-3.5 pb-2 text-[11px] text-muted-foreground">Cornere așteptate ~{r0.corner_mean} · {r0.src}</div>}
      <div className="space-y-2 px-3 pb-3">
        {shown.map((r) => <SsPick key={r.key} r={r} />)}
      </div>
      <div className="flex items-center gap-2 border-t px-3.5">
        {rows.length > 2 && (
          <button type="button" onClick={() => setMore(!more)} className="min-h-11 text-[13px] font-semibold text-muted-foreground hover:text-foreground">
            {more ? 'Mai puține' : `Încă ${rows.length - 2} ${rows.length - 2 === 1 ? 'piață' : 'piețe'}`}
          </button>
        )}
        {m?.superbet_url && <SuperbetLink url={m.superbet_url} eventId={m.superbet_event_id} className="ml-auto inline-flex min-h-11 shrink-0 items-center gap-1 px-1 text-[13px] font-semibold text-[hsl(0_75%_55%)]" />}
      </div>
    </article>
  );
}

function SsPick({ r }: { r: Row }) {
  const name = NAME[r.key] ?? (r.label === r.key ? SHORT[r.key] ?? r.label : r.label);
  const info = SB[r.key];
  return (
    <div className="rounded-[14px] bg-[hsl(var(--elevated))] px-3 py-2.5 shadow-[inset_3px_0_0_hsl(var(--primary))]">
      <div className="flex items-center gap-3">
        <div className="min-w-0 flex-1">
          <div className="break-words text-[16px] font-extrabold leading-tight">{name}</div>
          {info && <div className="mt-0.5 break-words text-[12px] text-muted-foreground">{info.what}</div>}
          <div className="chance-track mt-2" aria-hidden><span style={{ width: `${Math.max(4, Math.round(r.p * 100))}%` }} /></div>
          <div className="mt-1 flex flex-wrap items-center gap-x-2 text-[12px] text-muted-foreground">
            <span>Șansă <b className="num text-foreground">{Math.round(r.p * 100)}%</b></span>
            {r.edge != null && <span>EV <b className={cn('num', r.edge > 0 ? 'text-win' : 'text-loss')}>{r.edge > 0 ? '+' : ''}{(r.edge * 100).toFixed(1)}%</b></span>}
            {r.bb && <span className="rounded bg-muted px-1 text-[10px] font-bold">Bet Builder</span>}
          </div>
        </div>
        {r.odds ? <span className="odd-chip shrink-0 text-[15px]">{r.odds.toFixed(2)}{r.est ? '*' : ''}</span>
          : <span className="num shrink-0 text-[11px] text-muted-foreground">corect {r.fair_odds?.toFixed(2)}</span>}
      </div>
      {info && <div className="mt-1.5 break-words text-[11px] text-muted-foreground">Pe Superbet: <b className="font-semibold text-foreground/80">{info.where}</b>{r.est ? ' · * cotă estimată' : ''}</div>}
    </div>
  );
}
