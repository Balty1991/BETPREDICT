import { useEffect, useState } from 'react';
import type { OddsBucket } from '@/types/betpredict';
import { buildOddsIndex, type BestOddsRow } from '@/utils/oddsIndex';

export function useBestOdds(): { oddsByEvent: Map<string, OddsBucket>; loading: boolean } {
  const [oddsByEvent, setOddsByEvent] = useState<Map<string, OddsBucket>>(new Map());
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    fetch(`./data/best_odds.json?_=${Date.now()}`)
      .then(r => (r.ok ? r.json() : null))
      .then((data: { results?: BestOddsRow[] } | null) => {
        if (cancelled) return;
        setOddsByEvent(buildOddsIndex(data?.results ?? []));
      })
      .catch(() => { /* offline or file missing — local picks fall back to fair odds */ })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, []);

  return { oddsByEvent, loading };
}
