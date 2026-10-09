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
  prudent: 'Șansa „prudentă”: estimarea Robotului trasă 50% spre piață, ca să nu fie prea optimistă.',
};
