import type { Prediction } from './types';
import { isRecommended } from './rules';

/** Singura combinație măsurată pe arhivă. Nu e un pont nou și nu e șansa biletului. */
export const MEASURED_KEY = 'BB_G05_C75';
export const MEASURED_LABEL = 'Peste 0,5 goluri + Peste 7,5 cornere';
export const MEASURED_HIT = 0.746;
export const MEASURED_N = 354;

export type MeasuredRow = {
  m: number;
  k: string;
  p: number;
  o: number;
  pk?: Prediction['sb_pick'];
};

const PLAY_LO = 1.3;
const PLAY_HI = 2.2;

export function isMeasuredText(text: string | null | undefined): boolean {
  const t = (text ?? '').toLowerCase().replace(/,/g, '.');
  if (!/(^|[^0-9])7\.5 cornere/.test(t) || !/(^|[^0-9])0\.5 gol/.test(t)) return false;
  return !/4\.5 cornere|5\.5 cornere|6\.5 cornere|8\.5 cornere|9\.5 cornere/.test(t);
}

export function isMeasuredPick(p: { selection?: string | null; label?: string | null }): boolean {
  return p.selection === MEASURED_KEY || isMeasuredText(p.label) || isMeasuredText(p.selection);
}

/** Etichetă scurtă. „Piață: Piață” și eticheta dublă a bet builder-ului devin o singură propoziție. */
export function shortPickLabel(market: string, selection: string, fallback?: string | null): string | null {
  const raw = `${fallback ?? ''} ${selection ?? ''}`;
  if (market === 'bb' || market === 'ss' || isMeasuredText(raw)) {
    if (isMeasuredText(raw)) return MEASURED_LABEL;
  }
  const text = (fallback || '').trim();
  const parts = text.split(/\s*:\s*/);
  if (parts.length === 2 && parts[0].trim().toLowerCase() === parts[1].trim().toLowerCase()) {
    return isMeasuredText(parts[0]) ? MEASURED_LABEL : parts[0].trim();
  }
  if (market === 'bb' && text) return text;
  return null;
}

/** Ce merită pus în față. Nu schimbă modelul: doar nu promovează cota sub 1,30 și pune combinația măsurată prima. */
export function offerTier(p: Prediction): number {
  const o = p.odds ?? 0;
  if (isMeasuredPick(p) && o >= 1.2 && o <= 2.5) return 5;
  if (isRecommended(p)) return 4;
  const ev = p.ev ?? (o > 1 ? p.p * o - 1 : -1);
  if (o >= PLAY_LO && o <= PLAY_HI && p.market_healthy !== false && ev > -0.08) return 3;
  if (p.is_pick && o >= 1.25) return 2;
  if (o >= 1.25 && o <= 3.5 && ev > -0.12) return 1;
  return 0;
}

export function compareOffers(a: Prediction, b: Prediction): number {
  const d = offerTier(b) - offerTier(a);
  if (d) return d;
  const ma = a.p_market, mb = b.p_market;
  if (ma != null || mb != null) {
    const gap = (mb ?? -1) - (ma ?? -1);
    if (Math.abs(gap) > 1e-9) return gap;
  }
  return (b.p ?? 0) - (a.p ?? 0);
}

export function measuredPrediction(row: MeasuredRow, label?: string): Prediction {
  return {
    id: `ss-${row.m}-${row.k}`,
    match_id: row.m,
    market: 'ss',
    line: null,
    selection: row.k,
    label: label && isMeasuredText(label) ? label : MEASURED_LABEL,
    p: row.p,
    odds: row.o,
    odds_source: 'superbet',
    bookmaker: 'Superbet',
    ev: null,
    grade: null,
    market_healthy: true,
    reasons: [`Combinația măsurată: ${MEASURED_N} decontate, cam ${Math.round(MEASURED_HIT * 100)}% pe selecție. Nu e șansa biletului.`],
    sb_pick: row.pk ?? null,
  };
}
