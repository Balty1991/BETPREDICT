import { useMemo, useState } from 'react';
import { ChevronDown, Target, Trophy } from 'lucide-react';
import type { Ticket } from '@/lib/types';
import { cn } from '@/lib/utils';

type Period = '1' | '7' | '30' | 'all';
const PERIODS: Array<[Period, string]> = [['1', 'Azi'], ['7', '7 zile'], ['30', '30 zile'], ['all', 'Tot']];

type Stat = {
  key: string; label: string; n: number; won: number; lost: number; active: number; profit: number; roi: number | null;
  legsWon: number; legsSettled: number; nearMiss: number; best: number | null; last: Array<'w' | 'l'>;
};

const dayOf = (t: Ticket) => t.date ?? t.created_at?.slice(0, 10) ?? '';
const pay = (t: Ticket) => t.total_odds_published ?? t.total_odds;
const isDone = (t: Ticket) => t.status === 'won' || t.status === 'lost';

function stat(key: string, label: string, ts: Ticket[]): Stat {
  const done = ts.filter(isDone).sort((a, b) => dayOf(a).localeCompare(dayOf(b)));
  const won = done.filter((t) => t.status === 'won');
  const legs = done.flatMap((t) => t.legs.filter((l) => l.result && l.result !== 'void'));
  const profit = won.reduce((a, t) => a + pay(t) - 1, 0) - (done.length - won.length);
  return {
    key, label, n: done.length, won: won.length, lost: done.length - won.length,
    active: ts.filter((t) => !isDone(t) && t.status !== 'void').length,
    profit, roi: done.length ? profit / done.length : null,
    legsWon: legs.filter((l) => l.result === 'won' || l.result === 'half_won').length, legsSettled: legs.length,
    nearMiss: done.filter((t) => t.status === 'lost' && t.legs.filter((l) => l.result === 'lost').length === 1).length,
    best: won.length ? Math.max(...won.map(pay)) : null,
    last: done.slice(-10).map((t) => (t.status === 'won' ? 'w' : 'l')),
  };
}

const signed = (x: number, d = 1) => `${x > 0 ? '+' : x < 0 ? '−' : ''}${Math.abs(x).toFixed(d)}`;
const pctS = (x: number | null) => (x == null ? '—' : `${signed(x * 100, 0)}%`);
const tone = (x: number | null) => (x == null || x === 0 ? 'text-foreground' : x > 0 ? 'text-win' : 'text-loss');

/** Profitul cumulat pe zile (1 unitate pe bilet): o singură serie, linia de zero ca reper. */
function ProfitChart({ points }: { points: Array<{ d: string; v: number; n: number }> }) {
  const [hover, setHover] = useState<number | null>(null);
  if (points.length < 2) return null;
  const W = 320, H = 96, pad = 6;
  const vs = points.map((p) => p.v);
  const lo = Math.min(0, ...vs), hi = Math.max(0, ...vs), span = hi - lo || 1;
  const x = (i: number) => pad + (i * (W - 2 * pad)) / (points.length - 1);
  const y = (v: number) => pad + ((hi - v) * (H - 2 * pad)) / span;
  const line = points.map((p, i) => `${i ? 'L' : 'M'}${x(i).toFixed(1)},${y(p.v).toFixed(1)}`).join(' ');
  const area = `${line} L${x(points.length - 1).toFixed(1)},${y(0).toFixed(1)} L${x(0).toFixed(1)},${y(0).toFixed(1)} Z`;
  const end = points[points.length - 1].v;
  const color = end >= 0 ? 'hsl(var(--win))' : 'hsl(var(--loss))';
  const h = hover == null ? null : points[hover];
  return (
    <div className="relative">
      <svg viewBox={`0 0 ${W} ${H}`} className="h-24 w-full" preserveAspectRatio="none" role="img"
        aria-label={`Profit cumulat: ${signed(end)} unități`}
        onMouseLeave={() => setHover(null)} onTouchEnd={() => setHover(null)}>
        <defs>
          <linearGradient id="tm-area" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={color} stopOpacity="0.28" />
            <stop offset="100%" stopColor={color} stopOpacity="0" />
          </linearGradient>
        </defs>
        <line x1={pad} x2={W - pad} y1={y(0)} y2={y(0)} stroke="hsl(var(--border))" strokeDasharray="3 3" strokeWidth="1" vectorEffect="non-scaling-stroke" />
        <path d={area} fill="url(#tm-area)" />
        <path d={line} fill="none" stroke={color} strokeWidth="2" strokeLinejoin="round" strokeLinecap="round" vectorEffect="non-scaling-stroke" />
        {h && <line x1={x(hover!)} x2={x(hover!)} y1={pad} y2={H - pad} stroke="hsl(var(--muted-foreground))" strokeWidth="1" vectorEffect="non-scaling-stroke" />}
        {points.map((p, i) => (
          <rect key={p.d} x={x(i) - (W / points.length) / 2} y={0} width={W / points.length} height={H} fill="transparent"
            onMouseEnter={() => setHover(i)} onTouchStart={() => setHover(i)} />
        ))}
      </svg>
      {h && (
        <div className="pointer-events-none absolute top-0 rounded-lg border bg-popover px-2 py-1 text-[11px] shadow"
          style={{ left: `${Math.min(70, Math.max(0, (hover! / (points.length - 1)) * 100 - 15))}%` }}>
          <b>{h.d.slice(8)}.{h.d.slice(5, 7)}</b> · {h.n} bilete · cumulat <b className={tone(h.v)}>{signed(h.v)}u</b>
        </div>
      )}
      <div className="flex justify-between text-[10px] text-muted-foreground">
        <span>{points[0].d.slice(8)}.{points[0].d.slice(5, 7)}</span>
        <span className={cn('font-bold', tone(end))}>{signed(end)}u</span>
        <span>{points[points.length - 1].d.slice(8)}.{points[points.length - 1].d.slice(5, 7)}</span>
      </div>
    </div>
  );
}

