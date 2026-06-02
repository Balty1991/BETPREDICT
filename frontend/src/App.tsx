import React, { useState } from 'react';
import { LayoutDashboard, Zap, BarChart3, Shield, RefreshCw } from 'lucide-react';
import { Dashboard } from '@/pages/Dashboard';
import { PredictionsPage } from '@/pages/PredictionsPage';
import { StatisticsPage } from '@/pages/StatisticsPage';
import { PremiumPage } from '@/pages/PremiumPage';
import { useBetPredictData } from '@/hooks/useBetPredictData';
import { filteredSignals, vbSetFromList } from '@/utils/filters';
import './App.css';

type Page = 'dashboard' | 'predictions' | 'stats' | 'premium';

const tabs: { id: Page; label: string; icon: React.ReactNode }[] = [
  { id: 'dashboard', label: 'Dash', icon: <LayoutDashboard className="w-5 h-5" /> },
  { id: 'predictions', label: 'Predicții', icon: <Zap className="w-5 h-5" /> },
  { id: 'stats', label: 'Stats', icon: <BarChart3 className="w-5 h-5" /> },
  { id: 'premium', label: 'Premium', icon: <Shield className="w-5 h-5" /> },
];

function App() {
  const [page, setPage] = useState<Page>('dashboard');
  const { signals, valueBets, loading, refresh } = useBetPredictData();
  const picksCount = filteredSignals(signals, vbSetFromList(valueBets)).length;

  return (
    <div className="min-h-screen bg-[#05080f]">
      <div className="fixed inset-0 pointer-events-none z-0">
        <div className="absolute inset-0 bg-[radial-gradient(ellipse_80%_35%_at_50%_-5%,rgba(0,232,122,.04)_0%,transparent_65%)]" />
        <div className="absolute inset-0 bg-[radial-gradient(ellipse_50%_30%_at_90%_80%,rgba(74,158,255,.03)_0%,transparent_55%)]" />
      </div>

      <header className="fixed top-0 inset-x-0 z-30 h-14 bg-[#05080f]/90 backdrop-blur-xl border-b border-white/[0.06]">
        <div className="max-w-lg mx-auto h-full flex items-center justify-between px-4">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-xl bg-gradient-to-br from-[#00e87a] to-[#4a9eff] flex items-center justify-center">
              <span className="text-[#05080f] font-black text-sm">B</span>
            </div>
            <div>
              <h1 className="text-sm font-extrabold bg-gradient-to-r from-[#00e87a] to-[#4a9eff] bg-clip-text text-transparent leading-none">
                BETPREDICT
              </h1>
              <p className="text-[7px] text-[#303d57] font-bold uppercase tracking-[0.2em]">Pro · Sports AI</p>
            </div>
          </div>
          <button onClick={refresh} className="p-2 rounded-lg text-[#6b7a9e] hover:text-white transition-colors">
            <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
          </button>
        </div>
      </header>

      <main className="relative z-10 max-w-lg mx-auto pt-14 pb-20 px-3">
        {page === 'dashboard' && <Dashboard />}
        {page === 'predictions' && <PredictionsPage />}
        {page === 'stats' && <StatisticsPage />}
        {page === 'premium' && <PremiumPage />}
      </main>

      <nav className="fixed bottom-0 inset-x-0 z-30 bg-[#05080f]/95 backdrop-blur-xl border-t border-white/[0.06]">
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
                  style={{ color: page === t.id ? '#00e87a' : '#303d57' }}
                >
                  {t.icon}
                </div>
                {t.id === 'predictions' && picksCount > 0 && (
                  <span className="absolute -top-1 -right-1 w-4 h-4 rounded-full bg-[#00e87a] text-[#05080f] text-[8px] font-black flex items-center justify-center">
                    {picksCount}
                  </span>
                )}
              </div>
              <span className={`text-[9px] font-bold uppercase tracking-wider transition-colors ${
                page === t.id ? 'text-[#00e87a]' : 'text-[#303d57]'
              }`}>
                {t.label}
              </span>
            </button>
          ))}
        </div>
      </nav>
    </div>
  );
}

export default App;
