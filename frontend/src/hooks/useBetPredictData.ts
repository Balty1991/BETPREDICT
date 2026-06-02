import { useState, useEffect, useCallback } from 'react';
import type { BetPredictData, Signal, JournalEntry, ValueBet, PerformanceHeatmap } from '@/types/betpredict';

const BASE = './data';

async function fetchJSON<T>(path: string, fallback: T): Promise<T> {
  try {
    const r = await fetch(`${BASE}/${path}?_=${Date.now()}`);
    if (!r.ok) return fallback;
    return await r.json();
  } catch {
    return fallback;
  }
}

export function useBetPredictData(): BetPredictData {
  const [signals, setSignals] = useState<Signal[]>([]);
  const [journal, setJournal] = useState<JournalEntry[]>([]);
  const [valueBets, setValueBets] = useState<ValueBet[]>([]);
  const [heatmap, setHeatmap] = useState<PerformanceHeatmap>({});
  const [updatedAt, setUpdatedAt] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [sigData, journalData, vbData, hmData] = await Promise.all([
        fetchJSON<Record<string, unknown>>('signals.json', {}),
        fetchJSON<Record<string, unknown>>('selection_journal.json', {}),
        fetchJSON<Record<string, unknown>>('value_bets.json', {}),
        fetchJSON<Record<string, unknown>>('performance_heatmap.json', {}),
      ]);

      const rawSignals = Array.isArray(sigData.signals) ? sigData.signals as Signal[] : [];
      setSignals(rawSignals);
      setUpdatedAt((sigData.updated_at as string) ?? null);

      const rawJournal = Array.isArray(journalData.results) ? journalData.results as JournalEntry[] : [];
      setJournal(rawJournal);

      const rawVB = Array.isArray(vbData.results) ? vbData.results as ValueBet[] : [];
      setValueBets(rawVB);

      setHeatmap(hmData as PerformanceHeatmap);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Eroare la încărcare date');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  return { signals, journal, valueBets, heatmap, updatedAt, loading, error, refresh: load };
}
