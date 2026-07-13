import { useState, useEffect, useCallback } from 'react';
import type {
  RawEvent, PredictionRow, TeamFormEntry, H2HEntry, LeagueInfo, EventDeepInfo,
} from '@/types/betpredict';

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

export interface AllEventsData {
  events: RawEvent[];
  predictionsByEvent: Map<string, PredictionRow>;
  teamForm: Map<string, TeamFormEntry>;
  h2hByEvent: Map<string, H2HEntry>;
  leaguesById: Map<number, LeagueInfo>;
  deepByEvent: Map<string, EventDeepInfo>;
  updatedAt: string | null;
  loading: boolean;
  error: string | null;
  refresh: () => void;
}

export function useAllEvents(): AllEventsData {
  const [events, setEvents] = useState<RawEvent[]>([]);
  const [predictionsByEvent, setPredictionsByEvent] = useState<Map<string, PredictionRow>>(new Map());
  const [teamForm, setTeamForm] = useState<Map<string, TeamFormEntry>>(new Map());
  const [h2hByEvent, setH2hByEvent] = useState<Map<string, H2HEntry>>(new Map());
  const [leaguesById, setLeaguesById] = useState<Map<number, LeagueInfo>>(new Map());
  const [deepByEvent, setDeepByEvent] = useState<Map<string, EventDeepInfo>>(new Map());
  const [updatedAt, setUpdatedAt] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [
        eventsData, predsData, leagueData, formData, h2hData,
        statsData, lineupsData, playerStatsData,
      ] = await Promise.all([
        fetchJSON<Record<string, unknown>>('events_window.json', {}),
        fetchJSON<Record<string, unknown>>('predictions.json', {}),
        fetchJSON<Record<string, unknown>>('league_lookup.json', {}),
        fetchJSON<Record<string, unknown>>('team_form_cache.json', {}),
        fetchJSON<Record<string, unknown>>('h2h_context.json', {}),
        fetchJSON<Record<string, unknown>>('event_stats.json', {}),
        fetchJSON<Record<string, unknown>>('event_lineups.json', {}),
        fetchJSON<Record<string, unknown>>('event_player_stats.json', {}),
      ]);

      const rawEvents = Array.isArray(eventsData.results) ? (eventsData.results as RawEvent[]) : [];
      setEvents(rawEvents);
      setUpdatedAt((eventsData.updated_at as string) ?? null);

      const predMap = new Map<string, PredictionRow>();
      const preds = Array.isArray(predsData.results) ? (predsData.results as PredictionRow[]) : [];
      for (const p of preds) {
        const eid = p.event?.id;
        if (eid != null) predMap.set(String(eid), p);
      }
      setPredictionsByEvent(predMap);

      const leagueMap = new Map<number, LeagueInfo>();
      const byId = (leagueData.by_id ?? {}) as Record<string, LeagueInfo>;
      for (const [k, v] of Object.entries(byId)) leagueMap.set(Number(k), v);
      setLeaguesById(leagueMap);

      const formMap = new Map<string, TeamFormEntry>();
      const teams = (formData.teams ?? {}) as Record<string, TeamFormEntry>;
      for (const [k, v] of Object.entries(teams)) formMap.set(k, v);
      setTeamForm(formMap);

      const h2hMap = new Map<string, H2HEntry>();
      const h2hResults = Array.isArray(h2hData.results) ? (h2hData.results as H2HEntry[]) : [];
      for (const h of h2hResults) {
        if (h.event_id != null) h2hMap.set(String(h.event_id), h);
      }
      setH2hByEvent(h2hMap);

      const deepMap = new Map<string, EventDeepInfo>();
      const mergeResource = (data: Record<string, unknown>, key: keyof EventDeepInfo) => {
        const list = Array.isArray(data.results) ? (data.results as Array<Record<string, unknown>>) : [];
        for (const row of list) {
          const eid = row.event_id as number | string | undefined;
          if (eid == null) continue;
          const eidStr = String(eid);
          const entry = deepMap.get(eidStr) ?? {};
          entry[key] = (row.raw ?? row) as never;
          deepMap.set(eidStr, entry);
        }
      };
      mergeResource(statsData, 'stats');
      mergeResource(lineupsData, 'lineups');
      mergeResource(playerStatsData, 'playerStats');
      setDeepByEvent(deepMap);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Eroare la încărcare evenimente');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  return {
    events, predictionsByEvent, teamForm, h2hByEvent, leaguesById, deepByEvent,
    updatedAt, loading, error, refresh: load,
  };
}
