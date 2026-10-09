import type { Prediction } from './types';

/** Statisticile numără doar predicțiile Robotului 3.0 publicate de la această dată (ora României). */
export const STATS_SINCE = '2026-10-09';
export const ROBOT_MODEL_VERSIONS = ['robot-v1']; // versiunea modelului din pipeline-ul v3

/** Praguri „recomandat” (identice cu betpredict/robot/__init__.py). */
export const REC = { minP: 0.6, minOdds: 1.15, maxOdds: 2.2, minEv: 0, grades: ['A', 'B'] } as const;

export function isRecommended(p: Prediction): boolean {
  if (typeof p.recommended === 'boolean') return p.recommended;
  const ev = p.ev ?? (p.odds != null ? p.p * p.odds - 1 : null);
  return p.odds != null && ev != null && p.market_healthy !== false && !!p.grade && (REC.grades as readonly string[]).includes(p.grade)
    && p.p >= REC.minP && p.odds >= REC.minOdds && p.odds <= REC.maxOdds && ev > REC.minEv;
}

export function isV3Prediction(p: Prediction, date: string): boolean {
  if (date < STATS_SINCE) return false;
  if (p.robot_version) return p.robot_version === 'v3';
  return !!p.model_version && ROBOT_MODEL_VERSIONS.includes(p.model_version);
}
