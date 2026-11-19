import type { ReactNode } from 'react';
import { getJSON, useAsync } from '@/lib/fetcher';
import { roTime } from '@/lib/format';
import { cn } from '@/lib/utils';

interface Leg { label: string; odds: number; home: string; away: string; kickoff_utc: string | null; league: string; result?: string | null }
interface Short { id: number; odds: number; payout?: number | null; p: number; status: string; n_legs: number; legs: Leg[]; why: string[] }
interface Mrow { label: string; n: number; hit: number | null; roi: number | null; state: 'hot' | 'flat' | 'cold' | 'off' | 'few' }
interface Brief {
  date: string; weekday: string; headline: string; tone: 'good' | 'ok' | 'warn'; generated_at: string;
  quality: { level: string; label: string; club_day: number; night: number; intl: number; rec_matches: number | null; leagues: number; text: string };
  tickets: { short: Short[]; short_note: string | null; long_active: number; long_note: string };
  pyramid: { step: number; bank: number; stake: number; text: string; ticket: { odds: number; p: number; legs: Leg[] } | null };
  markets: { days: number; rows: Mrow[]; rule: string; note: string };
  warnings: string[];
  bankroll: Array<{ key: string; title: string; pct: number | null; text: string }>;
  yesterday: { date: string; lines: string[] };
  disclaimer: string;
}

const pc = (v: number | null | undefined, d = 0, sign = false) =>
  v == null ? '—' : `${sign && v >= 0 ? '+' : ''}${(v * 100).toFixed(d).replace('.', ',')}%`;
const STATE: Record<Mrow['state'], { t: string; c: string }> = {
  hot: { t: 'cald', c: 'bg-win text-win' }, flat: { t: 'neutru', c: 'bg-muted text-muted-foreground' },
  cold: { t: 'rece', c: 'bg-warn text-warn' }, off: { t: 'scos', c: 'bg-loss text-loss' }, few: { t: 'puține date', c: 'bg-muted text-muted-foreground' },
};
const TONE = { good: 'board-win', ok: '', warn: 'board-warn' } as const;

function Block({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="mt-3">
      <h3 className="label mb-1">{title}</h3>
      {children}
    </div>
  );
}

function Legs({ legs }: { legs: Leg[] }) {
  return (
    <ul className="mt-1 divide-y divide-border/50 text-xs">
      {legs.map((l, i) => (
        <li key={i} className="flex items-center justify-between gap-2 py-1">
          <span className="min-w-0 truncate">
            <span className="num text-muted-foreground">{roTime(l.kickoff_utc)}</span> {l.home} – {l.away}
            <span className="block truncate text-[11px] text-muted-foreground">{l.label}</span>
          </span>
          <span className="num shrink-0 font-semibold">{l.odds.toFixed(2)}</span>
        </li>
      ))}
    </ul>
  );
}

/** „Analiza zilei”: ce ar spune un analist în fiecare dimineață (din date: ziua, biletele, piețele, miza, ieri). */
export function AnalystBrief() {
  const { data } = useAsync(() => getJSON<Brief>('api/brief/today.json'), []);
  if (!data?.headline) return null;
  const q = data.quality;
  return (
    <section className={cn('card ab-card relative overflow-hidden p-4', TONE[data.tone])} aria-label="Analiza zilei">
      <div className="flex items-baseline justify-between gap-2">
        <h2 className="text-[17px] font-bold">Analiza zilei</h2>
        <span className="text-[11px] capitalize text-muted-foreground">{data.weekday}, {data.date.split('-').reverse().join('.')}</span>
      </div>
      <p className="mt-1 text-sm font-semibold">{data.headline}</p>

      <div className="mt-2 grid grid-cols-4 gap-1.5 text-center">
        {[
          [q.club_day, 'cluburi 10–24'],
          [q.rec_matches ?? '—', 'cu recomandări'],
          [q.intl, 'internaționale'],
          [q.night, 'noaptea'],
        ].map(([v, l]) => (
          <div key={String(l)} className="rounded-xl bg-muted/50 py-1.5">
            <div className="big-num text-[18px]">{v}</div>
            <div className="text-[10px] leading-tight text-muted-foreground">{l}</div>
          </div>
        ))}
      </div>
      <p className="mt-1.5 text-xs text-muted-foreground">{q.text}</p>

      {data.warnings.length > 0 && (
        <Block title="Atenție azi">
          <ul className="space-y-1 text-xs">
            {data.warnings.map((w, i) => <li key={i} className="rounded-lg bg-warn px-2 py-1.5 text-foreground">{w}</li>)}
          </ul>
        </Block>
      )}

      <Block title="Biletele zilei">
        {data.tickets.short.length === 0 && <p className="text-xs">{data.tickets.short_note}</p>}
        {data.tickets.short.map((t) => (
          <details key={t.id} className="rounded-xl bg-muted/40 p-2 text-xs">
            <summary className="flex min-h-9 cursor-pointer list-none items-center justify-between gap-2">
              <span className="font-semibold">Cotă ~10 · {t.n_legs} selecții</span>
              <span className="num"><b className="text-primary">{t.odds.toFixed(2)}</b> · șansă {pc(t.p, 1)} ▾</span>
            </summary>
            {t.why.map((w, i) => <p key={i} className="mt-1 text-muted-foreground">{w}</p>)}
            <Legs legs={t.legs} />
          </details>
        ))}
        <p className="mt-1.5 text-xs text-muted-foreground">{data.tickets.long_note}</p>
      </Block>

      <Block title="Piramida cotă 2">
        <p className="text-xs">{data.pyramid.text}</p>
        {data.pyramid.ticket && <Legs legs={data.pyramid.ticket.legs} />}
      </Block>

      <Block title={`Piețele recomandate · ${data.markets.days} zile`}>
        <ul className="divide-y divide-border/50 text-xs">
          {data.markets.rows.map((m) => (
            <li key={m.label} className="flex items-center justify-between gap-2 py-1.5">
              <span className="min-w-0 truncate">{m.label}</span>
              <span className="num flex shrink-0 items-center gap-1.5 text-muted-foreground">
                {m.n} · {pc(m.hit)} ·{' '}
                <b className={(m.roi ?? 0) >= 0 ? 'text-win' : 'text-loss'}>{pc(m.roi, 1, true)}</b>
                <span className={cn('rounded-full px-1.5 py-0.5 text-[10px] font-semibold', STATE[m.state].c)}>{STATE[m.state].t}</span>
              </span>
            </li>
          ))}
        </ul>
        <p className="mt-1 text-[11px] text-muted-foreground">Selecții · intrate · ROI la închidere. {data.markets.note} {data.markets.rule}</p>
      </Block>

      <Block title="Cât pui azi">
        <ul className="space-y-1.5 text-xs">
          {data.bankroll.map((b) => (
            <li key={b.key} className="flex gap-2">
              <span className="big-num w-12 shrink-0 text-[15px] text-primary">{b.pct != null ? pc(b.pct, b.pct < 0.01 ? 1 : 0) : '½'}</span>
              <span><b>{b.title}.</b> {b.text}</span>
            </li>
          ))}
        </ul>
      </Block>

      <Block title="Ieri">
        <ul className="list-disc space-y-0.5 pl-4 text-xs">
          {data.yesterday.lines.map((l, i) => <li key={i}>{l}</li>)}
        </ul>
      </Block>

      <p className="mt-3 text-[11px] text-muted-foreground">{data.disclaimer}</p>
    </section>
  );
}
