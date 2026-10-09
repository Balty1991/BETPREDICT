/**
 * Încărcătoare de date: întâi contractul nou (`./api/…`), apoi adaptorul pentru `./data/` vechi.
 * Totul e lazy: fiecare pagină cere doar fișierele de care are nevoie.
 */
import { getJSON } from './fetcher';
import { todayRo, addDays } from './format';
import { legacyDay, legacyDayIndex, legacyContext, legacyPyramidHistory } from './legacy';
import { STATS_SINCE, isV3Prediction, isRecommended } from './rules';
import type { Day, Meta, TicketsFile, PyramidState, StatsSummary, StatsSeries, CalibrationMarket, Learning, JournalRow, Match, MatchContext } from './types';

/* eslint-disable @typescript-eslint/no-explicit-any */

export async function loadMeta(): Promise<Meta> {
  const m = await getJSON<Meta>('api/meta.json');
  if (m) return { ...m, _source: 'api' };
  const s = await getJSON<any>('data/update_status.json');
  return {
    _source: 'legacy',
    generated_at: s?.updated_at,
    status: s?.status === 'GREEN' ? 'ok' : s?.status === 'RED' ? 'stale' : 'degraded',
    quota: { effective_remaining: s?.api_quota?.remaining, daily_quota: 7500 },
    warnings: s?.notes ?? [],
  };
}

export async function loadDayIndex(minOdds: number): Promise<{ days: string[]; source: 'api' | 'legacy' }> {
  const idx = await getJSON<{ days: string[] }>('api/days/index.json');
  if (idx?.days?.length) return { days: [...idx.days].sort(), source: 'api' };
  return { days: await legacyDayIndex(minOdds), source: 'legacy' };
}

/** Protejează UI-ul de câmpuri nule din API (ex. ligi fără nume). */
function normalizeMatch(m: Match): Match {
  const lg = m.league ?? ({} as Match['league']);
  return {
    ...m,
    kickoff_utc: m.kickoff_utc ?? '',
    home: { ...m.home, name: m.home?.name ?? 'Gazde' },
    away: { ...m.away, name: m.away?.name ?? 'Oaspeți' },
    league: { ...lg, name: lg.name ?? (lg.id ? `Liga #${lg.id}` : 'Ligă necunoscută') },
    predictions: m.predictions ?? [],
  };
}

export async function loadDay(date: string, minOdds: number): Promise<Day | null> {
  const d = await getJSON<Day>(`api/days/${date}.json`);
  if (d && Array.isArray(d.matches) && d.matches.length) {
    return { ...d, matches: d.matches.map(normalizeMatch), _source: 'api' };
  }
  return legacyDay(date, minOdds, date < todayRo());
}

/** Caută un meci în zilele din jurul datei (pagina /meci/:id). */
export async function findMatch(id: number, hintDate: string | null, minOdds: number): Promise<{ match: Match; day: Day } | null> {
  const t = todayRo();
  const candidates = hintDate ? [hintDate] : [];
  for (let i = -3; i <= 7; i++) candidates.push(addDays(t, i));
  for (const date of [...new Set(candidates)]) {
    const day = await loadDay(date, minOdds);
    const match = day?.matches.find((m) => m.id === id);
    if (match && day) return { match, day };
  }
  return null;
}

export async function loadMatchContext(m: Match, source: Day['_source']): Promise<MatchContext> {
  const hasCtx = m.context && (m.context.form || m.context.absences || m.context.standings);
  if (source === 'api' || hasCtx) {
    // contractul poate publica și un fișier per meci (generat lazy)
    const extra = await getJSON<{ context?: MatchContext }>(`api/match/${m.id}.json`);
    return { ...(m.context ?? {}), ...(extra?.context ?? {}) };
  }
  return legacyContext(m);
}

export async function loadTickets(date: string): Promise<TicketsFile | null> {
  const t = (await getJSON<TicketsFile>(`api/tickets/${date}.json`)) ?? (date === todayRo() ? await getJSON<TicketsFile>('api/tickets/today.json') : null);
  if (t && t.tickets?.length && t.date === date) return { ...t, _source: 'api' };
  return null;
}

export async function loadTicketsHistory(): Promise<TicketsFile['tickets']> {
  const h = await getJSON<{ tickets: TicketsFile['tickets'] }>('api/tickets/history.json');
  return h?.tickets ?? [];
}

export async function loadPyramid(): Promise<PyramidState | null> {
  const p = await getJSON<PyramidState>('api/pyramid/state.json');
  // folosim starea oficială doar când pipeline-ul a generat ceva (altfel calculăm local)
  if (p && p.rules && (p.today?.main || (p.history?.length ?? 0) > 0)) return { ...p, _source: 'api' };
  return null;
}
export { legacyPyramidHistory };

