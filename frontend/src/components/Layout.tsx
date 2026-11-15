import { NavLink, Outlet, Link, useLocation, useNavigate } from 'react-router';
import { Settings, Moon, Sun, Home, List, Ticket, Layers, CalendarDays, BarChart3 } from 'lucide-react';
import { useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { cn } from '@/lib/utils';
import { useMeta } from '@/lib/hooks';
import { useStore, actions } from '@/lib/store';
import { longDay, todayRo, roDateTime, roTime } from '@/lib/format';
import { SlipBar } from './Slip';
import { WinWatcher } from './WinWatcher';
import { usePullToRefresh } from '@/lib/gestures';
import { clearCache } from '@/lib/fetcher';
import { toast } from 'sonner';
import { ErrorBoundary } from './ErrorBoundary';
import { Suspense } from 'react';
import { Loading } from './kit';

const NAV = [
  { to: '/', label: 'Acasă', icon: Home, end: true },
  { to: '/predictii', label: 'Predicții', icon: List },
  { to: '/bilete', label: 'Cornere', icon: Ticket },
  { to: '/piramida', label: 'Piramidă', icon: Layers },
  { to: '/istoric', label: 'Istoric', icon: CalendarDays },
];

function ageLabel(iso: string, now: number): string {
  const ms = now - Date.parse(iso);
  if (!Number.isFinite(ms) || ms < 0) return '';
  const min = Math.floor(ms / 60000);
  if (min < 1) return 'acum mai puțin de un minut';
  if (min < 60) return `acum ${min} min`;
  const h = Math.floor(min / 60);
  if (h < 48) return `acum ${h} h`;
  return `acum ${Math.floor(h / 24)} zile`;
}

function statusCopy(m: { status?: string } | null | undefined): { dot: string; short: string } {
  if (!m?.status) return { dot: 'bg-muted-foreground', short: 'stare necunoscută' };
  if (m.status === 'ok') return { dot: 'bg-emerald-500', short: 'date la zi' };
  if (m.status === 'stale') return { dot: 'bg-rose-500', short: 'date vechi' };
  return { dot: 'bg-amber-500', short: 'date parțiale' };
}

function StatusDot() {
  const meta = useMeta();
  const m = meta.data;
  const [open, setOpen] = useState(false);
  const [now, setNow] = useState(() => Date.now());
  const box = useRef<HTMLDivElement>(null);
  const pop = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!m?.generated_at) return;
    const id = window.setInterval(() => setNow(Date.now()), 60_000);
    return () => window.clearInterval(id);
  }, [m?.generated_at]);
  useEffect(() => {
    if (!open) return;
    const onDoc = (e: MouseEvent) => {
      const t = e.target as Node;
      if (box.current?.contains(t) || pop.current?.contains(t)) return;
      setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') setOpen(false); };
    document.addEventListener('mousedown', onDoc);
    document.addEventListener('keydown', onKey);
    return () => { document.removeEventListener('mousedown', onDoc); document.removeEventListener('keydown', onKey); };
  }, [open]);
  const copy = statusCopy(m);
  const when = m?.generated_at ? `Actualizat ${roDateTime(m.generated_at)}, ora României` : 'Fără timestamp. Nu știu când s-au actualizat datele.';
  const age = m?.generated_at ? ageLabel(m.generated_at, now) : '';
  const summary = `${copy.short}. ${when}${m?._source === 'legacy' ? ' Sursă veche, fișierele din data/.' : ''}`;
  const q = m?.quota?.effective_remaining;
  return (
    <div ref={box} className="relative">
      <button type="button" className="casa-tool" aria-expanded={open} aria-haspopup="dialog" aria-label={summary} onClick={() => setOpen((v) => !v)}>
        <span className={cn('h-2 w-2 shrink-0', copy.dot)} aria-hidden />
        {m?.generated_at ? <time dateTime={m.generated_at}>{roTime(m.generated_at)}</time> : <span>fără oră</span>}
        <span className="hidden lg:inline">{copy.short}</span>
        {q != null && <span className="hidden md:inline">API {q.toLocaleString('ro-RO')}</span>}
      </button>
      {open && createPortal(
        <div ref={pop} role="dialog" aria-label="Prospețimea datelor" className="fresh-pop fixed right-3 z-[80] w-[min(18rem,calc(100vw-1.5rem))] border bg-card p-3 text-left text-xs shadow-lg" style={{ top: 'calc(3.25rem + var(--safe-top))' }}>
          <div className="flex items-center gap-2 font-bold text-foreground"><span className={cn('h-2 w-2', copy.dot)} aria-hidden />{copy.short}</div>
          {m?.generated_at ? <time dateTime={m.generated_at} className="mt-1 block text-muted-foreground">{roDateTime(m.generated_at)}, ora României{age ? ` · ${age}` : ''}</time> : <p className="mt-1 text-muted-foreground">Nu există timestamp de publicare.</p>}
          {m?._source === 'legacy' && <p className="mt-2 text-muted-foreground">Sursă veche: se folosesc fișierele din data/, nu contractul api/.</p>}
          {m?.status === 'degraded' && <p className="mt-2 text-muted-foreground">Date parțiale: o parte din surse nu s-a actualizat.</p>}
          {m?.status === 'stale' && <p className="mt-2 text-muted-foreground">Datele sunt marcate vechi. Nu sunt un semnal nou.</p>}
        </div>,
        document.body,
      )}
    </div>
  );
}

