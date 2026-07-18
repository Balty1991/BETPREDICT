import { useCallback, useEffect, useState } from 'react';
import type { ClaudeVerdict, SavedPrediction } from '@/types/betpredict';
import { settleMarket } from '@/utils/settlement';

const STORAGE_KEY = 'betpredict_saved_predictions_v1';

interface RecentResultRow {
  id: number;
  status: string;
  home_score: number | null;
  away_score: number | null;
}

export function verdictKey(eventId: number | string, market: string): string {
  return `${eventId}_${market}`;
}

function loadAll(): SavedPrediction[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    return raw ? (JSON.parse(raw) as SavedPrediction[]) : [];
  } catch {
    return [];
  }
}

function persist(list: SavedPrediction[]): void {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(list));
  } catch {
    // localStorage unavailable/full — saved predictions won't persist this session
  }
}

export interface SavedPredictionsData {
  predictions: SavedPrediction[];
  save: (v: ClaudeVerdict) => void;
  saveMany: (vs: ClaudeVerdict[]) => void;
  remove: (id: string) => void;
  isSaved: (eventId: number | string, market: string) => boolean;
}

function toSavedEntry(v: ClaudeVerdict): SavedPrediction {
  return {
    id: verdictKey(v.event_id, v.market), event_id: v.event_id, home_team: v.home_team, away_team: v.away_team,
    league: v.league, event_date: v.event_date ?? '', market: v.market, market_label: v.market_label,
    probability: v.probability, risk_tier: v.risk_tier, odds: v.odds ?? 0, odds_is_market: v.odds_is_market,
    saved_at: new Date().toISOString(), status: 'pending',
  };
}

export function useSavedPredictions(): SavedPredictionsData {
  const [predictions, setPredictions] = useState<SavedPrediction[]>(() => loadAll());

  const save = useCallback((v: ClaudeVerdict) => {
    setPredictions(prev => {
      const id = verdictKey(v.event_id, v.market);
      if (prev.some(p => p.id === id)) return prev;
      const next = [toSavedEntry(v), ...prev];
      persist(next);
      return next;
    });
  }, []);

  // Salvare în masă (auto-tracking): adaugă toate verdictele care nu sunt deja
  // salvate, într-o singură scriere. Cele deja prezente sunt ignorate (idempotent).
  const saveMany = useCallback((vs: ClaudeVerdict[]) => {
    setPredictions(prev => {
      const existing = new Set(prev.map(p => p.id));
      const additions: SavedPrediction[] = [];
      for (const v of vs) {
        const id = verdictKey(v.event_id, v.market);
        if (existing.has(id)) continue;
        existing.add(id);
        additions.push(toSavedEntry(v));
      }
      if (additions.length === 0) return prev;
      const next = [...additions, ...prev];
      persist(next);
      return next;
    });
  }, []);

  const remove = useCallback((id: string) => {
    setPredictions(prev => {
      const next = prev.filter(p => p.id !== id);
      persist(next);
      return next;
    });
  }, []);

  const isSaved = useCallback(
    (eventId: number | string, market: string) => predictions.some(p => p.id === verdictKey(eventId, market)),
    [predictions]
  );

  // Auto-settle pending saves against the rolling 14-day finished-results feed. Runs once
  // per hook mount — cheap, and re-saving/removing doesn't need to re-trigger it.
  useEffect(() => {
    let cancelled = false;
    fetch(`./data/recent_results.json?_=${Date.now()}`)
      .then(r => (r.ok ? r.json() : null))
      .then((data: { results?: RecentResultRow[] } | null) => {
        if (cancelled || !data?.results) return;
        const byId = new Map(data.results.map(r => [String(r.id), r]));
        setPredictions(prev => {
          let changed = false;
          const next = prev.map(p => {
            if (p.status !== 'pending') return p;
            const res = byId.get(String(p.event_id));
            if (!res || res.status !== 'finished' || res.home_score == null || res.away_score == null) return p;
            changed = true;
            const outcome = settleMarket(p.market, res.home_score, res.away_score);
            return { ...p, status: outcome, settled_at: new Date().toISOString(), final_score: `${res.home_score}-${res.away_score}` };
          });
          if (changed) persist(next);
          return changed ? next : prev;
        });
      })
      .catch(() => { /* offline or file missing — settlement retried on next mount */ });
    return () => { cancelled = true; };
  }, []);

  return { predictions, save, saveMany, remove, isSaved };
}
