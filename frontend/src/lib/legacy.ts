/**
 * Adaptor pentru fișierele vechi din `./data/` (pipeline v2). Este folosit DOAR cât timp
 * pipeline-ul nou (`./api/…`, docs/data-contract.md) nu a publicat încă fișierele lui.
 * Transformă totul în forma contractului v1, ca restul aplicației să nu știe diferența.
 */
import { getJSON } from './fetcher';
import { roDay } from './format';
import { selectionLabel, settleSelection, profitFor, isFinished, VOID_STATUSES } from './markets';
import type { Day, Match, Prediction, PyramidState, JournalRow, MatchContext, Absence, LegResult } from './types';

/* eslint-disable @typescript-eslint/no-explicit-any */
type Any = Record<string, any>;

const IMG = 'https://sports.bzzoiro.com/img';
const n = (v: unknown): number | null => (typeof v === 'number' && Number.isFinite(v) ? v : null);
const prob = (v: unknown): number | null => {
  const x = n(v);
  if (x == null) return null;
  return x > 1 ? x / 100 : x;
};

function normName(s: string): string[] {
  return s
    .normalize('NFD').replace(/[\u0300-\u036f]/g, '')
    .toLowerCase()
    .replace(/[^a-z0-9 ]/g, ' ')
    .split(/\s+/)
    .filter((t) => t.length > 1 && !['fc', 'cf', 'sc', 'afc', 'ac', 'fk', 'sk', 'club', 'de', 'the', 'cd', 'ca', 'if', 'bk', 'united', 'city'].includes(t));
}
function overlap(a: string[], b: string[]): number {
  if (!a.length || !b.length) return 0;
  const sb = new Set(b);
  const inter = a.filter((t) => sb.has(t)).length;
  return inter / Math.min(a.length, b.length);
}

interface OddsIndex { byEvent: Map<number, Record<string, Record<string, number>>>; source: Map<number, string> }

async function loadOddsIndex(preds: Any[]): Promise<OddsIndex> {
  const byEvent = new Map<number, Record<string, Record<string, number>>>();
  const source = new Map<number, string>();
  const [snap, sb] = await Promise.all([
    getJSON<Any>('data/odds_snapshot.json'),
    getJSON<Any>('data/superbet_live_odds.json'),
  ]);
  const put = (eid: number, key: string, sel: string, v: number, src: string) => {
    if (!(v > 1)) return;
    const o = byEvent.get(eid) ?? {};
    o[key] = o[key] ?? {};
    if (o[key][sel] == null) o[key][sel] = v;
    byEvent.set(eid, o);
    if (!source.has(eid)) source.set(eid, src);
  };
  for (const row of Object.values<Any>(snap?.snapshot ?? {})) {
    const eid = Number(row.event_id);
    const m: string = row.market ?? '';
    const out: string = String(row.outcome ?? '').toUpperCase();
    if (m === '1x2') put(eid, '1x2', out, row.decimal_odds, 'bsd_consensus');
    else if (m.startsWith('over_under_')) {
      const line = Number(m.slice(-2)) / 10;
      put(eid, `over_under_${line}`, out.startsWith('OVER') ? 'OVER' : 'UNDER', row.decimal_odds, 'bsd_consensus');
    } else if (m === 'btts') put(eid, 'btts', out, row.decimal_odds, 'bsd_consensus');
  }
  // Superbet: potrivire după nume normalizate + ora de start (±3h).
  const sbm: Any[] = sb?.matches ?? [];
  if (sbm.length) {
    const byDay = new Map<string, Any[]>();
    for (const m of sbm) {
      const t = Date.parse(String(m.match_date).replace(' ', 'T') + 'Z');
      m._t = t; m._h = normName(m.home_team_superbet ?? m.home_team_norm ?? ''); m._a = normName(m.away_team_superbet ?? m.away_team_norm ?? '');
      const d = new Date(t).toISOString().slice(0, 10);
      byDay.set(d, [...(byDay.get(d) ?? []), m]);
    }
    for (const p of preds) {
      const ev = p.event ?? {};
      const eid = Number(ev.id);
      const t = Date.parse(ev.event_date);
      if (!Number.isFinite(t)) continue;
      const days = [new Date(t).toISOString().slice(0, 10), new Date(t - 86400000).toISOString().slice(0, 10), new Date(t + 86400000).toISOString().slice(0, 10)];
      const h = normName(ev.home_team ?? ''); const a = normName(ev.away_team ?? '');
      let best: Any | null = null; let bestScore = 0;
      for (const d of days) for (const m of byDay.get(d) ?? []) {
        if (Math.abs(m._t - t) > 3 * 3600 * 1000) continue;
        const s = overlap(h, m._h) + overlap(a, m._a);
        if (s > bestScore) { bestScore = s; best = m; }
      }
      if (best && bestScore >= 1.5) {
        for (const [mk, sels] of Object.entries<Any>(best.markets ?? {})) {
          let key = mk;
          if (mk.startsWith('over_under_')) key = `over_under_${Number(mk.slice(-2)) / 10}`;
          for (const [sel, v] of Object.entries<any>(sels)) put(eid, key, String(sel).toUpperCase(), Number(v), 'superbet');
        }
      }
    }
  }
  return { byEvent, source };
}

