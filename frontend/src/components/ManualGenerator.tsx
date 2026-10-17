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
    { id: 'h1', label: 'Victorie gazde (1)', robot: (p) => p.market === '1x2' && p.selection === 'HOME' },
    { id: 'x', label: 'Egal (X)', robot: (p) => p.market === '1x2' && p.selection === 'DRAW' },
    { id: 'a2', label: 'Victorie oaspeți (2)', robot: (p) => p.market === '1x2' && p.selection === 'AWAY' },
    { id: 'dc1x', label: 'Șansă dublă 1X', robot: (p) => p.market === 'double_chance' && p.selection === '1X' },
    { id: 'dc12', label: 'Șansă dublă 12', robot: (p) => p.market === 'double_chance' && p.selection === '12' },
    { id: 'dcx2', label: 'Șansă dublă X2', robot: (p) => p.market === 'double_chance' && p.selection === 'X2' },
    { id: 'dnbh', label: 'Egal = returnat · gazde', robot: (p) => p.market === 'draw_no_bet' && p.selection === 'HOME' },
    { id: 'dnba', label: 'Egal = returnat · oaspeți', robot: (p) => p.market === 'draw_no_bet' && p.selection === 'AWAY' },
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

/** Câmp numeric ușor de scris pe telefon: la atingere se selectează tot, scrii liber (cu virgulă sau punct), valoarea
 *  se verifică și se încadrează în limite doar la ieșirea din câmp sau la „Enter”. */
function NumField({ label, value, min, max, decimals, onCommit }: { label: string; value: number; min: number; max: number; decimals: boolean; onCommit: (v: number) => void }) {
  const [text, setText] = useState<string | null>(null);
  const commit = () => {
    if (text === null) return;
    const v = Number(text.replace(',', '.').trim());
    if (text.trim() !== '' && Number.isFinite(v)) onCommit(Math.min(max, Math.max(min, decimals ? Math.round(v * 100) / 100 : Math.round(v))));
    setText(null);
  };
  return (
    <label className="text-xs text-muted-foreground">{label}
      <input type="text" inputMode={decimals ? 'decimal' : 'numeric'} enterKeyHint="done" className="input mt-1"
        value={text ?? String(value)} onFocus={(e) => { setText(String(value)); e.currentTarget.select(); }}
        onChange={(e) => setText(e.target.value.replace(/[^\d.,]/g, ''))} onBlur={commit}
        onKeyDown={(e) => { if (e.key === 'Enter') (e.currentTarget as HTMLInputElement).blur(); }} />
    </label>
  );
}

/** Ligile mari (pentru filtrul „doar ligile mari”), după numele din date. */
const TOP = /premier league|laliga|la liga|serie a|bundesliga|ligue 1|eredivisie|primeira|liga portugal|superliga|liga i\b|champions league|europa league|conference league|championship|s[üu]per lig|pro league|scottish premiership/i;
type Rules = { target: number; nMin: number; nMax: number; span: number; minP: number; groups: string[]; oddsLo: number; oddsHi: number;
  valueOnly: boolean; noMine: boolean; leagues: 'all' | 'top'; exclude: string; pick?: string[]; tag?: string;
  posOnly?: boolean; realOnly?: boolean; hFrom?: number; hTo?: number; variants?: number };
const DEFAULT_RULES: Rules = { target: 20, nMin: 3, nMax: 8, span: 3, minP: 0.55, groups: ['dc1x', 'dc12', 'o15', 'gg', 'bb14'], oddsLo: 1.1, oddsHi: 3,
  valueOnly: false, noMine: false, leagues: 'all', exclude: '' };
const LAST = 'bp_gen_last', PRESETS = 'bp_gen_presets';
/** Regulile vechi (înainte de împărțirea pe variante): „dc”, „1x2”, „dnb” → toate variantele lor. */
const ALIAS: Record<string, string[]> = { dc: ['dc1x', 'dc12', 'dcx2'], '1x2': ['h1', 'x', 'a2'], dnb: ['dnbh', 'dnba'] };
const normGroups = (g: string[]) => [...new Set(g.flatMap((x) => ALIAS[x] ?? [x]))];
/** Reguli gata făcute: predicțiile ≥ 80% pe piețele care au ieșit pe plus (sau pe zero) la cota Superbet (vezi Audit › Tiparul 80%+).
 *  „cu Stil” adaugă selecțiile Stil de 80%+ care au ținut pasul pe istoric (echipa marchează, cornere Peste 6.5 / Sub 14.5,
 *  cartonașe Sub 5.5); cotele lor sunt mici, deci biletul are mai multe selecții. */
