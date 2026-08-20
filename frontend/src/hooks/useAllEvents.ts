import { useState, useEffect, useCallback } from 'react';
import type {
  RawEvent, PredictionRow, TeamFormEntry, H2HEntry, LeagueInfo, EventDeepInfo,
} from '@/types/betpredict';

const BASE = './data';

type JsonResponse<T> = { data: T; ok: boolean };

async function fetchJSON<T>(path: string, fallback: T): Promise<JsonResponse<T>> {
  try {
    const r = await fetch(`${BASE}/${path}?_=${Date.now()}`, { cache: 'no-store' });
    if (!r.ok) return { data: fallback, ok: false };
    return { data: await r.json() as T, ok: true };
  } catch {
    return { data: fallback, ok: false };
  }
}

function eventRows(data: Record<string, unknown>): RawEvent[] {
  return Array.isArray(data.results) ? (data.results as RawEvent[]) : [];
}

function eventsFromPredictions(data: Record<string, unknown>): RawEvent[] {
  const rows = Array.isArray(data.results) ? (data.results as PredictionRow[]) : [];
  const events: RawEvent[] = [];
  for (const row of rows) {
    const event = row.event;
    if (!event || event.id == null) continue;
    // Schema de predicții numește cheia `id`, în timp ce UI-ul folosește
    // `event_id`; păstrăm ambele fără să pierdem câmpurile disponibile.
    events.push({ ...event, event_id: event.id } as RawEvent);
  }
  return events;
}

export type EventSource = 'events_window' | 'matches_today' | 'predictions_fallback' | 'unavailable';

export interface AllEventsData {
  events: RawEvent[];
  predictionsByEvent: Map<string, PredictionRow>;
  teamForm: Map<string, TeamFormEntry>;
  h2hByEvent: Map<string, H2HEntry>;
  leaguesById: Map<number, LeagueInfo>;
  deepByEvent: Map<string, EventDeepInfo>;
  updatedAt: string | null;
  eventSource: EventSource;
  loading: boolean;
  error: string | null;
  refresh: () => void;
}

/**
 * Încarcă o singură dată toate datele folosite de pagini. `events_window.json`
 * este sursa preferată, însă endpointul exact poate fi temporar gol chiar când
 * `matches_today.json` și `predictions.json` au date valide. În acea situație
 * alegem o sursă publicată mai largă, în loc să afișăm un fals „zero evenimente”.
 */
export function useAllEvents(): AllEventsData {
  const [events, setEvents] = useState<RawEvent[]>([]);
  const [predictionsByEvent, setPredictionsByEvent] = useState<Map<string, PredictionRow>>(new Map());
  const [teamForm, setTeamForm] = useState<Map<string, TeamFormEntry>>(new Map());
  const [h2hByEvent, setH2hByEvent] = useState<Map<string, H2HEntry>>(new Map());
  const [leaguesById, setLeaguesById] = useState<Map<number, LeagueInfo>>(new Map());
  const [deepByEvent, setDeepByEvent] = useState<Map<string, EventDeepInfo>>(new Map());
  const [updatedAt, setUpdatedAt] = useState<string | null>(null);
  const [eventSource, setEventSource] = useState<EventSource>('unavailable');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [
        windowResponse, todayResponse, predsResponse, leagueResponse, formResponse, h2hResponse,
        statsResponse, lineupsResponse, playerStatsResponse,
      ] = await Promise.all([
        fetchJSON<Record<string, unknown>>('events_window.json', {}),
        fetchJSON<Record<string, unknown>>('matches_today.json', {}),
        fetchJSON<Record<string, unknown>>('predictions.json', {}),
        fetchJSON<Record<string, unknown>>('league_lookup.json', {}),
        fetchJSON<Record<string, unknown>>('team_form_cache.json', {}),
        fetchJSON<Record<string, unknown>>('h2h_context.json', {}),
        fetchJSON<Record<string, unknown>>('event_stats.json', {}),
        fetchJSON<Record<string, unknown>>('event_lineups.json', {}),
        fetchJSON<Record<string, unknown>>('event_player_stats.json', {}),
      ]);

      const windowEvents = eventRows(windowResponse.data);
      const todayEvents = eventRows(todayResponse.data);
      const predictionEvents = eventsFromPredictions(predsResponse.data);
      const source: EventSource = windowEvents.length > 0
        ? 'events_window'
        : todayEvents.length > 0
          ? 'matches_today'
          : predictionEvents.length > 0
            ? 'predictions_fallback'
            : 'unavailable';
      // Păstrăm prioritatea sursei cu calendarul cel mai precis, dar completăm
      // uniunea cu meciurile care au deja predicții. Astfel, răspunsul temporar
      // incomplet al unui endpoint nu ascunde meciuri analizabile din celelalte.
      const seenEventIds = new Set<string>();
      const rawEvents = [
        ...(source === 'events_window' ? windowEvents : []),
        ...todayEvents,
        ...predictionEvents,
      ].filter((event) => {
        const id = event.id ?? event.event_id;
        if (id == null) return false;
        const key = String(id);
        if (seenEventIds.has(key)) return false;
        seenEventIds.add(key);
        return true;
      });

      setEvents(rawEvents);
      setEventSource(source);
      setUpdatedAt(
        (source === 'events_window' ? windowResponse.data.updated_at : undefined) as string
        ?? (source === 'matches_today' ? todayResponse.data.updated_at : undefined) as string
        ?? (predsResponse.data.updated_at as string)
        ?? null,
      );
      if (source === 'unavailable') {
        setError('Nu s-a putut încărca nicio sursă de evenimente. Verifică actualizarea datelor, nu filtrele din pagină.');
      }

      const predMap = new Map<string, PredictionRow>();
      const preds = Array.isArray(predsResponse.data.results) ? (predsResponse.data.results as PredictionRow[]) : [];
      for (const p of preds) {
        const eid = p.event?.id;
        if (eid != null) predMap.set(String(eid), p);
      }
      setPredictionsByEvent(predMap);

      const leagueMap = new Map<number, LeagueInfo>();
      const byId = (leagueResponse.data.by_id ?? {}) as Record<string, LeagueInfo>;
      for (const [k, v] of Object.entries(byId)) leagueMap.set(Number(k), v);
      setLeaguesById(leagueMap);

      const formMap = new Map<string, TeamFormEntry>();
      const teams = (formResponse.data.teams ?? {}) as Record<string, TeamFormEntry>;
      for (const [k, v] of Object.entries(teams)) formMap.set(k, v);
      setTeamForm(formMap);

      const h2hMap = new Map<string, H2HEntry>();
      const h2hResults = Array.isArray(h2hResponse.data.results) ? (h2hResponse.data.results as H2HEntry[]) : [];
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
      mergeResource(statsResponse.data, 'stats');
      mergeResource(lineupsResponse.data, 'lineups');
      mergeResource(playerStatsResponse.data, 'playerStats');
      setDeepByEvent(deepMap);
    } catch (e) {
      setEventSource('unavailable');
      setError(e instanceof Error ? e.message : 'Eroare la încărcare evenimente');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  return {
    events, predictionsByEvent, teamForm, h2hByEvent, leaguesById, deepByEvent,
    updatedAt, eventSource, loading, error, refresh: load,
  };
}
