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
const StatsPage = lazy(() => import('@/pages/StatsPage'));
const EdgePage = lazy(() => import('@/pages/EdgePage'));
const BuilderPage = lazy(() => import('@/pages/BuilderPage'));
const SettingsPage = lazy(() => import('@/pages/SettingsPage'));

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
            <Route path="statistici" element={<StatsPage />} />
            <Route path="edge" element={<EdgePage />} />
            <Route path="builder" element={<BuilderPage />} />
            <Route path="setari" element={<SettingsPage />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Route>
        </Routes>
      </Suspense>
      <Toaster theme={theme} position="top-center" richColors />
    </HashRouter>
  );
}
