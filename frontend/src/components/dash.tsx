import { useEffect, useLayoutEffect, useRef, useState, type ReactNode } from 'react';
import { cn } from '@/lib/utils';

/** Piese pentru panoul de pe Acasă: SVG simplu, animat din CSS, fără bibliotecă de grafice. */

const reduced = () => typeof window !== 'undefined' && window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;

/** Numărul urcă de la 0 la valoare. Scrie direct în DOM, fără re-render la fiecare cadru. */
export function CountUp({ value, digits = 0, prefix = '', suffix = '', signed = false, className }: { value: number | null | undefined; digits?: number; prefix?: string; suffix?: string; signed?: boolean; className?: string }) {
  const el = useRef<HTMLSpanElement>(null);
  const from = useRef(0);
  const fmt = (v: number) => `${signed && v > 0 ? '+' : ''}${prefix}${v.toLocaleString('ro-RO', { minimumFractionDigits: digits, maximumFractionDigits: digits })}${suffix}`;
  // fără copii React în <span>: textul e scris doar de aici, ca React să nu-l suprascrie
  useLayoutEffect(() => {
    const node = el.current;
    if (!node || value == null || !Number.isFinite(value)) return;
    const start = from.current, end = value;
    from.current = end;
    node.textContent = fmt(start);
    if (reduced() || start === end) { node.textContent = fmt(end); return; }
    const t0 = performance.now(), dur = 1100;
    let raf = 0;
    const step = (t: number) => {
      const k = Math.min(1, (t - t0) / dur);
      const e = 1 - Math.pow(1 - k, 4);
      node.textContent = fmt(start + (end - start) * e);
      if (k < 1) raf = requestAnimationFrame(step);
    };
    raf = requestAnimationFrame(step);
    return () => cancelAnimationFrame(raf);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- fmt depinde doar de props deja în listă
  }, [value, digits, prefix, suffix, signed]);
  if (value == null || !Number.isFinite(value)) return <span className={className}>—</span>;
  return <span ref={el} className={cn('num tabular-nums', className)} />;
}

/** Devine true la primul cadru după montare: pornește tranzițiile CSS de la zero. */
function useArmed() {
  const [on, setOn] = useState(false);
  useEffect(() => { const id = requestAnimationFrame(() => setOn(true)); return () => cancelAnimationFrame(id); }, []);
  return on;
}

/** Inel cu gradient care se umple. */
export function Ring({ value, size = 120, stroke = 10, tone = 'primary', children, label }: { value: number | null; size?: number; stroke?: number; tone?: 'primary' | 'win' | 'loss' | 'warn' | 'info'; children?: ReactNode; label: string }) {
  const on = useArmed();
  const r = (size - stroke) / 2, c = 2 * Math.PI * r;
  const v = Math.max(0, Math.min(1, value ?? 0));
  const id = `ring-${tone}`;
  return (
    <div className="dash-ring relative inline-grid shrink-0 place-items-center" style={{ width: size, height: size }} role="img" aria-label={`${label}: ${value == null ? 'fără date' : `${Math.round(v * 100)}%`}`}>
      <svg width={size} height={size} className="-rotate-90 overflow-visible" aria-hidden>
        <defs>
          <linearGradient id={id} x1="0" y1="0" x2="1" y2="1">
            <stop offset="0" stopColor={`hsl(var(--${tone === 'primary' ? 'primary' : tone}))`} />
            <stop offset="1" stopColor={tone === 'primary' ? 'hsl(var(--glow-3))' : `hsl(var(--${tone}) / .55)`} />
          </linearGradient>
        </defs>
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="hsl(var(--muted))" strokeWidth={stroke} opacity={0.7} />
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="hsl(var(--foreground) / .08)" strokeWidth={1} strokeDasharray="2 6" />
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke={`url(#${id})`} strokeWidth={stroke} strokeLinecap="round"
          strokeDasharray={c} strokeDashoffset={on ? c * (1 - v) : c} className="dash-ring-arc" style={{ filter: `drop-shadow(0 0 6px hsl(var(--${tone === 'primary' ? 'primary' : tone}) / .55))` }} />
      </svg>
      <div className="absolute inset-0 grid place-items-center text-center">{children}</div>
    </div>
  );
}