/** Rândul unei categorii: bara de ROI pornește din zero (spre dreapta pe plus, spre stânga pe minus). */
function CatRow({ s, scale }: { s: Stat; scale: number }) {
  const [open, setOpen] = useState(false);
  const hit = s.legsSettled ? s.legsWon / s.legsSettled : null;
  const w = s.roi == null ? 0 : Math.min(50, (Math.abs(s.roi) / scale) * 50);
  return (
    <li className="border-b border-border/50 last:border-0">
      <button type="button" onClick={() => setOpen(!open)} aria-expanded={open} className="press flex w-full items-center gap-3 py-2.5 text-left">
        <div className="min-w-0 flex-1">
          <div className="flex items-baseline gap-2">
            <span className="min-w-0 flex-1 truncate text-[14px] font-bold">{s.label}</span>
            <span className={cn('num text-[14px] font-extrabold', tone(s.roi))}>{pctS(s.roi)}</span>
          </div>
          <div className="relative mt-1.5 h-1.5 rounded-full bg-muted" aria-hidden>
            <span className="absolute left-1/2 top-[-2px] h-[10px] w-px bg-border" />
            {s.roi != null && <span className={cn('absolute top-0 h-1.5 rounded-full', s.roi >= 0 ? 'left-1/2 bg-[hsl(var(--win))]' : 'right-1/2 bg-[hsl(var(--loss))]')} style={{ width: `${w}%` }} />}
          </div>
          <div className="mt-1 flex gap-3 text-[11px] text-muted-foreground">
            {s.n ? <>
              <span><b className="num text-win">{s.won}</b>–<b className="num text-loss">{s.lost}</b> bilete</span>
              <span>selecții <b className="num text-foreground">{hit == null ? '—' : `${Math.round(hit * 100)}%`}</b></span>
            </> : <span>încă nedecontate</span>}
            {s.active > 0 && <span><b className="num text-foreground">{s.active}</b> active</span>}
          </div>
        </div>
        <ChevronDown className={cn('h-4 w-4 shrink-0 text-muted-foreground transition-transform', open && 'rotate-180')} />
      </button>
      {open && (
        <div className="mb-2.5 grid grid-cols-2 gap-1.5 text-[11px]">
          <div className="rounded-lg bg-[hsl(var(--elevated))] px-2.5 py-1.5"><div className="text-muted-foreground">Profit</div><b className={cn('num text-[13px]', tone(s.profit))}>{signed(s.profit)}u</b></div>
          <div className="rounded-lg bg-[hsl(var(--elevated))] px-2.5 py-1.5"><div className="text-muted-foreground">Selecții intrate</div><b className="num text-[13px]">{s.legsWon} din {s.legsSettled}</b></div>
          <div className="rounded-lg bg-[hsl(var(--elevated))] px-2.5 py-1.5"><div className="flex items-center gap-1 text-muted-foreground"><Target className="h-3 w-3" />Pierdute la o selecție</div><b className="num text-[13px]">{s.nearMiss}</b></div>
          <div className="rounded-lg bg-[hsl(var(--elevated))] px-2.5 py-1.5"><div className="flex items-center gap-1 text-muted-foreground"><Trophy className="h-3 w-3" />Cel mai mare câștig</div><b className="num text-[13px]">{s.best ? `cota ${s.best.toFixed(2)}` : '—'}</b></div>
          {s.last.length > 0 && (
            <div className="col-span-2 flex items-center gap-1.5 rounded-lg bg-[hsl(var(--elevated))] px-2.5 py-1.5">
              <span className="text-muted-foreground">Ultimele bilete</span>
              <span className="ml-auto flex gap-1">{s.last.map((x, i) => (
                <span key={i} className={cn('flex h-4 w-4 items-center justify-center rounded text-[9px] font-black', x === 'w' ? 'bg-win/20 text-win' : 'bg-loss/15 text-loss')}>{x === 'w' ? 'C' : 'P'}</span>
              ))}</span>
            </div>
          )}
        </div>
      )}
    </li>
  );
}

