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

/** Ce costă din bugetul săptămânii un bilet marcat „Îl joc” (lei noi), cu motivul.
 *  25.10: suma ajunsese la 113 lei din 50 pentru că (a) treptele de piramidă ≥ 2 („Reinvestește”) se numărau ca bani noi
 *  (până la 5 lei fiecare), deși sunt câștigul rulat; (b) un bilet salvat fără miza în lei (fără sugestie de buget) se număra cu
 *  miza implicită din setări (10 lei) sau cu unitățile interne ale Robotului. Acum: miza în lei pusă de tine; altfel miza de bază
 *  a regulii (Pont 8, piramidă 5, 100+ 1–2 lei…); treptele reinvestite = 0. */
export function budgetCost(t: Ticket, budget?: number): { lei: number; why: string } {
  if (!t.followed) return { lei: 0, why: 'nemarcat' };
  const x = t as Ticket & { pyr_action?: string; pyr_step?: number; stake_lei?: number; paper?: boolean; experimental?: boolean };
  // bilete pe hârtie (piramida 100+, experimentale): nu sunt bani jucați
  if (t.created_by !== 'user' && (x.paper === true || x.experimental === true)) return { lei: 0, why: 'pe hârtie (nu e bani reali)' };
  const act = `${x.pyr_action ?? ''}`.toLowerCase();
  if ((t.kind === 'pyramid' || x.pyr_step != null) && (/reinvest|încas|incas/.test(act) || (x.pyr_step ?? 1) > 1))
    return { lei: 0, why: 'treaptă reinvestită (câștig rulat)' };
  let v: number; let why: string;
  if (x.stake_lei != null) { v = Number(x.stake_lei) || 0; why = 'miza ta'; }
  else { v = Number(t.stake) || 0; why = t.created_by === 'user' ? 'bilet manual' : 'miza pusă la „Îl joc”'; }
  // nu inventăm o miză sugerată de server: fără miză salvată, biletul nu consumă bugetul
  // piramidă: doar miza de start e bani noi
  if (t.kind === 'pyramid') { const cap = budget ? Math.max(1, Math.round(5 * Math.max(0.2, budget / 50))) : 5; if (v > cap) { v = cap; why += ' (plafon start piramidă)'; } }
  if (budget && v > budget) return { lei: 0, why: 'miză peste buget = unitate greșită, ignorată' };
  return { lei: Math.round(v * 100) / 100, why };
}

/** Biletele „Îl joc” din săptămâna curentă (luni–duminică, ora României) și cât cântărește fiecare. */
export function weekEntries(mine: Ticket[], now = new Date(), budget?: number): { t: Ticket; lei: number; why: string }[] {
  const ws = weekStart(now);
  return mine.filter((t) => t.followed && (t.date ?? t.created_at ?? '').slice(0, 10) >= ws).map((t) => ({ t, ...budgetCost(t, budget) }));
}

/** Cât ai jucat săptămâna asta: doar biletele marcate „Îl joc” (followed), nu mizele sugerate și nu câștigul reinvestit. */
export function weekSpent(mine: Ticket[], now = new Date(), budget?: number): number {
  return Math.round(weekEntries(mine, now, budget).reduce((a, e) => a + e.lei, 0) * 100) / 100;
}

/** Miza de bază din bugetul săptămânal (la 50 lei): Pont 8, cotă mărită EV ≥ 0 4, piramidă 5, lanț 3, 20–99 2, 100+ 1–2. */
export function budgetBase(t: Ticket, budget: number): number | null {
  if (t.status && t.status !== 'pending') return null;
  const v = `${t.kind ?? ''} ${t.variant ?? ''} ${(t as { tier?: string }).tier ?? ''} ${t.variant_label ?? ''}`.toLowerCase();
  const odds = t.total_odds || t.target_odds || 0;
  const f = Math.max(0.2, budget / 50); // scalare față de 50 lei
  // Calea 100+ (25.10): miza fixă a treptei (T0/T1 2 lei, T2/T3 1 leu), scalată cu bugetul
  if (t.kind === 'acca_calea') return Math.max(1, Math.round((Number(t.stake_units ?? t.stake) || 0.1) * 10 * f));
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
