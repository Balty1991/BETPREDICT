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

/** Cât ai jucat săptămâna asta (bilete din „Biletele mele”). */
export function weekSpent(mine: Ticket[], now = new Date()): number {
  const ws = weekStart(now);
  return mine.reduce((a, t) => a + (((t.date ?? t.created_at ?? '').slice(0, 10) >= ws) ? Number(t.stake) || 0 : 0), 0);
}

/** Miza de bază din bugetul săptămânal: lanț ~5, piramidă 10 start, compact 2–5, 100+ 2, 500+/1000+ 1–2. */
export function budgetBase(t: Ticket, budget: number): number | null {
  if (t.status && t.status !== 'pending') return null;
  const v = `${t.kind ?? ''} ${t.variant ?? ''} ${(t as { tier?: string }).tier ?? ''} ${t.variant_label ?? ''}`.toLowerCase();
  const odds = t.total_odds || t.target_odds || 0;
  const f = Math.max(0.2, budget / 50); // scalare față de 50 lei
  let base: number;
  if (t.kind === 'pyramid' || v.includes('pyramid') || v.includes('piramid')) base = 10;
  else if (v.includes('chain') || v.includes('lanț') || v.includes('lant')) base = 5;
  else if (odds >= 500) base = odds >= 1000 ? 1 : 2;
  else if (odds >= 100) base = 3;
  else if (odds >= 60) base = 2;
  else if (odds >= 20) base = odds >= 30 ? 2 : 3;
  else base = 5;
  const r = Math.max(1, Math.round(base * f));
  return odds >= 100 ? Math.min(5, r) : r;
}

/** Miza sugerată, plafonată la ce a rămas din buget (null = bugetul e consumat). */
export function budgetLei(t: Ticket, budget: number, spent: number): number | null {
  const b = budgetBase(t, budget);
  if (b == null || !budget) return null;
  const left = Math.max(0, budget - spent);
  return left >= 1 ? Math.min(b, Math.floor(left)) : null;
}