const PATTERN80: Rules = { target: 20, nMin: 12, nMax: 26, span: 3, minP: 0.8, groups: ['o15', 'o25', 'dc1x', 'dc12', 'h1', 'dnba'],
  oddsLo: 1.15, oddsHi: 1.6, valueOnly: false, noMine: false, leagues: 'all', exclude: '', tag: 'p80' };
const PATTERN80S: Rules = { ...PATTERN80, nMin: 14, nMax: 30, oddsLo: 1.08, groups: [...PATTERN80.groups, 'o05t', 'c65', 'cu145', 'ycu55'], tag: 'p80s' };
const PATTERNS: Array<{ r: Rules; label: string; hint: string }> = [
  { r: PATTERN80, label: 'Tiparul 80%+ · clasice', hint: 'Peste 1.5, 1X, 12, victorie gazde' },
  { r: PATTERN80S, label: 'Tiparul 80%+ · clasice + Stil', hint: 'plus echipa marchează, cornere, cartonașe Sub 5.5' },
];
const PREV = 'bp_gen_prev';
function readLS<T>(k: string, d: T): T { try { const v = localStorage.getItem(k); return v ? { ...d, ...JSON.parse(v) } as T : d; } catch { return d; } }
function readPresets(): Record<string, Rules> { try { return JSON.parse(localStorage.getItem(PRESETS) || '{}'); } catch { return {}; } }
function writeLS(k: string, v: unknown) { try { localStorage.setItem(k, JSON.stringify(v)); } catch { /* fără stocare: regulile rămân doar acum */ } }

const oneIn = (p: number) => (p > 0 ? `1 din ${p >= 0.5 ? (1 / p).toFixed(1) : Math.round(1 / p).toLocaleString('ro-RO')}` : '—');

type Gen = { legs: Candidate[]; ticket: Ticket };
type PosDoc = { stil: string[]; main: Array<{ market: string; band: string }> };
const roHour = (iso: string) => Number(new Intl.DateTimeFormat('en-GB', { hour: '2-digit', hourCycle: 'h23', timeZone: 'Europe/Bucharest' }).format(new Date(iso)));
const bandOf = (o: number) => (o < 1.4 ? 'lo' : o <= 2 ? 'mid' : 'hi');
const mkKey = (p: Prediction) => (p.market === 'over_under' ? `over_under_${Number(p.line)}` : p.market);
/** Piață cu ROI pozitiv pe rezultatele reale: Stil după cheie, Robotul principal după piață × banda de cotă. */
function isPositive(c: Candidate, d: PosDoc | null): boolean {
  if (!d) return false;
  if (c.p.market === 'ss') return d.stil.includes(c.p.selection);
  return d.main.some((x) => x.market === mkKey(c.p) && x.band === bandOf(c.odds));
}
/** Șansa ca cel mult o selecție să piardă (sistemul N−1 plătește ceva). */
function sysChance(legs: Candidate[]): number {
  const ps = legs.map((c) => c.pAdj);
  const all = ps.reduce((a, p) => a * p, 1);
  return all + ps.reduce((a, p) => a + (all / p) * (1 - p), 0);
}

