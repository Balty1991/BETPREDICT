import type { Ticket } from './types';

/** Un meci intră o singură dată. Aceeași predicție pe două bilete ar pierde de două ori dintr-un singur rezultat. */
const PER_DAY = 10;

function candidate(t: Ticket): boolean {
  if (t.kind === 'acca_pont' || t.kind === 'acca_soft' || t.kind === 'pyramid' || t.kind === 'acca_safe') return false;
  if (t.lottery || t.safe) return false;
  const v = (t.variant ?? '').toLowerCase();
  if (v === 'super' || v.includes('loter')) return false;
  if (t.kind === 'acca_stil' || v === 'stil_supersocial') return true;
  if (t.kind === 'acca_value' || t.kind === 'acca_double') return !t.informational && (t.ev ?? -9) > 0;
  return false;
}

/** Până la 10 bilete pe zi, cele cu șansa cea mai mare, fără meci repetat. */
export function pickBoard(tickets: Ticket[]): Ticket[] {
  const byDay = new Map<string, Ticket[]>();
  for (const t of tickets) {
    if (!candidate(t) || !t.legs?.length) continue;
    const day = t.date ?? t.created_at?.slice(0, 10) ?? '';
    const list = byDay.get(day) ?? [];
    list.push(t);
    byDay.set(day, list);
  }
  const out: Ticket[] = [];
  for (const day of [...byDay.keys()].sort()) {
    const pool = byDay.get(day)!.sort((a, b) => (b.p_ticket ?? 0) - (a.p_ticket ?? 0) || (b.ev ?? -9) - (a.ev ?? -9));
    const used = new Set<number>();
    let n = 0;
    for (const t of pool) {
      if (n >= PER_DAY) break;
      const matches = [...new Set(t.legs.map((l) => l.match_id))];
      if (matches.some((id) => used.has(id))) continue;
      out.push(t);
      matches.forEach((id) => used.add(id));
      n += 1;
    }
  }
  return out;
}
