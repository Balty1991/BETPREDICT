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
