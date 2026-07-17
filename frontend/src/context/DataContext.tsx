import React, { createContext, useCallback, useContext } from 'react';
import { useAllEvents, type AllEventsData } from '@/hooks/useAllEvents';
import { useClaudeAnalysis, type ClaudeAnalysisData } from '@/hooks/useClaudeAnalysis';
import { useV7Edge } from '@/hooks/useV7Edge';
import type { V7Edge } from '@/types/betpredict';

export interface AppData {
  events: AllEventsData;
  claude: ClaudeAnalysisData;
  v7Edge: Map<string, V7Edge>;
  loading: boolean;
  refreshAll: () => void;
}

const DataContext = createContext<AppData | null>(null);

/**
 * Fetches events (~7MB across 8 files) and Claude verdicts ONCE for the whole app,
 * instead of every page independently re-fetching them on every mount (previously:
 * App.tsx + Dashboard.tsx + PredictionsPage.tsx each called useClaudeAnalysis(), and
 * Dashboard.tsx + PredictionsPage.tsx each called useAllEvents() — a full re-fetch of
 * the same ~7MB on every tab switch since App.tsx unmounts the previous page).
 */
export const DataProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const events = useAllEvents();
  const claude = useClaudeAnalysis();
  const v7Edge = useV7Edge();

  const refreshAll = useCallback(() => {
    events.refresh();
    claude.refresh();
  }, [events, claude]);

  const value: AppData = { events, claude, v7Edge, loading: events.loading || claude.loading, refreshAll };
  return <DataContext.Provider value={value}>{children}</DataContext.Provider>;
};

export function useAppData(): AppData {
  const ctx = useContext(DataContext);
  if (!ctx) throw new Error('useAppData must be used within a DataProvider');
  return ctx;
}