function gradeFrom(p: number, ev: number | null, legacyGrade?: string): string {
  if (legacyGrade && /^[A-D]/.test(legacyGrade) && legacyGrade !== 'E') {
    // gradul vechi e despre meci; îl combinăm cu probabilitatea selecției
    if (p >= 0.7 && (ev ?? 0) > -0.03) return 'A';
  }
  if (p >= 0.72 && (ev == null || ev > -0.04)) return 'A';
  if (p >= 0.6 && (ev == null || ev > -0.06)) return 'B';
  if (p >= 0.5) return 'C';
  return 'D';
}

function predictionsFromLegacy(row: Any, odds: Record<string, Record<string, number>> | undefined, oddsSrc: string | undefined, minOdds: number): Prediction[] {
  const ev = row.event ?? {};
  const mid = Number(ev.id);
  const mk = row.markets ?? {};
  const pH = prob(row.home_win_probability) ?? prob(mk.match_result?.prob_home);
  const pD = prob(row.draw_probability) ?? prob(mk.match_result?.prob_draw);
  const pA = prob(row.away_win_probability) ?? prob(mk.match_result?.prob_away);
  const out: Array<{ market: string; line: number | null; sel: string; p: number | null; pb?: number | null }> = [];
  if (pH != null && pD != null && pA != null) {
    out.push({ market: '1x2', line: null, sel: 'HOME', p: pH, pb: prob(mk.match_result?.prob_home) });
    out.push({ market: '1x2', line: null, sel: 'DRAW', p: pD, pb: prob(mk.match_result?.prob_draw) });
    out.push({ market: '1x2', line: null, sel: 'AWAY', p: pA, pb: prob(mk.match_result?.prob_away) });
    out.push({ market: 'double_chance', line: null, sel: '1X', p: pH + pD });
    out.push({ market: 'double_chance', line: null, sel: 'X2', p: pA + pD });
    out.push({ market: 'double_chance', line: null, sel: '12', p: pH + pA });
    if (pH + pA > 0) {
      out.push({ market: 'draw_no_bet', line: null, sel: 'HOME', p: pH / (pH + pA) });
      out.push({ market: 'draw_no_bet', line: null, sel: 'AWAY', p: pA / (pH + pA) });
    }
  }
  for (const [line, key] of [[1.5, 'over_15_probability'], [2.5, 'over_25_probability'], [3.5, 'over_35_probability']] as const) {
    const po = prob(row[key]) ?? prob(mk.over_under?.[`prob_over_${String(line).replace('.', '')}`]);
    if (po != null) {
      out.push({ market: 'over_under', line, sel: 'OVER', p: po });
      out.push({ market: 'over_under', line, sel: 'UNDER', p: 1 - po });
    }
  }
  const pb = prob(row.btts_probability) ?? prob(mk.btts?.prob_yes);
  if (pb != null) {
    out.push({ market: 'btts', line: null, sel: 'YES', p: pb });
    out.push({ market: 'btts', line: null, sel: 'NO', p: 1 - pb });
  }
  for (const [line, k] of [[8.5, 'prob_over_85'], [9.5, 'prob_over_95'], [10.5, 'prob_over_105']] as const) {
    const pc = prob(mk.corners?.[k]);
    if (pc != null) {
      out.push({ market: 'corners', line, sel: 'OVER', p: pc });
      out.push({ market: 'corners', line, sel: 'UNDER', p: 1 - pc });
    }
  }
  const xgH = n(row.predicted_home_goals) ?? n(mk.expected_goals?.home);
  const xgA = n(row.predicted_away_goals) ?? n(mk.expected_goals?.away);
  const preds: Prediction[] = [];
  for (const o of out) {
    if (o.p == null) continue;
    const key = o.line == null ? o.market : `${o.market}_${o.line}`;
    const od = odds?.[key]?.[o.sel] ?? null;
    if (od != null && od < minOdds) continue; // sub cota minimă nu se afișează
    const p = Math.max(0.001, Math.min(0.999, o.p));
    const evv = od != null ? p * od - 1 : null;
    const reasons: string[] = [];
    if (od != null) reasons.push(`Probabilitate Robot ${(p * 100).toFixed(0)}% vs. ${(100 / od).toFixed(0)}% implicită în cota ${od.toFixed(2)}`);
    else reasons.push(`Probabilitate Robot ${(p * 100).toFixed(0)}% (cota lipsește în sursele gratuite)`);
    if (xgH != null && xgA != null && (o.market === 'over_under' || o.market === 'btts')) reasons.push(`Goluri așteptate: ${xgH.toFixed(2)} – ${xgA.toFixed(2)}`);
    if (xgH != null && xgA != null && (o.market === '1x2' || o.market === 'double_chance' || o.market === 'draw_no_bet')) reasons.push(`xG estimat ${xgH.toFixed(2)} vs ${xgA.toFixed(2)}`);
    if (o.pb != null && Math.abs(o.pb - p) < 0.05) reasons.push(`Acord cu modelul BSD (${(o.pb * 100).toFixed(0)}%)`);
    if (row.most_likely_score) reasons.push(`Scor probabil: ${row.most_likely_score}`);
    preds.push({
      id: `${mid}:${key}:${o.sel}`,
      match_id: mid,
      market: o.market,
      line: o.line,
      selection: o.sel,
      label: selectionLabel(o.market, o.line, o.sel),
      p,
      p_bsd: o.pb ?? null,
      odds: od,
      odds_source: od != null ? oddsSrc ?? 'necunoscut' : null,
      fair_odds: 1 / p,
      edge: od != null ? p - 1 / od : null,
      ev: evv,
      value: evv != null && evv > 0,
      grade: gradeFrom(p, evv, row.quality_grade),
      confidence: Math.round(p * 100),
      market_healthy: o.market !== 'corners',
      reasons,
      result: null,
      profit: null,
      model_version: row.model?.version ?? 'legacy',
    });
  }
  preds.sort((a, b) => (b.p * (b.odds ? 1 : 0.5)) - (a.p * (a.odds ? 1 : 0.5)));
  // predicția principală: cea mai bună combinație probabilitate + valoare, cu cotă reală ≥ 1.15
  const withOdds = preds.filter((p) => p.odds != null && p.market !== 'corners');
  const strong = withOdds.filter((p) => p.p >= 0.55);
  const pick = (strong.length ? strong : withOdds.length ? withOdds : preds.filter((p) => p.market !== 'corners'))
    .slice().sort((a, b) => (b.p + 0.6 * (b.ev ?? 0)) - (a.p + 0.6 * (a.ev ?? 0)))[0];
  if (pick) pick.is_pick = true;
  return preds;
}

