/**
 * Sincronizare automată a biletelor tale între telefon și PC printr-un Gist SECRET din contul tău GitHub.
 *
 * - Fără server și fără secrete în site: tokenul (doar permisiunea „gist”) îl introduci tu pe fiecare
 *   dispozitiv și rămâne DOAR în stocarea locală a acelui dispozitiv (nu intră în codurile de sincronizare,
 *   în backup sau în site-ul public).
 * - Gistul e „secret” (nelistat, vizibil doar în contul tău sau cu linkul exact) și conține doar biletele:
 *   manuale, „Îl joc”, arhiva biletelor generate în aplicație, jurnalul piramidei și retragerile. Setările nu
 *   se sincronizează (fiecare dispozitiv își păstrează tema și pragurile).
 * - Îmbinare, nu suprascriere: la fiecare sincronizare citim gistul, îl îmbinăm local (după id), apoi
 *   scriem rezultatul înapoi. Un bilet șters pe un dispozitiv poate reapărea dacă există încă pe celălalt.
 */
import { actions, getState, mergeState, type State } from './store';

const API = 'https://api.github.com';
const FILE = 'betpredict-sync.json';
const K_TOKEN = 'bp-cloud-token';
const K_GIST = 'bp-cloud-gist';
const K_LAST = 'bp-cloud-last';
const K_HASH = 'bp-cloud-hash';

type SyncPart = Pick<State, 'myTickets' | 'robotArchive' | 'robotLog' | 'pyramidLog' | 'withdrawals'>;
interface Payload { schema: 'betpredict.sync.v1'; updated_at: string; device: string; data: SyncPart }

export interface CloudStatus { enabled: boolean; gistId: string | null; lastSync: number; lastError: string | null; busy: boolean; login?: string | null }

let status: CloudStatus = {
  enabled: !!read(K_TOKEN), gistId: read(K_GIST), lastSync: Number(read(K_LAST) || 0), lastError: null, busy: false,
};
const subs = new Set<(s: CloudStatus) => void>();
function emit(patch: Partial<CloudStatus>) { status = { ...status, ...patch }; subs.forEach((f) => f(status)); }
export function cloudStatus() { return status; }
export function onCloudStatus(f: (s: CloudStatus) => void) { subs.add(f); return () => { subs.delete(f); }; }

function read(k: string): string | null { try { return localStorage.getItem(k); } catch { return null; } }
function write(k: string, v: string | null) { try { if (v == null) localStorage.removeItem(k); else localStorage.setItem(k, v); } catch { /* plin */ } }

function part(s: State): SyncPart {
  return { myTickets: s.myTickets, robotArchive: s.robotArchive, robotLog: s.robotLog, pyramidLog: s.pyramidLog, withdrawals: s.withdrawals };
}
function hash(x: unknown): string {
  const t = JSON.stringify(x); let h = 2166136261;
  for (let i = 0; i < t.length; i++) { h ^= t.charCodeAt(i); h = Math.imul(h, 16777619); }
  return `${t.length}:${(h >>> 0).toString(36)}`;
}
function device(): string {
  const ua = navigator.userAgent;
  return /BetPredictApp/.test(ua) ? 'Aplicația Android' : /Android|iPhone|iPad/.test(ua) ? 'Telefon (browser)' : 'PC';
}

async function gh<T>(path: string, init: RequestInit = {}): Promise<T> {
  const token = read(K_TOKEN);
  if (!token) throw new Error('Sincronizarea nu e activată');
  const r = await fetch(API + path, {
    ...init,
    cache: 'no-store',
    headers: { Accept: 'application/vnd.github+json', Authorization: `Bearer ${token}`, 'X-GitHub-Api-Version': '2022-11-28', ...(init.body ? { 'Content-Type': 'application/json' } : {}) },
  });
  if (r.status === 401) throw new Error('Token invalid sau expirat');
  if (r.status === 403 || r.status === 404) throw new Error(`Tokenul nu are acces la gisturi (HTTP ${r.status})`);
  if (!r.ok) throw new Error(`GitHub HTTP ${r.status}`);
  return (await r.json()) as T;
}

interface GistFile { content?: string; truncated?: boolean; raw_url?: string }
interface Gist { id: string; description?: string; files: Record<string, GistFile> }

async function findOrCreateGist(): Promise<string> {
  const cached = read(K_GIST);
  if (cached) return cached;
  for (let page = 1; page <= 5; page++) {
    const list = await gh<Gist[]>(`/gists?per_page=100&page=${page}`);
    const g = list.find((x) => x.files && FILE in x.files);
    if (g) { write(K_GIST, g.id); return g.id; }
    if (list.length < 100) break;
  }
  const created = await gh<Gist>('/gists', {
    method: 'POST',
    body: JSON.stringify({ description: 'BetPredict — sincronizare bilete (secret, nu-l partaja)', public: false, files: { [FILE]: { content: JSON.stringify(payload(), null, 1) } } }),
  });
  write(K_GIST, created.id);
  return created.id;
}

