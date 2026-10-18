import type { Ticket } from './types';

/** Miza sugerată ca procent din bancă, după cât de des iese un astfel de bilet.
 *  Ideea: biletele care ies rar (cotă 80–200) primesc o miză mică, ca o serie lungă de pierderi să nu golească banca
 *  înainte să vină câștigul. Piramida are regulile ei (nu primește sugestie aici). */
export function stakePct(t: Ticket): number | null {
  const odds = t.total_odds || t.target_odds || 0;
  if (t.kind === 'pyramid') return null;
  if (t.lottery || t.variant === 'super' || (t.variant ?? '').includes('loter')) return 0.001;
  if (t.kind === 'acca_soft') return 0.01;
  if (t.kind === 'acca_stil' || t.variant === 'stil_supersocial') return odds >= 60 ? 0.0025 : 0.005;
  if (odds <= 3) return 0.02;
  if (odds <= 8) return 0.01;
  if (odds <= 25) return 0.005;
  return 0.0025;
}

export function suggestedLei(t: Ticket, bank: number): number | null {
  const p = stakePct(t);
  if (p == null || !bank || bank <= 0) return null;
  return Math.max(1, Math.round(bank * p * 2) / 2);
}

/** Luni (YYYY-MM-DD, ora României) a săptămânii curente. */
export function weekStart(now = new Date()): string {
  const ro = new Date(now.toLocaleString('en-US', { timeZone: 'Europe/Bucharest' }));
  const d = (ro.getDay() + 6) % 7; ro.setDate(ro.getDate() - d);
  return `${ro.getFullYear()}-${String(ro.getMonth() + 1).padStart(2, '0')}-${String(ro.getDate()).padStart(2, '0')}`;
}

/** Cât ai jucat săptămâna asta: doar biletele marcate „Îl joc” (followed), nu mizele sugerate. */
export function weekSpent(mine: Ticket[], now = new Date(), budget?: number): number {
  const ws = weekStart(now);
  // doar mizele în lei puse de Alin: biletele vechi ale Robotului salvate cu miza internă (unități, banca piramidei 100)
  // nu sunt lei; o miză peste bugetul săptămânal e tratată ca greșeală de unitate și ignorată
  return mine.reduce((a, t) => {
    if (!t.followed || (t.date ?? t.created_at ?? '').slice(0, 10) < ws) return a;
    const x = Number((t as { stake_lei?: number }).stake_lei ?? t.stake) || 0;
    return a + (budget && x > budget ? 0 : x);
  }, 0);
}

/** Miza de bază din bugetul săptămânal (la 50 lei): Pont 8, cotă mărită EV ≥ 0 4, piramidă 5, lanț 3, 20–99 2, 100+ 1–2. */
export function budgetBase(t: Ticket, budget: number): number | null {
  if (t.status && t.status !== 'pending') return null;
  const v = `${t.kind ?? ''} ${t.variant ?? ''} ${(t as { tier?: string }).tier ?? ''} ${t.variant_label ?? ''}`.toLowerCase();
  const odds = t.total_odds || t.target_odds || 0;
  const f = Math.max(0.2, budget / 50); // scalare față de 50 lei
  // 18.10: mizele urmează rezultatele — Pontul zilei (+11% în oct.) și biletele cu cotă mărită EV ≥ 0 (+22%, n 86)
  // primesc mai mult; 100+/500+/1000+ (0 din 55 în oct.) stau la minim
  const boostEv = t.legs?.some((l) => String(l.market ?? '').startsWith('boost')) && (t.ev ?? -1) >= 0;
  let base: number;
  if (t.kind === 'acca_pont') base = 8;
  else if (t.kind === 'pyramid' || v.includes('pyramid') || v.includes('piramid')) base = 5;
  else if (v.includes('chain') || v.includes('lanț') || v.includes('lant')) base = 3;
  else if (odds >= 100) base = 1;
  else if (boostEv) base = 4;
  else if (odds >= 20) base = 2;
  else base = 3;
  const r = Math.max(1, Math.round(base * f));
  return odds >= 100 ? Math.min(2, r) : r;
}

/** Miza sugerată, plafonată la ce a rămas din buget (null = bugetul e consumat). */
export function budgetLei(t: Ticket, budget: number, spent: number): number | null {
  const b = budgetBase(t, budget);
  if (b == null || !budget) return null;
  const left = Math.max(0, budget - spent);
  return left >= 1 ? Math.min(b, Math.floor(left)) : null;
}
