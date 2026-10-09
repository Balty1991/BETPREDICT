/**
 * „Robotul” din browser: construiește bilete acumulator și propunerea de piramidă din
 * predicțiile deja publicate (fără niciun apel API). Pipeline-ul de pe server face același
 * lucru zilnic (api/tickets, api/pyramid); aici îl folosim pentru „Generează din nou”,
 * pentru variantele cu reguli proprii și când serverul n-a publicat încă biletele.
 */
import type { Day, Match, Prediction, Ticket, TicketLeg, LegResult, TicketStatus } from './types';
import { roTime } from './format';
import { marketKey, settleSelection, isFinished, VOID_STATUSES } from './markets';

export interface Candidate { m: Match; p: Prediction; odds: number; pAdj: number; lo: number; lp: number; estimated: boolean }
export const evAdj = (c: Candidate) => c.pAdj * c.odds - 1;

export interface PoolOptions {
  minOdds: number;
  allowEstimated: boolean;
  onlyUpcoming?: boolean;
  now?: number;
  /** include și piețele sub pragul de EV (pentru „Bilet sigur”) */
  includeUnhealthy?: boolean;
}

/** Probabilitate „prudentă”: 50% model + 50% piață fără marjă (identic cu pipeline-ul). */
export const SHRINK_MODEL_WEIGHT = 0.5;
export function shrink(p: number, odds: number, pMarket?: number | null): number {
  const mkt = pMarket != null && pMarket > 0 && pMarket < 1 ? pMarket : Math.min(0.97, (1 / odds) / 1.05);
  return SHRINK_MODEL_WEIGHT * p + (1 - SHRINK_MODEL_WEIGHT) * mkt;
}

/** Miză sugerată în unități (1u = 1% din bancă): ¼ Kelly, plafonat. 0 dacă EV ≤ 0. */
export function suggestedStake(p: number, odds: number, cap: number): number {
  const ev = p * odds - 1;
  if (odds <= 1 || ev <= 0) return 0;
  return Math.round(Math.max(0.05, Math.min(cap, 0.25 * (ev / (odds - 1)) * 100)) * 100) / 100;
}
export const STAKE_CAP: Record<number, number> = { 50: 0.5, 100: 0.3, 500: 0.15, 2: 2 };
/** Plafon pentru bilete manuale, după cota totală (aceeași scară ca biletele Robotului). */
export function manualStakeCap(total: number): number { return total <= 3 ? 2 : total <= 20 ? 0.5 : total <= 75 ? 0.3 : 0.15; }
/** Bilet manual: probabilitate prudentă (model tras 50% spre piață) și miza sugerată ¼ Kelly. */
export function manualTicketMetrics(legs: Array<{ p?: number | null; odds: number; p_market?: number | null }>): { total: number; pAdj: number | null; evAdj: number | null; stakeUnits: number } {
  const total = legs.reduce((a, l) => a * l.odds, 1);
  if (!legs.length || legs.some((l) => l.p == null)) return { total, pAdj: null, evAdj: null, stakeUnits: 0 };
  const pAdj = legs.reduce((a, l) => a * shrink(l.p!, l.odds, l.p_market), 1);
  return { total, pAdj, evAdj: pAdj * total - 1, stakeUnits: suggestedStake(pAdj, total, manualStakeCap(total)) };
}

export function buildPool(days: Day[], opts: PoolOptions): Candidate[] {
  const now = opts.now ?? Date.now();
  const out: Candidate[] = [];
  for (const d of days) for (const m of d.matches) {
    if (opts.onlyUpcoming !== false) {
      if (m.status !== 'notstarted') continue;
      if (Date.parse(m.kickoff_utc) < now + 5 * 60 * 1000) continue;
    }
    for (const p of m.predictions) {
      if (p.market_healthy === false && !opts.includeUnhealthy) continue;
      if (p.market === 'corners') continue;
      const odds = p.odds;
      if (odds == null) continue; // fără cotă reală → nu intră niciodată în bilete
      const estimated = false;
      if (odds < opts.minOdds || p.p <= 0.05) continue;
      const pAdj = shrink(p.p, odds, estimated ? null : p.p_market);
      out.push({ m, p, odds, pAdj, lo: Math.log(odds), lp: Math.log(pAdj), estimated });
    }
  }
  return out;
}

