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

/** Grupele de piețe din care poate alege generatorul: clasice (Robotul principal) și Stil (oferta Superbet). */
const GROUPS: Array<{ id: string; label: string; stil?: boolean }> = [
  { id: 'rezultat', label: 'Rezultat (1X2, șansă dublă, egal = returnat)' },
  { id: 'goluri', label: 'Goluri clasice (Peste/Sub, GG)' },
  { id: 'interval', label: 'Intervale goluri', stil: true },
  { id: 'echipe', label: 'Goluri pe echipă (marchează, 1–3, 1–4)', stil: true },
  { id: 'reprize', label: 'Reprize', stil: true },
  { id: 'combo', label: 'Combinații (GG sau Peste 2.5, R1 + meci)', stil: true },
  { id: 'cornere', label: 'Cornere', stil: true },
  { id: 'r1_cornere', label: 'Cornere prima repriză', stil: true },
  { id: 'cartonase', label: 'Cartonașe', stil: true },
];
const CLASSIC: Record<string, string[]> = { rezultat: ['1x2', 'double_chance', 'draw_no_bet'], goluri: ['over_under', 'btts'] };
const BB = ['BB_C65_U145', 'BB_H1C25_U65', 'BB_H13x2_O15', 'BB_HG13_U35', 'BB_AG13_U35', 'BB_HG14_U45', 'BB_AG14_U45'];
type Pick = { market: string; outcome: string; ref?: string };
type GenRow = { m: number; k: string; g: string; p: number; o: number; e?: 1; pk?: Pick; bp?: Pick[]; bs?: string[] };
type GenDoc = { labels: Record<string, string>; rows: GenRow[] };

/** Selecțiile Stil ca selecții de generator (șansa realistă publicată de Robot, cota Superbet). */
function stilPool(doc: GenDoc, matches: Map<number, Match>, groups: Set<string>, withBB: boolean, minOdds: number): Candidate[] {
  const now = Date.now();
  const out: Candidate[] = [];
  for (const r of doc.rows) {
    if (!groups.has(r.g) || (!withBB && BB.includes(r.k)) || r.o < minOdds) continue;
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
  const [groups, setGroups] = useState<Set<string>>(() => new Set(['rezultat', 'goluri']));
  const [withBB, setWithBB] = useState(true);
  const wantStil = GROUPS.some((g) => g.stil && groups.has(g.id));
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
    const classic = Object.entries(CLASSIC).filter(([g]) => groups.has(g)).flatMap(([, ms]) => ms);
    const matches = new Map<number, Match>();
    for (const d of days.data ?? []) for (const m of d?.matches ?? []) matches.set(m.id, m);
    const stil = wantStil && gen ? stilPool(gen, matches, groups, withBB, settings.minOdds) : [];
    const f = [...pool.filter((c) => classic.includes(c.p.market)), ...stil].filter((c) => c.pAdj >= minP * 0.9);
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
    setRes(makeTicket(legs, { kind: 'manual_robot', variant: 'personalizat', variant_label: `Personalizat ~${target}`, target, date, created_by: 'robot', reasons: [`Reguli: ${nMin}–${nMax} meciuri, p ≥ ${Math.round(minP * 100)}%, ${GROUPS.filter((g) => groups.has(g.id)).map((g) => g.label.split(' (')[0].toLowerCase()).join(', ')}`] }));
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
      <fieldset className="mt-3">
        <legend className="text-xs text-muted-foreground">Piețe (bifează ce vrei să intre pe bilet)</legend>
        <div className="mt-1 flex flex-wrap gap-1.5">
          {GROUPS.map((g) => (
            <button key={g.id} type="button" aria-pressed={groups.has(g.id)} onClick={() => toggle(g.id)}
              className={`press rounded-full border px-3 py-1.5 text-xs font-semibold ${groups.has(g.id) ? 'border-primary bg-primary/15 text-primary' : 'text-muted-foreground'}`}>
              {groups.has(g.id) ? '✓ ' : ''}{g.label}
            </button>
          ))}
          {wantStil && <button type="button" aria-pressed={withBB} onClick={() => setWithBB((v) => !v)}
            className={`press rounded-full border px-3 py-1.5 text-xs font-semibold ${withBB ? 'border-primary bg-primary/15 text-primary' : 'text-muted-foreground'}`}>{withBB ? '✓ ' : ''}Include Bet Builder</button>}
        </div>
        {wantStil && <p className="mt-1 text-[11px] text-muted-foreground">Piețele Stil vin din oferta Superbet pe următoarele 3 zile, cu șansa realistă (corectată cu rezultatele reale).{!gen ? ' Se încarcă…' : ''}</p>}
      </fieldset>
      <button className="btn btn-primary mt-3" disabled={days.loading || !groups.size || (wantStil && !gen)} onClick={run}><Bot className="h-4 w-4" />{days.loading ? 'Se încarcă meciurile…' : 'Generează'}</button>
      {err && <p className="mt-2 text-sm text-warn">{err}</p>}
      {res && !isLostTicket(res) && <div className="mt-3"><TicketCard t={res} /></div>}
    </div>
  );
}
