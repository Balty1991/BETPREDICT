import { useEffect, useState, useCallback } from 'react';

/** Rădăcina site-ului (GitHub Pages servește aplicația dintr-un subfolder). */
export const BASE = import.meta.env.BASE_URL || './';

const cache = new Map<string, Promise<unknown>>();
const STALE_MS = 5 * 60 * 1000;
const stamps = new Map<string, number>();

/**
 * Citește un JSON static publicat de pipeline. Fără autentificare, fără chei:
 * browserul nu vorbește niciodată cu API-ul BSD. Rezultatul e ținut în memorie 5 min.
 * Întoarce `null` dacă fișierul lipsește (404) sau nu e JSON valid.
 */
export function getJSON<T>(path: string, opts: { fresh?: boolean } = {}): Promise<T | null> {
  const url = `${BASE}${path}`;
  const t = stamps.get(url) ?? 0;
  if (!opts.fresh && cache.has(url) && Date.now() - t < STALE_MS) return cache.get(url) as Promise<T | null>;
  const p = fetch(url, { cache: 'no-cache' })
    .then(async (r) => {
      if (!r.ok) return null;
      const ct = r.headers.get('content-type') || '';
      if (ct.includes('text/html')) return null; // SPA fallback / 404 servit ca HTML
      try { return (await r.json()) as T; } catch { return null; }
    })
    .catch(() => null);
  cache.set(url, p);
  stamps.set(url, Date.now());
  return p;
}

export function clearCache() { cache.clear(); stamps.clear(); }

export interface AsyncState<T> { data: T | null; loading: boolean; error: string | null; reload: () => void }

/** Hook minimal de încărcare asincronă (lazy, per pagină). */
export function useAsync<T>(fn: () => Promise<T | null>, deps: unknown[]): AsyncState<T> {
  const [state, setState] = useState<{ data: T | null; loading: boolean; error: string | null }>({ data: null, loading: true, error: null });
  const [tick, setTick] = useState(0);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  const run = useCallback(fn, deps);
  useEffect(() => {
    let alive = true;
    setState((s) => ({ ...s, loading: true, error: null }));
    run()
      .then((data) => { if (alive) setState({ data, loading: false, error: null }); })
      .catch((e: unknown) => { if (alive) setState({ data: null, loading: false, error: e instanceof Error ? e.message : String(e) }); });
    return () => { alive = false; };
  }, [run, tick]);
  const reload = useCallback(() => { clearCache(); setTick((x) => x + 1); }, []);
  return { ...state, reload };
}