export function legFromCandidate(c: Candidate): TicketLeg {
  return {
    prediction_id: c.p.id, match_id: c.m.id, kickoff_utc: c.m.kickoff_utc, league: c.m.league.name,
    home: c.m.home.name, away: c.m.away.name, market: c.p.market, line: c.p.line, selection: c.p.selection,
    label: c.p.label, odds: c.odds, p: c.p.p, grade: c.p.grade ?? null, result: null,
    reasons: legReasons(c),
  };
}

export function legReasons(c: Candidate): string[] {
  const r: string[] = [];
  const implied = 1 / c.odds;
  r.push(`Robot ${(c.p.p * 100).toFixed(0)}% vs. cotă ${(implied * 100).toFixed(0)}% → ${c.p.p > implied ? 'valoare' : 'ancoră sigură'}`);
  if (c.estimated) r.push('⚠ cotă estimată (lipsește cota reală în sursa gratuită)');
  for (const x of (c.p.reasons ?? []).slice(0, 3)) if (!r.includes(x) && !x.startsWith('Probabilitate Robot')) r.push(x);
  if (c.p.grade) r.push(`Grad ${c.p.grade}${c.p.confidence ? ` · încredere ${c.p.confidence}/100` : ''}`);
  r.push(`${c.m.league.name}, ${roTime(c.m.kickoff_utc)}`);
  return r.slice(0, 5);
}

export interface VariantSpec {
  id: string;
  label: string;
  describe: string;
  filter: (c: Candidate) => boolean;
  /** cost per selecție: mai mic = mai bun (bilet cu probabilitate maximă la cota-țintă) */
  cost: (c: Candidate) => number;
}

const efficiency = (c: Candidate) => -c.lp / c.lo; // ≈1 la cotă corectă; <1 = valoare

export const VARIANTS: VariantSpec[] = [
  { id: 'echilibrat', label: 'Echilibrat', describe: 'Probabilitate prudentă maximă la cota-țintă, cu bonus pentru valoare', filter: (c) => c.odds <= 2.6, cost: (c) => efficiency(c) - 0.5 * evAdj(c) - (c.p.p >= 0.6 && c.odds <= 2.2 ? 0.05 : 0) },
  { id: 'valoare', label: 'Valoare', describe: 'Cele mai mari valori EV (ajustate spre piață), mai puține selecții', filter: (c) => c.odds >= 1.3, cost: (c) => efficiency(c) - 1.5 * evAdj(c) },
  { id: 'ancora_surpriza', label: 'Ancoră + Surpriză', describe: 'Favoriți 1.15–1.70 (p prudent ≥ 62%) + 1–2 selecții de valoare la 2.30–3.60', filter: (c) => (c.odds <= 1.7 && c.pAdj >= 0.62) || (c.odds >= 2.3 && c.odds <= 3.6), cost: (c) => (c.odds >= 2.3 ? efficiency(c) - 0.3 : efficiency(c)) },
  { id: 'goluri', label: 'Goluri', describe: 'Doar piețe de goluri (Peste/Sub, GG/NG)', filter: (c) => c.p.market === 'over_under' || c.p.market === 'btts', cost: (c) => efficiency(c) - 0.5 * evAdj(c) },
];

/** Doar selecții A/B, cote reale, EV > 0 după ajustarea spre piață; p prudent minim pe selecție (plafon pe cele improbabile). */
export const TARGETS: Array<{ target: number; kind: string; min: number; max: number; nMin: number; nMax: number; realistic: string; minLegP: number }> = [
  { target: 50, kind: 'acca_50', min: 42, max: 63, nMin: 4, nMax: 9, realistic: '~1,5–3%', minLegP: 0.42 },
  { target: 100, kind: 'acca_100', min: 85, max: 125, nMin: 5, nMax: 11, realistic: '~0,7–1,5%', minLegP: 0.38 },
  { target: 500, kind: 'acca_500', min: 425, max: 900, nMin: 7, nMax: 14, realistic: '~0,1–0,3%', minLegP: 0.33 },
];