/** Bilete › Monitorizare: o perioadă pentru tot (azi / 7 / 30 zile / tot), cifrele mari, profitul cumulat pe zile
 *  și categoriile ordonate după ROI, fiecare cu detaliile ei la atingere. ROI și profit la 1 unitate pe bilet. */
export function TicketMonitor({ tickets, kinds, kindOf, today }: {
  tickets: Ticket[]; kinds: Array<[string, string]>; kindOf: (t: Ticket) => string; today: string;
}) {
  const [period, setPeriod] = useState<Period>(() => { try { return (localStorage.getItem('bp.tm.period') as Period) || '7'; } catch { return '7'; } });
  // strâns implicit: biletele rămân aproape de capul paginii; starea se ține minte
  const [open, setOpen] = useState(() => { try { return localStorage.getItem('bp.tm.open') === '1'; } catch { return false; } });
  const toggle = () => setOpen((v) => { try { localStorage.setItem('bp.tm.open', v ? '0' : '1'); } catch { /* fără stocare */ } return !v; });
  const pickPeriod = (p: Period) => { setPeriod(p); try { localStorage.setItem('bp.tm.period', p); } catch { /* fără stocare */ } };
  const d = useMemo(() => {
    const from = period === 'all' ? '' : new Date(Date.parse(today) - (Number(period) - 1) * 86400000).toISOString().slice(0, 10);
    const ts = tickets.filter((t) => dayOf(t) >= from);
    const total = stat('toate', 'Toate biletele', ts);
    const cats = kinds.filter(([k]) => k !== 'toate').map(([k, label]) => stat(k, label, ts.filter((t) => kindOf(t) === k || (k === 'mine' && t.followed))))
      .filter((s) => s.n || s.active).sort((a, b) => (b.roi ?? -9) - (a.roi ?? -9) || b.n - a.n);
    const byDay = new Map<string, Ticket[]>();
    for (const t of ts.filter(isDone)) byDay.set(dayOf(t), [...(byDay.get(dayOf(t)) ?? []), t]);
    const points: Array<{ d: string; v: number; n: number }> = [];
    for (const day of [...byDay.keys()].sort()) {
      const xs = byDay.get(day)!;
      const prev = points.length ? points[points.length - 1].v : 0;
      points.push({ d: day, v: prev + xs.reduce((a, t) => a + (t.status === 'won' ? pay(t) - 1 : -1), 0), n: xs.length });
    }
    return { total, cats, points };
  }, [tickets, kinds, kindOf, period, today]);
  const t = d.total;
  const wr = t.n ? t.won / t.n : null;
  const hit = t.legsSettled ? t.legsWon / t.legsSettled : null;
  const scale = Math.max(0.25, ...d.cats.map((c) => Math.abs(c.roi ?? 0)));
  const positive = d.cats.filter((c) => c.n >= 3 && (c.roi ?? 0) > 0);
  return (
    <section className="card p-4" aria-labelledby="tm-title">
      <button type="button" onClick={toggle} aria-expanded={open} className="press flex w-full items-center gap-2 text-left">
        <h2 id="tm-title" className="text-[15px] font-extrabold">Monitorizare</h2>
        {!open && (
          <span className="flex min-w-0 flex-1 items-center gap-2 text-[12px] text-muted-foreground">
            <span>{PERIODS.find(([p]) => p === period)?.[1]}:</span>
            <b className={cn('num', tone(t.roi))}>ROI {pctS(t.roi)}</b>
            <span className="num"><b className="text-win">{t.won}</b>–<b className="text-loss">{t.lost}</b></span>
          </span>
        )}
        {open && <span className="flex-1 text-[11px] text-muted-foreground">la 1 unitate pe bilet</span>}
        <ChevronDown className={cn('h-4 w-4 shrink-0 text-muted-foreground transition-transform', open && 'rotate-180')} />
      </button>
      {open && <>
      <div className="mt-2 grid grid-cols-4 gap-1 rounded-xl border bg-muted/60 p-1" role="tablist" aria-label="Perioada">
        {PERIODS.map(([p, l]) => (
          <button key={p} type="button" role="tab" aria-selected={period === p} onClick={() => pickPeriod(p)}
            className={cn('press rounded-lg py-1.5 text-xs font-bold', period === p ? 'bg-primary text-primary-foreground shadow' : 'text-muted-foreground')}>{l}</button>
        ))}
      </div>

      <div className="mt-3 grid grid-cols-2 gap-2">
        <div className="col-span-2 flex items-end justify-between rounded-2xl bg-[hsl(var(--elevated))] px-3.5 py-3">
          <div>
            <div className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground">ROI</div>
            <div className={cn('num text-[34px] font-black leading-none', tone(t.roi))}>{pctS(t.roi)}</div>
          </div>
          <div className="text-right">
            <div className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground">Profit</div>
            <div className={cn('num text-[20px] font-extrabold leading-tight', tone(t.profit))}>{signed(t.profit)}u</div>
          </div>
        </div>
        <div className="rounded-2xl bg-[hsl(var(--elevated))] px-3 py-2.5">
          <div className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground">Bilete</div>
          <div className="num text-[20px] font-extrabold leading-tight"><span className="text-win">{t.won}</span><span className="text-muted-foreground"> – </span><span className="text-loss">{t.lost}</span></div>
          <div className="text-[11px] text-muted-foreground">rată câștig <b className="text-foreground">{wr == null ? '—' : `${Math.round(wr * 100)}%`}</b>{t.active ? ` · ${t.active} active` : ''}</div>
        </div>
        <div className="rounded-2xl bg-[hsl(var(--elevated))] px-3 py-2.5">
          <div className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground">Selecții intrate</div>
          <div className="num text-[20px] font-extrabold leading-tight">{hit == null ? '—' : `${Math.round(hit * 100)}%`}</div>
          <div className="text-[11px] text-muted-foreground">{t.legsWon} din {t.legsSettled} · <b className="text-foreground">{t.nearMiss}</b> la o selecție</div>
        </div>
      </div>

      {d.points.length >= 2 && (
        <div className="mt-3">
          <div className="mb-1 text-[10px] font-bold uppercase tracking-wider text-muted-foreground">Profit cumulat pe zile</div>
          <ProfitChart points={d.points} />
        </div>
      )}

      {d.cats.length > 0 && (
        <div className="mt-3">
          <div className="mb-0.5 flex items-baseline justify-between text-[10px] font-bold uppercase tracking-wider text-muted-foreground">
            <span>Pe categorii, după ROI</span><span className="normal-case tracking-normal">atinge pentru detalii</span>
          </div>
          <ul>{d.cats.map((s) => <CatRow key={s.key} s={s} scale={scale} />)}</ul>
          <p className="mt-1.5 text-[11px] text-muted-foreground">
            {positive.length
              ? <>Pe plus în perioada asta: <b className="text-win">{positive.map((c) => c.label).join(', ')}</b>.</>
              : <>Nicio categorie cu cel puțin 3 bilete decontate nu e pe plus în perioada asta.</>}
            {' '}Bara pornește din mijloc: spre dreapta = pe plus, spre stânga = pe minus.
          </p>
        </div>
      )}
      {!t.n && !d.cats.length && <p className="mt-3 text-sm text-muted-foreground">Încă nu sunt bilete decontate în perioada asta.</p>}
      </>}
    </section>
  );
}
