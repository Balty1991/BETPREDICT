import type { Signal, JournalEntry, ValueBet } from '@/types/betpredict';

const IMG_BASE = 'https://sports.bzzoiro.com/img';

export function teamLogoUrl(id?: number | null): string | null {
  if (!id) return null;
  return `${IMG_BASE}/team/${id}/`;
}

export function effectiveScore(s: Signal): number {
  const ds = s.display_score ?? s.market_signal_score;
  if (ds != null && ds > 0) return ds;
  return s.smartbet_score_v6 ?? s.smartbet_score ?? 0;
}

export function effectiveGrade(s: Signal): string {
  return s.quality_grade_v6 ?? s.quality_grade ?? '';
}

export function effectiveEV(s: Signal): number {
  const ev = s.ev_calibrated ?? s.ev;
  if (ev != null) return ev;
  const evp = s.ev_pct;
  if (typeof evp === 'number') return evp / 100;
  if (typeof evp === 'string') return parseFloat(evp) / 100 || 0;
  return 0;
}

export function effectiveProb(s: Signal): number {
  const cp = s.calibrated_prob;
  if (cp != null) return cp <= 1 ? cp * 100 : cp;
  const ap = s.adj_prob;
  if (ap != null) return ap <= 1 ? ap * 100 : ap;
  return 0;
}

export function isVeyra(s: Signal): boolean {
  return s.strategy === 'veyra_engine' || (s.engine_version ?? '').includes('veyra');
}

const GOOD_GRADES = new Set(['A+', 'A', 'B']);
export const CUTOFF_MS = 5 * 60 * 1000;

export function passesFilter(s: Signal): boolean {
  const g = effectiveGrade(s);
  const sc = effectiveScore(s);
  const ev = effectiveEV(s);
  const odds = s.odds ?? 0;
  const scMin = 50;
  const gradeOk = GOOD_GRADES.has(g) || (g === 'C' && sc >= 70);
  const koMs = s.event_date ? new Date(s.event_date).getTime() : Infinity;
  return gradeOk && ev > 0 && sc >= scMin && koMs > Date.now() - CUTOFF_MS && odds >= 1.35 && odds <= 3.50;
}

export function filteredSignals(signals: Signal[], vbSet: Set<string>): Signal[] {
  const passed = signals.filter(passesFilter);
  const byEid = new Map<string | number, Signal>();
  for (const s of passed) {
    const cur = byEid.get(s.event_id);
    const scNew = effectiveScore(s) + (vbSet.has(`${s.event_id}_${s.market}`) ? 12 : 0);
    const scCur = cur ? effectiveScore(cur) + (vbSet.has(`${cur.event_id}_${cur.market}`) ? 12 : 0) : -1;
    if (!cur || scNew > scCur) byEid.set(s.event_id, s);
  }
  return Array.from(byEid.values()).sort(
    (a, b) => new Date(a.event_date).getTime() - new Date(b.event_date).getTime()
  );
}

const QUALIFIED_RISK_TIERS = new Set(['foarte_sigur', 'sigur']);

export function isQualifiedVerdict(v?: { risk_tier?: string } | null): boolean {
  return !!v && QUALIFIED_RISK_TIERS.has(v.risk_tier ?? '');
}

export function vbSetFromList(vbs: ValueBet[]): Set<string> {
  return new Set(vbs.map(v => `${v.event_id}_${v.market}`));
}

export function journalStats(journal: JournalEntry[]) {
  const settled = journal.filter(e => e.status === 'settled');
  const wins = settled.filter(e => e.result === 'WIN').length;
  const losses = settled.filter(e => e.result === 'LOSS').length;
  const profit = settled.reduce((s, e) => s + (e.profit_units ?? 0), 0);
  const wr = settled.length > 0 ? Math.round((wins / settled.length) * 100) : null;
  const roi = settled.length > 0 ? Math.round((profit / settled.length) * 100) : null;
  return { wins, losses, settled: settled.length, pending: journal.filter(e => e.status === 'pending').length, profit, wr, roi };
}

export const MARKET_LABELS: Record<string, string> = {
  homeWin: 'Gazdă câștigă',
  draw: 'Egal',
  awayWin: 'Oaspete câștigă',
  btts: 'Ambele marchează',
  over15: 'Over 1.5G',
  over25: 'Over 2.5G',
  under35: 'Under 3.5G',
  over35: 'Over 3.5G',
  under25: 'Under 2.5G',
  '1x2_home': 'Gazdă câștigă',
  '1x2_draw': 'Egal',
  '1x2_away': 'Oaspete câștigă',
  'double_chance_1x': 'Gazdă sau Egal (1X)',
  'double_chance_x2': 'Egal sau Deplasare (X2)',
  'double_chance_12': 'Gazdă sau Deplasare (12)',
  'btts_yes': 'Ambele marchează - Da',
  'btts_no': 'Ambele marchează - Nu',
};

export function marketLabel(market: string, fallback?: string): string {
  return MARKET_LABELS[market] ?? fallback ?? market;
}

export function formatDate(iso: string): string {
  try {
    const d = new Date(iso);
    const now = new Date();
    const isToday = d.toDateString() === now.toDateString();
    const tom = new Date(now); tom.setDate(now.getDate() + 1);
    const isTomorrow = d.toDateString() === tom.toDateString();
    const time = d.toLocaleTimeString('ro-RO', { hour: '2-digit', minute: '2-digit' });
    if (isToday) return `Azi · ${time}`;
    if (isTomorrow) return `Mâine · ${time}`;
    return `${d.getDate().toString().padStart(2, '0')}.${(d.getMonth()+1).toString().padStart(2,'0')} · ${time}`;
  } catch { return iso.slice(0, 10); }
}

export function timeAgo(iso: string | null | undefined): string {
  if (!iso) return '—';
  try {
    const diffMs = Date.now() - new Date(iso).getTime();
    const mins = Math.floor(diffMs / 60000);
    if (mins < 1) return 'chiar acum';
    if (mins < 60) return `acum ${mins}m`;
    const hours = Math.floor(mins / 60);
    if (hours < 24) return `acum ${hours}h`;
    const days = Math.floor(hours / 24);
    return `acum ${days}z`;
  } catch { return '—'; }
}

export function scoreColor(sc: number): string {
  if (sc >= 75) return '#00e87a';
  if (sc >= 60) return '#4a9eff';
  if (sc >= 45) return '#ffb830';
  return '#ff3d5a';
}

export function gradeColor(grade: string): string {
  switch (grade) {
    case 'A+': return '#00e87a';
    case 'A': return '#22c55e';
    case 'B': return '#4a9eff';
    case 'C': return '#fbbf24';
    case 'D': return '#fb923c';
    default: return '#94a3b8';
  }
}