const DONUT = ['hsl(var(--primary))', 'hsl(var(--glow-2))', 'hsl(var(--glow-3))', 'hsl(var(--warn))', 'hsl(var(--info))', 'hsl(var(--loss))'];

/** Inel pe segmente (piețe). */
export function Donut({ parts, size = 132, stroke = 16, children }: { parts: Array<{ label: string; n: number }>; size?: number; stroke?: number; children?: ReactNode }) {
  const on = useArmed();
  const r = (size - stroke) / 2, c = 2 * Math.PI * r;
  const total = parts.reduce((a, p) => a + p.n, 0) || 1;
  const gap = parts.length > 1 ? 3 : 0;
  const starts = parts.map((_, i) => parts.slice(0, i).reduce((a, p) => a + (p.n / total) * c, 0));
  return (
    <div className="relative inline-grid shrink-0 place-items-center" style={{ width: size, height: size }}>
      <svg width={size} height={size} className="-rotate-90" aria-hidden>
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="hsl(var(--muted))" strokeWidth={stroke} opacity={0.5} />
        {parts.map((p, i) => {
          const len = Math.max(0, (p.n / total) * c - gap);
          const off = -starts[i];
          return <circle key={p.label} cx={size / 2} cy={size / 2} r={r} fill="none" stroke={DONUT[i % DONUT.length]} strokeWidth={stroke}
            strokeDasharray={`${on ? len : 0} ${c}`} strokeDashoffset={off} className="dash-donut-seg" style={{ transitionDelay: `${i * 90}ms` }} />;
        })}
      </svg>
      <div className="absolute inset-0 grid place-items-center text-center">{children}</div>
    </div>
  );
}
export const donutColor = (i: number) => DONUT[i % DONUT.length];

/** Coloane verticale care cresc din bază. */
export function Bars({ data, height = 96, highlight, className, label }: { data: Array<{ k: string; n: number; tone?: string }>; height?: number; highlight?: (k: string) => boolean; className?: string; label: string }) {
  const max = Math.max(1, ...data.map((d) => d.n));
  return (
    <div className={cn('flex items-end gap-1.5', className)} style={{ height }} role="img" aria-label={`${label}: ${data.map((d) => `${d.k} ${d.n}`).join(', ')}`}>
      {data.map((d, i) => (
        <div key={d.k} className="flex h-full min-w-0 flex-1 flex-col items-center justify-end gap-1">
          <span className="num text-[10px] font-bold text-muted-foreground">{d.n || ''}</span>
          <div className={cn('dash-bar w-full rounded-t-md', highlight?.(d.k) && 'dash-bar-hot')} style={{ height: `${Math.max(d.n ? 6 : 2, (d.n / max) * (height - 30))}px`, animationDelay: `${i * 55}ms`, background: d.tone }} />
          <span className="num max-w-full truncate text-[10px] text-muted-foreground">{d.k}</span>
        </div>
      ))}
    </div>
  );
}

/** Linie care se desenează (ex. rata de câștig pe zile). */
export function Spark({ values, height = 56, className, label, domain }: { values: Array<number | null>; height?: number; className?: string; label: string; domain?: [number, number] }) {
  const pts = values.map((v, i) => ({ i, v })).filter((p): p is { i: number; v: number } => p.v != null);
  const w = 100;
  if (pts.length < 2) return <div className={cn('grid place-items-center text-xs text-muted-foreground', className)} style={{ height }}>Prea puține zile pentru grafic</div>;
  const lo = domain?.[0] ?? Math.min(...pts.map((p) => p.v)), hi = domain?.[1] ?? Math.max(...pts.map((p) => p.v));
  const span = hi - lo || 1;
  const x = (i: number) => (values.length === 1 ? 50 : (i / (values.length - 1)) * w);
  const y = (v: number) => 4 + (1 - (v - lo) / span) * (height - 8);
  const d = pts.map((p, k) => `${k ? 'L' : 'M'}${x(p.i).toFixed(2)},${y(p.v).toFixed(2)}`).join(' ');
  const area = `${d} L${x(pts[pts.length - 1].i)},${height} L${x(pts[0].i)},${height} Z`;
  const last = pts[pts.length - 1];
  return (
    <div className={cn('relative', className)} style={{ height }} role="img" aria-label={label}>
      <svg viewBox={`0 0 ${w} ${height}`} preserveAspectRatio="none" className="dash-spark h-full w-full overflow-visible" aria-hidden>
      <defs>
        <linearGradient id="spark-fill" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stopColor="hsl(var(--primary))" stopOpacity=".35" /><stop offset="1" stopColor="hsl(var(--primary))" stopOpacity="0" /></linearGradient>
        <linearGradient id="spark-line" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stopColor="hsl(var(--glow-2))" /><stop offset="1" stopColor="hsl(var(--primary))" /></linearGradient>
      </defs>
      <path d={area} fill="url(#spark-fill)" className="dash-spark-area" />
      <path d={d} fill="none" stroke="url(#spark-line)" strokeWidth={2.2} vectorEffect="non-scaling-stroke" strokeLinejoin="round" strokeLinecap="round" className="dash-spark-line" />
      </svg>
      <span aria-hidden className="dash-spark-dot" style={{ left: `${x(last.i)}%`, top: y(last.v) }} />
    </div>
  );
}

