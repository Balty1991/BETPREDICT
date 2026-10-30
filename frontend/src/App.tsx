import { lazy, Suspense } from 'react';
import { HashRouter, Routes, Route, Navigate } from 'react-router';
import { Toaster } from 'sonner';
import { Layout } from '@/components/Layout';
import { Loading } from '@/components/kit';
import { useStore } from '@/lib/store';

const HomePage = lazy(() => import('@/pages/HomePage'));
const PredictionsPage = lazy(() => import('@/pages/PredictionsPage'));
const MatchPage = lazy(() => import('@/pages/MatchPage'));
const PyramidPage = lazy(() => import('@/pages/PyramidPage'));
const TicketsPage = lazy(() => import('@/pages/TicketsPage'));
const StatsPage = lazy(() => import('@/pages/StatsPage'));
const EdgePage = lazy(() => import('@/pages/EdgePage'));
const BuilderPage = lazy(() => import('@/pages/BuilderPage'));
const SettingsPage = lazy(() => import('@/pages/SettingsPage'));
const EgaluriPage = lazy(() => import('@/pages/EgaluriPage'));
const HistoryPage = lazy(() => import('@/pages/HistoryPage'));
const PontPage = lazy(() => import('@/pages/PontPage'));

// după prima afișare, când browserul e liber: descarcă în fundal paginile principale, ca navigarea să fie instantă.
// Pe date mobile economisite (Save-Data) sau conexiune 2G nu se face.
if (typeof window !== 'undefined') {
  const nc = (navigator as Navigator & { connection?: { saveData?: boolean; effectiveType?: string } }).connection;
  if (!nc?.saveData && !/2g/.test(nc?.effectiveType ?? '')) {
    const idle = (cb: () => void) => ('requestIdleCallback' in window ? window.requestIdleCallback(cb, { timeout: 4000 }) : setTimeout(cb, 2500));
    window.addEventListener('load', () => idle(() => {
      void import('@/pages/TicketsPage'); void import('@/pages/PredictionsPage'); void import('@/pages/PyramidPage');
      idle(() => { void import('@/pages/StatsPage'); void import('@/pages/MatchPage'); void import('@/pages/HistoryPage'); void import('@/pages/PontPage'); });
    }), { once: true });
  }
}

export default function App() {
  const theme = useStore((s) => s.settings.theme);
  return (
    <HashRouter>
      <Suspense fallback={<Loading />}>
        <Routes>
          <Route element={<Layout />}>
            <Route index element={<HomePage />} />
            <Route path="predictii" element={<PredictionsPage />} />
            <Route path="meci/:id" element={<MatchPage />} />
            <Route path="piramida" element={<PyramidPage />} />
            <Route path="bilete" element={<TicketsPage />} />
            <Route path="statistici" element={<StatsPage />} />
            <Route path="edge" element={<EdgePage />} />
            <Route path="builder" element={<BuilderPage />} />
            <Route path="setari" element={<SettingsPage />} />
            <Route path="istoric" element={<HistoryPage />} />
            <Route path="pont" element={<PontPage />} />
            <Route path="egaluri" element={<EgaluriPage />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Route>
        </Routes>
      </Suspense>
      <Toaster theme={theme} position="top-center" richColors />
    </HashRouter>
  );
}
