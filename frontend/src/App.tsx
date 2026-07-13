import React, { Suspense, lazy, useState } from 'react';
import { LayoutDashboard, Zap, BarChart3, RefreshCw, Sun, Moon } from 'lucide-react';
import { DataProvider, useAppData } from '@/context/DataContext';
import { isQualifiedVerdict } from '@/utils/filters';
import './App.css';

const Dashboard = lazy(() => import('@/pages/Dashboard').then(m => ({ default: m.Dashboard })));
const PredictionsPage = lazy(() => import('@/pages/PredictionsPage').then(m => ({ default: m.PredictionsPage })));
const StatisticsPage = lazy(() => import('@/pages/StatisticsPage').then(m => ({ default: m.StatisticsPage })));

export type Theme = 'dark' | 'light';

type Page = 'dashboard' | 'predictions' | 'stats';

const tabs: { id: Page; label: string; icon: React.ReactNode }[] = [
  { id: 'dashboard', label: 'Dash', icon: <LayoutDashboard className="w-5 h-5" /> },
  { id: 'predictions', label: 'Predicții', icon: <Zap className="w-5 h-5" /> },
  { id: 'stats', label: 'Stats', icon: <BarChart3 className="w-5 h-5" /> },
];

function PageFallback() {
  return (
    <div className="flex items-center justify-center py-24">
      <RefreshCw className="w-6 h-6 animate-spin" style={{ color: 'var(--bp-dim)' }} />
    </div>
  );
}

function AppShell() {
  const [page, setPage] = useState<Page>('dashboard');
  const [theme, setTheme] = useState<Theme>('dark');
  const { claude, loading, refreshAll } = useAppData();
  const picksCount = Array.from(claude.verdictsByEvent.values()).filter(isQualifiedVerdict).length;
  const light = theme === 'light';

  return (
    <div
      className={`min-h-screen ${light ? 'bp-light' : 'bp-dark'}`}
      style={{ background: 'var(--bp-bg)' }}
    >
      {/* Ambient gradients */}
      <div className="fixed inset-0 pointer-events-none z-0">
        <div className="absolute inset-0 bg-[radial-gradient(ellipse_80%_35%_at_50%_-5%,rgba(0,232,122,.04)_0%,transparent_65%)]" />
        <div className="absolute inset-0 bg-[radial-gradient(ellipse_50%_30%_at_90%_80%,rgba(74,158,255,.03)_0%,transparent_55%)]" />
      </div>

      {/* Header */}
      <header
        className="fixed top-0 inset-x-0 z-30 h-14 backdrop-blur-xl border-b"
        style={{ background: 'var(--bp-header)', borderColor: 'var(--bp-border)' }}
      >
        <div className="max-w-lg mx-auto h-full flex items-center justify-between px-4">
          <div className="flex items-center gap-2.5">
            <div
              className="w-9 h-9 rounded-xl bg-gradient-to-br from-[#00e87a] to-[#4a9eff] flex items-center justify-center"
              style={{ boxShadow: '0 0 18px -2px rgba(0,232,122,0.55), 0 0 3px 0 rgba(74,158,255,0.4)' }}
            >
              <span className="text-[#05080f] font-black text-base">B</span>
            </div>
            <div>
              <h1 className="text-base font-extrabold bg-gradient-to-r from-[#00e87a] to-[#4a9eff] bg-clip-text text-transparent leading-none tracking-tight">
                BETPREDICT
              </h1>
              <p className="text-[9px] font-bold uppercase tracking-[0.2em]" style={{ color: 'var(--bp-dim)' }}>
                Pro · Sports AI
              </p>
            </div>
          </div>
          <div className="flex items-center gap-1">
            <button
              onClick={refreshAll}
              aria-label="Reîmprospătează datele"
              className="p-2 rounded-lg transition-colors"
              style={{ color: 'var(--bp-muted)' }}
            >
              <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
            </button>
            <button
              onClick={() => setTheme(t => t === 'dark' ? 'light' : 'dark')}
              aria-label={light ? 'Comută la tema întunecată' : 'Comută la tema deschisă'}
              className="p-2 rounded-lg transition-colors"
              style={{ color: 'var(--bp-muted)' }}
            >
              {light ? <Moon className="w-4 h-4" /> : <Sun className="w-4 h-4" />}
            </button>
          </div>
        </div>
      </header>

      {/* Content */}
      <main className="relative z-10 max-w-lg mx-auto pt-14 pb-20 px-3">
        <Suspense fallback={<PageFallback />}>
          {page === 'dashboard' && <Dashboard onNavigate={setPage} />}
          {page === 'predictions' && <PredictionsPage />}
          {page === 'stats' && <StatisticsPage />}
        </Suspense>
      </main>

      {/* Bottom Nav */}
      <nav
        className="fixed bottom-0 inset-x-0 z-30 backdrop-blur-xl border-t"
        style={{ background: 'var(--bp-nav)', borderColor: 'var(--bp-border)' }}
      >
        <div className="max-w-lg mx-auto flex items-start justify-around pt-1.5 pb-2">
          {tabs.map(t => (
            <button
              key={t.id}
              onClick={() => setPage(t.id)}
              className="flex flex-col items-center gap-0.5 py-1.5 px-3 rounded-xl transition-all"
            >
              <div className="relative">
                <div
                  className={`transition-transform ${page === t.id ? 'scale-110' : ''}`}
                  style={{ color: page === t.id ? '#00e87a' : 'var(--bp-dim)' }}
                >
                  {t.icon}
                </div>
                {t.id === 'predictions' && picksCount > 0 && (
                  <span className="absolute -top-1 -right-1 w-4 h-4 rounded-full bg-[#00e87a] text-[#05080f] text-[8px] font-black flex items-center justify-center">
                    {picksCount}
                  </span>
                )}
              </div>
              <span
                className="text-[9px] font-bold uppercase tracking-wider transition-colors"
                style={{ color: page === t.id ? '#00e87a' : 'var(--bp-dim)' }}
              >
                {t.label}
              </span>
            </button>
          ))}
        </div>
      </nav>
    </div>
  );
}

function App() {
  return (
    <DataProvider>
      <AppShell />
    </DataProvider>
  );
}

export default App;
