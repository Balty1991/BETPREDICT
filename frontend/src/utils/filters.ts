const IMG_BASE = 'https://sports.bzzoiro.com/img';

export function teamLogoUrl(id?: number | null): string | null {
  if (!id) return null;
  return `${IMG_BASE}/team/${id}/`;
}

// Cote sub acest prag (ex. @1.04) nu se afișează nicăieri — nici în predicții,
// nici în statistici: valoarea e practic zero, edge-ul aproape mereu negativ,
// iar riscul nu se justifică pentru cât plătește cota.
export const MIN_DISPLAY_ODDS = 1.07;

/** Edge v8: sub 1.50 e capcana de volum (Over 1.5 @1.32, favorite @1.14). */
export const MIN_QUALIFIED_ODDS = 1.50;
export const MIN_ACCA_LEG_ODDS = 1.60;
export const MAX_QUALIFIED_ODDS = 3.30;
export const MIN_EDGE_PP = 4;

const BLACKLIST = ['under_35', 'under35', 'over_25', 'over25', 'under_25', 'under25'];

export function isBlacklistedMarket(market?: string | null): boolean {
  if (!market) return false;
  const m = market.toLowerCase().replace(/[\s.]/g, '_');
  return BLACKLIST.some((b) => m.includes(b.replace('_', '')) || m.includes(b));
}

export function isVolumeOver15(market?: string | null, odds?: number | null): boolean {
  if (!market) return false;
  const m = market.toLowerCase();
  const o15 = m.includes('over_15') || m.includes('over15') || m.includes('over 1.5');
  return o15 && (odds == null || odds < 1.68);
}

export function isEdgePass(v?: {
  risk_tier?: string; odds?: number | null; market?: string; edge_pp?: number | null;
} | null): boolean {
  if (!v || v.odds == null) return false;
  if (v.odds < MIN_QUALIFIED_ODDS || v.odds > MAX_QUALIFIED_ODDS) return false;
  if (isBlacklistedMarket(v.market)) return false;
  if (isVolumeOver15(v.market, v.odds)) return false;
  if (v.edge_pp != null && v.edge_pp < MIN_EDGE_PP) return false;
  return true;
}

export function isQualifiedVerdict(v?: {
  risk_tier?: string; odds?: number | null; market?: string; edge_pp?: number | null;
} | null): boolean {
  return isEdgePass(v);
}

export function isAccaLeg(v?: {
  odds?: number | null; market?: string; edge_pp?: number | null; risk_tier?: string;
} | null): boolean {
  if (!isEdgePass(v)) return false;
  return (v?.odds ?? 0) >= MIN_ACCA_LEG_ODDS;
}

/** De ce un verdict V7 e BLOCHEAZĂ pe Edge v8 — afișat pe card. */
export function blockedReason(v?: {
  odds?: number | null; market?: string; edge_pp?: number | null;
} | null): string | null {
  if (!v || v.odds == null) return 'Fără cotă de piață — nu se pariază.';
  if (isBlacklistedMarket(v.market)) return 'Piață pe blacklist (U3.5 / O2.5 / U2.5) — leak-ul V7.';
  if (isVolumeOver15(v.market, v.odds)) {
    return `Over 1.5 @${v.odds.toFixed(2)} e cotă de volum. Doar ≥1.68.`;
  }
  if (v.odds < MIN_QUALIFIED_ODDS) {
    return `Cotă ${v.odds.toFixed(2)} sub 1.50 — capcana de volum V7 (76% WR, −ROI).`;
  }
  if (v.odds > MAX_QUALIFIED_ODDS) {
    return `Cotă ${v.odds.toFixed(2)} peste 3.30 — zgomot, nu edge.`;
  }
  if (v.edge_pp != null && v.edge_pp < MIN_EDGE_PP) {
    return `Edge ${v.edge_pp > 0 ? '+' : ''}${v.edge_pp.toFixed(1)}pp sub minimul de +4.`;
  }
  return null;
}

export function ticketPassesEdge(t?: {
  legs?: Array<{ odds?: number | null; market?: string; edge_pp?: number | null }>;
} | null): boolean {
  const legs = t?.legs;
  if (!legs?.length) return false;
  return legs.every((leg) => isAccaLeg(leg) || isEdgePass(leg));
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

export function formatTicketProb(pct: number): string {
  if (pct >= 1) return `${pct.toFixed(0)}%`;
  if (pct >= 0.01) return `${pct.toFixed(2)}%`;
  return `${pct.toFixed(4)}%`;
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
