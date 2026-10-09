import { NavLink, Outlet, Link, useLocation } from 'react-router';
import { Home, ListChecks, Triangle, BarChart3, Settings, Moon, Sun } from 'lucide-react';
import { useEffect } from 'react';
import { cn } from '@/lib/utils';
import { useMeta } from '@/lib/hooks';
import { useStore, actions } from '@/lib/store';
import { longDay, todayRo, roDateTime } from '@/lib/format';
import { Slip } from './Slip';
import { ErrorBoundary } from './ErrorBoundary';
import { Suspense } from 'react';
import { Loading } from './kit';

const NAV = [
  { to: '/', label: 'Acasă', icon: Home, end: true },
  { to: '/predictii', label: 'Predicții', icon: ListChecks },
  { to: '/piramida', label: 'Piramida', icon: Triangle },
  { to: '/statistici', label: 'Statistici', icon: BarChart3 },
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
  useEffect(() => { document.documentElement.classList.toggle('dark', theme === 'dark'); }, [theme]);
  useEffect(() => { window.scrollTo(0, 0); }, [loc.pathname]);
  return (
    <div className="min-h-screen pb-[calc(128px+env(safe-area-inset-bottom))] md:pb-0">
      <header className="sticky top-0 z-30 pt-[env(safe-area-inset-top)] border-b border-[hsl(var(--glass-border))] bg-background/65 backdrop-blur-xl backdrop-saturate-150">
        <div className="mx-auto flex h-14 max-w-6xl items-center gap-3 px-4 md:px-6">
          <Link to="/" className="flex items-center gap-2 font-extrabold tracking-tight">
            <span className="brand-gradient flex h-9 w-9 items-center justify-center rounded-2xl text-sm font-black text-white shadow-[0_8px_20px_-8px_hsl(var(--primary)/0.8)]">BP</span>
            <span className="text-[18px] tracking-[-0.04em]">BetPredict</span><span className="rounded-full bg-primary/15 px-2 py-0.5 text-[10px] font-extrabold text-primary ring-1 ring-primary/25">3.0</span>
          </Link>
          <nav className="ml-4 hidden items-center gap-1 md:flex">
            {NAV.map((n) => (
              <NavLink key={n.to} to={n.to} end={n.end} className={({ isActive }) => cn('btn btn-ghost', isActive && 'bg-primary/12 text-primary ring-1 ring-primary/25')}>
                <n.icon className="h-4 w-4" />{n.label}
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
      </header>
      <main className="mx-auto max-w-6xl px-4 py-4 md:px-6 md:py-6">
        <div className="min-h-[calc(100vh-140px)]"><ErrorBoundary key={loc.pathname}><Suspense fallback={<Loading />}><div key={loc.pathname} className="page-enter"><Outlet /></div></Suspense></ErrorBoundary></div>
        <footer className="mt-10 border-t pt-4 text-center text-[11px] text-muted-foreground">
          Predicțiile sunt estimări statistice, nu garanții. Pariază responsabil, doar sume pe care îți permiți să le pierzi. 18+
        </footer>
      </main>
      <nav className="fixed inset-x-0 bottom-0 z-30 px-3 pb-[calc(10px+env(safe-area-inset-bottom))] md:hidden" aria-label="Navigare principală">
        <div className="glass mx-auto grid h-[62px] max-w-md grid-cols-4 gap-1 rounded-full border p-1.5">
          {NAV.map((n) => (
            <NavLink key={n.to} to={n.to} end={n.end} className={({ isActive }) => cn('press relative flex flex-col items-center justify-center gap-0.5 rounded-full text-[10.5px] font-bold transition-colors', isActive ? 'text-primary-foreground' : 'text-muted-foreground active:bg-accent/70')}>
              {({ isActive }) => (<>
                {isActive && <span aria-hidden className="nav-pill absolute inset-0 rounded-full" />}
                <n.icon className="relative h-[21px] w-[21px]" strokeWidth={isActive ? 2.5 : 2} />
                <span className="relative">{n.label}</span>
              </>)}
            </NavLink>
          ))}
        </div>
      </nav>
      <Slip />
    </div>
  );
}
