/**
 * Integrare Superbet (doar linkuri; nu plasăm pariuri și nu folosim contul utilizatorului).
 *
 * Formatul verificat în aplicația oficială ro.superbet.sport 8.4.0 (manifest + parserul de deep link):
 *  - aplicația NU revendică linkurile https://superbet.ro/cote/… (doar /activare-cont, /deblocare-cont etc.),
 *    deci un link https deschide mereu site-ul, nu aplicația;
 *  - aplicația înregistrează schema proprie `rosuperbetsport://`:
 *      rosuperbetsport://event/odds?platform_id=<eventId>         → pagina meciului (cote)
 *      rosuperbetsport://betslip?bets[]=<eventId>,,,0,<oddUuid>&…  → bilet precompletat (fără miză, fără plasare)
 *    unde eventId și oddUuid vin din oferta publică Superbet (aceeași pe care o citește Robotul).
 */
import { isNativeApp, nativeOpenUrl, getSbMode } from './native';

const OFFER = 'https://production-superbet-offer-ro.freetls.fastly.net/v2/ro-RO/events/';
const M = { x12: 547, dc: 531, dnb: 555, btts: 539, total: 200734 };

export interface SbLegRef { eventId: string; market: string; line?: number | null; selection: string }
interface SbOdd { uuid?: string; marketId?: number; name?: string; price?: number; status?: string; specialBetValue?: string }

const cache = new Map<string, Promise<SbOdd[]>>();
function offer(eventId: string): Promise<SbOdd[]> {
  if (!cache.has(eventId)) {
    cache.set(eventId, fetch(OFFER + encodeURIComponent(eventId)).then((r) => (r.ok ? r.json() : null)).then((j) => {
      const e = (j?.data?.[0] ?? j) as { odds?: SbOdd[] } | null;
      return e?.odds ?? [];
    }).catch(() => []));
  }
  return cache.get(eventId)!;
}

/** Găsește cota Superbet (uuid + preț) pentru selecția noastră (aceeași mapare ca ingestia din backend). */
export async function resolveOdd(l: SbLegRef): Promise<{ uuid: string; price: number } | null> {
  const odds = (await offer(l.eventId)).filter((o) => (o.status ?? 'active') === 'active' && o.uuid);
  const pick = (mid: number, name: string) => odds.find((o) => o.marketId === mid && (o.name ?? '').trim() === name);
  let o: SbOdd | undefined;
  const s = l.selection;
  if (l.market === '1x2') o = pick(M.x12, ({ HOME: '1', DRAW: 'X', AWAY: '2' } as Record<string, string>)[s] ?? '');
  else if (l.market === 'double_chance') o = pick(M.dc, s);
  else if (l.market === 'btts') o = pick(M.btts, s === 'YES' ? 'Da' : 'Nu');
  else if (l.market === 'over_under' && l.line != null) o = pick(M.total, `${s === 'OVER' ? 'Peste' : 'Sub'} ${l.line}`);
  else if (l.market === 'draw_no_bet') { const d = odds.filter((x) => x.marketId === M.dnb); o = d[s === 'HOME' ? 0 : 1]; }
  return o?.uuid && o.price ? { uuid: o.uuid, price: o.price } : null;
}

export const eventAppLink = (eventId: string) => `rosuperbetsport://event/odds?platform_id=${encodeURIComponent(eventId)}`;
export function betslipAppLink(bets: Array<{ eventId: string; uuid: string }>) {
  return 'rosuperbetsport://betslip?' + bets.map((b) => `bets[]=${encodeURIComponent(`${b.eventId},,,0,${b.uuid}`)}`).join('&');
}

/**
 * Deschide un link al aplicației Superbet; dacă aplicația lipsește (sau utilizatorul a ales browserul) → `webUrl`.
 * Fără package forțat: Android alege handlerul implicit al schemei (inclusiv „dual app” pe Xiaomi).
 */
export function openSuperbet(appLink: string, webUrl: string, mode = getSbMode() ?? 'app') {
  if (mode === 'web') { if (isNativeApp()) void nativeOpenUrl(webUrl); else window.open(webUrl, '_blank', 'noopener'); return; }
  if (isNativeApp()) { void nativeOpenUrl(appLink, webUrl); return; }
  if (/Android/i.test(navigator.userAgent)) {
    const rest = appLink.replace(/^rosuperbetsport:\/\//, '');
    window.location.href = `intent://${rest}#Intent;scheme=rosuperbetsport;S.browser_fallback_url=${encodeURIComponent(webUrl)};end`;
    return;
  }
  window.open(webUrl, '_blank', 'noopener');
}
