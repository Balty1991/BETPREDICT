import { useState, useEffect } from 'react';
import type { V7Edge } from '@/types/betpredict';

/**
 * useV7Edge — încarcă data/v7_edge_index.json o singură dată (cache la nivel de
 * modul) și expune un Map<event_id, V7Edge> pentru afișarea verdictului de
 * valoare pe carduri, predicții și analiza evenimentelor.
 */
let _cache: Map<string, V7Edge> | null = null;
let _promise: Promise<Map<string, V7Edge>> | null = null;

async function loadEdge(): Promise<Map<string, V7Edge>> {
  if (_cache) return _cache;
  if (_promise) return _promise;
  _promise = (async () => {
    try {
      const r = await fetch(`./data/v7_edge_index.json?_=${Date.now()}`);
      const data = r.ok ? await r.json() : {};
      const byEvent = (data.by_event ?? {}) as Record<string, V7Edge>;
      const map = new Map<string, V7Edge>();
      for (const [k, v] of Object.entries(byEvent)) map.set(String(k), v);
      _cache = map;
      return map;
    } catch {
      _cache = new Map();
      return _cache;
    }
  })();
  return _promise;
}

export function useV7Edge(): Map<string, V7Edge> {
  const [map, setMap] = useState<Map<string, V7Edge>>(_cache ?? new Map());
  useEffect(() => {
    let alive = true;
    loadEdge().then(m => { if (alive) setMap(m); });
    return () => { alive = false; };
  }, []);
  return map;
}
