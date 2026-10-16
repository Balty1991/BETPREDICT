import { useEffect, useMemo, useState } from 'react';
import { Bot, ChevronRight, Wand2 } from 'lucide-react';
import { useDays } from '@/lib/hooks';
import { useStore } from '@/lib/store';
import { buildPool, beamSearch, makeTicket, type Candidate } from '@/lib/robot';
import { isLostTicket } from '@/lib/board';
import { addDays } from '@/lib/format';
import { TicketCard } from './TicketCard';
import type { Match, Prediction, Ticket } from '@/lib/types';
import { getJSON } from '@/lib/fetcher';

/** Opțiunile generatorului, pe secțiuni. `robot`: predicțiile Robotului principal; `keys`: selecțiile Stil (oferta Superbet). */
type Opt = { id: string; label: string; robot?: (p: Prediction) => boolean; keys?: string[] };
const ou = (sel: 'OVER' | 'UNDER', line: number) => (p: Prediction) => p.market === 'over_under' && p.selection === sel && Number(p.line) === line;
const SECTIONS: Array<{ title: string; opts: Opt[] }> = [
  { title: 'Rezultat', opts: [
    { id: '1x2', label: '1X2', robot: (p) => p.market === '1x2' },
    { id: 'dc', label: 'Șansă dublă', robot: (p) => p.market === 'double_chance' },
    { id: 'dnb', label: 'Egal = pariu returnat', robot: (p) => p.market === 'draw_no_bet' },
  ] },
  { title: 'Goluri în meci · Peste', opts: [
    { id: 'o05', label: 'Peste 0.5', robot: ou('OVER', 0.5) },
    { id: 'o15', label: 'Peste 1.5', robot: ou('OVER', 1.5), keys: ['O15'] },
    { id: 'o25', label: 'Peste 2.5', robot: ou('OVER', 2.5) },
    { id: 'o35', label: 'Peste 3.5', robot: ou('OVER', 3.5) },
  ] },
  { title: 'Goluri în meci · Sub', opts: [
    { id: 'u15', label: 'Sub 1.5', robot: ou('UNDER', 1.5) },
    { id: 'u25', label: 'Sub 2.5', robot: ou('UNDER', 2.5) },
    { id: 'u35', label: 'Sub 3.5', robot: ou('UNDER', 3.5) },
    { id: 'u45', label: 'Sub 4.5', robot: ou('UNDER', 4.5) },
  ] },
  { title: 'Ambele marchează', opts: [
    { id: 'gg', label: 'GG (Da)', robot: (p) => p.market === 'btts' && p.selection === 'YES', keys: ['GG'] },
    { id: 'ng', label: 'GG (Nu)', robot: (p) => p.market === 'btts' && p.selection === 'NO' },
    { id: 'ggo25', label: 'GG sau Peste 2.5', keys: ['GGO25'] },
    { id: 'dcx2o15', label: 'X2 & Peste 1.5', keys: ['DCX2_O15'] },
  ] },
  { title: 'Intervale goluri', opts: [
    { id: 'g13', label: '1–3 goluri', keys: ['G13'] },
    { id: 'g24', label: '2–4 goluri', keys: ['G24'] },
    { id: 'g25', label: '2–5 goluri', keys: ['G25'] },
  ] },
  { title: 'Goluri pe echipă', opts: [
    { id: 'o05t', label: 'Echipa marchează (Peste 0.5)', keys: ['HO05', 'AO05'] },
    { id: 'o15t', label: 'Echipa Peste 1.5', keys: ['HO15', 'AO15'] },
    { id: 'g13t', label: 'Echipa 1–3 goluri', keys: ['HG13', 'AG13'] },
  ] },
  { title: 'Bet Builder', opts: [
    { id: 'bb14', label: 'Echipa 1–4 & R1 Sub 4.5', keys: ['BB_HG14_U45', 'BB_AG14_U45'] },
    { id: 'bb13', label: 'Echipa 1–3 & R1 Sub 3.5', keys: ['BB_HG13_U35', 'BB_AG13_U35'] },
    { id: 'bbh13', label: '1–3 în fiecare repriză & Peste 1.5', keys: ['BB_H13x2_O15'] },
    { id: 'bbc', label: 'Cornere Peste 6.5 & Sub 14.5', keys: ['BB_C65_U145'] },
    { id: 'bbh1c', label: 'R1 cornere 3–6', keys: ['BB_H1C25_U65'] },
  ] },
  { title: 'Reprize', opts: [
    { id: 'r1r2', label: 'Gol în ambele reprize', keys: ['R1R2'] },
    { id: 'h13x2', label: '1–3 goluri în fiecare repriză', keys: ['H13x2'] },
    { id: 'h1o05', label: 'R1 Peste 0.5', keys: ['H1O05'] },
    { id: 'h1o15', label: 'R1 Peste 1.5', keys: ['H1O15'] },
    { id: 'h2g13', label: 'R2 1–3 goluri', keys: ['H2G13'] },
    { id: 'r1o15', label: 'R1 Peste 0.5 & meci Peste 1.5', keys: ['R1O15'] },
    { id: 'r1o25', label: 'R1 Peste 0.5 & meci Peste 2.5', keys: ['R1O25'] },
  ] },
  { title: 'Cornere', opts: [
    { id: 'c65', label: 'Peste 6.5', keys: ['C65'] },
    { id: 'c75', label: 'Peste 7.5', keys: ['C75'] },
    { id: 'c85', label: 'Peste 8.5', keys: ['C85'] },
    { id: 'c95', label: 'Peste 9.5', keys: ['C95'] },
    { id: 'cu145', label: 'Sub 14.5', keys: ['CU145'] },
  ] },
  { title: 'Cornere prima repriză', opts: [
    { id: 'h1c25', label: 'R1 Peste 2.5', keys: ['H1C25'] },
    { id: 'h1c35', label: 'R1 Peste 3.5', keys: ['H1C35'] },
    { id: 'h1u65', label: 'R1 Sub 6.5', keys: ['H1U65'] },
    { id: 'h1cint', label: 'R1 interval (<5, 5–6, 7+)', keys: ['H1CLT5', 'H1C56', 'H1C7P'] },
  ] },
  { title: 'Cartonașe', opts: [
    { id: 'yc35', label: 'Peste 3.5', keys: ['YC35'] },
    { id: 'yc45', label: 'Peste 4.5', keys: ['YC45'] },
    { id: 'ycu45', label: 'Sub 4.5', keys: ['YCU45'] },
    { id: 'ycu55', label: 'Sub 5.5', keys: ['YCU55'] },
    { id: 'both15', label: 'Ambele echipe 2+', keys: ['BOTH15'] },
    { id: 'yteam', label: 'Pe echipă (Peste 1.5 / 2.5)', keys: ['HY15', 'AY15', 'HY25', 'AY25'] },
  ] },
];
const OPTS = SECTIONS.flatMap((x) => x.opts);
type Pick = { market: string; outcome: string; ref?: string };
type GenRow = { m: number; k: string; g: string; p: number; o: number; e?: 1; pk?: Pick; bp?: Pick[]; bs?: string[] };
type GenDoc = { labels: Record<string, string>; rows: GenRow[] };

