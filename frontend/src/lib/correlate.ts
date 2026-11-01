/** Aceeași tabelă ca betpredict/builder/bb_corr.py. Două selecții pe un meci nu sunt independente. */

export const BB_LIFTS = {
  fav_win_fav_o15: 1.66,
  over25_gg: 1.53,
  under35_gg_no: 1.32,
  fav_win_corners: 0.94,
} as const;

type Leg = { match_id?: number; market: string; selection: string; line?: number | null; p?: number | null };

function kind(leg: Leg): string {
  const sel = leg.selection || '';
  const mk = leg.market || '';
  const line = leg.line ?? null;
  if ((mk === '1x2' && sel === 'HOME') || sel === 'R:1x2:0:HOME') return 'home_win';
  if ((mk === '1x2' && sel === 'AWAY') || sel === 'R:1x2:0:AWAY') return 'away_win';
  if (sel === 'HO15' || (mk === 'team_total_home' && sel === 'OVER' && line === 1.5)) return 'home_o15';
  if (sel === 'AO15' || (mk === 'team_total_away' && sel === 'OVER' && line === 1.5)) return 'away_o15';
  if ((mk === 'over_under' && sel === 'OVER' && line === 2.5) || sel === 'O25') return 'over25';
  if (mk === 'over_under' && sel === 'UNDER' && line === 3.5) return 'under35';
  if ((mk === 'btts' && sel === 'YES') || sel === 'GG' || sel === 'GGO25') return 'gg_yes';
  if (mk === 'btts' && sel === 'NO') return 'gg_no';
  if (mk === 'corners' || ['C65', 'C75', 'C85', 'C95'].includes(sel) || sel.startsWith('H1C') || sel.startsWith('BB_C') || sel.startsWith('BB_H1C')) return 'corners';
  return `${mk}:${sel}:${line}`;
}

export function pairLift(a: Leg, b: Leg): number | null {
  const pair = new Set([kind(a), kind(b)]);
  const has = (...xs: string[]) => xs.every((x) => pair.has(x)) && pair.size === xs.length;
  if (has('home_win', 'home_o15') || has('away_win', 'away_o15')) return BB_LIFTS.fav_win_fav_o15;
  if (has('over25', 'gg_yes')) return BB_LIFTS.over25_gg;
  if (has('under35', 'gg_no')) return BB_LIFTS.under35_gg_no;
  if (pair.has('corners') && (pair.has('home_win') || pair.has('away_win')) && pair.size === 2) return BB_LIFTS.fav_win_corners;
  return null;
}

function joint(pa: number, pb: number, lift: number): number {
  return Math.min(0.99, Math.max(0, pa * pb * lift));
}

/** Șansa biletului. `unknown` înseamnă selecții corelate fără lift: nu se înmulțesc ca și cum ar fi independente. */
export function correlatedChance(legs: Leg[]): { p: number | null; correlated: boolean; unknown: boolean } {
  const groups = new Map<number, Leg[]>();
  legs.forEach((leg, i) => {
    const id = leg.match_id ?? -(i + 1);
    groups.set(id, [...(groups.get(id) ?? []), leg]);
  });
  let p = 1;
  let correlated = false;
  let unknown = false;
  for (const group of groups.values()) {
    if (group.some((l) => l.p == null)) { unknown = true; continue; }
    if (group.length === 1) { p *= group[0].p as number; continue; }
    correlated = true;
    if (group.length !== 2) { unknown = true; continue; }
    const lift = pairLift(group[0], group[1]);
    if (lift == null) { unknown = true; continue; }
    p *= joint(group[0].p as number, group[1].p as number, lift);
  }
  if (unknown || !legs.length) return { p: null, correlated, unknown: true };
  return { p: Math.min(0.99, p), correlated, unknown: false };
}
