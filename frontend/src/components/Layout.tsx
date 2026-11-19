import { NavLink, Outlet, Link, useLocation } from 'react-router';
import { Settings, Moon, Sun, Home, List, Ticket, Layers, CalendarDays, BarChart3, Bot, LayoutGrid, ChevronRight } from 'lucide-react';
import { useCallback, useEffect, useRef, useState } from 'react';
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
import { Loading, Sheet } from './kit';

/** Navigarea principală: doar produsele de bază. */
const NAV = [
  { to: '/', label: 'Acasă', icon: Home, end: true },
  { to: '/predictii', label: 'Predicții', icon: List },
  { to: '/bilete', label: 'Bilete', icon: Ticket },
  { to: '/piramida', label: 'Piramidă', icon: Layers },
  { to: '/statistici', label: 'Statistici', icon: BarChart3 },
];

/** Instrumentele secundare, în meniul „Mai mult”. */
const MORE = [
  { to: '/generator', label: 'Generator', hint: 'Bilet construit după regulile tale', icon: Bot },
  { to: '/istoric', label: 'Istoric', hint: 'Zilele trecute, pe rezultate', icon: CalendarDays },
  { to: '/setari', label: 'Setări', hint: 'Bancă, buget, notificări, temă', icon: Settings },
];
const ORDER = [...NAV.map((n) => n.to), ...MORE.map((n) => n.to)];
const isMore = (p: string) => MORE.some((m) => p.startsWith(m.to));

function MoreSheet({ open, onClose }: { open: boolean; onClose: () => void }) {
  const theme = useStore((s) => s.settings.theme);
  const loc = useLocation();
  return (
    <Sheet open={open} onClose={onClose} title="Mai mult" subtitle="Instrumente secundare. Esențialul e în bara de jos.">
      <ul className="more-list">
        {MORE.map((m) => (
          <li key={m.to}>
            <Link to={m.to} onClick={onClose} className={cn('more-item', loc.pathname.startsWith(m.to) && 'is-on')}>
              <span className="more-ico"><m.icon className="h-[18px] w-[18px]" /></span>
              <span className="min-w-0 flex-1"><span className="more-name">{m.label}</span><span className="more-hint">{m.hint}</span></span>
              <ChevronRight className="h-4 w-4 shrink-0 opacity-60" />
            </Link>
          </li>
        ))}
        <li>
          <button type="button" className="more-item w-full text-left" onClick={() => actions.setSettings({ theme: theme === 'dark' ? 'light' : 'dark' })}>
            <span className="more-ico">{theme === 'dark' ? <Sun className="h-[18px] w-[18px]" /> : <Moon className="h-[18px] w-[18px]" />}</span>
            <span className="min-w-0 flex-1"><span className="more-name">{theme === 'dark' ? 'Temă deschisă' : 'Temă închisă'}</span><span className="more-hint">Acum: {theme === 'dark' ? 'închisă' : 'deschisă'}</span></span>
          </button>
        </li>
      </ul>
      <p className="more-foot">Estimări, nu garanții. Marja casei e reală. Joacă doar ce îți permiți să pierzi. 18+</p>
    </Sheet>
  );
}

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
  useEffect(() => { document.documentElement.classList.toggle('dark', theme === 'dark'); }, [theme]);
  const scroller = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const el = document.documentElement; el.classList.add('bp-shell');
    return () => el.classList.remove('bp-shell');
  }, []);
  useEffect(() => { scroller.current?.scrollTo(0, 0); window.scrollTo(0, 0); }, [loc.pathname]);
  const rank = (p: string) => { const i = ORDER.findIndex((to) => (to === '/' ? p === '/' : p.startsWith(to))); return i < 0 ? 10 : i; };
  const [more, setMore] = useState(false);
  const closeMore = useCallback(() => setMore(false), []);
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
        <div className="mx-auto flex h-14 max-w-6xl items-center gap-2 px-4 md:px-6">
          <Link to="/" className="casa-brand" aria-label="BetPredict, acasă">
            <span className="brand-dot">B</span>
            <span className="flex flex-col leading-none">
              <span className="casa-name">BetPredict</span>
              <span className="casa-tag">{longDay(todayRo())}</span>
            </span>
          </Link>
          <nav className="ml-4 hidden items-center gap-1 md:flex" aria-label="Navigare">
            {NAV.map((n) => (
              <NavLink key={n.to} to={n.to} end={n.end} className={({ isActive }) => cn('casa-tab casa-tab-desk', isActive && 'is-on')}>
                <n.icon className="h-4 w-4" />{n.label}
              </NavLink>
            ))}
            <button type="button" className={cn('casa-tab casa-tab-desk', isMore(loc.pathname) && 'is-on')} aria-haspopup="dialog" onClick={() => setMore(true)}>
              <LayoutGrid className="h-4 w-4" />Mai mult
            </button>
          </nav>
          <div className="casa-tools ml-auto">
            <StatusDot />
            <button className="casa-tool" aria-label={theme === 'dark' ? 'Temă deschisă' : 'Temă închisă'} onClick={() => actions.setSettings({ theme: theme === 'dark' ? 'light' : 'dark' })}>
              {theme === 'dark' ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
            </button>
          </div>
        </div>
      </header>
      <div id="bp-scroll" ref={scroller} className="relative min-h-0 flex-1 overflow-y-auto overflow-x-hidden overscroll-y-contain">
      {pull > 0 && <div aria-hidden className="ptr" style={{ height: pull }}><span className={cn('ptr-ring', pull >= 70 && 'ptr-ready')} style={{ ['--ptr' as string]: `${Math.min(100, pull / 0.7)}%`, transform: `rotate(${pull * 2}deg) scale(${0.6 + Math.min(1, pull / 70) * 0.4})` }} /></div>}
      <main className="mx-auto max-w-6xl px-4 pb-8 pt-4 md:px-6 md:py-6">
        <div className="min-h-[60vh]"><ErrorBoundary key={loc.pathname}><Suspense fallback={<Loading />}><div key={`${loc.pathname}-${gen}`} className={`page-enter page-${dir}`}><Outlet /></div></Suspense></ErrorBoundary></div>
        <footer className="casa-foot">
          Biletul de cotă ~10, biletele lungi și piramida de cotă 2. Estimări, nu garanții. Marja casei e reală. 18+
        </footer>
      </main>
      </div>
      <SlipBar />
      <nav className="casa-nav md:hidden" aria-label="Navigare principală">
        {NAV.map((n) => (
          <NavLink key={n.to} to={n.to} end={n.end}
            onClick={(e) => {
              if (loc.pathname === n.to) { e.preventDefault(); document.getElementById('bp-scroll')?.scrollTo({ top: 0, behavior: 'smooth' }); }
            }}
            className={({ isActive }) => cn('casa-tab', isActive && 'is-on')}>
            {({ isActive }) => (
              <>
                <span className="casa-tab-ico"><n.icon className="h-[20px] w-[20px]" strokeWidth={isActive ? 2.3 : 1.8} /></span>
                <span>{n.label}</span>
              </>
            )}
          </NavLink>
        ))}
        <button type="button" className={cn('casa-tab', (more || isMore(loc.pathname)) && 'is-on')} aria-haspopup="dialog" aria-expanded={more} onClick={() => setMore(true)}>
          <span className="casa-tab-ico"><LayoutGrid className="h-[20px] w-[20px]" strokeWidth={more || isMore(loc.pathname) ? 2.3 : 1.8} /></span>
          <span>Mai mult</span>
        </button>
      </nav>
      <MoreSheet open={more} onClose={closeMore} />
      <WinWatcher />
    </div>
  );
}
