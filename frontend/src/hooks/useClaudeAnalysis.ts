import { useState, useEffect, useCallback } from 'react';
import type { ClaudeVerdict, ClaudeAccumulator } from '@/types/betpredict';

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

/** Chei disponibile în tickets_by_period (vezi ACCUMULATOR_PERIODS în src/claude_analysis.py). */
export type AccumulatorPeriodKey = '7' | '10' | '30';

export interface ClaudeAnalysisData {
  verdictsByEvent: Map<string, ClaudeVerdict>;
  accumulatorsByPeriod: Record<AccumulatorPeriodKey, ClaudeAccumulator[]>;
  updatedAt: string | null;
  loading: boolean;
  refresh: () => void;
}

const EMPTY_PERIODS: Record<AccumulatorPeriodKey, ClaudeAccumulator[]> = { '7': [], '10': [], '30': [] };

export function useClaudeAnalysis(): ClaudeAnalysisData {
  const [verdictsByEvent, setVerdictsByEvent] = useState<Map<string, ClaudeVerdict>>(new Map());
  const [accumulatorsByPeriod, setAccumulatorsByPeriod] = useState<Record<AccumulatorPeriodKey, ClaudeAccumulator[]>>(EMPTY_PERIODS);
  const [updatedAt, setUpdatedAt] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    const [predsData, accData] = await Promise.all([
      fetchJSON<Record<string, unknown>>('claude_predictions.json', {}),
      fetchJSON<Record<string, unknown>>('claude_accumulators.json', {}),
    ]);

    const results = Array.isArray(predsData.results) ? (predsData.results as ClaudeVerdict[]) : [];
    const map = new Map<string, ClaudeVerdict>();
    for (const v of results) {
      if (v.event_id != null) map.set(String(v.event_id), v);
    }
    setVerdictsByEvent(map);
    setUpdatedAt((predsData.updated_at as string) ?? null);

    const byPeriod = accData.tickets_by_period as Record<string, ClaudeAccumulator[]> | undefined;
    setAccumulatorsByPeriod(byPeriod ? { ...EMPTY_PERIODS, ...byPeriod } : EMPTY_PERIODS);

    setLoading(false);
  }, []);

  useEffect(() => { load(); }, [load]);

  return { verdictsByEvent, accumulatorsByPeriod, updatedAt, loading, refresh: load };
}
