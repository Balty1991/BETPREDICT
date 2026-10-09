import { NavLink, Outlet, Link, useLocation } from 'react-router';
import { Home, ListChecks, Triangle, BarChart3, Settings, Moon, Sun } from 'lucide-react';
import { useEffect } from 'react';
import { cn } from '@/lib/utils';
import { useMeta } from '@/lib/hooks';
import { useStore, actions } from '@/lib/store';
import { longDay, todayRo, roDateTime } from '@/lib/format';
import { Slip } from './Slip';

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
    <div className="min-h-screen pb-20 md:pb-0">
      <header className="sticky top-0 z-30 border-b bg-background/85 backdrop-blur">
        <div className="mx-auto flex h-14 max-w-6xl items-center gap-3 px-3 md:px-6">
          <Link to="/" className="flex items-center gap-2 font-extrabold tracking-tight">
            <span className="flex h-7 w-7 items-center justify-center rounded-lg bg-primary text-sm text-primary-foreground">BP</span>
            <span className="hidden sm:inline">BETPREDICT</span><span className="text-xs font-semibold text-primary">3.0</span>
          </Link>
          <nav className="ml-4 hidden items-center gap-1 md:flex">
            {NAV.map((n) => (
              <NavLink key={n.to} to={n.to} end={n.end} className={({ isActive }) => cn('btn btn-ghost', isActive && 'bg-accent text-foreground')}>
                <n.icon className="h-4 w-4" />{n.label}
              </NavLink>
            ))}
          </nav>
          <div className="ml-auto flex items-center gap-2">
            <div className="hidden text-xs capitalize text-muted-foreground lg:block">{longDay(todayRo())}</div>
            <StatusDot />
            <button className="btn btn-ghost px-2" aria-label="Temă" onClick={() => actions.setSettings({ theme: theme === 'dark' ? 'light' : 'dark' })}>
              {theme === 'dark' ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
            </button>
            <NavLink to="/setari" className={({ isActive }) => cn('btn btn-ghost px-2', isActive && 'bg-accent')} aria-label="Setări"><Settings className="h-4 w-4" /></NavLink>
          </div>
        </div>
      </header>
      <main className="mx-auto max-w-6xl px-3 py-4 md:px-6 md:py-6">
        <Outlet />
        <footer className="mt-10 border-t pt-4 text-center text-[11px] text-muted-foreground">
          Predicțiile sunt estimări statistice, nu garanții. Pariază responsabil, doar sume pe care îți permiți să le pierzi. 18+
        </footer>
      </main>
      <nav className="fixed inset-x-0 bottom-0 z-30 border-t bg-background/95 backdrop-blur md:hidden">
        <div className="grid grid-cols-4">
          {NAV.map((n) => (
            <NavLink key={n.to} to={n.to} end={n.end} className={({ isActive }) => cn('flex flex-col items-center gap-0.5 py-2 text-[11px]', isActive ? 'text-primary' : 'text-muted-foreground')}>
              <n.icon className="h-5 w-5" />{n.label}
            </NavLink>
          ))}
        </div>
      </nav>
      <Slip />
    </div>
  );
}
