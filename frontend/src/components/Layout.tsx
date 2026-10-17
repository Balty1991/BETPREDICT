import { NavLink, Outlet, Link, useLocation, useNavigate } from 'react-router';
import { Logo } from './Logo';
import { Settings, Moon, Sun, Ellipsis, Crosshair, Blocks, Ticket, CalendarDays, Equal, ClipboardCheck, FlaskConical, Wand2 } from 'lucide-react';
import { IconHome, IconPredict, IconPyramid, IconStats } from './icons';
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
import { Loading, Sheet } from './kit';

const NAV = [
  { to: '/', label: 'Acasă', icon: IconHome, end: true },
  { to: '/predictii', label: 'Predicții', icon: IconPredict },
  { to: '/bilete', label: 'Bilete', icon: Ticket },
  { to: '/piramida', label: 'Piramida', icon: IconPyramid },
];

const MORE_GROUPS = [
  { title: 'Analiză', items: [
    { to: '/builder', label: 'Bet Builder', d: 'Combinații pe un meci', icon: Blocks },
    { to: '/edge', label: 'Edge', d: 'Valoare și siguranță', icon: Crosshair },
    { to: '/egaluri', label: 'Egaluri', d: 'Egaluri peste piață', icon: Equal },
    { to: '/bilete#generator', label: 'Generator', d: 'Biletul tău, după reguli', icon: Wand2 },
  ] },
  { title: 'Rezultate', items: [
    { to: '/statistici', label: 'Statistici', d: 'Cum a ieșit Robotul', icon: IconStats },
    { to: '/istoric', label: 'Istoric', d: 'Zi de zi', icon: CalendarDays },
    { to: '/statistici?tab=laborator', label: 'Laborator', d: 'Strategii testate', icon: FlaskConical },
    { to: '/statistici?tab=audit', label: 'Audit piețe', d: 'Ce câștigă pe cotele Superbet', icon: ClipboardCheck },
  ] },
  { title: 'Cont', items: [
    { to: '/setari', label: 'Setări', d: 'Buget, notificări, temă', icon: Settings },
  ] },
];
const MORE = MORE_GROUPS.flatMap((g) => g.items);
/** Pe ecran mare: doar paginile (fără scurtăturile spre file din Statistici sau Bilete). */
const MORE_PAGES = MORE.filter((m) => !/[?#]/.test(m.to));

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
      <button type="button" className="flex h-11 items-center gap-1.5 rounded-xl px-1 text-xs text-muted-foreground" aria-expanded={open} aria-haspopup="dialog" aria-label={summary} onClick={() => setOpen((v) => !v)}>
        <span className={cn('h-2 w-2 shrink-0 rounded-full', copy.dot)} aria-hidden />
        {m?.generated_at ? <time dateTime={m.generated_at} className="num text-[11px] font-bold tabular-nums text-foreground sm:hidden">{roTime(m.generated_at)}</time> : <span className="text-[11px] font-semibold sm:hidden">fără oră</span>}
        <span className="hidden sm:inline">{copy.short}{m?.generated_at ? ` · ${roDateTime(m.generated_at)}` : ' · fără oră'}</span>
        {q != null && <span className="hidden md:inline">· API {q.toLocaleString('ro-RO')}/{(m?.quota?.daily_quota ?? 7500).toLocaleString('ro-RO')}</span>}
        {m?._source === 'legacy' && <span className="rounded bg-warn/15 px-1 text-[10px] font-bold text-warn">v2</span>}
      </button>
      {open && createPortal(
        <div ref={pop} role="dialog" aria-label="Prospețimea datelor" className="fresh-pop fixed right-3 z-[80] w-[min(18rem,calc(100vw-1.5rem))] rounded-2xl border bg-card p-3 text-left text-xs shadow-lg" style={{ top: 'calc(3.25rem + var(--safe-top))' }}>
          <div className="flex items-center gap-2 font-bold text-foreground"><span className={cn('h-2 w-2 rounded-full', copy.dot)} aria-hidden />{copy.short}</div>
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
  // „App shell”: documentul NU derulează (derulează doar #bp-scroll). Astfel bara dinamică a
  // browserului (Brave/Chrome cu bara jos) nu mai glisează, iar bara de navigare stă în flux,
  // nu position:fixed — pe Android, fixed + backdrop-filter + bara dinamică desena nav-ul într-un
  // loc și primea atingerile în altul (de aici „fantoma” de sub nav și butoanele moarte).
  useEffect(() => {
    const el = document.documentElement; el.classList.add('bp-shell');
    return () => el.classList.remove('bp-shell');
  }, []);
  useEffect(() => { scroller.current?.scrollTo(0, 0); window.scrollTo(0, 0); }, [loc.pathname]);
  // tranziții „native”: spre dreapta în meniu / pagini adânci => intră din dreapta; înapoi => din stânga
  const rank = (p: string) => { const i = NAV.findIndex((n) => (n.end ? p === n.to : p.startsWith(n.to))); return i < 0 ? 10 : i; };
  const [navState, setNavState] = useState<{ path: string; dir: 'fwd' | 'back' }>(() => ({ path: loc.pathname, dir: 'fwd' }));
  if (navState.path !== loc.pathname) setNavState({ path: loc.pathname, dir: rank(loc.pathname) >= rank(navState.path) ? 'fwd' : 'back' });
  const dir = navState.dir;
  // pull-to-refresh: golește cache-ul și remontează pagina (fără reîncărcarea aplicației)
  const [gen, setGen] = useState(0);
  const [more, setMore] = useState(false);
  const moreOn = MORE.some((m) => loc.pathname === m.to || loc.pathname.startsWith(`${m.to}/`));
  const pull = usePullToRefresh(scroller, () => { clearCache(); setGen((g) => g + 1); toast.success('Date reîmprospătate'); });
  return (
    <div className="app-shell flex flex-col overflow-hidden">
      <header className="glass relative z-30 shrink-0 border-b border-[hsl(var(--glass-border))] pt-[var(--safe-top)]">
        <div className="mx-auto flex h-12 max-w-6xl items-center gap-2 px-3 md:gap-3 md:px-6">
          <Link to="/" className="flex shrink-0 items-center gap-2 font-extrabold tracking-tight">
            <span className="logo-glow"><Logo size={32} /></span>
            <span className="text-[17px] tracking-[-0.04em]">BetPredict</span>
            <span className="hidden shrink-0 rounded-full bg-primary/15 px-2 py-0.5 text-[10px] font-extrabold text-primary ring-1 ring-primary/25 min-[400px]:inline">3.0</span>
            <span className="hidden rounded-full bg-muted px-2 py-0.5 text-[10px] font-bold text-muted-foreground sm:inline">pe hârtie</span>
          </Link>
          <nav className="ml-4 hidden min-w-0 items-center gap-1 overflow-x-auto md:flex">
            {NAV.map((n) => (
              <NavLink key={n.to} to={n.to} end={n.end} className={({ isActive }) => cn('btn btn-ghost', isActive && 'bg-primary/12 text-primary ring-1 ring-primary/25')}>
                <n.icon className="h-4 w-4" />{n.label}
              </NavLink>
            ))}
            {MORE_PAGES.filter((m) => m.to !== '/setari').map((m) => (
              <NavLink key={m.to} to={m.to} className={({ isActive }) => cn('btn btn-ghost', isActive && 'bg-primary/12 text-primary ring-1 ring-primary/25')}>
                <m.icon className="h-4 w-4" />{m.label}
              </NavLink>
            ))}
          </nav>
          <div className="ml-auto flex items-center gap-2">
            <div className="hidden text-xs text-muted-foreground lg:block">{longDay(todayRo())}</div>
            <StatusDot />
            <button className="btn btn-ghost px-2" aria-label="Temă" onClick={() => actions.setSettings({ theme: theme === 'dark' ? 'light' : 'dark' })}>
              {theme === 'dark' ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
            </button>
            <NavLink to="/setari" className={({ isActive }) => cn('btn btn-ghost px-2', isActive && 'bg-accent')} aria-label="Setări"><Settings className="h-4 w-4" /></NavLink>
          </div>
        </div>
        <div aria-hidden className="h-px w-full bg-gradient-to-r from-transparent via-primary/80 to-transparent" />
      </header>
      <div id="bp-scroll" ref={scroller} className="relative min-h-0 flex-1 overflow-y-auto overflow-x-hidden overscroll-y-contain">
      {pull > 0 && <div aria-hidden className="ptr" style={{ height: pull }}><span className={cn('ptr-dot', pull >= 70 && 'ptr-ready')} style={{ transform: `rotate(${pull * 3}deg)` }} /></div>}
      <main className="mx-auto max-w-6xl px-4 pb-6 pt-4 md:px-6 md:py-6">
        <div className="min-h-[60vh]"><ErrorBoundary key={loc.pathname}><Suspense fallback={<Loading />}><div key={`${loc.pathname}-${gen}`} className={`page-enter page-${dir}`}><Outlet /></div></Suspense></ErrorBoundary></div>
        <footer className="mt-10 border-t pt-4 text-center text-[11px] text-muted-foreground">
          Predicțiile sunt estimări statistice, nu garanții. Pariază responsabil, doar sume pe care îți permiți să le pierzi. 18+
        </footer>
      </main>
      </div>
      <SlipBar />
      <nav className="nav-dock relative z-[80] shrink-0 px-3 pb-[calc(8px+var(--safe-bottom))] md:hidden" aria-label="Navigare principală">
        <div className="nav-float mx-auto grid h-[62px] max-w-md grid-cols-5">
          {NAV.map((n) => (
            <NavLink key={n.to} to={n.to} end={n.end}
              onClick={() => {
                if (loc.pathname === n.to) document.getElementById('bp-scroll')?.scrollTo(0, 0);
                else navigate(n.to);
              }}
              className={({ isActive }) => cn('relative z-0 flex min-h-[48px] touch-manipulation select-none flex-col items-center justify-center gap-1 text-[11px] font-bold', isActive ? 'nav-item-on' : 'text-muted-foreground')}>
              {({ isActive }) => (<>
                {isActive && <span aria-hidden className="nav-blob" />}
                <n.icon className="pointer-events-none relative h-[20px] w-[20px]" strokeWidth={isActive ? 2.4 : 1.8} />
                <span className="pointer-events-none relative">{n.label}</span>
              </>)}
            </NavLink>
          ))}
          <button type="button" aria-expanded={more} aria-label="Mai mult" onClick={() => setMore(true)}
            className={cn('relative z-0 flex min-h-[48px] touch-manipulation select-none flex-col items-center justify-center gap-1 text-[11px] font-bold', moreOn || more ? 'nav-item-on' : 'text-muted-foreground')}>
            {(moreOn || more) && <span aria-hidden className="nav-blob" />}
            <Ellipsis className="pointer-events-none relative h-[20px] w-[20px]" strokeWidth={moreOn || more ? 2.4 : 1.8} />
            <span className="pointer-events-none relative">Mai mult</span>
          </button>
        </div>
      </nav>
      <Sheet open={more} onClose={() => setMore(false)} title="Mai mult" subtitle="Analiză, rezultate, cont">
        <nav className="space-y-4" aria-label="Destinații secundare">
          {MORE_GROUPS.map((g) => (
            <section key={g.title} className="space-y-2">
              <h3 className="px-1 text-[11px] font-bold uppercase tracking-wider text-muted-foreground">{g.title}</h3>
              <div className="grid grid-cols-2 gap-2">
              {g.items.map((m) => {
                const [path, rest] = m.to.split(/(?=[?#])/);
                const on = loc.pathname === path && (rest ? loc.search === rest || loc.hash === rest : !loc.search.includes('tab='));
                return (
                  <Link key={m.to} to={m.to} onClick={() => setMore(false)} aria-current={on ? 'page' : undefined} className={cn('more-tile press flex min-h-[64px] flex-col items-start justify-center gap-1 rounded-2xl border px-3 py-2', on ? 'border-primary/50 bg-primary/12 text-primary' : 'border-transparent bg-[hsl(var(--elevated))]')}>
                    <m.icon className="h-5 w-5 shrink-0" />
                    <span className="min-w-0"><span className="block font-extrabold">{m.label}</span><span className={cn('block text-xs', on ? 'text-primary/80' : 'text-muted-foreground')}>{m.d}</span></span>
                  </Link>
                );
              })}
              </div>
            </section>
          ))}
        </nav>
      </Sheet>
      <WinWatcher />
    </div>
  );
}
