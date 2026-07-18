import { useCallback, useEffect, useState } from 'react';
import type { ClaudeAccumulator, SavedTicket } from '@/types/betpredict';
import { settleLegDetail, settleTicket, type FinishedResult } from '@/utils/settlement';

const STORAGE_KEY = 'betpredict_saved_tickets_v1';

export function ticketKey(legs: Array<{ event_id: number | string; market: string }>): string {
  return legs.map(l => `${l.event_id}_${l.market}`).sort().join('|');
}

function loadAll(): SavedTicket[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    return raw ? (JSON.parse(raw) as SavedTicket[]) : [];
  } catch {
    return [];
  }
}

function persist(list: SavedTicket[]): void {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(list));
  } catch {
    // localStorage unavailable/full — placed tickets won't persist this session
  }
}

export interface SavedTicketsData {
  tickets: SavedTicket[];
  save: (t: ClaudeAccumulator) => void;
  remove: (id: string) => void;
  isSaved: (t: ClaudeAccumulator) => boolean;
}

export function useSavedTickets(): SavedTicketsData {
  const [tickets, setTickets] = useState<SavedTicket[]>(() => loadAll());

  const save = useCallback((t: ClaudeAccumulator) => {
    setTickets(prev => {
      const id = ticketKey(t.legs);
      if (prev.some(x => x.id === id)) return prev;
      const entry: SavedTicket = {
        id, label: t.label, risk_level: t.risk_level,
        legs: t.legs.map(leg => ({
          event_id: leg.event_id, home_team: leg.home_team, away_team: leg.away_team,
          league: leg.league, event_date: leg.event_date, market: leg.market, market_label: leg.market_label,
          odds: leg.odds, probability: leg.probability,
        })),
        combined_odds: t.combined_odds, combined_probability_pct: t.combined_probability_pct,
        saved_at: new Date().toISOString(), status: 'pending',
      };
      const next = [entry, ...prev];
      persist(next);
      return next;
    });
  }, []);

  const remove = useCallback((id: string) => {
    setTickets(prev => {
      const next = prev.filter(x => x.id !== id);
      persist(next);
      return next;
    });
  }, []);

  const isSaved = useCallback(
    (t: ClaudeAccumulator) => tickets.some(x => x.id === ticketKey(t.legs)),
    [tickets]
  );

  // Auto-settle pending tickets against the rolling 14-day finished-results feed, once per mount.
  // Decontam si picioarele individuale (nu doar biletul agregat) — asa poti vedea care
  // selectie exacta a picat, chiar inainte ca tot biletul sa se decida.
  useEffect(() => {
    let cancelled = false;
    fetch(`./data/recent_results.json?_=${Date.now()}`)
      .then(r => (r.ok ? r.json() : null))
      .then((data: { results?: Array<{ id: number } & FinishedResult> } | null) => {
        if (cancelled || !data?.results) return;
        const byId = new Map(data.results.map(r => [String(r.id), r]));
        setTickets(prev => {
          let changed = false;
          const next = prev.map(t => {
            // Decontare picioare individuale — pe orice bilet, indiferent de statusul lui,
            // ca sa completam picioare care nu aveau inca status/scor salvat.
            let legsChanged = false;
            const legs = t.legs.map(leg => {
              if (leg.status && leg.status !== 'pending') return leg;
              const detail = settleLegDetail(leg, byId);
              if (detail.status === 'pending') return leg.status === 'pending' ? leg : { ...leg, status: 'pending' as const };
              legsChanged = true;
              return { ...leg, status: detail.status, final_score: detail.final_score };
            });
            if (t.status !== 'pending') {
              if (!legsChanged) return t;
              changed = true;
              return { ...t, legs };
            }
            const outcome = settleTicket(t.legs, byId);
            if (outcome === 'pending') {
              if (!legsChanged) return t;
              changed = true;
              return { ...t, legs };
            }
            changed = true;
            return { ...t, legs, status: outcome, settled_at: new Date().toISOString() };
          });
          if (changed) persist(next);
          return changed ? next : prev;
        });
      })
      .catch(() => { /* offline or file missing — settlement retried on next mount */ });
    return () => { cancelled = true; };
  }, []);

  return { tickets, save, remove, isSaved };
}
