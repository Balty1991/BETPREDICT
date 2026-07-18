const IMG_BASE = 'https://sports.bzzoiro.com/img';

export function teamLogoUrl(id?: number | null): string | null {
  if (!id) return null;
  return `${IMG_BASE}/team/${id}/`;
}

// Cote sub acest prag (ex. @1.04) nu se afișează nicăieri — nici în predicții,
// nici în statistici: valoarea e practic zero, edge-ul aproape mereu negativ,
// iar riscul nu se justifică pentru cât plătește cota.
export const MIN_DISPLAY_ODDS = 1.07;

const QUALIFIED_RISK_TIERS = new Set(['foarte_sigur', 'sigur']);
// Aceeași cotă minimă folosită pentru accumulator_eligible în claude_analysis.py —
// sub acest prag riscul nu se justifică pentru ce oferă cota, indiferent de tab.
const MIN_QUALIFIED_ODDS = 1.10;

export function isQualifiedVerdict(v?: { risk_tier?: string; odds?: number | null } | null): boolean {
  if (!v || !QUALIFIED_RISK_TIERS.has(v.risk_tier ?? '')) return false;
  return v.odds == null || v.odds >= MIN_QUALIFIED_ODDS;
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
