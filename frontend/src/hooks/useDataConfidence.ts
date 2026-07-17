import { useState, useEffect } from 'react';
import type { DataConfidence } from '@/types/betpredict';

/** Încarcă data/data_confidence.json o singură dată (cache modul). */
let _cache: Map<string, DataConfidence> | null = null;
let _promise: Promise<Map<string, DataConfidence>> | null = null;

async function load(): Promise<Map<string, DataConfidence>> {
  if (_cache) return _cache;
  if (_promise) return _promise;
  _promise = (async () => {
    try {
      const r = await fetch(`./data/data_confidence.json?_=${Date.now()}`);
      const data = r.ok ? await r.json() : {};
      const byEvent = (data.by_event ?? {}) as Record<string, DataConfidence>;
      const map = new Map<string, DataConfidence>();
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

export function useDataConfidence(): Map<string, DataConfidence> {
  const [map, setMap] = useState<Map<string, DataConfidence>>(_cache ?? new Map());
  useEffect(() => {
    let alive = true;
    load().then(m => { if (alive) setMap(m); });
    return () => { alive = false; };
  }, []);
  return map;
}