export async function loadStats(): Promise<{ summary: StatsSummary | null; daily: StatsSeries | null; monthly: StatsSeries | null; calibration: CalibrationMarket[] | null; learning: Learning | null }> {
  const [summary, daily, monthly, cal, learning] = await Promise.all([
    getJSON<StatsSummary>('api/stats/summary.json'),
    getJSON<StatsSeries>('api/stats/daily.json'),
    getJSON<StatsSeries>('api/stats/monthly.json'),
    getJSON<{ markets: CalibrationMarket[] }>('api/stats/calibration.json'),
    getJSON<Learning>('api/stats/learning.json'),
  ]);
  const hasSummary = summary && (summary.overall?.n ?? 0) > 0;
  return { summary: hasSummary ? { ...summary!, _source: 'api' } : null, daily, monthly, calibration: cal?.markets ?? null, learning };
}

/** Rânduri plate pentru statistici: DOAR predicțiile Robotului 3.0 publicate de la STATS_SINCE (fără jurnal vechi/importat). */
interface JournalFile { since?: string; cols: string[]; src?: Record<string, string>; matches: Record<string, [string, string, string, string | null]>; rows: unknown[][] }

/** Jurnalul precalculat de pipeline (`api/stats/journal.json`): mic, fără fișierele zilelor. */
async function loadJournalFile(daysBack: number): Promise<JournalRow[] | null> {
  const j = await getJSON<JournalFile>('api/stats/journal.json');
  if (!j?.rows || !j.cols || !j.matches) return null;
  const ix = (k: string) => j.cols.indexOf(k);
  const [iD, iM, iMk, iL, iO, iP, iR, iPr, iG, iS] = ['date', 'match_id', 'market', 'label', 'odds', 'p', 'result', 'profit', 'grade', 'src'].map(ix);
  const src = j.src ?? { 0: 'predicții', 1: 'principală', 2: 'recomandată' };
  const t = todayRo();
  const lo = addDays(t, -daysBack) > STATS_SINCE ? addDays(t, -daysBack) : STATS_SINCE;
  const out: JournalRow[] = [];
  for (const r of j.rows) {
    const date = r[iD] as string;
    if (date < lo || date > t) continue;
    const mm = j.matches[String(r[iM])] ?? ['Gazde', 'Oaspeți', 'Ligă necunoscută', null];
    out.push({
      date, match_id: r[iM] as number, match: `${mm[0]} – ${mm[1]}`, league: mm[2], market: r[iMk] as string, label: r[iL] as string,
      odds: r[iO] as number, p: r[iP] as number, result: (r[iR] as JournalRow['result']) ?? 'pending', profit: (r[iPr] as number | null) ?? null,
      grade: r[iG] as JournalRow['grade'], source: src[String(r[iS])] ?? 'predicții', score: mm[3],
    });
  }
  return out;
}

export async function loadJournalRows(minOdds: number, daysBack = 14): Promise<{ rows: JournalRow[]; source: 'api' | 'legacy' }> {
  const pre = await loadJournalFile(daysBack);
  if (pre) return { rows: pre, source: 'api' };
  const idx = await getJSON<{ days: string[] }>('api/days/index.json');
  if (idx?.days?.length) {
    const t = todayRo();
    const days = idx.days.filter((d) => d <= t && d >= STATS_SINCE).sort().slice(-daysBack);
    const loaded = await Promise.all(days.map((d) => getJSON<Day>(`api/days/${d}.json`)));
    const rows: JournalRow[] = [];
    for (const day of loaded) {
      for (const m of (day?.matches ?? []).map(normalizeMatch)) {
        for (const p of m.predictions ?? []) {
          if (p.odds == null || !isV3Prediction(p, day!.date)) continue;
          rows.push({
            date: day!.date, match_id: m.id, match: `${m.home.name} – ${m.away.name}`, league: m.league.name,
            market: p.line != null ? `${p.market}_${p.line}` : p.market, label: p.label, odds: p.odds, p: p.p,
            result: p.result ?? 'pending', profit: p.profit ?? null, grade: p.grade, source: isRecommended(p) ? 'recomandată' : p.is_pick ? 'principală' : 'predicții',
            score: m.score?.ft ? `${m.score.ft[0]}-${m.score.ft[1]}` : null,
          });
        }
      }
    }
    return { rows, source: 'api' };
  }
  void minOdds;
  return { rows: [], source: 'api' };
}
