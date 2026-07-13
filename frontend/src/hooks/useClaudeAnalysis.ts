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

export interface ClaudeAnalysisData {
  verdictsByEvent: Map<string, ClaudeVerdict>;
  accumulators: ClaudeAccumulator[];
  updatedAt: string | null;
  loading: boolean;
  refresh: () => void;
}

export function useClaudeAnalysis(): ClaudeAnalysisData {
  const [verdictsByEvent, setVerdictsByEvent] = useState<Map<string, ClaudeVerdict>>(new Map());
  const [accumulators, setAccumulators] = useState<ClaudeAccumulator[]>([]);
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

    const tickets = Array.isArray(accData.tickets) ? (accData.tickets as ClaudeAccumulator[]) : [];
    setAccumulators(tickets);

    setLoading(false);
  }, []);

  useEffect(() => { load(); }, [load]);

  return { verdictsByEvent, accumulators, updatedAt, loading, refresh: load };
}
