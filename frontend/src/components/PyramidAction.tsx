import type { ReactNode } from 'react';
import { ArrowDownToLine, RotateCcw, Repeat, Play, PauseCircle } from 'lucide-react';
import { Card } from '@/components/kit';
import { cn } from '@/lib/utils';

export type PyrAction = { kind: string; text: string; today?: string; stake?: number | null; step?: number | null; rule?: string; short?: string };

const ICON: Record<string, ReactNode> = {
  withdraw: <ArrowDownToLine className="h-6 w-6" />, take_all: <ArrowDownToLine className="h-6 w-6" />, restart: <RotateCcw className="h-6 w-6" />,
  reinvest: <Repeat className="h-6 w-6" />, start: <Play className="h-6 w-6" />,
};

/** Instrucțiunea zilei pentru o piramidă: ce faci cu banii + miza de azi + regula curentă. */
export function ActionCard({ a, compact }: { a?: PyrAction | null; compact?: boolean }) {
  if (!a || a.kind === 'error') return null;
  const strong = a.kind === 'withdraw' || a.kind === 'take_all';
  if (compact) return <span className={cn('font-bold', strong ? 'text-win' : 'text-primary')}>{a.short}</span>;
  return (
    <Card className={cn('flex items-start gap-3 p-4', strong ? 'border-emerald-500/50' : 'border-primary/40')} aria-label="Ce faci azi">
      <span className={cn('grid h-11 w-11 shrink-0 place-items-center rounded-2xl', strong ? 'bg-win text-win' : 'bg-info text-info')}>{ICON[a.kind] ?? <PauseCircle className="h-6 w-6" />}</span>
      <div className="min-w-0">
        <div className="text-[11px] font-bold uppercase tracking-wider text-muted-foreground">Ce faci azi</div>
        <div className={cn('text-lg font-extrabold', strong ? 'text-win' : '')}>{a.short}</div>
        <p className="text-sm">{a.text}</p>
        {a.today && <p className="mt-1 text-sm font-semibold">{a.today}</p>}
        {a.rule && <p className="mt-1 text-[11px] text-muted-foreground">{a.rule} Robotul reevaluează regula pe rezultatele reale (doar cu dovezi suficiente).</p>}
      </div>
    </Card>
  );
}