function GeneratorBody({ date }: { date: string }) {
  const [r, setR] = useState<Rules>(() => {
    const x = readLS(LAST, DEFAULT_RULES);
    // reguli salvate înainte de etichetă: dacă sunt exact tiparul, le recunoaștem ca tipar
    const same = !x.tag && PATTERNS.find((pt) => pt.r.minP === x.minP && [...pt.r.groups].sort().join() === [...x.groups].sort().join());
    return { ...x, groups: normGroups(x.groups), tag: x.tag ?? (same ? same.r.tag : undefined) };
  });
  // orice schimbare manuală scoate eticheta tiparului (regulile rămân, dar nu mai sunt „tiparul”)
  const set = (patch: Partial<Rules>) => setR((x) => { const n = { ...x, tag: undefined, ...patch }; writeLS(LAST, n); return n; });
  /** Tiparul se bifează și se debifează: la debifare revin regulile de dinainte. */
  const togglePattern = (pt: Rules) => {
    if (r.tag === pt.tag) { set({ ...readLS(PREV, DEFAULT_RULES), tag: undefined }); return; }
    if (!r.tag) writeLS(PREV, r);
    set(pt);
  };
  const [presets, setPresets] = useState<Record<string, Rules>>(() => readPresets());
  const [presetName, setPresetName] = useState('');
  const days = useDays(useMemo(() => Array.from({ length: r.span }, (_, i) => addDays(date, i)), [date, r.span]));
  const settings = useStore((s) => s.settings);
  const myTickets = useStore((s) => s.myTickets);
  const pool: Candidate[] = useMemo(() => (days.data ? buildPool(days.data.filter(Boolean) as never, { minOdds: settings.minOdds, allowEstimated: settings.allowEstimatedOdds, includeUnhealthy: true }) : []), [days.data, settings.minOdds, settings.allowEstimatedOdds]);
  const groups = useMemo(() => new Set(r.groups), [r.groups]);
  const chosen = OPTS.filter((o) => groups.has(o.id));
  const stilKeys = new Set(chosen.flatMap((o) => o.keys ?? []));
  const wantStil = stilKeys.size > 0;
  const [gen, setGen] = useState<GenDoc | null>(null);
  useEffect(() => {
    if (!wantStil || gen) return;
    getJSON<GenDoc>('api/supersocial/generator.json').then(setGen, () => setGen({ labels: {}, rows: [] }));
  }, [wantStil, gen]);
  const toggle = (id: string) => set({ groups: groups.has(id) ? r.groups.filter((g) => g !== id) : [...r.groups, id] });
  const [posDoc, setPosDoc] = useState<PosDoc | null>(null);
  useEffect(() => {
    if (!r.posOnly || posDoc) return;
    getJSON<PosDoc>('api/stats/positive_markets.json').then(setPosDoc, () => setPosDoc({ stil: [], main: [] }));
  }, [r.posOnly, posDoc]);
  const [res, setRes] = useState<Gen[]>([]);
  const [locked, setLocked] = useState<Set<string>>(new Set());
  const [err, setErr] = useState('');
  const [mq, setMq] = useState('');

  /** Toate selecțiile care respectă regulile (piețe, șansă, cotă pe selecție, valoare, ligi, meciurile mele). */
  const eligible = (): Candidate[] => {
    const robotOk = chosen.filter((o) => o.robot).map((o) => o.robot!);
    const matches = new Map<number, Match>();
    for (const d of days.data ?? []) for (const m of d?.matches ?? []) matches.set(m.id, m);
    const stil = wantStil && gen ? stilPool(gen, matches, stilKeys, settings.minOdds) : [];
    const mine = new Set(r.noMine ? myTickets.filter((t) => t.status === 'pending').flatMap((t) => t.legs.map((l) => l.match_id)) : []);
    const ex = r.exclude.split(',').map((x) => x.trim().toLowerCase()).filter(Boolean);
    return [...pool.filter((c) => robotOk.some((ok) => ok(c.p))), ...stil].filter((c) => {
      const lg = `${c.m.league.name} ${c.m.league.country ?? ''}`.toLowerCase();
      const h = roHour(c.m.kickoff_utc);
      if (h < (r.hFrom ?? 0) || h > (r.hTo ?? 23)) return false;
      if (r.realOnly && (c.estimated || (c.p.market !== 'ss' && (c.p as { odds_source?: string }).odds_source !== 'superbet'))) return false;
      if (r.posOnly && !isPositive(c, posDoc)) return false;
      return c.p.p >= r.minP && c.odds >= r.oddsLo && c.odds <= r.oddsHi && (!r.valueOnly || c.pAdj * c.odds > 1)
        && !mine.has(c.m.id) && (r.leagues === 'all' || TOP.test(c.m.league.name)) && (!r.pick?.length || r.pick.includes(lgKey(c.m))) && !ex.some((x) => lg.includes(x));
    });
  };
  const cost = (c: Candidate) => (-c.lp / c.lo) * (c.p.market_healthy === false ? 1.1 : 1);
  /** Un bilet: selecțiile fixate + restul căutat, fără meciurile interzise. */
  const build = (f: Candidate[], fixed: Candidate[], banMatches: Set<number>): Candidate[] | null => {
    const lo = fixed.reduce((a, c) => a * c.odds, 1);
    const used = new Set([...fixed.map((c) => c.m.id), ...banMatches]);
    const nMin = Math.max(0, r.nMin - fixed.length), nMax = r.nMax - fixed.length;
    if (lo >= r.target * 0.85 && lo <= r.target * 1.25 && nMin === 0) return fixed;
    if (nMax < 1) return null;
    const rest = beamSearch(f.filter((c) => !used.has(c.m.id)), { min: (r.target * 0.85) / lo, max: (r.target * 1.25) / lo, nMin: Math.max(1, nMin), nMax }, cost, new Set());
    return rest ? [...fixed, ...rest] : null;
  };
  const ticketOf = (legs: Candidate[], i: number): Ticket => {
    const t = makeTicket(legs, { kind: 'manual_robot', variant: `personalizat${i}`, variant_label: `${r.tag ? PATTERNS.find((x) => x.r.tag === r.tag)?.label ?? 'Personalizat' : 'Personalizat'} ~${r.target}${i ? ` · varianta ${i + 1}` : ''}`, target: r.target, date, created_by: 'robot',
      reasons: [`Reguli: ${r.nMin}–${r.nMax} meciuri, șansă ≥ ${Math.round(r.minP * 100)}%, cotă pe selecție ${r.oddsLo}–${r.oddsHi}${r.valueOnly ? ', doar cu valoare' : ''}${r.leagues === 'top' ? ', ligile mari' : ''}: ${chosen.map((o) => o.label).join(', ')}`] });
    return t;
  };
  const run = () => {
    const f = eligible();
    const fixed = res.flatMap((g) => g.legs).filter((c, i, a) => locked.has(String(c.p.id)) && a.findIndex((x) => x.p.id === c.p.id) === i);
    const out: Gen[] = [];
    const ban = new Set<number>();
    for (let i = 0; i < (r.variants ?? 3); i++) {
      // variantele 2 și 3: alte meciuri decât cele de pe variantele de dinainte (dacă nu ajung, se acceptă repetări)
      const legs = build(f, fixed, ban) ?? (i ? build(f, fixed, new Set()) : null);
      if (!legs || out.some((g) => g.legs.map((c) => c.p.id).sort().join() === legs.map((c) => c.p.id).sort().join())) break;
      out.push({ legs, ticket: ticketOf(legs, i) });
      legs.forEach((c) => { if (!locked.has(String(c.p.id))) ban.add(c.m.id); });
    }
    if (!out.length) {
      const nm = new Set(f.map((c) => c.m.id)).size;
      setRes([]);
      setErr(nm < r.nMin
        ? `Doar ${nm} meciuri neîncepute trec regulile (piețe, șansă ≥ ${Math.round(r.minP * 100)}%, cotă ${r.oddsLo}–${r.oddsHi}${r.valueOnly ? ', cu valoare' : ''}) în ${r.span === 1 ? 'ziua aleasă' : `următoarele ${r.span} zile`}; ai cerut cel puțin ${r.nMin}.${r.tag === 'p80' ? ' Încearcă „Tiparul 80%+ · clasice + Stil”: are mult mai multe selecții.' : ' Bifează mai multe piețe, ia mai multe zile sau scade șansa minimă.'}`
        : `Sunt ${nm} meciuri potrivite, dar nu ies ${r.nMin}–${r.nMax} selecții la cota ~${r.target}. Schimbă cota țintă, numărul de meciuri sau cota pe selecție.`);
      return;
    }
    setErr('');
    setRes(out);
  };
  /** Înlocuiește o selecție: aceleași selecții (fără ea), meciul ei nu mai intră. */
  const swap = (gi: number, c: Candidate) => {
    const g = res[gi];
    const keep = g.legs.filter((x) => x.p.id !== c.p.id);
    const f = eligible();
    const lo = keep.reduce((a, x) => a * x.odds, 1);
    const others = new Set([...keep.map((x) => x.m.id), c.m.id]);
    const alt = f.filter((x) => !others.has(x.m.id)).sort((a, b) => Math.abs(Math.log(lo * a.odds / r.target)) - Math.abs(Math.log(lo * b.odds / r.target)) || cost(a) - cost(b))[0];
    const legs = alt ? [...keep, alt] : build(f, keep.filter((x) => locked.has(String(x.p.id))), others);
    if (!legs) { setErr('Nu am găsit altă selecție care să păstreze cota; schimbă regulile.'); return; }
    setErr('');
    setRes(res.map((x, i) => (i === gi ? { legs, ticket: ticketOf(legs, gi) } : x)));
  };
  const toggleLock = (c: Candidate) => setLocked((l) => { const n = new Set(l); const id = String(c.p.id); if (n.has(id)) n.delete(id); else n.add(id); return n; });
  const savePreset = () => {
    const name = presetName.trim();
    if (!name) return;
    const n = { ...presets, [name]: r };
    setPresets(n); writeLS(PRESETS, n); setPresetName('');
  };
  const delPreset = (name: string) => { const n = { ...presets }; delete n[name]; setPresets(n); writeLS(PRESETS, n); };
  return (
    <div className="gen mt-3 space-y-3">
      <div className="flex items-center justify-end gap-2">
        {Object.keys(presets).length > 0 && (
          <select aria-label="Regulile mele" className="input h-9 min-h-0 w-auto py-0 text-xs" value="" onChange={(e) => { const n = e.target.value; if (n) set({ ...presets[n], groups: normGroups(presets[n].groups) }); }}>
            <option value="">Regulile mele…</option>{Object.keys(presets).map((n) => <option key={n} value={n}>{n}</option>)}
          </select>
        )}
        <details className="relative">
          <summary className="btn btn-outline h-9 min-h-0 list-none px-3 text-xs">Salvează</summary>
          <div className="absolute right-0 z-30 mt-1 w-60 space-y-2 rounded-2xl border bg-popover p-3 shadow-lg">
            <input className="input h-9 min-h-0" placeholder="Nume reguli" value={presetName} onChange={(e) => setPresetName(e.target.value)} />
            <button type="button" className="btn btn-primary h-9 min-h-0 w-full" disabled={!presetName.trim()} onClick={savePreset}>Salvează regulile</button>
            {Object.keys(presets).map((n) => <div key={n} className="flex items-center justify-between text-xs"><span>{n}</span><button type="button" className="text-loss" aria-label={`Șterge regulile ${n}`} onClick={() => delPreset(n)}>Șterge</button></div>)}
          </div>
        </details>
      </div>

      <GenCard n={1} title="Obiectiv" summary={`cotă ${r.target >= 1000 ? '1000+' : r.target} · ${r.variants ?? 3} variante`} open>
        <div className="grid grid-cols-5 gap-1 rounded-2xl bg-muted/60 p-1" role="group" aria-label="Cotă țintă">
          {[20, 50, 100, 500, 1000].map((v) => (
            <button key={v} type="button" aria-pressed={r.target === v} onClick={() => set({ target: v, nMax: Math.max(r.nMax, v >= 500 ? 16 : v >= 100 ? 12 : r.nMax) })}
              className={`press min-h-11 rounded-xl text-sm font-extrabold ${r.target === v ? 'gen-seg-on' : 'text-muted-foreground'}`}>{v >= 1000 ? '1000+' : v}</button>
          ))}
        </div>
        <div className="mt-3 grid grid-cols-2 gap-3">
          <NumField label="Altă cotă" value={r.target} min={1.5} max={100000} decimals={true} onCommit={(v) => set({ target: v })} />
          <div className="text-xs text-muted-foreground">Variante<div className="mt-1 grid grid-cols-3 gap-1">{[3, 4, 5].map((n) => <button key={n} type="button" aria-pressed={(r.variants ?? 3) === n} onClick={() => set({ variants: n })} className={`press min-h-11 rounded-xl border text-sm font-bold ${(r.variants ?? 3) === n ? 'gen-seg-on border-transparent' : ''}`}>{n}</button>)}</div></div>
        </div>
      </GenCard>

      <GenCard n={2} title="Meciuri" summary={`${r.nMin}–${r.nMax} meciuri · cotă ${r.oddsLo}–${r.oddsHi} · șansă ≥ ${Math.round(r.minP * 100)}%`}>
        <DualRange label="Meciuri pe bilet" min={1} max={30} step={1} lo={r.nMin} hi={r.nMax} fmt={(v) => String(v)} onChange={(lo, hi) => set({ nMin: lo, nMax: hi })} />
        <DualRange label="Cotă pe selecție" min={1.05} max={5} step={0.05} lo={Math.max(1.05, r.oddsLo)} hi={Math.min(5, r.oddsHi)} fmt={(v) => v.toFixed(2)} onChange={(lo, hi) => set({ oddsLo: Math.round(lo * 100) / 100, oddsHi: Math.round(hi * 100) / 100 })} />
        <label className="block text-xs text-muted-foreground">Șansă minimă pe selecție <b className="num float-right text-foreground">{Math.round(r.minP * 100)}%</b>
          <input type="range" min={0.4} max={0.9} step={0.05} className="gen-range mt-2 w-full" value={r.minP} onChange={(e) => set({ minP: Number(e.target.value) })} /></label>
        <div>
          <div className="mb-1 text-xs text-muted-foreground">Zile</div>
          <div className="grid grid-cols-4 gap-1">{([[1, 'Azi'], [2, '+ mâine'], [3, '3 zile'], [7, '7 zile']] as const).map(([v, l]) => <button key={v} type="button" aria-pressed={r.span === v} onClick={() => set({ span: v })} className={`press min-h-10 rounded-xl border text-xs font-bold ${r.span === v ? 'gen-seg-on border-transparent' : ''}`}>{l}</button>)}</div>
        </div>
        <div className="grid grid-cols-2 gap-2">
          <label className="text-xs text-muted-foreground">Start de la<select className="input mt-1" value={r.hFrom ?? 0} onChange={(e) => set({ hFrom: Number(e.target.value) })}>{Array.from({ length: 24 }, (_, h) => <option key={h} value={h}>{String(h).padStart(2, '0')}:00</option>)}</select></label>
          <label className="text-xs text-muted-foreground">până la<select className="input mt-1" value={r.hTo ?? 23} onChange={(e) => set({ hTo: Number(e.target.value) })}>{Array.from({ length: 24 }, (_, h) => <option key={h} value={h}>{String(h).padStart(2, '0')}:59</option>)}</select></label>
        </div>
      </GenCard>

      <GenCard n={3} title="Piețe" summary={`${chosen.length} piețe${r.tag ? ' · ' + (PATTERNS.find((x) => x.r.tag === r.tag)?.label ?? '') : ''}`}>
        <div className="flex flex-wrap gap-1.5">
          {PATTERNS.map((pt) => { const on = r.tag === pt.r.tag; return (
            <button key={pt.r.tag} type="button" aria-pressed={on} onClick={() => togglePattern(pt.r)} title={pt.hint}
              className={`press rounded-full border px-3 py-1.5 text-xs font-bold ${on ? 'gen-seg-on border-transparent' : 'border-primary/40 text-primary'}`}>{on ? '✓ ' : '✦ '}{pt.label}</button>); })}
          <button type="button" className="ml-auto text-xs font-semibold text-muted-foreground" onClick={() => set({ groups: [] })}>Golește</button>
        </div>
        <input className="input h-9 min-h-0 text-sm" placeholder="Caută piață…" value={mq} onChange={(e) => setMq(e.target.value)} />
        <div className="space-y-1.5">
          {SECTIONS.map((sec) => {
            const opts = sec.opts.filter((o) => !mq.trim() || o.label.toLowerCase().includes(mq.trim().toLowerCase()));
            if (!opts.length) return null;
            const nOn = sec.opts.filter((o) => groups.has(o.id)).length;
            const all = nOn === sec.opts.length;
            return (
              <details key={sec.title} className="group rounded-xl border bg-[hsl(var(--elevated)/0.6)] px-3" open={!!mq.trim()}>
                <summary className="flex min-h-11 cursor-pointer list-none items-center gap-2 text-sm font-semibold">
                  <span className="flex-1">{sec.title}</span>
                  <span className={`num rounded-full px-2 text-[11px] font-bold ${nOn ? 'bg-primary/15 text-primary' : 'text-muted-foreground'}`}>{nOn}/{sec.opts.length}</span>
                  <span className="text-xs text-muted-foreground transition-transform group-open:rotate-180">▾</span>
                </summary>
                <div className="pb-3">
                  <button type="button" className="mb-1.5 text-xs font-semibold text-primary" onClick={() => set({ groups: all ? r.groups.filter((g) => !sec.opts.some((o) => o.id === g)) : [...new Set([...r.groups, ...sec.opts.map((o) => o.id)])] })}>{all ? 'Niciuna' : 'Toate'}</button>
                  <div className="flex flex-wrap gap-1.5">
                    {opts.map((o) => (
                      <button key={o.id} type="button" aria-pressed={groups.has(o.id)} onClick={() => toggle(o.id)}
                        className={`press rounded-full border px-3 py-1.5 text-xs font-semibold ${groups.has(o.id) ? 'border-primary bg-primary/15 text-primary' : 'text-muted-foreground'}`}>{o.label}</button>
                    ))}
                  </div>
                </div>
              </details>
            );
          })}
        </div>
        {wantStil && !gen && <p className="text-[11px] text-muted-foreground">Se încarcă oferta Superbet…</p>}
      </GenCard>

      <GenCard n={4} title="Ligi și filtre" summary={[(r.pick?.length ? `${r.pick.length} ligi` : r.leagues === 'top' ? 'ligi mari' : 'toate ligile'), r.posOnly && 'ROI+', r.realOnly && 'cotă reală', r.valueOnly && 'valoare', r.noMine && 'fără ale mele'].filter(Boolean).join(' · ')}>
        <div className="grid grid-cols-2 gap-1 rounded-2xl bg-muted/60 p-1">{([['all', 'Toate ligile'], ['top', 'Ligile mari']] as const).map(([v, l]) => <button key={v} type="button" aria-pressed={r.leagues === v} onClick={() => set({ leagues: v })} className={`press min-h-10 rounded-xl text-xs font-bold ${r.leagues === v ? 'gen-seg-on' : 'text-muted-foreground'}`}>{l}</button>)}</div>
        <LeaguePicker matches={(days.data ?? []).flatMap((d) => d?.matches ?? [])} value={r.pick ?? []} onChange={(v) => set({ pick: v })} />
        <label className="block text-xs text-muted-foreground">Fără ligile<input className="input mt-1" placeholder="ex: brazil, mexic" value={r.exclude} onChange={(e) => set({ exclude: e.target.value })} /></label>
        <ul className="divide-y rounded-xl border">
          {([['posOnly', 'Doar piețe cu ROI pozitiv'], ['realOnly', 'Doar cotă Superbet reală'], ['valueOnly', 'Doar cu valoare (EV > 0)'], ['noMine', 'Fără meciurile mele în joc']] as const).map(([k, lab]) => (
            <li key={k}><button type="button" role="switch" aria-checked={!!r[k]} onClick={() => set({ [k]: !r[k] } as Partial<Rules>)} className="flex min-h-12 w-full items-center gap-3 px-3 text-left text-sm">
              <span className="flex-1">{lab}</span><span className={`gen-switch ${r[k] ? 'on' : ''}`} aria-hidden><span /></span></button></li>
          ))}
        </ul>
      </GenCard>

      <div className="gen-bar sticky bottom-2 z-20 flex items-center gap-2 rounded-2xl p-2 pl-3.5">
        <span className="min-w-0 flex-1 truncate text-xs text-muted-foreground"><b className="text-foreground">țintă {r.target >= 1000 ? '1000+' : r.target}</b> · {r.nMin}–{r.nMax} meciuri · {chosen.length} piețe</span>
        {locked.size > 0 && <button type="button" className="text-[11px] font-semibold text-primary" onClick={() => setLocked(new Set())}>Deblochează</button>}
        <button className="btn btn-primary h-11 shrink-0 px-5" disabled={days.loading || !groups.size || (wantStil && !gen) || (!!r.posOnly && !posDoc)} onClick={run}><Bot className="h-4 w-4" />{days.loading ? 'Se încarcă…' : locked.size ? `Generează (${locked.size})` : 'Generează'}</button>
      </div>
      {err && <p className="mt-2 text-sm text-warn">{err}</p>}
      {res.map((g, gi) => {
        if (isLostTicket(g.ticket)) return null;
        const p = g.ticket.p_ticket ?? 0;
        return (
          <div key={g.ticket.id} className="mt-3 space-y-1.5">
            <div className="hot-ticket">
              <span className="big-num text-[22px] text-muted-foreground">#{gi + 1}</span>
              <div className="grid flex-1 grid-cols-3 gap-1 text-center">
                <div><div className="big-num neon-text text-[22px]">{g.ticket.total_odds.toFixed(g.ticket.total_odds < 100 ? 2 : 0)}</div><div className="label">cotă</div></div>
                <div><div className="big-num text-[22px]">{(p * 100).toFixed(p < 0.01 ? 2 : 1)}<span className="text-xs">%</span></div><div className="label">șansă · {oneIn(p)}</div></div>
                <div><div className={`big-num text-[22px] ${p * g.ticket.total_odds >= 1 ? 'text-win' : 'text-loss'}`}>{((p * g.ticket.total_odds - 1) * 100).toFixed(0)}<span className="text-xs">%</span></div><div className="label">EV</div></div>
              </div>
            </div>
            {g.legs.length >= 6 && <p className="text-[11px] text-muted-foreground">Opțiune sistem {g.legs.length - 1}/{g.legs.length}: {g.legs.length} bilete de {g.legs.length - 1}; dacă pică o singură selecție mai iei ~{(g.ticket.total_odds / (g.legs.reduce((a, c) => a + c.odds, 0) / g.legs.length) / g.legs.length).toFixed(0)}× miza totală (șansă să intre măcar sistemul ~{(sysChance(g.legs) * 100).toFixed(1)}%).</p>}
            <TicketCard t={g.ticket} />
            <details className="rounded-xl border px-3 py-2 text-xs">
              <summary className="cursor-pointer font-semibold">Schimbă sau fixează selecții</summary>
              <ul className="mt-1.5 divide-y">
                {g.legs.map((c) => (
                  <li key={String(c.p.id)} className="flex items-center gap-2 py-1.5">
                    <span className="min-w-0 flex-1"><b>{c.p.label}</b> · {c.m.home.name} – {c.m.away.name} · {c.odds.toFixed(2)}</span>
                    <button type="button" className={`press rounded-full border px-2.5 py-1 font-semibold ${locked.has(String(c.p.id)) ? 'border-primary bg-primary/15 text-primary' : ''}`} onClick={() => toggleLock(c)}>{locked.has(String(c.p.id)) ? 'Fixată' : 'Fixează'}</button>
                    <button type="button" className="press rounded-full border px-2.5 py-1 font-semibold" onClick={() => swap(gi, c)}>Schimbă</button>
                  </li>
                ))}
              </ul>
              <p className="mt-1 text-muted-foreground">„Fixează” păstrează selecția la următoarea generare; „Schimbă” pune alt meci în locul ei, cu o cotă cât mai apropiată.</p>
            </details>
          </div>
        );
      })}
    </div>
  );
}