function baseMatch(ev: Any, league?: Any): Omit<Match, 'predictions'> {
  const lid = ev.league_id ?? league?.id ?? null;
  const score = ev.home_score != null && ev.away_score != null
    ? { ft: [ev.home_score, ev.away_score] as [number, number], ht: ev.home_score_ht != null ? [ev.home_score_ht, ev.away_score_ht] as [number, number] : null }
    : null;
  return {
    id: Number(ev.id ?? ev.event_id),
    kickoff_utc: ev.event_date,
    status: ev.status ?? 'notstarted',
    league: { id: lid, name: ev.league_name ?? ev.league ?? league?.name ?? 'Ligă necunoscută', logo: lid ? `${IMG}/league/${lid}/` : null },
    home: { id: ev.home_team_id ?? null, name: ev.home_team ?? '?', logo: ev.home_team_id ? `${IMG}/team/${ev.home_team_id}/` : null },
    away: { id: ev.away_team_id ?? null, name: ev.away_team ?? '?', logo: ev.away_team_id ? `${IMG}/team/${ev.away_team_id}/` : null },
    round: ev.round_label ?? null,
    score,
    minute: ev.current_minute ?? null,
  };
}

function applyResult(m: Match) {
  if (VOID_STATUSES.has(m.status)) {
    for (const p of m.predictions) { p.result = 'void'; p.profit = 0; }
    return;
  }
  if (!isFinished(m.status) || !m.score?.ft) return;
  const [h, a] = m.score.ft;
  for (const p of m.predictions) {
    if (p.result) continue;
    const r = settleSelection(p.market, p.line, p.selection, h, a);
    p.result = r;
    p.profit = r && p.odds ? profitFor(r, p.odds) : null;
  }
}