interface BeamState { idx: number[]; lo: number; lp: number; cost: number; leagues: Map<string, number>; matches: Set<number> }

function sameLeaguePairs(legs: Candidate[]): number {
  const c = new Map<string, number>();
  for (const l of legs) c.set(l.m.league.name, (c.get(l.m.league.name) ?? 0) + 1);
  let pairs = 0;
  for (const v of c.values()) pairs += (v * (v - 1)) / 2;
  return pairs;
}

export function ticketProbability(legs: Array<{ pAdj: number; m: Match }>): number {
  let p = 1;
  for (const l of legs) p *= l.pAdj;
  return p * Math.pow(0.985, sameLeaguePairs(legs as Candidate[]));
}

/**
 * Căutare în fascicul: adaugă selecții (max. 1 pe meci, max. 2 pe ligă) până când cota totală
 * intră în intervalul țintei; păstrează combinațiile cu cel mai mic „cost” mediu pe unitate de cotă.
 */
export function beamSearch(pool: Candidate[], t: { min: number; max: number; nMin: number; nMax: number }, cost: (c: Candidate) => number, banned: Set<string>, width = 80): Candidate[] | null {
  const cands = pool.filter((c) => !banned.has(String(c.p.id))).map((c) => ({ c, k: cost(c) })).sort((a, b) => a.k - b.k).slice(0, 220);
  const lmin = Math.log(t.min), lmax = Math.log(t.max);
  let beam: BeamState[] = [{ idx: [], lo: 0, lp: 0, cost: 0, leagues: new Map(), matches: new Set() }];
  let best: { s: BeamState; score: number } | null = null;
  for (let depth = 0; depth < t.nMax; depth++) {
    const next: BeamState[] = [];
    for (const s of beam) {
      const start = s.idx.length ? s.idx[s.idx.length - 1] + 1 : 0;
      for (let i = start; i < cands.length; i++) {
        const { c, k } = cands[i];
        if (s.matches.has(c.m.id)) continue;
        if ((s.leagues.get(c.m.league.name) ?? 0) >= 2) continue;
        const lo = s.lo + c.lo;
        if (lo > lmax) continue;
        const ns: BeamState = { idx: [...s.idx, i], lo, lp: s.lp + c.lp, cost: s.cost + k * c.lo, leagues: new Map(s.leagues).set(c.m.league.name, (s.leagues.get(c.m.league.name) ?? 0) + 1), matches: new Set(s.matches).add(c.m.id) };
        if (lo >= lmin && ns.idx.length >= t.nMin) {
          const score = ns.cost / ns.lo; // cost mediu pe unitate de log-cotă
          if (!best || score < best.score) best = { s: ns, score };
        } else {
          next.push(ns);
        }
      }
    }
    if (!next.length) break;
    // prioritate: cost mediu mic, cu un mic bonus pentru progres spre țintă
    next.sort((a, b) => (a.cost / a.lo - 0.02 * (a.lo / lmin)) - (b.cost / b.lo - 0.02 * (b.lo / lmin)));
    beam = next.slice(0, width);
  }
  return best ? best.s.idx.map((i) => cands[i].c) : null;
}

let seq = 0;
export function makeTicket(legs: Candidate[], meta: { kind: string; variant: string; variant_label: string; target?: number; date: string; created_by?: string; reasons?: string[] }): Ticket {
  const total = legs.reduce((a, c) => a * c.odds, 1);
  const pT = ticketProbability(legs);
  const leagues = new Set(legs.map((l) => l.m.league.name)).size;
  return {
    id: `local-${meta.date}-${meta.kind}-${meta.variant}-${Date.now().toString(36)}-${seq++}`,
    kind: meta.kind, variant: meta.variant, variant_label: meta.variant_label, created_by: meta.created_by ?? 'robot',
    date: meta.date, created_at: new Date().toISOString(), target_odds: meta.target ?? null,
    total_odds: Math.round(total * 100) / 100, p_ticket: pT, ev: pT * total - 1, status: 'pending',
    stake_units: suggestedStake(pT, total, STAKE_CAP[meta.target ?? 0] ?? 0.15),
    legs_count: legs.length, settled_legs: 0,
    legs: [...legs].sort((a, b) => a.m.kickoff_utc.localeCompare(b.m.kickoff_utc)).map(legFromCandidate),
    reasons: meta.reasons ?? [`${legs.length} selecții din ${leagues} ligi`, `Cotă medie ${(Math.pow(total, 1 / legs.length)).toFixed(2)}`, legs.some((l) => l.estimated) ? 'Conține cote estimate' : 'Doar cote reale'],
  };
}

