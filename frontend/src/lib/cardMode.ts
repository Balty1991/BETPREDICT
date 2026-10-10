import { useSyncExternalStore } from 'react';

export type CardMode = 'compact' | 'detailed';
const KEY = 'bp.card.mode';
const subs = new Set<() => void>();
const read = (): CardMode => (localStorage.getItem(KEY) === 'compact' ? 'compact' : 'detailed');
export function setCardMode(m: CardMode) { localStorage.setItem(KEY, m); subs.forEach((f) => f()); }
/** Mod card (compact / detaliat), salvat pe dispozitiv. */
export function useCardMode(): CardMode {
  return useSyncExternalStore((f) => { subs.add(f); return () => subs.delete(f); }, read, () => 'detailed');
}
