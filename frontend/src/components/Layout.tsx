import { NavLink, Outlet, Link, useLocation, useNavigate } from 'react-router';
import { Settings, Moon, Sun, Ellipsis, Crosshair, Blocks } from 'lucide-react';
import { IconHome, IconPredict, IconPyramid, IconStats } from './icons';
import { useEffect, useRef, useState } from 'react';
import { cn } from '@/lib/utils';
import { useMeta } from '@/lib/hooks';
import { useStore, actions } from '@/lib/store';
import { longDay, todayRo, roDateTime } from '@/lib/format';
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
  { to: '/piramida', label: 'Piramida', icon: IconPyramid },
  { to: '/statistici', label: 'Statistici', icon: IconStats },
];

const MORE = [
  { to: '/edge', label: 'Edge', d: 'Valoare și siguranță', icon: Crosshair },
  { to: '/builder', label: 'Builder', d: 'Combinații pe un meci', icon: Blocks },
  { to: '/setari', label: 'Setări', d: 'Bancă, temă, praguri', icon: Settings },
];

function StatusDot() {
  const meta = useMeta();
  const m = meta.data;
  const color = !m ? 'bg-muted-foreground' : m.status === 'ok' ? 'bg-emerald-500' : m.status === 'stale' ? 'bg-rose-500' : 'bg-amber-500';
  const label = !m ? 'stare necunoscută' : m.status === 'ok' ? 'date la zi' : m.status === 'stale' ? 'date vechi' : 'parțial';
  const q = m?.quota?.effective_remaining;
  return (
    <div className="flex items-center gap-2 text-xs text-muted-foreground" title={m?.generated_at ? `Actualizat ${roDateTime(m.generated_at)} (ora României)` : ''}>
      <span className={cn('h-2 w-2 rounded-full', color)} />
      <span className="hidden sm:inline">{label}{m?.generated_at ? ` · ${roDateTime(m.generated_at)}` : ''}</span>
      {q != null && <span className="hidden md:inline">· API {q.toLocaleString('ro-RO')}/{(m?.quota?.daily_quota ?? 7500).toLocaleString('ro-RO')}</span>}
      {m?._source === 'legacy' && <span className="rounded bg-warn px-1 text-[10px] text-warn" title="Pipeline-ul nou nu a publicat încă ./api; se folosesc fișierele vechi din ./data">date v2</span>}
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
      <header className="relative z-30 shrink-0 pt-[var(--safe-top)] border-b border-[hsl(var(--glass-border))] bg-background">
        <div className="mx-auto flex h-12 max-w-6xl items-center gap-3 px-4 md:px-6">
          <Link to="/" className="flex items-center gap-2 font-extrabold tracking-tight">
            <span className="brand-gradient flex h-8 w-8 items-center justify-center rounded-xl text-[13px] font-black text-white">BP</span>
            <span className="text-[17px] tracking-[-0.04em]">BetPredict</span>
            <span className="rounded-full bg-primary/15 px-2 py-0.5 text-[10px] font-extrabold text-primary ring-1 ring-primary/25">3.0</span>
            <span className="hidden rounded-full bg-muted px-2 py-0.5 text-[10px] font-bold text-muted-foreground sm:inline">pe hârtie</span>
          </Link>
          <nav className="ml-4 hidden items-center gap-1 md:flex">
            {NAV.map((n) => (
              <NavLink key={n.to} to={n.to} end={n.end} className={({ isActive }) => cn('btn btn-ghost', isActive && 'bg-primary/12 text-primary ring-1 ring-primary/25')}>
                <n.icon className="h-4 w-4" />{n.label}
              </NavLink>
            ))}
            {MORE.filter((m) => m.to !== '/setari').map((m) => (
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
      <main className="mx-auto max-w-6xl px-4 pb-[calc(96px+var(--safe-bottom))] pt-4 md:px-6 md:py-6">
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
              className={({ isActive }) => cn('relative z-0 flex min-h-[48px] touch-manipulation select-none flex-col items-center justify-center gap-0.5 text-[10px] font-bold', isActive ? 'nav-item-on' : 'text-muted-foreground')}>
              {({ isActive }) => (<>
                {isActive && <span aria-hidden className="nav-blob" />}
                <n.icon className="pointer-events-none relative h-[20px] w-[20px]" strokeWidth={isActive ? 2.4 : 1.8} />
                <span className="pointer-events-none relative">{n.label}</span>
              </>)}
            </NavLink>
          ))}
          <button type="button" aria-expanded={more} aria-label="Mai mult" onClick={() => setMore(true)}
            className={cn('relative z-0 flex min-h-[48px] touch-manipulation select-none flex-col items-center justify-center gap-0.5 text-[10px] font-bold', moreOn || more ? 'nav-item-on' : 'text-muted-foreground')}>
            {(moreOn || more) && <span aria-hidden className="nav-blob" />}
            <Ellipsis className="pointer-events-none relative h-[20px] w-[20px]" strokeWidth={moreOn || more ? 2.4 : 1.8} />
            <span className="pointer-events-none relative">Mai mult</span>
          </button>
        </div>
      </nav>
      <Sheet open={more} onClose={() => setMore(false)} title="Mai mult" subtitle="Edge, Builder și setări">
        <nav className="grid gap-2" aria-label="Destinații secundare">
          {MORE.map((m) => {
            const on = loc.pathname === m.to || loc.pathname.startsWith(`${m.to}/`);
            return (
              <Link key={m.to} to={m.to} onClick={() => setMore(false)} className={cn('flex min-h-[56px] items-center gap-3 rounded-2xl px-3', on ? 'bg-primary/15 text-primary' : 'bg-[hsl(var(--elevated))]')}>
                <m.icon className="h-5 w-5 shrink-0" />
                <span className="min-w-0"><span className="block font-extrabold">{m.label}</span><span className={cn('block text-xs', on ? 'text-primary/80' : 'text-muted-foreground')}>{m.d}</span></span>
              </Link>
            );
          })}
        </nav>
      </Sheet>
      <WinWatcher />
    </div>
  );
}