export function generateAccumulators(allPool: Candidate[], date: string, opts: { targets?: number[]; variants?: string[]; seedBan?: Set<string> } = {}): Ticket[] {
  const out: Ticket[] = [];
  // ROI pozitiv: doar selecții A/B cu cote reale și EV > 0 după ajustarea spre piață
  const positive = allPool.filter((c) => !c.estimated && evAdj(c) > 0 && (c.p.grade === 'A' || c.p.grade === 'B'));
  for (const t of TARGETS) {
    if (opts.targets && !opts.targets.includes(t.target)) continue;
    const pool = positive.filter((c) => c.pAdj >= t.minLegP);
    const usage = new Map<string, number>();
    const prevSets: Set<string>[] = [];
    for (const v of VARIANTS) {
      if (opts.variants && !opts.variants.includes(v.id)) continue;
      const banned = new Set<string>(opts.seedBan ?? []);
      for (const [id, n] of usage) if (n >= 2) banned.add(id);
      let legs: Candidate[] | null = null;
      for (let attempt = 0; attempt < 3 && !legs; attempt++) {
        const res = beamSearch(pool.filter(v.filter), t, v.cost, banned);
        if (!res) break;
        const ids = new Set(res.map((c) => String(c.p.id)));
        const tooSimilar = prevSets.some((s) => [...ids].filter((x) => s.has(x)).length / ids.size > 0.5);
        if (tooSimilar) {
          // excludem cea mai „folosită” selecție și reîncercăm
          const shared = res.filter((c) => prevSets.some((s) => s.has(String(c.p.id))));
          shared.slice(0, Math.ceil(shared.length / 2)).forEach((c) => banned.add(String(c.p.id)));
          continue;
        }
        legs = res;
      }
      if (!legs) continue;
      const pT = ticketProbability(legs);
      if (pT * legs.reduce((a, c) => a * c.odds, 1) - 1 <= 0) continue; // mai bine niciun bilet decât unul cu EV negativ
      legs.forEach((c) => usage.set(String(c.p.id), (usage.get(String(c.p.id)) ?? 0) + 1));
      prevSets.push(new Set(legs.map((c) => String(c.p.id))));
      out.push(makeTicket(legs, { kind: t.kind, variant: v.id, variant_label: v.label, target: t.target, date, reasons: [v.describe, `Șansă realistă pentru cota ~${t.target}: ${t.realistic}`] }));
    }
  }
  return out;
}

/* ───────────────────────────── Bilet sigur (~2 / ~3 / ~5) ───────────────────────────── */

/** Favoriți clari la cote mici; se publică mereu, chiar și cu EV ușor negativ (marcat clar). */
export const SAFE_TARGETS: Array<{ target: number; min: number; max: number; nMin: number; nMax: number }> = [
  { target: 2, min: 1.8, max: 2.3, nMin: 2, nMax: 5 },
  { target: 3, min: 2.7, max: 3.45, nMin: 3, nMax: 7 },
  { target: 5, min: 4.5, max: 5.75, nMin: 5, nMax: 10 },
];
const SAFE_LEVELS: Array<{ lo: number; hi: number; grades: string[]; minP: number; text: string }> = [
  { lo: 1.2, hi: 1.4, grades: ['A', 'B'], minP: 0, text: 'cote 1.20–1.40, încredere mare/bună (A/B)' },
  { lo: 1.15, hi: 1.4, grades: ['A', 'B'], minP: 0, text: 'cote 1.15–1.40, încredere mare/bună (A/B)' },
  { lo: 1.15, hi: 1.4, grades: ['A', 'B', 'C'], minP: 0.72, text: 'cote 1.15–1.40, încredere A/B/C cu șansă ≥ 72%' },
];
export const SAFE_STAKE_INFO = 0.1;

