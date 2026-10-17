import { useStore } from '@/lib/store';

/** Miza simulată a piramidei (bancă de start din Setări) tradusă în lei pe bugetul tău: start 10 lei la 50 lei/săptămână. */
export function YourStake({ bank }: { bank: number | null | undefined }) {
  const budget = useStore((s) => s.settings.weeklyBudget ?? 50);
  const start = useStore((s) => s.settings.pyramid.startBank || 100);
  if (!bank || !budget) return null;
  const mine = Math.max(1, Math.round(bank * (Math.max(1, Math.round(10 * Math.max(0.2, budget / 50))) / start)));
  return <div className="stake-chip mx-auto mt-1">tu: {mine} lei</div>;
}
