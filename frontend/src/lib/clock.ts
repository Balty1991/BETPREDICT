import { useSyncExternalStore } from 'react';

const TICK_MS = 30_000;
const listeners = new Set<() => void>();
let snapshot = Date.now();
let timer: number | null = null;

function refresh() {
  snapshot = Date.now();
  listeners.forEach((listener) => listener());
}

function subscribe(listener: () => void) {
  listeners.add(listener);
  if (listeners.size === 1) {
    snapshot = Date.now();
    timer = window.setInterval(refresh, TICK_MS);
    document.addEventListener('visibilitychange', refresh);
    listener();
  }
  return () => {
    listeners.delete(listener);
    if (!listeners.size && timer !== null) {
      window.clearInterval(timer);
      document.removeEventListener('visibilitychange', refresh);
      timer = null;
    }
  };
}

function getSnapshot() { return snapshot; }

/** Ora curentă reactivă: un singur timer comun, cu refresh la revenirea aplicației în prim-plan. */
export function useNow(): number {
  return useSyncExternalStore(subscribe, getSnapshot, getSnapshot);
}
