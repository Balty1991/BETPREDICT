import { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router';
import { Blocks, FlaskConical, Wand2 } from 'lucide-react';
import { Card, Segmented, Badge, Loading, Empty, Notice } from '@/components/kit';
import { useAsync, getJSON } from '@/lib/fetcher';
import { useDay } from '@/lib/hooks';
import { loadDay } from '@/lib/data';
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

const ODDS_LO = 1.3;
const ODDS_HI = 1.8;
const DRAFT_KEY = 'bp.corner.drafts.v1';

type Placed = { m: BuilderMatch; c: BuilderCombo };

function isCorner(c: BuilderCombo): boolean {
  const t = `${c.label} ${(c.legs ?? []).join(' ')} ${c.superbet?.market ?? ''} ${c.superbet?.outcome ?? ''}`.toLowerCase();
  return t.includes('corner');
}

/** Superbonus Superbet: procent din profit, de la 3 selecții cu cotă ≥ 1,35. */
function superbonus(n: number): number {
  if (n < 3) return 0;
  if (n >= 25) return 1;
  const table: Record<number, number> = { 3: 0.03, 4: 0.04, 5: 0.06, 6: 0.08, 7: 0.1 };
  return table[n] ?? Math.min(1, 0.15 + (n - 8) * 0.05);
}

function pickBand(matches: BuilderMatch[], now: number, eventOf: Map<number, { id: string; url?: string | null }>, hi: number): Placed[] {
  const out: Placed[] = [];
  for (const m of matches) {
    if (Date.parse(m.kickoff_utc) <= now) continue;
    const ok = (m.combos ?? []).filter((c) => c.superbet && c.sb_odds && c.sb_odds >= ODDS_LO && c.sb_odds <= hi && isCorner(c));
    ok.sort((a, b) => Math.abs(a.sb_odds! - 1.5) - Math.abs(b.sb_odds! - 1.5) || b.p - a.p);
    if (ok[0] && eventOf.has(m.match_id)) out.push({ m, c: ok[0] });
  }
  return out.sort((a, b) => b.c.sb_odds! - a.c.sb_odds! || a.m.kickoff_utc.localeCompare(b.m.kickoff_utc));
}

function shareTooHigh(ids: number[], existing: Ticket[], cap: number): boolean {
  const set = new Set(ids);
  for (const tk of existing) {
    let n = 0;
    for (const l of tk.legs) if (set.has(l.match_id)) n++;
    if (n > cap) return true;
  }
  return false;
}

function loadDrafts(): Ticket[] {
  try {
    const raw = JSON.parse(localStorage.getItem(DRAFT_KEY) || '[]');
    return Array.isArray(raw) ? raw.filter((t) => t && t.kind === 'bb_corners') : [];
  } catch { return []; }
}
function toTicket(legs: Placed[], date: string, eventOf: Map<number, { id: string; url?: string | null }>, shape: 'short' | 'long', n: number): Ticket {
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
  const bonus = superbonus(tls.length);
  const back = total + bonus * (total - 1);
  const over = tls.some((l) => l.odds > ODDS_HI);
  return {
    id: `bb-${shape}-${date}-${n}-${Math.random().toString(36).slice(2, 7)}`, kind: 'bb_corners', variant: shape,
    variant_label: shape === 'short' ? `Cornere scurt · cotă ${Math.round(total)}` : `Cornere lung · cotă ${Math.round(total)}`,
    created_by: 'robot', experimental: true, paper: true, date, created_at: new Date().toISOString(),
    total_odds: Math.round(total * 100) / 100, p_ticket: pT, ev: pT * back - 1, status: 'pending',
    legs_count: tls.length, settled_legs: 0, legs: tls.sort((a, b) => (a.kickoff_utc ?? '').localeCompare(b.kickoff_utc ?? '')),
    reasons: [
      shape === 'short'
        ? `${tls.length} cornere, cotă 1,30–1,80, un meci o dată. Pe 798 de meciuri banda asta a fost pe plus circa 3–5%.`
        : `${tls.length} cornere, mai multe meciuri, cotă totală mai mare. Șansa e mai mică decât la biletul scurt.${over ? ' Are și cote peste 1,80: acolo eșantionul a fost pe minus.' : ''}`,
      `Superbonus ${Math.round(bonus * 100)}% din profit. La 2 lei, plata cu bonus e cam ${Math.round(2 * back)} lei.`,
      'Nu e marcat plasat. Îl pui tu, dacă vrei. Cash out-ul plătește sub valoarea biletului.',
    ],
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
  const mine = useMemo(() => tickets.filter((tk) => tk.kind === 'bb_corners' && tk.followed), [tickets]);
  const [drafts, setDrafts] = useState<Ticket[]>(loadDrafts);
  const [busy, setBusy] = useState(false);
  useEffect(() => { try { localStorage.setItem(DRAFT_KEY, JSON.stringify(drafts)); } catch { /* rămân în pagină */ } }, [drafts]);
  useEffect(() => {
    for (const tk of getState().myTickets) if (tk.kind === 'bb_auto' && !tk.followed) actions.removeTicket(tk.id);
  }, []);
  useEffect(() => {
    const recent = stats.data?.recent;
    if (!recent?.length) return;
    const by = new Map(recent.map((r) => [`${r.match_id}|${r.label}`, r]));
    const apply = (tk: Ticket): Ticket => {
      if (tk.kind !== 'bb_corners' && tk.kind !== 'bb_auto') return tk;
      let changed = false;
      const legs = tk.legs.map((l) => {
        const r = by.get(`${l.match_id}|${l.label}`);
        if (!r || r.result === 'pending' || r.result === l.result) return l;
        changed = true;
        return { ...l, result: r.result, score: r.score ?? l.score };
      });
      if (!changed) return tk;
      const lost = legs.some((l) => l.result === 'lost');
      const won = legs.every((l) => l.result === 'won');
      return { ...tk, legs, status: lost ? 'lost' : won ? 'won' : 'pending', settled_legs: legs.filter((l) => l.result === 'won' || l.result === 'lost').length };
    };
    setDrafts((ds) => ds.map(apply));
    for (const tk of getState().myTickets) {
      if (tk.kind !== 'bb_corners' || !tk.followed) continue;
      const next = apply(tk);
      if (next !== tk) actions.saveTicket(next);
    }
  }, [stats.data]);
  const [now] = useState(() => Date.now());
  const started = (m: BuilderMatch) => Date.parse(m.kickoff_utc) <= now;
  const ms = (res.data?.matches ?? []).slice().sort((a, b) => Number(started(a)) - Number(started(b)) || a.kickoff_utc.localeCompare(b.kickoff_utc));
  const hint = ms.filter((m) => (m.combos ?? []).some((c) => isCorner(c) && c.sb_odds && c.sb_odds >= ODDS_LO && c.sb_odds <= ODDS_HI)).length;
  const done = mine.filter((tk) => tk.status === 'won' || tk.status === 'lost');
  const wonN = done.filter((tk) => tk.status === 'won').length;
  const profit = done.reduce((a, tk) => a + (tk.status === 'won' ? tk.total_odds - 1 : -1), 0);
  const generate = async () => {
    if (busy) return;
    const pending = drafts.filter((tk) => tk.status === 'pending' || !tk.status);
    if (pending.length >= 15) { toast.error('Sunt deja 15 bilete în așteptare. Șterge din ele dacă vrei altele.'); return; }
    setBusy(true);
    try {
      const nowMs = Date.now();
      const evMap = new Map<number, { id: string; url?: string | null }>();
      const matches: BuilderMatch[] = [];
      for (const d of dates) {
        const [b, dayFile] = await Promise.all([
          getJSON<BuilderDay>(`api/builder/${d}.json`).catch(() => null),
          loadDay(d, 1).catch(() => null),
        ]);
        for (const x of dayFile?.matches ?? []) if (x.superbet_event_id) evMap.set(x.id, { id: String(x.superbet_event_id), url: x.superbet_url });
        matches.push(...(b?.matches ?? []));
      }
      const uses = new Map<number, number>();
      for (const tk of pending) for (const l of tk.legs) uses.set(l.match_id, (uses.get(l.match_id) ?? 0) + 1);
      const made: Ticket[] = [];
      const room = () => 15 - pending.length - made.length;
      const grab = (shape: 'short' | 'long', hi: number, min: number, max: number, stop: number, cap: number, useCap: number) => {
        if (room() <= 0) return false;
        const pool = pickBand(matches, nowMs, evMap, hi)
          .filter((x) => (uses.get(x.m.match_id) ?? 0) < useCap)
          .sort((a, b) => (uses.get(a.m.match_id) ?? 0) - (uses.get(b.m.match_id) ?? 0) || b.c.sb_odds! - a.c.sb_odds! || a.m.kickoff_utc.localeCompare(b.m.kickoff_utc));
        const take: Placed[] = [];
        let prod = 1;
        for (const x of pool) {
          if (take.length >= max) break;
          const ids = [...take.map((t) => t.m.match_id), x.m.match_id];
          if (shareTooHigh(ids, [...pending, ...made], 4)) continue;
          const next = prod * x.c.sb_odds!;
          if (take.length >= min && prod >= stop) break;
          if (take.length >= min && next > cap) continue;
          take.push(x);
          prod = next;
        }
        if (take.length < min) return false;
        made.push(toTicket(take, dates[0], evMap, shape, made.length));
        for (const x of take) uses.set(x.m.match_id, (uses.get(x.m.match_id) ?? 0) + 1);
        return true;
      };
      let spins = 0;
      while (room() > 0 && made.filter((tk) => tk.variant === 'short').length < 10 && spins < 12) {
        spins++;
        if (!grab('short', ODDS_HI, 10, 12, 80, 220, 3)) break;
      }
      spins = 0;
      while (room() > 0 && made.filter((tk) => tk.variant === 'long').length < 5 && spins < 8) {
        spins++;
        if (!grab('long', 2.5, 14, 24, 500, 8000, 3)) break;
      }
      spins = 0;
      while (pending.length + made.length < 10 && spins < 8) {
        spins++;
        if (!grab('short', ODDS_HI, 10, 12, 80, 220, 4)) break;
      }
      if (!made.length) { toast.error('Nu sunt destule cornere nejucate, cu preț pe Superbet, fără să repet meciurile.'); return; }
      setDrafts((d) => [...made, ...d]);
      const s = made.filter((tk) => tk.variant === 'short').length;
      const l = made.length - s;
      toast.success(`${made.length} bilete în așteptare (${s} scurte, ${l} lungi). Nu sunt marcate plasate.`);
    } finally { setBusy(false); }
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
          <h2 className="text-sm font-bold">Cornere, până la 15 bilete</h2>
          <button type="button" className="btn btn-primary h-10 px-3 text-xs" disabled={busy} onClick={() => void generate()}><Wand2 className="h-4 w-4" />{busy ? 'Caută…' : 'Generează'}</button>
        </div>
        <p className="text-[11px] leading-snug text-muted-foreground">Doar combinații cu cornere. Scurt: 10–12 meciuri, cotă 1,30–1,80. Lung: 14–24 meciuri, cotă totală mai mare și șansă mai mică. Un meci intră pe cel mult 3 bilete, iar două bilete au cel mult 4 meciuri la fel. {hint} meciuri bune în ziua aleasă; caută și în următoarele două. Nu se marchează plasat. Acum în așteptare: {drafts.filter((tk) => tk.status === 'pending' || !tk.status).length}.</p>
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