/** Panou de sticlă cu titlu mic, în stil HUD. */
export function Panel({ title, icon, right, children, className, glow }: { title?: ReactNode; icon?: ReactNode; right?: ReactNode; children: ReactNode; className?: string; glow?: 'a' | 'b' | 'c' }) {
  return (
    <section className={cn('dash-panel', glow && `dash-glow-${glow}`, className)}>
      {title && (
        <header className="mb-3 flex items-center gap-2">
          {icon && <span className="dash-ico">{icon}</span>}
          <h2 className="dash-title">{title}</h2>
          {right && <div className="ml-auto">{right}</div>}
        </header>
      )}
      {children}
    </section>
  );
}

/** Bară orizontală împărțită: câștigate / pierdute / anulate / în joc. */
export function ResultBar({ won, lost, void: v, pending, className }: { won: number; lost: number; void: number; pending: number; className?: string }) {
  const on = useArmed();
  const t = won + lost + v + pending || 1;
  const seg = (n: number, cls: string, title: string) => n > 0 && <div title={`${title}: ${n}`} className={cn('dash-seg h-full', cls)} style={{ width: on ? `${(n / t) * 100}%` : '0%' }} />;
  return (
    <div className={cn('flex h-2.5 w-full overflow-hidden rounded-full bg-muted', className)} role="img" aria-label={`${won} câștigate, ${lost} pierdute, ${v} anulate, ${pending} în joc`}>
      {seg(won, 'bg-[hsl(var(--win))]', 'câștigate')}
      {seg(lost, 'bg-[hsl(var(--loss))]', 'pierdute')}
      {seg(v, 'bg-[hsl(var(--pending))]', 'anulate')}
      {seg(pending, 'dash-seg-pending', 'în joc')}
    </div>
  );
}

/** Numărătoare inversă până la ora dată (se actualizează la secundă). */
export function Countdown({ iso, className }: { iso: string; className?: string }) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => { const id = window.setInterval(() => setNow(Date.now()), 1000); return () => window.clearInterval(id); }, []);
  const ms = Math.max(0, Date.parse(iso) - now);
  const h = Math.floor(ms / 3_600_000), m = Math.floor((ms % 3_600_000) / 60_000), s = Math.floor((ms % 60_000) / 1000);
  const pad = (n: number) => String(n).padStart(2, '0');
  return <span className={cn('num tabular-nums', className)} aria-label={`Începe în ${h} ore și ${m} minute`}>{h > 0 ? `${pad(h)}:` : ''}{pad(m)}:{pad(s)}</span>;
}

/** Ceas live (ora României). */
export function Clock({ className }: { className?: string }) {
  const [now, setNow] = useState(() => new Date());
  useEffect(() => { const id = window.setInterval(() => setNow(new Date()), 1000); return () => window.clearInterval(id); }, []);
  const t = new Intl.DateTimeFormat('ro-RO', { timeZone: 'Europe/Bucharest', hour: '2-digit', minute: '2-digit', second: '2-digit' }).format(now);
  return <time className={cn('num tabular-nums', className)} dateTime={now.toISOString()}>{t}</time>;
}