const lgKey = (m: Match) => `${m.league.country ?? ''}|${m.league.name}`;

/** Lista de ligi: bifezi ce vrei (nimic bifat = toate), cu căutare, grupate pe țară. */
function LeaguePicker({ matches, value, onChange }: { matches: Match[]; value: string[]; onChange: (v: string[]) => void }) {
  const [q, setQ] = useState('');
  const [open, setOpen] = useState(false);
  const groups = useMemo(() => {
    const cnt = new Map<string, number>();
    for (const m of matches) cnt.set(lgKey(m), (cnt.get(lgKey(m)) ?? 0) + 1);
    const by = new Map<string, Array<[string, string, number]>>();
    for (const [k, n] of cnt) { const [c, l] = k.split('|'); const ql = q.trim().toLowerCase();
      if (ql && !`${c} ${l}`.toLowerCase().includes(ql)) continue;
      const g = c || 'Altele'; by.set(g, [...(by.get(g) ?? []), [k, l, n]]); }
    return [...by.entries()].sort((a, b) => a[0].localeCompare(b[0], 'ro')).map(([c, ls]) => [c, ls.sort((a, b) => a[1].localeCompare(b[1], 'ro'))] as const);
  }, [matches, q]);
  const sel = new Set(value);
  const tog = (k: string) => { const n = new Set(sel); if (n.has(k)) n.delete(k); else n.add(k); onChange([...n]); };
  return (
    <div className="col-span-full text-xs">
      <button type="button" className="press w-full rounded-xl border px-3 py-2 text-left font-semibold" aria-expanded={open} onClick={() => setOpen(!open)}>
        Alege ligile: {value.length ? `${value.length} bifate` : 'toate'} {open ? '▴' : '▾'}</button>
      {open && <div className="mt-1.5 rounded-xl border p-2">
        <div className="flex gap-2"><input className="input h-9 flex-1" placeholder="Caută țară sau ligă" value={q} onChange={(e) => setQ(e.target.value)} />
          {value.length > 0 && <button type="button" className="font-semibold text-primary" onClick={() => onChange([])}>Toate</button>}</div>
        <div className="mt-2 max-h-72 space-y-2 overflow-y-auto">
          {groups.map(([c, ls]) => { const all = ls.every(([k]) => sel.has(k)); return (
            <div key={c}>
              <label className="flex min-h-9 items-center gap-2 font-bold"><input type="checkbox" checked={all} onChange={() => { const n = new Set(sel); ls.forEach(([k]) => (all ? n.delete(k) : n.add(k))); onChange([...n]); }} />{c}</label>
              {ls.map(([k, l, n]) => <label key={k} className="ml-5 flex min-h-9 items-center gap-2"><input type="checkbox" checked={sel.has(k)} onChange={() => tog(k)} /><span className="flex-1">{l}</span><span className="text-muted-foreground">{n}</span></label>)}
            </div>); })}
          {!groups.length && <p className="text-muted-foreground">Nicio ligă găsită.</p>}
        </div>
      </div>}
    </div>
  );
}