export function generateSafeTickets(allPool: Candidate[], date: string, banned: Set<string> = new Set()): Ticket[] {
  const out: Ticket[] = [];
  const used = new Map<string, number>();
  for (const t of SAFE_TARGETS) {
    let legs: Candidate[] | null = null;
    let text = '';
    for (const lv of SAFE_LEVELS) {
      const pool = allPool.filter((c) => !c.estimated && c.odds >= lv.lo && c.odds <= lv.hi && lv.grades.includes(c.p.grade ?? 'D') && c.p.p >= lv.minP);
      // cost mic = probabilitate calibrată mare pe unitate de cotă; penalizăm reutilizarea
      legs = beamSearch(pool, t, (c) => -Math.log(c.p.p) / c.lo + 0.15 * (used.get(String(c.p.id)) ?? 0), banned, 60);
      if (legs) { text = lv.text; break; }
    }
    if (!legs) continue;
    legs.forEach((c) => used.set(String(c.p.id), (used.get(String(c.p.id)) ?? 0) + 1));
    const tk = makeTicket(legs, { kind: 'acca_safe', variant: 'sigur', variant_label: 'Bilet sigur', target: t.target, date,
      reasons: [`Favoriți clari: ${text}`, 'Selecțiile cu cea mai mare probabilitate calibrată (o selecție pe meci, max. 2 pe ligă)'] });
    const ev = tk.ev ?? 0;
    tk.stake_units = ev > 0 ? suggestedStake(tk.p_ticket ?? 0, tk.total_odds, 1) : SAFE_STAKE_INFO;
    tk.safe = true;
    out.push(tk);
  }
  return out;
}

export const isSafeTicket = (t: Pick<Ticket, 'kind' | 'safe'>) => t.safe === true || t.kind === 'acca_safe';

/* ───────────────────────────── Piramida ~2.00 ───────────────────────────── */

export interface PyramidPick { status: 'pick' | 'no_bet'; reason: string; main: Ticket | null; alternatives: Ticket[] }

export function pyramidSelect(pool: Candidate[], date: string, rules = { band: [1.85, 2.2] as [number, number], maxLegs: 4, minP: 0.5, minEv: 0 }): PyramidPick {
  const cands = pool
    .filter((c) => c.pAdj >= 0.55 && c.odds <= rules.band[1] && !c.estimated && (c.p.grade ? ['A', 'B'].includes(c.p.grade) : true))
    .sort((a, b) => b.pAdj - a.pAdj)
    .slice(0, 50);
  type Combo = { legs: Candidate[]; odds: number; p: number };
  const combos: Combo[] = [];
  const consider = (legs: Candidate[]) => {
    const ids = new Set(legs.map((l) => l.m.id));
    if (ids.size !== legs.length) return;
    const odds = legs.reduce((a, c) => a * c.odds, 1);
    if (odds < rules.band[0] || odds > rules.band[1]) return;
    combos.push({ legs, odds, p: ticketProbability(legs) });
  };
  const N = cands.length;
  for (let i = 0; i < N; i++) {
    consider([cands[i]]);
    for (let j = i + 1; j < N; j++) {
      if (cands[i].odds * cands[j].odds > rules.band[1]) continue;
      consider([cands[i], cands[j]]);
      if (rules.maxLegs < 3) continue;
      for (let k = j + 1; k < Math.min(N, 40); k++) {
        const o3 = cands[i].odds * cands[j].odds * cands[k].odds;
        if (o3 > rules.band[1]) continue;
        consider([cands[i], cands[j], cands[k]]);
        if (rules.maxLegs < 4) continue;
        for (let l = k + 1; l < Math.min(N, 30); l++) {
          if (o3 * cands[l].odds > rules.band[1]) continue;
          consider([cands[i], cands[j], cands[k], cands[l]]);
        }
      }
    }
  }
  combos.sort((a, b) => b.p - a.p);
  const chosen: Combo[] = [];
  for (const c of combos) {
    if (chosen.length >= 3) break;
    const ids = new Set(c.legs.map((l) => l.m.id));
    if (chosen.some((x) => x.legs.filter((l) => ids.has(l.m.id)).length >= Math.max(1, Math.ceil(ids.size / 2)))) continue;
    chosen.push(c);
  }
  const best = chosen[0];
  if (!best) return { status: 'no_bet', reason: 'Nicio combinație de 1–4 meciuri cu cota 1.85–2.20 și selecții de grad A/B azi.', main: null, alternatives: [] };
  const ev = best.p * best.odds - 1;
  if (best.p < rules.minP || ev < rules.minEv) {
    return { status: 'no_bet', reason: `Cea mai bună combinație are p=${(best.p * 100).toFixed(0)}% și EV ${(ev * 100).toFixed(1)}% — sub pragul p≥${rules.minP * 100}% și EV≥${rules.minEv * 100}%. AZI NU — pauză.`, main: null, alternatives: [] };
  }
  const mk = (c: Combo, i: number) => makeTicket(c.legs, { kind: 'pyramid', variant: i === 0 ? 'principal' : 'alternativa', variant_label: i === 0 ? 'Propunerea zilei' : `Alternativa ${i}`, target: 2, date, reasons: [`p estimat ${(c.p * 100).toFixed(0)}% · EV ${((c.p * c.odds - 1) * 100).toFixed(1)}%`, `${c.legs.length} ${c.legs.length === 1 ? 'meci' : 'meciuri'}, doar grad A/B`] });
  return { status: 'pick', reason: `Combinație p=${(best.p * 100).toFixed(0)}%, EV ${(ev * 100).toFixed(1)}%`, main: mk(best, 0), alternatives: chosen.slice(1).filter((c) => c.p >= rules.minP).map((c, i) => mk(c, i + 1)) };
}

