export const TZ = 'Europe/Bucharest';

const dayFmt = new Intl.DateTimeFormat('en-CA', { timeZone: TZ, year: 'numeric', month: '2-digit', day: '2-digit' });
const timeFmt = new Intl.DateTimeFormat('ro-RO', { timeZone: TZ, hour: '2-digit', minute: '2-digit' });
const longDayFmt = new Intl.DateTimeFormat('ro-RO', { timeZone: TZ, weekday: 'long', day: 'numeric', month: 'long' });
const shortDayFmt = new Intl.DateTimeFormat('ro-RO', { timeZone: 'UTC', weekday: 'short', day: 'numeric', month: 'short' });
const dateTimeFmt = new Intl.DateTimeFormat('ro-RO', { timeZone: TZ, day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' });

/** Ziua din România (YYYY-MM-DD) pentru un moment UTC. */
export function roDay(iso: string | Date | null | undefined): string {
  if (!iso) return '';
  const d = typeof iso === 'string' ? new Date(iso) : iso;
  if (Number.isNaN(d.getTime())) return '';
  return dayFmt.format(d);
}
export function todayRo(): string { return roDay(new Date()); }
export function addDays(day: string, n: number): string {
  const d = new Date(`${day}T12:00:00Z`);
  d.setUTCDate(d.getUTCDate() + n);
  return d.toISOString().slice(0, 10);
}
export function roTime(iso?: string | null): string {
  if (!iso) return '—';
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? '—' : timeFmt.format(d);
}
export function roDateTime(iso?: string | null): string {
  if (!iso) return '—';
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? '—' : dateTimeFmt.format(d);
}
export function dayLabel(day: string): string {
  const t = todayRo();
  if (day === t) return 'Azi';
  if (day === addDays(t, -1)) return 'Ieri';
  if (day === addDays(t, 1)) return 'Mâine';
  return shortDayFmt.format(new Date(`${day}T12:00:00Z`));
}
export function longDay(day: string): string {
  const s = longDayFmt.format(new Date(`${day}T12:00:00Z`));
  return s.charAt(0).toUpperCase() + s.slice(1);
}
export function pct(p: number | null | undefined, digits = 0): string {
  if (p == null || Number.isNaN(p)) return '—';
  return `${(p * 100).toFixed(digits)}%`;
}
export function num(n: number | null | undefined, digits = 2): string {
  if (n == null || Number.isNaN(n)) return '—';
  return n.toLocaleString('ro-RO', { minimumFractionDigits: digits, maximumFractionDigits: digits });
}
export function odds(n: number | null | undefined): string {
  if (n == null || Number.isNaN(n)) return '—';
  if (n >= 100) return n.toLocaleString('ro-RO', { maximumFractionDigits: 0 });
  return n.toFixed(2);
}
export function signed(n: number | null | undefined, digits = 1, suffix = ''): string {
  if (n == null || Number.isNaN(n)) return '—';
  const s = n.toFixed(digits);
  return `${n > 0 ? '+' : ''}${s}${suffix}`;
}
export function lei(n: number | null | undefined): string {
  if (n == null || Number.isNaN(n)) return '—';
  return `${n.toLocaleString('ro-RO', { maximumFractionDigits: 2 })} lei`;
}
export function monthLabel(key: string): string {
  const d = new Date(`${key}-15T12:00:00Z`);
  return d.toLocaleDateString('ro-RO', { month: 'short', year: 'numeric', timeZone: 'UTC' });
}

const WD = ['Dum', 'Lun', 'Mar', 'Mie', 'Joi', 'Vin', 'Sâm'];
const MO = ['ian', 'feb', 'mar', 'apr', 'mai', 'iun', 'iul', 'aug', 'sep', 'oct', 'nov', 'dec'];
/** Data + ora de start în România, ex. „Sâm 10 oct · 21:30”. */
export function roKickoff(iso?: string | null): string {
  const day = roDay(iso);
  if (!day) return '—';
  const d = new Date(`${day}T12:00:00Z`);
  return `${WD[d.getUTCDay()]} ${d.getUTCDate()} ${MO[d.getUTCMonth()]} · ${roTime(iso)}`;
}