let basePromise: Promise<{ days: Map<string, Match[]>; meta: Any }> | null = null;

async function loadBase(minOdds: number) {
  const [preds, today, leagues] = await Promise.all([
    getJSON<Any>('data/predictions.json'),
    getJSON<Any>('data/matches_today.json'),
    getJSON<Any>('data/league_lookup.json'),
  ]);
  const rows: Any[] = preds?.results ?? [];
  const oddsIdx = await loadOddsIndex(rows);
  const live = new Map<number, Any>();
  for (const e of today?.results ?? []) live.set(Number(e.id), e);
  const leagueById: Any = leagues?.by_id ?? {};
  const days = new Map<string, Match[]>();
  const seen = new Set<number>();
  for (const row of rows) {
    const ev = { ...(row.event ?? {}) };
    const id = Number(ev.id);
    if (!id || seen.has(id)) continue;
    seen.add(id);
    const lv = live.get(id);
    if (lv) Object.assign(ev, { status: lv.status, home_score: lv.home_score, away_score: lv.away_score, home_score_ht: lv.home_score_ht, away_score_ht: lv.away_score_ht, current_minute: lv.current_minute, round_label: lv.round_label });
    const m: Match = { ...baseMatch(ev, leagueById[ev.league_id]), predictions: predictionsFromLegacy(row, oddsIdx.byEvent.get(id), oddsIdx.source.get(id), minOdds) };
    if (oddsIdx.byEvent.get(id)) m.odds = oddsIdx.byEvent.get(id);
    const ts: Any[] = row.top_scores ?? [];
    m.model = { lambda_home: row.predicted_home_goals, lambda_away: row.predicted_away_goals, most_likely_score: row.most_likely_score, top_scores: ts.map((t) => ({ score: t.score, p: t.prob })) };
    m.pick_id = m.predictions.find((p) => p.is_pick)?.id ?? null;
    applyResult(m);
    const d = roDay(m.kickoff_utc);
    days.set(d, [...(days.get(d) ?? []), m]);
  }
  // meciurile de azi fără predicții
  for (const e of today?.results ?? []) {
    const id = Number(e.id);
    if (seen.has(id)) continue;
    seen.add(id);
    const m: Match = { ...baseMatch(e, leagueById[e.league_id]), predictions: [] };
    const d = roDay(m.kickoff_utc);
    days.set(d, [...(days.get(d) ?? []), m]);
  }
  return { days, meta: { updated_at: preds?.updated_at } };
}

let pastPromise: Promise<Map<string, Match[]>> | null = null;

