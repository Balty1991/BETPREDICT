import { useState, type ReactNode } from 'react';
import { ArrowDownToLine, RotateCcw, Repeat, Play, PauseCircle } from 'lucide-react';
import { Card } from '@/components/kit';
import { cn } from '@/lib/utils';

export type PyrAction = { kind: string; text: string; today?: string; stake?: number | null; step?: number | null; rule?: string; short?: string; cashout?: number };

const ICON: Record<string, ReactNode> = {
  withdraw: <ArrowDownToLine className="h-6 w-6" />, take_all: <ArrowDownToLine className="h-6 w-6" />, restart: <RotateCcw className="h-6 w-6" />,
  reinvest: <Repeat className="h-6 w-6" />, start: <Play className="h-6 w-6" />, suggest: <ArrowDownToLine className="h-6 w-6" />,
};

/** Instrucțiunea zilei pentru o piramidă: ce faci cu banii + miza de azi + regula curentă. */
/** Alegerea mea la o propunere de încasare (ținută minte pe telefon, pe zi și pas). */
function useChoice(key: string): [string | null, (v: string | null) => void] {
  const [v, setV] = useState<string | null>(() => { try { return localStorage.getItem(key); } catch { return null; } });
  return [v, (x) => { setV(x); try { if (x) localStorage.setItem(key, x); else localStorage.removeItem(key); } catch { /* fără stocare */ } }];
}

function Suggest({ a }: { a: PyrAction }) {
  const [choice, setChoice] = useChoice(`bp.pyr.choice.${a.text.slice(0, 60)}`);
  if (choice) return (
    <p className="mt-2 text-sm font-semibold">
      {choice === 'cash' ? 'Ai ales să încasezi: retrage banii din Superbet și repornește de la treapta 1 cu miza de start.' : 'Ai ales să continui: reinvestești tot pe biletul de azi.'}
      <button type="button" className="ml-2 text-xs font-semibold text-primary" onClick={() => setChoice(null)}>schimbă</button>
    </p>
  );
  return (
    <div className="mt-2 flex flex-wrap gap-2">
      <button type="button" className="btn btn-primary h-9 px-3 text-xs" onClick={() => setChoice('cash')}>Încasez</button>
      <button type="button" className="btn h-9 px-3 text-xs" onClick={() => setChoice('go')}>Continui</button>
    </div>
  );
}

export function ActionCard({ a, compact }: { a?: PyrAction | null; compact?: boolean }) {
  if (!a || a.kind === 'error') return null;
  const strong = a.kind === 'withdraw' || a.kind === 'take_all' || a.kind === 'suggest';
  if (compact) return <span className={cn('font-bold', strong ? 'text-win' : 'text-primary')}>{a.short}</span>;
  return (
    <Card className={cn('flex items-start gap-3 p-4', strong ? 'border-emerald-500/50' : 'border-primary/40')} aria-label="Ce faci azi">
      <span className={cn('grid h-11 w-11 shrink-0 place-items-center rounded-2xl', strong ? 'bg-win text-win' : 'bg-info text-info')}>{ICON[a.kind] ?? <PauseCircle className="h-6 w-6" />}</span>
      <div className="min-w-0">
        <div className="text-[11px] font-bold uppercase tracking-wider text-muted-foreground">Ce faci azi</div>
        <div className={cn('text-lg font-extrabold', strong ? 'text-win' : '')}>{a.short}</div>
        <p className="text-sm">{a.text}</p>
        {a.kind === 'suggest' && <Suggest a={a} />}
        {a.today && <p className="mt-1 text-sm font-semibold">{a.today}</p>}
        {a.rule && <details className="mt-1"><summary className="cursor-pointer text-[11px] font-semibold text-primary">Regula</summary><p className="mt-1 text-[11px] leading-snug text-muted-foreground">{a.rule}</p></details>}
      </div>
    </Card>
  );
}