/* ───────────────────────────── Decontare ───────────────────────────── */

export interface MatchResult { status: string; ft?: [number, number] | null }

export function settleLeg(leg: TicketLeg, res: MatchResult | undefined): { result: LegResult; score: string | null } {
  if (!res) return { result: leg.result ?? null, score: leg.score ?? null };
  if (VOID_STATUSES.has(res.status)) return { result: 'void', score: null };
  if (!isFinished(res.status) || !res.ft) return { result: null, score: res.ft ? `${res.ft[0]}-${res.ft[1]}` : null };
  return { result: settleSelection(leg.market, leg.line, leg.selection, res.ft[0], res.ft[1]), score: `${res.ft[0]}-${res.ft[1]}` };
}

/** Bilet: pierdut la prima selecție pierdută; void → cota 1.00; câștigat doar când totul e decontat. */
export function settleTicket(t: Ticket, results: Map<number, MatchResult>): Ticket {
  let lost = false, pending = false, settled = 0, eff = 1, allVoid = true;
  const legs = t.legs.map((l) => {
    const { result, score } = l.result ? { result: l.result, score: l.score ?? null } : settleLeg(l, results.get(l.match_id));
    if (result) settled++;
    if (result === 'lost' || result === 'half_lost') lost = true;
    if (!result) pending = true;
    if (result === 'won') { eff *= l.odds; allVoid = false; }
    else if (result === 'half_won') { eff *= (1 + l.odds) / 2; allVoid = false; }
    else if (result !== 'void') allVoid = false;
    return { ...l, result, score };
  });
  const status: TicketStatus = lost ? 'lost' : pending ? 'pending' : allVoid ? 'void' : 'won';
  return { ...t, legs, status, settled_legs: settled, legs_count: legs.length, effective_odds: lost ? 0 : Math.round(eff * 100) / 100 };
}

export function resultsFromDays(days: Array<Day | null>): Map<number, MatchResult> {
  const map = new Map<number, MatchResult>();
  for (const d of days) for (const m of d?.matches ?? []) map.set(m.id, { status: m.status, ft: m.score?.ft ?? null });
  return map;
}

export function legKey(l: Pick<TicketLeg, 'match_id' | 'market' | 'line' | 'selection'>) { return `${l.match_id}|${marketKey(l.market, l.line)}|${l.selection}`; }
