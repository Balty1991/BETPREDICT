/** Etichete pe înțelesul tuturor (fără jargon): „Șansă”, „Valoare”, „Încredere”. */
export type Tone = 'win' | 'info' | 'warn' | 'muted' | 'loss';

export function confidence(grade?: string | null): { label: string; short: string; tone: Tone } | null {
  if (!grade) return null;
  if (grade === 'A') return { label: 'Încredere mare', short: 'mare', tone: 'win' };
  if (grade === 'B') return { label: 'Încredere bună', short: 'bună', tone: 'info' };
  if (grade === 'C') return { label: 'Încredere medie', short: 'medie', tone: 'warn' };
  return { label: 'Încredere scăzută', short: 'scăzută', tone: 'muted' };
}

/** Valoarea (EV) cu o zecimală; sub ±0,05% se afișează „corectă” (cota ≈ șansa). */
export function valueInfo(ev?: number | null): { text: string; tone: Tone } | null {
  if (ev == null || Number.isNaN(ev)) return null;
  const v = ev * 100;
  if (Math.abs(v) < 0.05) return { text: 'corectă', tone: 'muted' };
  return { text: `${v > 0 ? '+' : '−'}${Math.abs(v).toFixed(1)}%`, tone: v > 0 ? 'win' : 'loss' };
}

export const HELP = {
  chance: 'Șansa estimată de Robot ca selecția să iasă (probabilitate).',
  value: 'Valoarea: cât câștigi în medie pe termen lung la 100 lei pariați, dacă șansa Robotului e corectă. Pozitiv = cota e mai mare decât merită riscul.',
  confidence: 'Încrederea Robotului în estimare, din calitatea datelor și stabilitatea pieței (mare → scăzută).',
  stake: 'Miza sugerată în unități: 1u = 1% din banca ta. Calculată prudent (¼ Kelly), plafonată.',
  safety: 'Siguranță (0–100) combină șansa calibrată cu încrederea în date. E mare doar când AMBELE sunt mari: o șansă mare cu date slabe primește scor mic. ≥ 70 mare · 55–69 medie · sub 55 scăzută. Filtrul „Siguranță mare” = șansă ≥ 60% și încredere bună/mare.',
  prudent: 'Șansa „prudentă”: estimarea Robotului trasă 50% spre piață, ca să nu fie prea optimistă.',
};

const GRADE_CONF: Record<string, number> = { A: 82, B: 70, C: 60, D: 45 };
/** Scorul „Siguranță” publicat de pipeline; calcul identic ca rezervă (date vechi). */
export function safetyOf(p: { p: number; confidence?: number | null; grade?: string | null; safety?: number | null }): number {
  if (p.safety != null) return p.safety;
  const c = Math.min(1, Math.max(0, (p.confidence ?? GRADE_CONF[p.grade ?? ''] ?? 50) / 100));
  const q = Math.min(1, Math.max(0, p.p));
  return Math.round(100 * (0.7 * Math.min(q, c) + 0.3 * Math.sqrt(q * c)));
}
export function isHighSafety(p: { p: number; grade?: string | null; safety_high?: boolean; odds?: number | null }): boolean {
  if (p.odds == null) return false;
  return p.safety_high ?? (p.p >= 0.6 && (p.grade === 'A' || p.grade === 'B'));
}
export function safetyTone(s: number): Tone { return s >= 70 ? 'win' : s >= 55 ? 'warn' : 'loss'; }