/** Zilele trecute: rezultate (`recent_results.json`) + selecțiile din jurnalul vechi. */
async function loadPast(): Promise<Map<string, Match[]>> {
  const [recent, journal] = await Promise.all([
    getJSON<Any>('data/recent_results.json'),
    getJSON<Any>('data/selection_journal.json'),
  ]);
  const byId = new Map<number, Match>();
  for (const e of recent?.results ?? []) {
    const m: Match = { ...baseMatch(e), predictions: [] };
    if (e.head_to_head) {
      const h = e.head_to_head;
      m.context = { h2h: { total: h.total_matches, home_wins: h.home_wins, draws: h.draws, away_wins: h.away_wins, avg_goals: h.avg_total_goals, recent: (h.recent_matches ?? []).slice(0, 6).map((r: Any) => ({ date: r.date, home: r.home, away: r.away, score: r.score ?? (r.home_score != null ? `${r.home_score}-${r.away_score}` : undefined) })) } };
    }
    byId.set(m.id, m);
  }
  for (const j of journal?.results ?? []) {
    const id = Number(j.event_id);
    let m = byId.get(id);
    if (!m) {
      m = { ...baseMatch({ id, event_date: j.event_date, league_name: j.league, league_id: j.league_id, home_team: j.home_team, away_team: j.away_team, home_team_id: j.home_team_id, away_team_id: j.away_team_id, status: j.status === 'settled' ? 'finished' : 'notstarted', home_score: j.home_score, away_score: j.away_score }), predictions: [] };
      byId.set(id, m);
    }
    const jr = legacyJournalToRow(j);
    if (!jr) continue;
    m.predictions.push({
      id: j.key ?? `${id}:${j.market}`, match_id: id, market: jr.market, line: null, selection: '', label: jr.label,
      p: jr.p ?? 0, odds: jr.odds, odds_source: 'jurnal v2', result: jr.result === 'pending' ? null : jr.result, profit: jr.profit, grade: null, reasons: [`Strategie veche: ${j.strategy_label ?? j.strategy ?? '—'}`],
    });
  }
  const days = new Map<string, Match[]>();
  for (const m of byId.values()) {
    const d = roDay(m.kickoff_utc);
    days.set(d, [...(days.get(d) ?? []), m]);
  }
  return days;
}

export async function legacyDayIndex(minOdds: number): Promise<string[]> {
  basePromise = basePromise ?? loadBase(minOdds);
  const { days } = await basePromise;
  return [...days.keys()].sort();
}

export async function legacyDay(date: string, minOdds: number, includePast: boolean): Promise<Day | null> {
  basePromise = basePromise ?? loadBase(minOdds);
  const { days, meta } = await basePromise;
  let matches = days.get(date) ?? [];
  if (includePast) {
    pastPromise = pastPromise ?? loadPast();
    const past = await pastPromise;
    const extra = past.get(date) ?? [];
    const ids = new Set(matches.map((m) => m.id));
    matches = [...matches.map((m) => {
      const pm = extra.find((x) => x.id === m.id);
      if (pm && pm.score && !m.score) { const merged = { ...m, status: pm.status, score: pm.score }; applyResult(merged); return merged; }
      return m;
    }), ...extra.filter((m) => !ids.has(m.id))];
  }
  if (!matches.length && !days.size) return null;
  matches = [...matches].sort((a, b) => a.kickoff_utc.localeCompare(b.kickoff_utc));
  return { schema: 'legacy', date, generated_at: meta.updated_at, min_odds: minOdds, matches, count: matches.length, _source: 'legacy' };
}

export function legacyJournalToRow(j: Any): JournalRow | null {
  const odds = n(j.odds);
  if (!odds) return null;
  const raw = String(j.result ?? '').toUpperCase();
  const result: LegResult | 'pending' = raw === 'WIN' || raw === 'WON' ? 'won' : raw === 'LOSS' || raw === 'LOST' ? 'lost' : raw === 'VOID' ? 'void' : 'pending';
  return {
    date: roDay(j.event_date),
    match_id: Number(j.event_id),
    match: `${j.home_team ?? '?'} – ${j.away_team ?? '?'}`,
    league: j.league ?? '—',
    market: j.market_canonical ?? j.market ?? '?',
    label: j.market_label ?? j.market ?? '?',
    odds,
    p: prob(j.model_probability),
    result,
    profit: result === 'pending' ? null : n(j.profit_units) ?? profitFor(result, odds),
    source: j.strategy_label ?? j.strategy ?? j.source,
    score: j.actual_score ?? j.score_ft ?? null,
  };
}

