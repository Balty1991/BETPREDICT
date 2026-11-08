import { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router';
import { Blocks, FlaskConical, Wand2 } from 'lucide-react';
import { Card, Segmented, Badge, Loading, Empty, Notice } from '@/components/kit';
import { useAsync, getJSON } from '@/lib/fetcher';
import { useDay } from '@/lib/hooks';
import { addDays, todayRo, dayLabel, pct, odds as fo, roKickoff, signed } from '@/lib/format';
import type { BuilderCombo, BuilderDay, BuilderMatch, Ticket, TicketLeg } from '@/lib/types';
import { cn } from '@/lib/utils';
import { SbPickButton } from '@/components/SuperbetLink';
import { BuilderStats } from '@/components/BuilderStats';
import { TicketCard } from '@/components/TicketCard';
import { actions, getState, useStore } from '@/lib/store';
import { toast } from 'sonner';

const GROUPS: Record<string, string> = {
  team_total_home: 'Goluri gazde', team_total_away: 'Goluri oaspeți', ht_over_under: 'Goluri repriza 1', h2_over_under: 'Goluri repriza 2',
  half_most_goals: 'Repriza cu cele mai multe goluri', corners_over_under: 'Cornere', ht_corners_over_under: 'Cornere repriza 1',
};

function Stat({ k, v, hi, tone }: { k: string; v: string; hi?: boolean; tone?: string }) {
  return (
    <div className={cn('rounded-lg px-1 py-1', hi && 'bg-primary/10')}>
      <div className={cn('num text-base font-extrabold leading-tight', hi && 'text-primary', tone)}>{v}</div>
      <div className="text-[10px] uppercase leading-tight tracking-wide text-muted-foreground">{k}</div>
    </div>
  );
}
const esc = (x: string) => x.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
/** „Vasco da Gama câștigă; Peste 1.5 goluri” → ['Gazde câștigă', 'Peste 1.5 goluri'] */
function legsOf(label: string, home: string, away: string) {
  return label.split(/\s*;\s*/).filter(Boolean).map((l) => l.replace(new RegExp(esc(home), 'g'), 'Gazde').replace(new RegExp(esc(away), 'g'), 'Oaspeți'));
}

export function MatchBuilder({ m, only, started, event }: { m: BuilderMatch; only: boolean; started?: boolean; event?: { id: string; url?: string | null } }) {
  const combos = (m.combos ?? []).filter((c) => !only || c.value);
  const extras = (m.extra_markets ?? []).filter((x) => !only || (x.ev ?? -1) > 0);
  if (only && !combos.length && !extras.length) return null;
  const byGroup = new Map<string, typeof extras>();
  for (const x of extras) byGroup.set(x.market, [...(byGroup.get(x.market) ?? []), x]);
  return (
    <Card className="overflow-hidden">
      <header className="flex flex-wrap items-center gap-2 px-4 pt-3">
        <Link to={`/meci/${m.match_id}`} className="inline-flex min-h-[40px] items-center font-extrabold hover:text-primary">{m.home} – {m.away}</Link>
        <span className="text-xs text-muted-foreground">{roKickoff(m.kickoff_utc)}</span>{started && <Badge>început</Badge>}
        {m.lambda_home != null && <span className="num ml-auto hidden text-xs text-muted-foreground md:inline">xG {m.lambda_home.toFixed(2)} – {m.lambda_away?.toFixed(2)}{m.corners ? ` · cornere ~${m.corners.mu.toFixed(1)}` : ''}</span>}
      </header>
      {m.superavantaj?.note && <p className="hidden px-4 pt-1 text-[11px] text-muted-foreground md:block">{/^superavantaj/i.test(m.superavantaj.note) ? m.superavantaj.note : `SuperAvantaj: ${m.superavantaj.note}`}</p>}
      {!!combos.length && (
        <>
        <div className="mt-2 space-y-2 px-3 pb-3 md:hidden">
          {(() => { const row = (c: typeof combos[number], i: number) => (<li key={i} className={cn('rounded-xl border p-2.5', c.value && 'border-[hsl(var(--win)/0.5)]')}>
            <div className="flex flex-wrap items-center gap-1">
              {legsOf(c.label, m.home, m.away).map((l, j) => <span key={j} className="rounded-md bg-accent/50 px-1.5 py-0.5 text-[12px] font-semibold leading-tight">{l}</span>)}
              {c.value && <Badge tone="win">valoare</Badge>}
            </div>
            <div className="mt-2 grid grid-cols-3 gap-1 text-center">
              <Stat k="Șansă" v={pct(c.p, 0)} />
              <Stat k="Cotă minimă" v={fo(c.min_odds)} hi />
              <Stat k={c.sb_odds ? 'Superbet' : 'fără preț Superbet'} v={c.sb_odds ? fo(c.sb_odds) : '·'} tone={!c.sb_odds ? undefined : c.min_odds && c.sb_odds >= c.min_odds ? 'text-win' : 'text-loss'} />
            </div>
            {c.superbet && event && !started && <div className="mt-2 flex justify-end"><SbPickButton eventId={event.id} webUrl={event.url} picks={[c.superbet]} className="inline-flex min-h-9 items-center gap-1 rounded-xl bg-[hsl(0_75%_55%)] px-3 text-[12px] font-bold text-white" /></div>}
          </li>); return <>{combos.slice(0, 1).map(row)}{combos.length > 1 && <details className="group"><summary className="flex min-h-10 cursor-pointer list-none items-center justify-center text-xs font-semibold text-primary">Încă {combos.length - 1} combinații ▾</summary><div className="space-y-2">{combos.slice(1).map((c, i) => row(c, i + 1))}</div></details>}</>; })()}
        </div>
        <div className="hidden overflow-x-auto md:block"><table className="pro-table mt-2 w-full text-sm">
          <thead><tr><th className="text-left">Combinație</th><th>Șansă</th><th>Cotă corectă</th><th>Cotă minimă</th><th>Superbet</th><th>EV</th><th /></tr></thead>
          <tbody>{combos.map((c, i) => (
            <tr key={i}><td className="text-left"><span className="font-semibold">{c.label}</span>{c.value && <> <Badge tone="win">valoare</Badge></>}{c.source === 'model' && <span className="block text-[10px] text-muted-foreground">combinație proprie{c.correlation_lift ? ` · corelație ×${c.correlation_lift.toFixed(2)}` : ''}</span>}</td>
              <td>{pct(c.p, 1)}</td><td>{fo(c.fair_odds)}</td><td className="font-bold text-primary">{fo(c.min_odds)}</td><td>{c.sb_odds ? fo(c.sb_odds) : <span className="text-xs text-muted-foreground">fără preț</span>}</td>
              <td className={cn(c.ev == null ? '' : c.ev >= 0 ? 'text-win' : 'text-loss')}>{c.ev == null ? '—' : signed(c.ev * 100, 1, '%')}</td>
              <td>{c.superbet && event && !started ? <SbPickButton eventId={event.id} webUrl={event.url} picks={[c.superbet]} /> : null}</td></tr>
          ))}</tbody></table></div></>
      )}
      {!!extras.length && (
        <details className="border-t px-4 py-2 text-sm">
          <summary className="inline-flex min-h-9 cursor-pointer items-center text-xs font-semibold text-primary">Piețe experimentale ({extras.length})</summary>
          <div className="mt-2 grid gap-3 md:grid-cols-2">{[...byGroup.entries()].map(([g, xs]) => (
            <div key={g}><div className="mb-1 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">{GROUPS[g] ?? g}</div>
              <ul className="divide-y">{xs.map((x) => <li key={x.key} className="flex items-center gap-2 py-1"><span className="flex-1 truncate">{x.label}</span><span className="num text-xs text-muted-foreground">{pct(x.p)}</span><span className="num w-12 text-right">{fo(x.fair_odds)}</span><span className="num w-12 text-right text-xs">{x.sb_odds ? fo(x.sb_odds) : '·'}</span></li>)}</ul></div>
          ))}</div>
        </details>
      )}
    </Card>
  );
}

const MIN_P = 0.42;
const ODDS_LO = 1.4;
const ODDS_HI = 2.1;

type Placed = { m: BuilderMatch; c: BuilderCombo };

function pickPool(matches: BuilderMatch[], now: number, eventOf: Map<number, { id: string; url?: string | null }>): Placed[] {
  const out: Placed[] = [];
  for (const m of matches) {
    if (Date.parse(m.kickoff_utc) <= now || !eventOf.has(m.match_id)) continue;
    const ok = (m.combos ?? []).filter((c) => c.superbet && c.sb_odds && c.sb_odds >= ODDS_LO && c.sb_odds <= ODDS_HI && c.p >= MIN_P);
    ok.sort((a, b) => Math.abs(a.sb_odds! - 1.65) - Math.abs(b.sb_odds! - 1.65) || b.p - a.p);
    if (ok[0]) out.push({ m, c: ok[0] });
  }
  return out.sort((a, b) => Math.abs(a.c.sb_odds! - 1.65) - Math.abs(b.c.sb_odds! - 1.65));
}

/** Adaugă selecții până când cota trece de 100, fără să sară mult peste. */
function takeFor100(pool: Placed[]): Placed[] | null {
  const take: Placed[] = [];
  let prod = 1;
  for (const x of pool) {
    if (take.length >= 18) break;
    const next = prod * x.c.sb_odds!;
    if (prod >= 100 && take.length >= 8) break;
    if (prod >= 80 && next > 400 && take.length >= 8) continue;
    take.push(x);
    prod = next;
  }
  return prod >= 80 && take.length >= 8 ? take : null;
}

function toTicket(legs: Placed[], i: number, date: string, eventOf: Map<number, { id: string; url?: string | null }>): Ticket {
  const tls: TicketLeg[] = legs.map(({ m, c }) => {
    const ev = eventOf.get(m.match_id);
    return {
      match_id: m.match_id, sb_event_id: ev?.id ?? null, superbet_url: ev?.url ?? null, kickoff_utc: m.kickoff_utc,
      home: m.home, away: m.away, market: 'bb', line: null, selection: `${c.superbet!.market}|${c.superbet!.outcome}`,
      label: c.label, odds: c.sb_odds!, p: c.p, sb_pick: c.superbet, reasons: [`Șansă ${Math.round(c.p * 100)}% · cotă Superbet ${c.sb_odds}`],
    };
  });
  const total = tls.reduce((a, l) => a * l.odds, 1);
  const pT = tls.reduce((a, l) => a * (l.p ?? 0), 1);
  return {
    id: `bb-${date}-${i}-${Date.now().toString(36)}`, kind: 'bb_auto', variant: `bb${i}`, variant_label: `Builder · cotă 100+ · ${i + 1}`,
    created_by: 'robot', experimental: true, paper: true, date, created_at: new Date().toISOString(), target_odds: 100,
    total_odds: Math.round(total * 100) / 100, p_ticket: pT, ev: pT * total - 1, status: 'pending',
    legs_count: tls.length, settled_legs: 0, legs: tls.sort((a, b) => (a.kickoff_utc ?? '').localeCompare(b.kickoff_utc ?? '')),
    reasons: [`${tls.length} combinații, cotă pe selecție ${ODDS_LO}–${ODDS_HI}, țintă peste 100`, 'Nu e marcat plasat. Îl pui tu, dacă vrei.'],
  };
}

export default function BuilderPage() {
  const t = todayRo();
  const dates = useMemo(() => [0, 1, 2].map((i) => addDays(t, i)), [t]);
  const [day, setDay] = useState(dates[0]);
  const [only, setOnly] = useState<'value' | 'all'>('all');
  const res = useAsync(() => getJSON<BuilderDay>(`api/builder/${day}.json`), [day]);
  const stats = useAsync(() => getJSON<{ recent?: Array<{ match_id: number; label: string; result: 'won' | 'lost' | 'pending'; score?: string | null }> }>('api/builder/stats.json'), []);
  const dayDoc = useDay(day);
  const eventOf = useMemo(() => {
    const m = new Map<number, { id: string; url?: string | null }>();
    for (const x of dayDoc.data?.matches ?? []) if (x.superbet_event_id) m.set(x.id, { id: String(x.superbet_event_id), url: x.superbet_url });
    return m;
  }, [dayDoc.data]);
  const tickets = useStore((s) => s.myTickets);
  const mine = useMemo(() => tickets.filter((tk) => tk.kind === 'bb_auto' && tk.followed), [tickets]);
  const [drafts, setDrafts] = useState<Ticket[]>([]);
  useEffect(() => {
    for (const tk of getState().myTickets) if (tk.kind === 'bb_auto' && !tk.followed) actions.removeTicket(tk.id);
  }, []);
  useEffect(() => {
    const recent = stats.data?.recent;
    if (!recent?.length) return;
    const by = new Map(recent.map((r) => [`${r.match_id}|${r.label}`, r]));
    for (const tk of getState().myTickets) {
      if (tk.kind !== 'bb_auto') continue;
      let changed = false;
      const legs = tk.legs.map((l) => {
        const r = by.get(`${l.match_id}|${l.label}`);
        if (!r || r.result === 'pending' || r.result === l.result) return l;
        changed = true;
        return { ...l, result: r.result, score: r.score ?? l.score };
      });
      if (!changed) continue;
      const lost = legs.some((l) => l.result === 'lost');
      const won = legs.every((l) => l.result === 'won');
      actions.saveTicket({ ...tk, legs, status: lost ? 'lost' : won ? 'won' : 'pending', settled_legs: legs.filter((l) => l.result === 'won' || l.result === 'lost').length });
    }
  }, [stats.data]);
  const [now] = useState(() => Date.now());
  const started = (m: BuilderMatch) => Date.parse(m.kickoff_utc) <= now;
  const ms = (res.data?.matches ?? []).slice().sort((a, b) => Number(started(a)) - Number(started(b)) || a.kickoff_utc.localeCompare(b.kickoff_utc));
  const poolN = pickPool(ms, now, eventOf).length;
  const done = mine.filter((tk) => tk.status === 'won' || tk.status === 'lost');
  const wonN = done.filter((tk) => tk.status === 'won').length;
  const profit = done.reduce((a, tk) => a + (tk.status === 'won' ? tk.total_odds - 1 : -1), 0);
  const generate = () => {
    let rest = pickPool(ms, Date.now(), eventOf);
    const made: Ticket[] = [];
    for (let i = 0; i < 3; i++) {
      const take = takeFor100(rest);
      if (!take) break;
      made.push(toTicket(take, drafts.length + i, day, eventOf));
      const used = new Set(take.map((x) => x.m.match_id));
      rest = rest.filter((x) => !used.has(x.m.match_id));
    }
    if (!made.length) { toast.error('Nu sunt destule combinații cu cotă 1,40–2,10 ca să iasă un bilet de 100.'); return; }
    setDrafts((d) => [...made, ...d]);
    toast.success(made.length === 1 ? 'Un bilet de 100+, nu e marcat plasat' : `${made.length} bilete de 100+, nu sunt marcate plasate`);
  };
  return (
    <div className="space-y-4">
      <section className="page-hero">
        <div className="eyebrow">Același meci, mai multe selecții</div>
        <h1 className="flex items-center gap-2"><Blocks className="h-7 w-7 text-primary" aria-hidden />Bet Builder</h1>
        <p className="mt-1 text-sm text-muted-foreground">Șansa e a Robotului. Cota roșie e sub minimul corect: Superbet plătește prea puțin.</p>
      </section>
      <BuilderStats embedded />
      <Card className="space-y-2 p-3.5">
        <div className="flex items-center justify-between gap-2">
          <h2 className="text-sm font-bold">Bilete cotă 100+</h2>
          <button type="button" className="btn btn-primary h-10 px-3 text-xs" disabled={!ms.length} onClick={generate}><Wand2 className="h-4 w-4" />Generează</button>
        </div>
        <p className="text-[11px] leading-snug text-muted-foreground">Combinații cu cotă între 1,40 și 2,10, câte una pe meci, până trece de 100. {poolN} meciuri bune acum. Nu se marchează plasat: apeși tu „Marchează plasat” doar dacă îl pui.</p>
        {done.length > 0 && <p className="text-xs">Cele marcate de tine: <b>{wonN}/{done.length}</b> intrate · ROI <b className={profit >= 0 ? 'text-win' : 'text-loss'}>{signed(profit / done.length * 100, 0, '%')}</b> la 1 leu</p>}
        {drafts.map((tk) => <TicketCard key={tk.id} t={tk} onRemove={() => setDrafts((d) => d.filter((x) => x.id !== tk.id))} />)}
        {mine.filter((tk) => !drafts.some((d) => d.id === tk.id)).map((tk) => <TicketCard key={tk.id} t={tk} onRemove={() => actions.removeTicket(tk.id)} />)}
      </Card>
      <Notice><FlaskConical className="mr-1 inline h-4 w-4" aria-hidden /><b>Experimental.</b> {(res.data?.rule ?? '').replace('1/p', '1/șansă') || 'Joacă doar dacă Superbet dă cel puțin cota minimă (1/șansă × 1.05).'}</Notice>
      <div className="flex flex-wrap gap-2">
        <Segmented size="sm" value={day} onChange={setDay} options={dates.map((d) => ({ value: d, label: dayLabel(d) }))} />
        <Segmented size="sm" value={only} onChange={setOnly} options={[{ value: 'all', label: 'Toate' }, { value: 'value', label: 'Doar cu valoare' }]} />
      </div>
      {res.loading ? <Loading /> : !ms.length ? <Empty title="Încă nu există sugestii Bet Builder pentru această zi">Robotul le calculează la rularea de dimineață. Încearcă ziua de mâine sau revino mai târziu.</Empty>
        : only === 'value' && !ms.some((m) => (m.combos ?? []).some((c) => c.value) || (m.extra_markets ?? []).some((x) => (x.ev ?? -1) > 0)) ? <Empty title="Nicio combinație cu valoare azi">Superbet nu dă peste cota minimă la nicio combinație. Apasă „Toate” ca să vezi cotele corecte.</Empty> : (
        <div className="grid gap-4 xl:grid-cols-2">{ms.map((m) => <div key={m.match_id} className={cn(started(m) && 'opacity-50')}><MatchBuilder m={m} only={only === 'value'} started={started(m)} event={eventOf.get(m.match_id)} /></div>)}</div>
      )}
    </div>
  );
}