/** Selecțiile Stil ca selecții de generator (șansa realistă publicată de Robot, cota Superbet). */
function stilPool(doc: GenDoc, matches: Map<number, Match>, keys: Set<string>, minOdds: number): Candidate[] {
  const now = Date.now();
  const out: Candidate[] = [];
  for (const r of doc.rows) {
    if (!keys.has(r.k) || r.o < minOdds) continue;
    const m = matches.get(r.m);
    if (!m || m.status !== 'notstarted' || Date.parse(m.kickoff_utc) < now + 5 * 60 * 1000) continue;
    const p = { id: `ss-${r.m}-${r.k}`, match_id: r.m, market: 'ss', line: null, selection: r.k, label: doc.labels[r.k] ?? r.k, p: r.p,
      odds: r.o, p_market: null, grade: null, market_healthy: true, reasons: ['Stil Supersocial: șansa realistă, după rezultatele reale pe piață'],
      sb_pick: r.pk ?? null, bb_picks: r.bp ?? null, bb_steps: r.bs ?? null } as unknown as Prediction;
    out.push({ m, p, odds: r.o, pAdj: r.p, lo: Math.log(r.o), lp: Math.log(r.p), estimated: !!r.e });
  }
  return out;
}

/** Generatorul cu regulile tale. Încarcă meciurile zilei doar când e deschis. */
export function ManualGenerator({ date }: { date: string }) {
  const [open, setOpen] = useState(false);
  return (
    <details className="card group p-4" onToggle={(e) => setOpen(e.currentTarget.open)}>
      <summary className="flex min-h-[44px] cursor-pointer list-none items-center gap-2 font-bold"><Wand2 className="h-4 w-4 text-primary" />Generator cu regulile tale<ChevronRight className="ml-auto h-4 w-4 text-muted-foreground transition-transform group-open:rotate-90" /></summary>
      {open && <GeneratorBody date={date} />}
    </details>
  );
}

