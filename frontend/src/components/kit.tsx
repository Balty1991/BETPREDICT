import type { ReactNode } from 'react';
import { cn } from '@/lib/utils';
import { Loader2 } from 'lucide-react';
import type { LegResult } from '@/lib/types';
import { resultLabel } from '@/lib/markets';

export function Card({ className, children, ...rest }: { className?: string; children: ReactNode } & React.HTMLAttributes<HTMLDivElement>) {
  return <div className={cn('card', className)} {...rest}>{children}</div>;
}

export function SectionTitle({ icon, title, subtitle, right }: { icon?: ReactNode; title: string; subtitle?: ReactNode; right?: ReactNode }) {
  return (
    <div className="mb-3 flex items-end justify-between gap-3">
      <div>
        <h2 className="flex items-center gap-2 text-lg font-semibold">{icon}{title}</h2>
        {subtitle && <p className="text-sm text-muted-foreground">{subtitle}</p>}
      </div>
      {right}
    </div>
  );
}

export function Badge({ tone = 'muted', children, className, title }: { tone?: 'muted' | 'win' | 'loss' | 'warn' | 'primary' | 'outline'; children: ReactNode; className?: string; title?: string }) {
  const t = {
    muted: 'bg-muted text-muted-foreground border-transparent',
    win: 'bg-win text-win border-transparent',
    loss: 'bg-loss text-loss border-transparent',
    warn: 'bg-warn text-warn border-transparent',
    primary: 'bg-primary/15 text-primary border-transparent',
    outline: 'bg-transparent',
  }[tone];
  return <span title={title} className={cn('inline-flex items-center gap-1 whitespace-nowrap rounded-md border px-1.5 py-0.5 text-[11px] font-semibold', t, className)}>{children}</span>;
}

export function GradeBadge({ grade }: { grade?: string | null }) {
  if (!grade) return null;
  const tone = grade === 'A' ? 'win' : grade === 'B' ? 'primary' : grade === 'C' ? 'warn' : 'muted';
  return <Badge tone={tone} title="Grad de încredere (A = cel mai bun)">{grade}</Badge>;
}

export function ResultBadge({ r }: { r?: LegResult | 'pending' }) {
  const tone = r === 'won' || r === 'half_won' ? 'win' : r === 'lost' || r === 'half_lost' ? 'loss' : r === 'void' ? 'warn' : 'muted';
  return <Badge tone={tone}>{resultLabel(r)}</Badge>;
}

export function Segmented<T extends string | number>({ value, onChange, options, className, size = 'md' }: { value: T; onChange: (v: T) => void; options: Array<{ value: T; label: ReactNode }>; className?: string; size?: 'sm' | 'md' }) {
  return (
    <div className={cn('inline-flex max-w-full overflow-x-auto rounded-lg border bg-muted/50 p-0.5 scrollbar-none', className)}>
      {options.map((o) => (
        <button key={String(o.value)} type="button" onClick={() => onChange(o.value)}
          className={cn('whitespace-nowrap rounded-md font-medium transition-colors', size === 'sm' ? 'px-2.5 py-2 text-xs md:px-2 md:py-1' : 'px-3 py-2.5 text-sm md:py-1.5',
            value === o.value ? 'bg-card text-foreground shadow-sm' : 'text-muted-foreground hover:text-foreground')}>
          {o.label}
        </button>
      ))}
    </div>
  );
}

export function Stat({ label, value, sub, tone }: { label: string; value: ReactNode; sub?: ReactNode; tone?: 'win' | 'loss' | 'warn' }) {
  return (
    <div className="card p-3">
      <div className="text-xs text-muted-foreground">{label}</div>
      <div className={cn('mt-0.5 text-xl font-bold', tone === 'win' && 'text-win', tone === 'loss' && 'text-loss', tone === 'warn' && 'text-warn')}>{value}</div>
      {sub && <div className="text-xs text-muted-foreground">{sub}</div>}
    </div>
  );
}

export function Loading({ text = 'Se încarcă datele…' }: { text?: string }) {
  return <div className="flex items-center justify-center gap-2 py-16 text-sm text-muted-foreground"><Loader2 className="h-4 w-4 animate-spin" />{text}</div>;
}

export function Empty({ title, children, icon }: { title: string; children?: ReactNode; icon?: ReactNode }) {
  return (
    <div className="card flex flex-col items-center gap-2 px-6 py-10 text-center">
      {icon && <div className="text-muted-foreground">{icon}</div>}
      <div className="font-semibold">{title}</div>
      {children && <div className="max-w-md text-sm text-muted-foreground">{children}</div>}
    </div>
  );
}

export function TeamLogo({ src, name, size = 20 }: { src?: string | null; name: string; size?: number }) {
  if (!src) return <span style={{ width: size, height: size }} className="inline-flex shrink-0 items-center justify-center rounded-full bg-muted text-[10px] font-bold">{name.slice(0, 1)}</span>;
  return <img src={src} alt="" loading="lazy" width={size} height={size} style={{ width: size, height: size }} className="shrink-0 object-contain"
    onError={(e) => { (e.currentTarget as HTMLImageElement).style.visibility = 'hidden'; }} />;
}

export function ProbBar({ p, className }: { p: number; className?: string }) {
  const w = Math.max(0, Math.min(100, p * 100));
  const color = p >= 0.75 ? 'bg-emerald-500' : p >= 0.6 ? 'bg-lime-500' : p >= 0.5 ? 'bg-amber-500' : 'bg-rose-500';
  return <div className={cn('h-1.5 w-full overflow-hidden rounded-full bg-muted', className)}><div className={cn('h-full rounded-full', color)} style={{ width: `${w}%` }} /></div>;
}

export function Notice({ tone = 'info', children }: { tone?: 'info' | 'warn'; children: ReactNode }) {
  return <div className={cn('rounded-lg border px-3 py-2 text-xs', tone === 'warn' ? 'border-amber-500/30 bg-warn text-warn' : 'bg-muted/50 text-muted-foreground')}>{children}</div>;
}

/** Panou de jos (mobil). Se închide la tap pe fundal sau Escape. */
export function BottomSheet({ open, onClose, title, children, footer }: { open: boolean; onClose: () => void; title: string; children: ReactNode; footer?: ReactNode }) {
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-end bg-black/50 md:hidden" onClick={onClose} onKeyDown={(e) => e.key === 'Escape' && onClose()} role="dialog" aria-modal="true" aria-label={title}>
      <div className="sheet-enter pb-safe flex max-h-[85vh] w-full flex-col rounded-t-2xl border-t bg-card" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between border-b px-4 py-2">
          <span className="font-semibold">{title}</span>
          <button className="btn btn-ghost h-10 px-3" onClick={onClose}>Închide</button>
        </div>
        <div className="flex-1 overflow-y-auto px-4 py-3">{children}</div>
        {footer && <div className="border-t px-4 py-3">{footer}</div>}
      </div>
    </div>
  );
}
