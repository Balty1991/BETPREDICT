import { Link } from 'react-router';
import { useStore } from '@/lib/store';
import { weekSpent } from '@/lib/stake';

/** Bugetul săptămânii: o linie subțire. */
export function BudgetBar() {
  const budget = useStore((s) => s.settings.weeklyBudget ?? 50);
  const spent = useStore((s) => weekSpent(s.myTickets, new Date(), s.settings.weeklyBudget ?? 50));
  if (!budget) return null;
  const left = Math.max(0, budget - spent);
  return (
    <Link to="/setari" className="block px-1" aria-label={`Buget săptămână: ${left} lei rămași din ${budget}`}>
      <div className="flex items-center justify-between text-[11px] text-muted-foreground"><span>Buget săptămână</span><span className="num font-bold text-foreground">{left.toLocaleString('ro-RO')} / {budget} lei</span></div>
      <div className="mt-1 h-1 overflow-hidden rounded-full bg-muted"><div className={left < 1 ? 'h-full bg-destructive' : 'h-full bg-primary'} style={{ width: `${Math.min(100, (left / budget) * 100)}%` }} /></div>
    </Link>
  );
}
