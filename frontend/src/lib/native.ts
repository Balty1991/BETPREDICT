/**
 * Puntea către aplicația Android (Capacitor). Site-ul e același în browser și în aplicație;
 * doar în aplicație există `window.Capacitor` (injectat de WebView), cu pluginul nativ `BetPredictNative`.
 * Fără dependențe: în browser modulul doar raportează „indisponibil”.
 */

export type NotifyType = 'tickets_new' | 'tickets_won' | 'tickets_lost' | 'pyramid' | 'daily' | 'weekly';
export type NotifyPrefs = Record<NotifyType, boolean> & { quiet_hours: boolean };

export interface NativeStatus {
  available: true;
  prefs: NotifyPrefs;
  permission: 'granted' | 'denied' | 'prompt';
  versionName: string;
  versionCode: number;
  lastCheck: number;
  lastError?: string | null;
  periodMinutes: number;
  batteryUnrestricted: boolean;
  /** Notificări instant (FCM) incluse în acest APK și abonarea reușită. */
  pushAvailable?: boolean;
  pushSubscribed?: boolean;
}

export interface CheckResult {
  ok: boolean; seeded: boolean; skippedQuiet: boolean; unchanged: boolean;
  newTickets: number; won: number; lost: number; pyramid: number; daily: number; weekly?: number;
  error?: string; status: NativeStatus;
}

interface CapBridge {
  isNativePlatform?: () => boolean;
  getPlatform?: () => string;
  isPluginAvailable?: (name: string) => boolean;
  nativePromise?: (plugin: string, method: string, options?: unknown) => Promise<unknown>;
}

const PLUGIN = 'BetPredictNative';

/** Linkul stabil al APK-ului (release-ul „android” din GitHub, actualizat de workflow-ul Android APK). */
export const APK_URL = 'https://github.com/Balty1991/BETPREDICT/releases/download/android/BetPredict.apk';
const RELEASE_API = 'https://api.github.com/repos/Balty1991/BETPREDICT/releases/tags/android';

function cap(): CapBridge | null {
  const c = (window as unknown as { Capacitor?: CapBridge }).Capacitor;
  return c && typeof c.nativePromise === 'function' && c.isNativePlatform?.() ? c : null;
}

/** Rulează în aplicația Android (nu în browser). */
export function isNativeApp(): boolean {
  const c = cap();
  return !!c && (c.isPluginAvailable ? c.isPluginAvailable(PLUGIN) : true);
}

export function isAndroidBrowser(): boolean {
  return /Android/i.test(navigator.userAgent) && !isNativeApp();
}

function call<T>(method: string, options: Record<string, unknown> = {}): Promise<T> {
  const c = cap();
  if (!c?.nativePromise) return Promise.reject(new Error('Disponibil doar în aplicația Android'));
  return c.nativePromise(PLUGIN, method, options) as Promise<T>;
}

export const nativeNotify = {
  status: () => call<NativeStatus>('getStatus'),
  setPrefs: (prefs: Partial<NotifyPrefs>) => call<NativeStatus>('setPrefs', { prefs }),
  requestPermission: () => call<NativeStatus>('requestPermission'),
  openSettings: () => call<void>('openSettings'),
  requestBatteryExemption: () => call<void>('requestBatteryExemption'),
  checkNow: () => call<CheckResult>('checkNow'),
  test: () => call<NativeStatus>('testNotification'),
  /** Versiunea din release-ul „android” (version.json) față de cea instalată. */
  checkUpdate: () => call<{ versionCode: number; versionName: string; installedCode: number; installedName: string; available: boolean }>('checkUpdate'),
  /** Descarcă APK-ul nou și deschide instalatorul Android (cu ghidul pentru „aplicații necunoscute”, o dată). */
  startUpdate: () => call<void>('startUpdate'),
};

/** Ultima versiune publicată a APK-ului (din notele release-ului: „versionCode: N”). */
export async function latestApk(): Promise<{ versionCode: number; versionName: string } | null> {
  try {
    const r = await fetch(RELEASE_API, { headers: { Accept: 'application/vnd.github+json' } });
    if (!r.ok) return null;
    const j = (await r.json()) as { name?: string; body?: string };
    const code = Number(/versionCode:\s*(\d+)/.exec(j.body || '')?.[1]);
    const name = /(\d+\.\d+\.\d+)/.exec(j.name || '')?.[1] || '';
    return Number.isFinite(code) && code > 0 ? { versionCode: code, versionName: name } : null;
  } catch {
    return null;
  }
}