export function Layout() {
  const theme = useStore((s) => s.settings.theme);
  const loc = useLocation();
  const navigate = useNavigate();
  useEffect(() => { document.documentElement.classList.toggle('dark', theme === 'dark'); }, [theme]);
  const scroller = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const el = document.documentElement; el.classList.add('bp-shell');
    return () => el.classList.remove('bp-shell');
  }, []);
  useEffect(() => { scroller.current?.scrollTo(0, 0); window.scrollTo(0, 0); }, [loc.pathname]);
  const rank = (p: string) => { const i = NAV.findIndex((n) => (n.end ? p === n.to : p.startsWith(n.to))); return i < 0 ? 10 : i; };
  const [navState, setNavState] = useState<{ path: string; dir: 'fwd' | 'back' }>(() => ({ path: loc.pathname, dir: 'fwd' }));
  if (navState.path !== loc.pathname) setNavState({ path: loc.pathname, dir: rank(loc.pathname) >= rank(navState.path) ? 'fwd' : 'back' });
  const dir = navState.dir;
  const [gen, setGen] = useState(0);
  useEffect(() => {
    const on = (e: PointerEvent) => { if (e.pointerType === 'touch' && (e.target as HTMLElement)?.closest?.('button, a, [role=button]')) navigator.vibrate?.(6); };
    window.addEventListener('pointerdown', on, { passive: true });
    return () => window.removeEventListener('pointerdown', on);
  }, []);
  const pull = usePullToRefresh(scroller, () => { clearCache(); setGen((g) => g + 1); toast.success('Date reîmprospătate'); });
  return (
    <div className="app-shell casa-shell flex flex-col overflow-hidden">
      <header className="casa-top relative z-30 shrink-0 pt-[var(--safe-top)]">
        <div className="mx-auto flex h-14 max-w-6xl items-center gap-2 px-3 md:px-6">
          <Link to="/" className="casa-brand">
            <span className="brand-mark" aria-hidden><i /><i /><i /></span>
            <span className="flex flex-col leading-none">
              <span className="casa-name">BETPREDICT</span>
              <span className="casa-tag">analiză · nu casă</span>
            </span>
          </Link>
          <nav className="ml-4 hidden items-center gap-1 md:flex" aria-label="Navigare">
            {NAV.map((n) => (
              <NavLink key={n.to} to={n.to} end={n.end} className={({ isActive }) => cn('casa-tab casa-tab-desk', isActive && 'is-on')}>
                <n.icon className="h-4 w-4" />{n.label}
              </NavLink>
            ))}
            <NavLink to="/statistici" className={({ isActive }) => cn('casa-tab casa-tab-desk', isActive && 'is-on')}><BarChart3 className="h-4 w-4" />Rezultate</NavLink>
          </nav>
          <div className="casa-tools ml-auto">
            <div className="hidden text-xs lg:block">{longDay(todayRo())}</div>
            <StatusDot />
            <NavLink to="/statistici" className={({ isActive }) => cn('casa-tool md:hidden', isActive && 'is-on')} aria-label="Rezultate"><BarChart3 className="h-4 w-4" /></NavLink>
            <button className="casa-tool" aria-label={theme === 'dark' ? 'Temă deschisă' : 'Temă închisă'} onClick={() => actions.setSettings({ theme: theme === 'dark' ? 'light' : 'dark' })}>
              {theme === 'dark' ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
            </button>
            <NavLink to="/setari" className={({ isActive }) => cn('casa-tool', isActive && 'is-on')} aria-label="Setări"><Settings className="h-4 w-4" /></NavLink>
          </div>
        </div>
      </header>
      <div id="bp-scroll" ref={scroller} className="relative min-h-0 flex-1 overflow-y-auto overflow-x-hidden overscroll-y-contain">
      {pull > 0 && <div aria-hidden className="ptr" style={{ height: pull }}><span className={cn('ptr-ring', pull >= 70 && 'ptr-ready')} style={{ ['--ptr' as string]: `${Math.min(100, pull / 0.7)}%`, transform: `rotate(${pull * 2}deg) scale(${0.6 + Math.min(1, pull / 70) * 0.4})` }} /></div>}
      <main className="mx-auto max-w-6xl px-4 pb-8 pt-4 md:px-6 md:py-6">
        <div className="min-h-[60vh]"><ErrorBoundary key={loc.pathname}><Suspense fallback={<Loading />}><div key={`${loc.pathname}-${gen}`} className={`page-enter page-${dir}`}><Outlet /></div></Suspense></ErrorBoundary></div>
        <footer className="casa-foot">
          Cornere de jucat și piramida de cotă 2. Istoricul numără, nu listează bilete. Estimări, nu garanții. 18+
        </footer>
      </main>
      </div>
      <SlipBar />
      <nav className="casa-nav md:hidden" aria-label="Navigare principală">
        {NAV.map((n) => (
          <NavLink key={n.to} to={n.to} end={n.end}
            onClick={() => {
              if (loc.pathname === n.to) document.getElementById('bp-scroll')?.scrollTo(0, 0);
              else navigate(n.to);
            }}
            className={({ isActive }) => cn('casa-tab', isActive && 'is-on')}>
            {({ isActive }) => (
              <>
                <n.icon className="h-[18px] w-[18px]" strokeWidth={isActive ? 2.4 : 1.8} />
                <span>{n.label}</span>
              </>
            )}
          </NavLink>
        ))}
      </nav>
      <WinWatcher />
    </div>
  );
}
