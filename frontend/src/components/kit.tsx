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
        <h2 className="flex items-center gap-2">{icon}{title}</h2>
        {subtitle && <p className="text-sm text-muted-foreground">{subtitle}</p>}
      </div>
      {right}
    </div>
  );
}

export function Badge({ tone = 'muted', children, className, title }: { tone?: 'muted' | 'win' | 'loss' | 'warn' | 'primary' | 'outline' | 'info' | 'pending'; children: ReactNode; className?: string; title?: string }) {
  const t = {
    muted: 'bg-muted text-muted-foreground border-transparent',
    win: 'bg-win text-win border-transparent',
    loss: 'bg-loss text-loss border-transparent',
    warn: 'bg-warn text-warn border-transparent',
    primary: 'bg-primary/15 text-primary border-transparent',
    outline: 'bg-transparent text-muted-foreground',
    info: 'bg-info text-info border-transparent',
    pending: 'bg-pending text-pending border-transparent',
  }[tone];
  return <span title={title} className={cn('inline-flex items-center gap-1 whitespace-nowrap rounded-md border px-1.5 py-0.5 text-[11px] font-semibold leading-4', t, className)}>{children}</span>;
}

export function GradeBadge({ grade }: { grade?: string | null }) {
  if (!grade) return null;
  const tone = grade === 'A' ? 'win' : grade === 'B' ? 'info' : grade === 'C' ? 'warn' : 'muted';
  return <Badge tone={tone} title="Grad de încredere (A = cel mai bun)">{grade}</Badge>;
}

export function ResultBadge({ r }: { r?: LegResult | 'pending' }) {
  const tone = r === 'won' || r === 'half_won' ? 'win' : r === 'lost' || r === 'half_lost' ? 'loss' : r === 'void' ? 'warn' : 'pending';
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
    <div className="card p-3 md:p-4">
      <div className="label">{label}</div>
      <div className={cn('mt-1 text-[22px] font-bold leading-tight tabular-nums', tone === 'win' && 'text-win', tone === 'loss' && 'text-loss', tone === 'warn' && 'text-warn')}>{value}</div>
      {sub && <div className="text-xs text-muted-foreground">{sub}</div>}
    </div>
  );
}

export function Skeleton({ className }: { className?: string }) {
  return <div aria-hidden className={cn('skeleton rounded-lg', className)} />;
}

/** Încărcare cu schelet (carduri fantomă) — percepție de viteză mai bună decât un spinner. */
export function Loading({ text = 'Se încarcă datele…', rows = 3 }: { text?: string; rows?: number }) {
  return (
    <div role="status" aria-live="polite" className="space-y-3 py-2">
      <span className="sr-only">{text}</span>
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className="card space-y-3 p-4">
          <div className="flex items-center gap-2"><Skeleton className="h-4 w-4 rounded-full" /><Skeleton className="h-3 w-32" /><Skeleton className="ml-auto h-3 w-10" /></div>
          <div className="flex items-center gap-2"><Skeleton className="h-6 w-6 rounded-full" /><Skeleton className="h-4 w-40" /></div>
          <div className="flex items-center gap-2"><Skeleton className="h-6 w-6 rounded-full" /><Skeleton className="h-4 w-36" /></div>
          <Skeleton className="h-2 w-full" />
        </div>
      ))}
      <div className="flex items-center justify-center gap-2 text-xs text-muted-foreground"><Loader2 className="h-3.5 w-3.5 animate-spin" />{text}</div>
    </div>
  );
}

/** Inel de probabilitate (SVG, fără bibliotecă). */
export function ProbRing({ p, size = 44, stroke = 5, label }: { p: number; size?: number; stroke?: number; label?: string }) {
  const r = (size - stroke) / 2, c = 2 * Math.PI * r, v = Math.max(0, Math.min(1, p));
  const color = v >= 0.75 ? 'hsl(var(--win))' : v >= 0.6 ? 'hsl(var(--primary))' : v >= 0.5 ? 'hsl(var(--warn))' : 'hsl(var(--loss))';
  return (
    <div className="relative inline-flex shrink-0 items-center justify-center" style={{ width: size, height: size }} role="img" aria-label={`${label ?? 'Probabilitate'} ${Math.round(v * 100)}%`}>
      <svg width={size} height={size} className="-rotate-90">
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="hsl(var(--muted))" strokeWidth={stroke} />
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke={color} strokeWidth={stroke} strokeLinecap="round" strokeDasharray={c} strokeDashoffset={c * (1 - v)} className="ring-anim" />
      </svg>
      <span className="absolute text-[11px] font-bold tabular-nums" style={{ fontSize: size < 40 ? 10 : 12 }}>{Math.round(v * 100)}%</span>
    </div>
  );
}

/** Bară împărțită 1 / X / 2 (sau orice trei probabilități). */
export function SplitBar({ parts, className }: { parts: Array<{ label: string; p: number; tone: 'home' | 'draw' | 'away' }>; className?: string }) {
  const tot = parts.reduce((a, x) => a + x.p, 0) || 1;
  const col = { home: 'bg-primary', draw: 'bg-muted-foreground/50', away: 'bg-[hsl(var(--info))]' };
  return (
    <div className={className}>
      <div className="flex h-2 w-full overflow-hidden rounded-full bg-muted">
        {parts.map((x) => <div key={x.label} className={cn('h-full transition-[width] duration-500', col[x.tone])} style={{ width: `${(x.p / tot) * 100}%` }} />)}
      </div>
      <div className="mt-1 flex justify-between text-[11px] tabular-nums text-muted-foreground">
        {parts.map((x) => <span key={x.label}><b className="text-foreground">{x.label}</b> {Math.round((x.p / tot) * 100)}%</span>)}
      </div>
    </div>
  );
}

/** Puncte de formă V/E/Î (cele mai recente la dreapta). */
export function FormDots({ seq, max = 5 }: { seq?: string | null; max?: number }) {
  if (!seq) return null;
  const s = seq.slice(0, max).split('').reverse();
  return (
    <span className="inline-flex gap-0.5" aria-label={`Formă: ${s.join(' ')}`}>
      {s.map((c, i) => <span key={i} title={c === 'W' ? 'Victorie' : c === 'L' ? 'Înfrângere' : 'Egal'} className={cn('h-2 w-2 rounded-full', c === 'W' ? 'bg-[hsl(var(--win))]' : c === 'L' ? 'bg-[hsl(var(--loss))]' : 'bg-[hsl(var(--warn))]')} />)}
    </span>
  );
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

function hue(name: string) { let h = 0; for (let i = 0; i < name.length; i++) h = (h * 31 + name.charCodeAt(i)) % 360; return h; }

export function TeamLogo({ src, name, size = 20 }: { src?: string | null; name: string; size?: number }) {
  if (!src) return <span aria-hidden style={{ width: size, height: size, background: `hsl(${hue(name)} 45% 30%)`, fontSize: Math.max(9, size * 0.42) }} className="inline-flex shrink-0 items-center justify-center rounded-full font-bold text-white">{name.slice(0, 1)}</span>;
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
