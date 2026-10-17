import { Link } from 'react-router';
import { useStore } from '@/lib/store';
import { weekSpent } from '@/lib/stake';

/** Bugetul săptămânii (luni–duminică): cât a rămas din ce ți-ai propus. */
export function BudgetBar() {
  const budget = useStore((s) => s.settings.weeklyBudget ?? 50);
  const spent = useStore((s) => weekSpent(s.myTickets));
  if (!budget) return null;
  const left = Math.max(0, budget - spent);
  const pct = Math.min(100, (spent / budget) * 100);
  return (
    <Link to="/setari" className="press mt-3 block rounded-xl border bg-card/60 p-3 text-sm">
      <div className="flex items-center justify-between"><span className="font-semibold">Buget săptămână</span>
        <span className={left < 1 ? 'font-bold text-destructive' : 'font-bold text-primary'}>{left.toLocaleString('ro-RO')} lei rămași din {budget}</span></div>
      <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-muted"><div className={left < 1 ? 'h-full bg-destructive' : 'h-full bg-primary'} style={{ width: `${pct}%` }} /></div>
      {left < 1 && <div className="mt-1 text-xs text-muted-foreground">Bugetul e consumat — Robotul nu mai sugerează mize până luni.</div>}
    </Link>
  );
}