function GeneratorBody({ date }: { date: string }) {
  const [span, setSpan] = useState(3);
  const days = useDays(useMemo(() => Array.from({ length: span }, (_, i) => addDays(date, i)), [date, span]));
  const settings = useStore((s) => s.settings);
  const pool: Candidate[] = useMemo(() => (days.data ? buildPool(days.data.filter(Boolean) as never, { minOdds: settings.minOdds, allowEstimated: settings.allowEstimatedOdds, includeUnhealthy: true }) : []), [days.data, settings.minOdds, settings.allowEstimatedOdds]);
  const [target, setTarget] = useState(20);
  const [nMin, setNMin] = useState(3);
  const [nMax, setNMax] = useState(8);
  const [groups, setGroups] = useState<Set<string>>(() => new Set(['dc', 'o15', 'gg', 'bb14']));
  const chosen = OPTS.filter((o) => groups.has(o.id));
  const stilKeys = new Set(chosen.flatMap((o) => o.keys ?? []));
  const wantStil = stilKeys.size > 0;
  const [gen, setGen] = useState<GenDoc | null>(null);
  useEffect(() => {
    if (!wantStil || gen) return;
    getJSON<GenDoc>('api/supersocial/generator.json').then(setGen, () => setGen({ labels: {}, rows: [] }));
  }, [wantStil, gen]);
  const toggle = (id: string) => setGroups((g) => { const n = new Set(g); if (n.has(id)) n.delete(id); else n.add(id); return n; });
  const [minP, setMinP] = useState(0.55);
  const [res, setRes] = useState<Ticket | null>(null);
  const [err, setErr] = useState('');
  const run = () => {
    const robotOk = chosen.filter((o) => o.robot).map((o) => o.robot!);
    const matches = new Map<number, Match>();
    for (const d of days.data ?? []) for (const m of d?.matches ?? []) matches.set(m.id, m);
    const stil = wantStil && gen ? stilPool(gen, matches, stilKeys, settings.minOdds) : [];
    const f = [...pool.filter((c) => robotOk.some((ok) => ok(c.p))), ...stil].filter((c) => c.pAdj >= minP * 0.9);
    // regulile sunt ale tale: intră și predicțiile fără valoare față de cotă, dar cele cu valoare au prioritate
    const legs = beamSearch(f, { min: target * 0.85, max: target * 1.25, nMin, nMax }, (c) => (-c.lp / c.lo) * (c.p.market_healthy === false ? 1.1 : 1), new Set());
    if (!legs) {
      const nm = new Set(f.map((c) => c.m.id)).size;
      setRes(null);
      setErr(nm < nMin
        ? `Doar ${nm} meciuri neîncepute au o selecție cu șansă ≥ ${Math.round(minP * 100)}% și cotă ≥ ${settings.minOdds} în ${span === 1 ? 'ziua aleasă' : `următoarele ${span} zile`}; ai cerut cel puțin ${nMin}. Ia mai multe zile, scade șansa minimă sau cota minimă din Setări.`
        : `Sunt ${nm} meciuri potrivite, dar nu ies ${nMin}–${nMax} selecții la cota ~${target}. Schimbă cota țintă sau numărul de meciuri.`);
      return;
    }
    setErr('');
    setRes(makeTicket(legs, { kind: 'manual_robot', variant: 'personalizat', variant_label: `Personalizat ~${target}`, target, date, created_by: 'robot', reasons: [`Reguli: ${nMin}–${nMax} meciuri, p ≥ ${Math.round(minP * 100)}%, ${chosen.map((o) => o.label).join(', ')}`] }));
  };
  return (
    <div className="mt-3">
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-6">
        <label className="text-xs text-muted-foreground">Cotă țintă<input type="number" min={1.5} step={1} className="input mt-1" value={target} onChange={(e) => setTarget(Math.max(1.5, Number(e.target.value) || 2))} /></label>
        <label className="text-xs text-muted-foreground">Min. meciuri<input type="number" min={1} max={30} className="input mt-1" value={nMin} onChange={(e) => setNMin(Math.min(30, Number(e.target.value) || 1))} /></label>
        <label className="text-xs text-muted-foreground">Max. meciuri<input type="number" min={1} max={30} className="input mt-1" value={nMax} onChange={(e) => setNMax(Math.min(30, Number(e.target.value) || 1))} /></label>
        <label className="text-xs text-muted-foreground">Meciuri din<select className="input mt-1" value={span} onChange={(e) => setSpan(Number(e.target.value))}><option value={1}>Ziua aleasă</option><option value={2}>Ziua aleasă + mâine</option><option value={3}>Următoarele 3 zile</option><option value={7}>Următoarele 7 zile</option></select></label>
        <label className="text-xs text-muted-foreground">Șansă minimă / selecție: <b className="text-foreground">{Math.round(minP * 100)}%</b><input type="range" min={0.4} max={0.9} step={0.05} className="mt-2 w-full" value={minP} onChange={(e) => setMinP(Number(e.target.value))} /></label>
      </div>
      <fieldset className="mt-3 space-y-2.5">
        <legend className="text-xs text-muted-foreground">Piețe: bifează ce vrei să intre pe bilet ({chosen.length} alese) <button type="button" className="ml-1 font-semibold text-primary" onClick={() => setGroups(new Set())}>Golește</button></legend>
        {SECTIONS.map((sec) => {
          const all = sec.opts.every((o) => groups.has(o.id));
          return (
            <div key={sec.title}>
              <div className="mb-1 flex items-center gap-2 text-[11px] font-bold uppercase tracking-wider text-muted-foreground">
                {sec.title}
                <button type="button" className="font-semibold normal-case tracking-normal text-primary" onClick={() => setGroups((g) => { const n = new Set(g); sec.opts.forEach((o) => (all ? n.delete(o.id) : n.add(o.id))); return n; })}>{all ? 'niciuna' : 'toate'}</button>
              </div>
              <div className="flex flex-wrap gap-1.5">
                {sec.opts.map((o) => (
                  <button key={o.id} type="button" aria-pressed={groups.has(o.id)} onClick={() => toggle(o.id)}
                    className={`press rounded-full border px-3 py-1.5 text-xs font-semibold ${groups.has(o.id) ? 'border-primary bg-primary/15 text-primary' : 'text-muted-foreground'}`}>
                    {groups.has(o.id) ? '✓ ' : ''}{o.label}
                  </button>
                ))}
              </div>
            </div>
          );
        })}
        {wantStil && <p className="text-[11px] text-muted-foreground">Piețele din oferta Superbet (intervale, echipe, Bet Builder, reprize, cornere, cartonașe) sunt pe următoarele 3 zile, cu șansa realistă (corectată cu rezultatele reale).{!gen ? ' Se încarcă…' : ''}</p>}
      </fieldset>
      <button className="btn btn-primary mt-3" disabled={days.loading || !groups.size || (wantStil && !gen)} onClick={run}><Bot className="h-4 w-4" />{days.loading ? 'Se încarcă meciurile…' : 'Generează'}</button>
      {err && <p className="mt-2 text-sm text-warn">{err}</p>}
      {res && !isLostTicket(res) && <div className="mt-3"><TicketCard t={res} /></div>}
    </div>
  );
}
