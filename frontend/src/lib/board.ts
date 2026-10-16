import type { Ticket } from './types';

/** Un bilet poate repeta până la 3 meciuri deja alese. La al patrulea nu mai intră. */
const PER_DAY = 10;
/** Biletele 1–4 pe echipă (până la 3 pe zi, fiecare cu alte meciuri) intră mereu, peste limita de 10. */
const always = (t: Ticket) => (t.variant_label ?? t.bucket ?? '').includes('1–4 & R1');
const MAX_REPEAT = 3;
const BEST = 'Alegerea robotului';

/** Sub cota 20 nu are rost un bilet la o bancă mică (cotele mici se joacă doar în piramide). */
const MIN_ODDS = 20;
const LOW_ODDS = 50;
/** Regulile de cotă (minim 20, un singur bilet sub 50) se aplică de la această zi; istoricul rămâne cum a fost afișat. */
const RULES_FROM = '2026-10-16';

function candidate(t: Ticket, day: string): boolean {
  if (day >= RULES_FROM && (t.total_odds ?? 0) < MIN_ODDS) return false;
  if (t.kind === 'acca_pont' || t.kind === 'acca_soft' || t.kind === 'pyramid' || t.kind === 'acca_safe') return false;
  if (t.lottery || t.safe) return false;
  const v = (t.variant ?? '').toLowerCase();
  if (v === 'super' || v.includes('loter')) return false;
  if (t.kind === 'acca_stil' || v === 'stil_supersocial') return true;
  if (t.kind === 'acca_boost') return !t.informational && (t.ev ?? -9) > 0;
  if (t.kind === 'acca_value' || t.kind === 'acca_double') return !t.informational && (t.ev ?? -9) > 0;
  return false;
}

/** Biletul mixt „Alegerea robotului” (cele mai bune selecții din toate piețele). */
export function isBest(t: Ticket): boolean {
  return (t.variant_label ?? '').includes(BEST) || (t.bucket ?? '').startsWith(BEST);
}

/** Până la 10 bilete pe zi. Se sare peste biletul care repetă mai mult de 3 meciuri. */
export function pickBoard(tickets: Ticket[]): Ticket[] {
  const byDay = new Map<string, Ticket[]>();
  for (const t of tickets) {
    const day = t.date ?? t.created_at?.slice(0, 10) ?? '';
    if (!candidate(t, day) || !t.legs?.length) continue;
    const list = byDay.get(day) ?? [];
    list.push(t);
    byDay.set(day, list);
  }
  const out: Ticket[] = [];
  for (const day of [...byDay.keys()].sort()) {
    // „Alegerea robotului” (cele mai bune selecții din toate piețele) intră mereu prima
    const pool = byDay.get(day)!.sort((a, b) => Number(isBest(b)) - Number(isBest(a)) || (b.p_ticket ?? 0) - (a.p_ticket ?? 0) || (b.ev ?? -9) - (a.ev ?? -9));
    const used = new Set<number>();
    let n = 0;
    let low = 0; // bilete sub cota 50: unul singur pe zi (primul e „Alegerea robotului · cotă 20–40”, dacă există)
    for (const t of pool) {
      if (n >= PER_DAY && t.kind !== 'acca_boost' && !always(t)) continue;
      const matches = [...new Set(t.legs.map((l) => l.match_id))];
      const repeat = matches.filter((id) => used.has(id)).length;
      if (repeat > MAX_REPEAT && !isBest(t) && !always(t)) continue;
      if (day >= RULES_FROM && (t.total_odds ?? 0) < LOW_ODDS) {
        if (low >= 1) continue;
        low += 1;
      } // cele două „Alegerea robotului” iau firesc aceleași selecții bune
      out.push(t);
      matches.forEach((id) => used.add(id));
      if (t.kind !== 'acca_boost' && !always(t)) n += 1; // cotele mărite (simple / duble) nu iau locul celorlalte bilete
    }
  }
  return out;
}

/** Bilet deja pierdut (sau cu un meci pierdut, dacă nu e sistem). */
export function isLostTicket(t: Ticket): boolean {
  if (t.status === 'lost') return true;
  if (t.status === 'won' || t.status === 'void' || t.systems?.length) return false;
  return t.legs.some((l) => l.result === 'lost');
}
