import { useStore } from '@/lib/store';

/** Miza simulată a piramidei (bancă de start din Setări) tradusă în lei pe bugetul tău: start 10 lei la 50 lei/săptămână. */
export function leiRo(n: number): string {
  const r = Math.round(n * 100) / 100;
  const t = r.toLocaleString('ro-RO', { maximumFractionDigits: 2 });
  if (r === 1) return '1 leu';
  return Number.isInteger(r) && (r % 100 === 0 || r % 100 >= 20) ? `${t} de lei` : `${t} lei`;
}

export function YourStake({ bank, real = false }: { bank: number | null | undefined; real?: boolean }) {
  const budget = useStore((s) => s.settings.weeklyBudget ?? 50);
  const start = useStore((s) => s.settings.pyramid.startBank || 100);
  if (!bank || !budget) return null;
  const mine = real ? bank : Math.max(1, Math.round(bank * (Math.max(1, Math.round(10 * Math.max(0.2, budget / 50))) / start)));
  return <div className="stake-chip mx-auto mt-1">miza ta: {leiRo(mine)}</div>;
}