/** Card de pas: titlu numerotat, rezumat când e închis. */
function GenCard({ n, title, summary, open, children }: { n: number; title: string; summary: string; open?: boolean; children: React.ReactNode }) {
  return (
    <details className="gen-card group" open={open}>
      <summary className="flex min-h-14 cursor-pointer list-none items-center gap-3 px-4">
        <span className="gen-step" aria-hidden>{n}</span>
        <span className="min-w-0 flex-1"><span className="block text-[15px] font-extrabold">{title}</span><span className="block truncate text-[11px] text-muted-foreground">{summary}</span></span>
        <span className="text-xs text-muted-foreground transition-transform group-open:rotate-180" aria-hidden>▾</span>
      </summary>
      <div className="space-y-4 px-4 pb-4">{children}</div>
    </details>
  );
}

/** Slider dublu (min–max) din două range-uri suprapuse. */
function DualRange({ label, min, max, step, lo, hi, fmt, onChange }: { label: string; min: number; max: number; step: number; lo: number; hi: number; fmt: (v: number) => string; onChange: (lo: number, hi: number) => void }) {
  const pc = (v: number) => ((v - min) / (max - min)) * 100;
  return (
    <div className="text-xs text-muted-foreground">
      <div className="flex justify-between"><span>{label}</span><b className="num text-foreground">{fmt(lo)} – {fmt(hi)}</b></div>
      <div className="dual mt-2" style={{ ['--a' as string]: `${pc(lo)}%`, ['--b' as string]: `${pc(hi)}%` }}>
        <input type="range" aria-label={`${label}: minim`} min={min} max={max} step={step} value={lo} onChange={(e) => onChange(Math.min(Number(e.target.value), hi), hi)} />
        <input type="range" aria-label={`${label}: maxim`} min={min} max={max} step={step} value={hi} onChange={(e) => onChange(lo, Math.max(Number(e.target.value), lo))} />
      </div>
    </div>
  );
}