export async function legacyJournal(): Promise<JournalRow[]> {
  const j = await getJSON<Any>('data/selection_journal.json');
  return (j?.results ?? []).map(legacyJournalToRow).filter(Boolean) as JournalRow[];
}

/** Context detaliat pentru pagina meciului (formă, H2H, absențe, clasament) din cache-urile vechi. */
export async function legacyContext(m: Match): Promise<MatchContext> {
  const [form, h2h, squads, standings] = await Promise.all([
    getJSON<Any>('data/team_form_cache.json'),
    getJSON<Any>('data/h2h_context.json'),
    getJSON<Any>('data/team_squads.json'),
    getJSON<Any>('data/standings.json'),
  ]);
  const ctx: MatchContext = { ...(m.context ?? {}) };
  const tf: Any = form?.teams ?? {};
  const toForm = (t: Any | undefined) => t ? {
    played: t.sample ?? (t.form_string ? t.form_string.length : undefined), w: t.wins, d: t.draws, l: t.losses,
    gf: t.avg_goals_scored_last5 != null ? Math.round(t.avg_goals_scored_last5 * (t.sample ?? 5)) : undefined,
    ga: t.avg_goals_conceded_last5 != null ? Math.round(t.avg_goals_conceded_last5 * (t.sample ?? 5)) : undefined,
    sequence: t.form_string, ppm: t.form_score != null ? (t.form_score / 100) * 3 : undefined,
  } : null;
  ctx.form = { home: toForm(tf[String(m.home.id)]), away: toForm(tf[String(m.away.id)]) };
  if (!ctx.h2h) {
    const h = (h2h?.results ?? []).find((r: Any) => Number(r.event_id) === m.id
      || (r.home_team_id === m.home.id && r.away_team_id === m.away.id));
    if (h) ctx.h2h = { total: h.sample, home_wins: h.home_wins, draws: h.draws, away_wins: h.away_wins, avg_goals: h.avg_goals, over25_rate: prob(h.over25_pct), btts_rate: prob(h.btts_pct), recent: (h.matches ?? []).map((x: Any) => ({ date: roDay(x.event_date), home: x.home_team, away: x.away_team, score: x.score })) };
  }
  const abs = (tid: number | null): Absence[] => {
    const t = (squads?.results ?? []).find((s: Any) => s.team_id === tid);
    return (t?.players ?? []).filter((p: Any) => p.availability && p.availability !== 'available')
      .map((p: Any) => ({ player: p.name, status: p.availability, return: p.injury_expected_return, position: p.position }));
  };
  ctx.absences = { home: abs(m.home.id), away: abs(m.away.id) };
  const findStanding = (tid: number | null) => {
    for (const lg of Object.values<Any>(standings?.leagues ?? {})) {
      const rows: Any[] = lg.standings ?? lg.table ?? lg.results ?? (Array.isArray(lg) ? lg : []);
      const r = rows.find((x: Any) => (x.team_id ?? x.team?.id) === tid);
      if (r) return { position: r.position ?? r.rank, points: r.points ?? r.pts, played: r.played ?? r.matches_played ?? r.games };
    }
    return null;
  };
  ctx.standings = { home: findStanding(m.home.id), away: findStanding(m.away.id) };
  return ctx;
}

/** Istoricul piramidei vechi (tracker paper) în forma contractului. */
export async function legacyPyramidHistory(): Promise<Pick<PyramidState, 'history' | 'reach_probability'>> {
  const s = await getJSON<Any>('data/pyramid_state.json');
  const hist: Any[] = s?.tracks?.safe?.history ?? [];
  return {
    history: hist.map((h) => ({
      date: roDay(h.event_date), odds: n(h.odds), p: prob(h.adj_prob), status: 'pick',
      result: h.result === 'WIN' ? 'won' : h.result === 'LOSS' ? 'lost' : h.result === 'VOID' ? 'void' : 'pending',
      label: `${h.home_team} – ${h.away_team} · ${h.market_label ?? h.market}`,
    })),
    reach_probability: [],
  };
}