function payload(): Payload {
  return { schema: 'betpredict.sync.v1', updated_at: new Date().toISOString(), device: device(), data: part(getState()) };
}

async function readRemote(id: string): Promise<SyncPart | null> {
  const g = await gh<Gist>(`/gists/${id}`);
  const f = g.files?.[FILE];
  if (!f) return null;
  let txt = f.content ?? '';
  if (f.truncated && f.raw_url) txt = await (await fetch(f.raw_url, { cache: 'no-store' })).text();
  try {
    const p = JSON.parse(txt) as Partial<Payload>;
    return p?.data ?? null;
  } catch { return null; }
}

let running: Promise<void> | null = null;
let lastSeen: State | null = null;

/** Citește gistul, îl îmbină local, apoi scrie înapoi dacă s-a schimbat ceva. */
export function syncNow(): Promise<void> {
  if (!read(K_TOKEN)) return Promise.resolve();
  if (running) return running;
  running = (async () => {
    emit({ busy: true });
    try {
      let id = await findOrCreateGist();
      let remote: SyncPart | null;
      try { remote = await readRemote(id); } catch (e) {
        // gistul a fost șters între timp: îl recreăm
        if (String(e).includes('404')) { write(K_GIST, null); id = await findOrCreateGist(); remote = null; } else throw e;
      }
      // importăm doar dacă gistul aduce ceva nou (altfel n-am schimba starea degeaba → fără bucle)
      if (remote && hash(part(mergeState(getState(), remote))) !== hash(part(getState()))) actions.importState(JSON.stringify(remote));
      const merged = part(getState());
      const h = hash(merged);
      if (h !== hash(remote) && h !== read(K_HASH)) {
        await gh(`/gists/${id}`, { method: 'PATCH', body: JSON.stringify({ files: { [FILE]: { content: JSON.stringify(payload(), null, 1) } } }) });
      }
      write(K_HASH, h);
      lastSeen = getState();
      const now = Date.now();
      write(K_LAST, String(now));
      emit({ lastSync: now, lastError: null, gistId: id });
    } catch (e) {
      emit({ lastError: e instanceof Error ? e.message : String(e) });
      throw e;
    } finally {
      emit({ busy: false });
      running = null;
    }
  })();
  return running;
}

/** Activează: verifică tokenul, găsește (sau creează) gistul și face prima sincronizare. */
export async function enableCloudSync(token: string): Promise<void> {
  const t = token.trim();
  if (!/^(ghp_|github_pat_|gho_)[A-Za-z0-9_]{20,}$/.test(t)) throw new Error('Tokenul nu arată ca un token GitHub (ghp_… sau github_pat_…)');
  write(K_TOKEN, t);
  write(K_GIST, null);
  write(K_HASH, null);
  try {
    const me = await gh<{ login: string }>('/user').catch(() => null);
    emit({ enabled: true, login: me?.login ?? null, lastError: null });
    await syncNow();
  } catch (e) {
    write(K_TOKEN, null);
    emit({ enabled: false });
    throw e;
  }
}

/** Dezactivează pe acest dispozitiv (șterge tokenul local; gistul rămâne în contul tău). */
export function disableCloudSync() {
  write(K_TOKEN, null); write(K_GIST, null); write(K_HASH, null); write(K_LAST, null);
  emit({ enabled: false, gistId: null, lastSync: 0, lastError: null });
}

let started = false;
/** Pornește sincronizarea automată: la deschidere, la revenirea în aplicație și la 8 s după orice schimbare. */
export function startCloudSync() {
  if (started || typeof window === 'undefined') return;
  started = true;
  lastSeen = getState();
  let timer: ReturnType<typeof setTimeout> | undefined;
  const soon = (ms: number) => { clearTimeout(timer); timer = setTimeout(() => { syncNow().catch(() => {}); }, ms); };
  if (read(K_TOKEN)) soon(1500);
  // fără să modificăm store-ul: verificăm ieftin referința stării (se schimbă doar la scriere)
  setInterval(() => {
    const s = getState();
    if (s !== lastSeen) { lastSeen = s; if (read(K_TOKEN) && !running) soon(8000); }
  }, 2000);
  document.addEventListener('visibilitychange', () => { if (document.visibilityState === 'visible' && read(K_TOKEN)) soon(500); });
}
