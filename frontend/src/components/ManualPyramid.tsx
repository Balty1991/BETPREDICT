import { useEffect, useMemo, useState } from 'react';
import { toast } from 'sonner';
import { Plus, Trash2, RotateCcw, Check, X, ChevronDown } from 'lucide-react';
import { useAsync } from '@/lib/fetcher';
import { loadSsResults } from '@/lib/data';
import { useStore, actions, getState } from '@/lib/store';
import { weekSpent } from '@/lib/stake';
import { lei, odds as fo, pct, roTime, todayRo } from '@/lib/format';
import { Card, Badge, Notice, SectionTitle } from '@/components/kit';
import { cn } from '@/lib/utils';
import { combo, loadManualPool, loadManualResults, pyrState, ticketLegs, type MPItem, type ManualPyr, type MPStep } from '@/lib/manualPyr';
import type { Ticket } from '@/lib/types';

const clamp = (x: number, lo: number, hi: number) => Math.min(hi, Math.max(lo, x));
const num = (s: string) => Number(String(s).replace(',', '.'));
const sgn = (x: number) => `${x >= 0 ? '+' : ''}${(x * 100).toFixed(1)}%`;

function NewForm({ onDone }: { onDone: (id: string) => void }) {
  const [start, setStart] = useState('2');
  const [steps, setSteps] = useState(5);
  const [target, setTarget] = useState('2');
  const [name, setName] = useState('');
  const create = () => {
    const s = clamp(num(start) || 2, 1, 1000), t = clamp(num(target) || 2, 1.3, 5);
    const id = `mp-${Date.now().toString(36)}`;
    actions.saveManualPyr({ id, name: name.trim() || `Piramida mea ${t.toFixed(2)}×${steps}`, created: todayRo(), start: s, steps, target: t, history: [], cycles: [] });
    toast.success('Piramidă creată. Alege selecțiile pentru treapta 1.');
    onDone(id);
  };
  const final = (num(start) || 0) * Math.pow(clamp(num(target) || 2, 1.3, 5), steps);
  return (
    <Card className="space-y-3 p-4">
      <h2 className="font-semibold">Piramidă nouă</h2>
      <label className="block text-xs font-semibold">Nume (opțional)<input className="input mt-1 h-10" value={name} maxLength={30} onChange={(e) => setName(e.target.value)} placeholder="ex. Duminica mea" /></label>
      <div className="grid grid-cols-2 gap-2">
        <label className="block text-xs font-semibold">Miza de start (lei)<input className="input mt-1 h-10 text-center font-bold" inputMode="decimal" value={start} onChange={(e) => setStart(e.target.value.replace(/[^\d.,]/g, ''))} /></label>
        <label className="block text-xs font-semibold">Cota pe treaptă (1.30–5)<input className="input mt-1 h-10 text-center font-bold" inputMode="decimal" value={target} onChange={(e) => setTarget(e.target.value.replace(/[^\d.,]/g, ''))} /></label>
      </div>
      <div>
        <div className="mb-1 text-xs font-semibold">Trepte</div>
        <div className="flex gap-1">{[1, 2, 3, 4, 5, 6, 7].map((n) => (
          <button key={n} type="button" className={cn('chip chip-sm flex-1 justify-center', steps === n && 'chip-on')} onClick={() => setSteps(n)} aria-pressed={steps === n}>{n}</button>))}
        </div>
      </div>
      <p className="text-xs text-muted-foreground">Dacă iese tot: {lei(num(start) || 0)} → <b className="text-foreground">{lei(final)}</b>. Fiecare treaptă reinvestește tot câștigul; doar miza de start e bani noi din buget.</p>
      <button type="button" className="btn btn-primary w-full" onClick={create}>Creează piramida</button>
    </Card>
  );
}

function Steps({ mp, st, phase }: { mp: ManualPyr; st: ReturnType<typeof pyrState>['st']; phase: string }) {
  // bara pe trepte + graficul băncii (ținta vs. realizat)
  const bars = Array.from({ length: mp.steps }, (_, i) => {
    const x = st[i];
    const plan = mp.start * Math.pow(mp.target, i + 1);
    const real = x && x.status === 'won' ? x.s.stake * x.odds : null;
    return { i, x, plan, real };
  });
  // scară logaritmică cu înălțime minimă: la cota 3, T5 e de 243 de ori T1 — liniar, primele trepte nu s-ar vedea
  const vals = bars.flatMap((b) => [b.plan, b.real ?? b.plan]).filter((v) => v > 0);
  const lo = Math.min(...vals, mp.start), hi = Math.max(...vals);
  const h = (v: number) => (hi <= lo ? 60 : 22 + 78 * (Math.log(Math.max(v, lo)) - Math.log(lo)) / (Math.log(hi) - Math.log(lo)));
  return (
    <div>
      <div className="mb-2 flex gap-1" aria-label="Progres pe trepte">{bars.map((b) => (
        <div key={b.i} className={cn('h-2 flex-1 rounded-full', !b.x ? 'bg-muted' : b.x.status === 'won' ? 'bg-[hsl(var(--win))]' : b.x.status === 'lost' ? 'bg-[hsl(var(--loss))]' : 'bg-[hsl(var(--warn))]')} />))}
      </div>
      <div className="flex h-28 gap-1.5" role="img" aria-label="Banca pe fiecare treaptă">{bars.map((b) => (
        <div key={b.i} className="flex min-w-0 flex-1 flex-col items-center gap-1">
          <span className="num truncate text-[10px] font-bold">{lei(b.real ?? b.plan)}</span>
          <div className="relative w-full flex-1">
            <div className="absolute bottom-0 w-full rounded-t-md bg-[hsl(var(--muted-foreground)/0.22)]" style={{ height: `${h(b.plan)}%` }} />
            {b.real != null && <div className="absolute bottom-0 w-full rounded-t-md bg-[hsl(var(--win))]" style={{ height: `${h(b.real)}%` }} />}
            {b.x?.status === 'pending' && <div className="absolute bottom-0 w-full rounded-t-md pyr-on" style={{ height: '18%' }} />}
          </div>
          <span className="num text-[10px] text-muted-foreground">T{b.i + 1}</span>
        </div>))}
      </div>
      <p className="mt-1 text-[11px] text-muted-foreground">Gri = planul la cota {fo(mp.target)}; verde = banca reală (scară logaritmică). {phase === 'done' ? 'Gata: toate treptele au ieșit.' : ''}</p>
    </div>
  );
}

function recBadge(it: MPItem) {
  if (it.src === 'pinnacle') return <Badge tone="win" title="Superbet peste prețul corect Pinnacle (cote ≤ 2h)">Pinnacle EV {sgn(it.ev)}</Badge>;
  if (!it.rec) return <Badge tone="muted">piață nouă</Badge>;
  return <Badge tone={it.rec.roi >= 0 ? 'win' : it.rec.roi > -0.05 ? 'muted' : 'loss'} title={`${it.rec.n} rezultate în 30 de zile, intră ${(it.rec.hit * 100).toFixed(0)}%`}>piață {sgn(it.rec.roi)}</Badge>;
}

function Picker({ mp, stake, n, onSaved }: { mp: ManualPyr; stake: number; n: number; onSaved: () => void }) {
  const pool = useAsync(loadManualPool, []);
  const [sel, setSel] = useState<MPItem[]>([]);
  const [f, setF] = useState<'all' | 'pin' | 'plus'>('all');
  const [now] = useState(() => Date.now() + 10 * 60e3);
  const items = useMemo(() => (pool.data?.items ?? []).filter((x) => new Date(x.kickoff_utc).getTime() > now
    && (f === 'all' || (f === 'pin' ? x.group === 0 : x.group <= 1))), [pool.data, f, now]);
  const c = combo(sel);
  const ok = sel.length > 0 && c.odds >= mp.target - 1e-9;
  const [open, setOpen] = useState(true);
  const toggle = (it: MPItem) => {
    if (sel.some((x) => x.id === it.id)) { setSel(sel.filter((x) => x.id !== it.id)); return; }
    const clash = sel.find((x) => x.match_id === it.match_id);
    // un singur pariu pe meci: două selecții din același meci sunt legate (și Superbet le poate refuza pe același bilet)
    if (clash) toast.warning(`Un singur pariu pe meci: am înlocuit „${clash.label}” cu „${it.label}” la ${it.home} – ${it.away}.`);
    setSel([...sel.filter((x) => x.match_id !== it.match_id), it]);
  };
  const remove = (id: string) => setSel(sel.filter((x) => x.id !== id));
  const chosen = new Set(sel.map((x) => x.match_id));
  const save = () => {
    const step: MPStep = { n, date: todayRo(), stake, legs: sel.map((x) => ({ ...x })) };
    actions.saveManualPyr({ ...mp, history: [...mp.history, step] });
    toast.success(`Treapta ${n} salvată: ${lei(stake)} la cota ${fo(c.odds)}`);
    setSel([]); onSaved();
  };
  if (pool.loading) return <Notice>Se încarcă oferta zilei…</Notice>;
  if (!pool.data) return <Notice tone="warn">Oferta pentru piramida manuală apare după următoarea rulare a Robotului.</Notice>;
  return (
    <section className="space-y-2">
      <SectionTitle title={`Treapta ${n} · alege selecțiile`} subtitle={`Miză ${lei(stake)} · țintă cota ${fo(mp.target)}`} />
      <div className="card sticky top-2 z-10 bg-[hsl(var(--card))] p-3 shadow-md">
        <div className="flex items-baseline justify-between gap-2">
          <span className="big-num text-2xl">{fo(c.odds)}</span>
          <span className="text-xs text-muted-foreground">șansă <b className="text-foreground">{pct(sel.length ? c.p : 0)}</b> · EV <b className={c.ev >= 0 ? 'text-win' : 'text-loss'}>{sel.length ? sgn(c.ev) : '—'}</b></span>
        </div>
        <div className="mt-1.5 h-1.5 overflow-hidden rounded-full bg-muted"><div className={cn('h-full', ok ? 'bg-[hsl(var(--win))]' : 'bg-primary')} style={{ width: `${Math.min(100, (Math.log(c.odds) / Math.log(mp.target)) * 100)}%` }} /></div>
        <div className="mt-1.5 flex items-center justify-between gap-2 text-[11px] text-muted-foreground">
          <span>{sel.length} selecții · dacă iese: {lei(stake * c.odds)}</span>
          <button type="button" className="btn btn-primary h-9 min-h-0 px-3 text-xs" disabled={!ok} onClick={save}><Check className="h-4 w-4" />Salvează pasul</button>
        </div>
      </div>
      {sel.length > 0 && (
        <div className="card p-3" aria-label="Selecțiile tale">
          <button type="button" className="flex w-full items-center justify-between gap-2 text-left" onClick={() => setOpen(!open)} aria-expanded={open}>
            <b className="text-sm">Selecțiile tale ({sel.length})</b>
            <span className="flex items-center gap-1 text-[11px] text-muted-foreground">{open ? 'ascunde' : 'arată'}<ChevronDown className={cn('h-4 w-4 transition-transform', open && 'rotate-180')} /></span>
          </button>
          {open && <ul className="mt-1.5 divide-y">{[...sel].sort((a, b) => a.kickoff_utc.localeCompare(b.kickoff_utc)).map((x) => (
            <li key={x.id} className="flex items-center gap-2 py-1.5">
              <div className="min-w-0 flex-1">
                <div className="truncate text-[13px] font-semibold">{x.home} – {x.away}</div>
                <div className="truncate text-[11px] text-muted-foreground"><span className="num">{roTime(x.kickoff_utc)}</span> · <span className="font-semibold text-foreground">{x.label}</span></div>
              </div>
              <div className="shrink-0 text-right"><div className="num text-sm font-extrabold">{fo(x.odds)}</div><div className="num text-[10px] text-muted-foreground">{pct(x.p)} · EV {sgn(x.ev)}</div></div>
              <button type="button" className="slip-ico h-8 w-8 shrink-0" aria-label={`Scoate ${x.label}, ${x.home} – ${x.away}`} onClick={() => remove(x.id)}><X className="h-4 w-4" /></button>
            </li>))}</ul>}
          {open && <button type="button" className="mt-1 text-[11px] font-semibold text-primary" onClick={() => setSel([])}>Golește tot</button>}
        </div>)}
      <div className="flex gap-1" role="group" aria-label="Filtru">
        {([['all', 'Toate'], ['pin', 'Pinnacle EV+'], ['plus', 'Piețe pe plus']] as const).map(([k, l]) => (
          <button key={k} type="button" className={cn('chip chip-sm', f === k && 'chip-on')} onClick={() => setF(k)} aria-pressed={f === k}>{l}</button>))}
      </div>
      <p className="text-[11px] text-muted-foreground">{pool.data.rules}</p>
      {items.length === 0 && <Notice>Nimic în filtrul ăsta acum.</Notice>}
      <ul className="space-y-1.5">{items.slice(0, 80).map((it) => {
        const on = sel.some((x) => x.id === it.id);
        const other = !on && chosen.has(it.match_id);
        return (
          <li key={it.id}>
            <button type="button" onClick={() => toggle(it)} aria-pressed={on}
              className={cn('card relative w-full p-2.5 text-left', on && 'border-[hsl(var(--primary))] bg-[hsl(var(--primary)/0.08)] ring-2 ring-[hsl(var(--primary))]', other && 'opacity-70')}>
              {on && <span className="absolute -left-1.5 -top-1.5 grid h-6 w-6 place-items-center rounded-full bg-[hsl(var(--primary))] text-primary-foreground shadow" aria-hidden><Check className="h-3.5 w-3.5" /></span>}
              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0">
                  <div className="truncate text-[13px] font-bold">{it.home} – {it.away}</div>
                  <div className="truncate text-[11px] text-muted-foreground">{roTime(it.kickoff_utc)} · {it.league ?? ''}</div>
                  <div className="mt-0.5 text-xs font-semibold">{it.label}</div>
                </div>
                <div className="shrink-0 text-right">
                  <div className="big-num text-lg">{fo(it.odds)}</div>
                  <div className="num text-[10px] text-muted-foreground">{pct(it.p)} · EV {sgn(it.ev)}</div>
                </div>
              </div>
              <div className="mt-1 flex flex-wrap gap-1">{recBadge(it)}{it.lrec && it.lrec.roi < -0.05 && <Badge tone="warn" title={`${it.lrec.n} rezultate`}>ligă {sgn(it.lrec.roi)}</Badge>}{on && <Badge tone="primary">✓ Adăugat · atinge ca să scoți</Badge>}{other && <Badge tone="warn">ai deja un pariu pe meci</Badge>}</div>
            </button>
          </li>);
      })}</ul>
    </section>
  );
}

export default function ManualPyramid() {
  const stored = useStore((s) => s.manualPyr);
  const list = useMemo(() => stored ?? [], [stored]);
  const [cur, setCur] = useState<string | null>(() => list[0]?.id ?? null);
  const [creating, setCreating] = useState(list.length === 0);
  const res = useAsync(loadManualResults, []);
  const ss = useAsync(loadSsResults, []);
  const pool = useAsync(loadManualPool, []);
  const mp = list.find((x) => x.id === cur) ?? null;
  const state = useMemo(() => (mp ? pyrState(mp, res.data ?? {}, ss.data ?? {}) : null), [mp, res.data, ss.data]);

  // decontare automată: rezultatul selecțiilor se salvează local, iar biletul „Îl joc” din Biletele mele primește statusul
  useEffect(() => {
    if (!mp || !state) return;
    let changed = false;
    const history = mp.history.map((s, i) => {
      const x = state.st[i];
      const legs = s.legs.map((l, k) => (x.rs[k] && x.rs[k] !== l.result ? ((changed = true), { ...l, result: x.rs[k] }) : l));
      if (s.ticketId && x.status !== 'pending') {
        const t = getState().myTickets.find((q) => String(q.id) === s.ticketId);
        if (t && t.status !== x.status) actions.saveTicket({ ...t, status: x.status, payout: x.status === 'won' ? x.odds : 0 } as Ticket);
      }
      return { ...s, legs };
    });
    if (changed) actions.saveManualPyr({ ...mp, history });
  }, [mp, state]);

  // biletele „Îl joc” salvate înainte: completează șansa, numărul de selecții și id-urile Superbet (o singură dată)
  useEffect(() => {
    if (!mp) return;
    for (const s of mp.history) {
      if (!s.ticketId) continue;
      const t = getState().myTickets.find((q) => String(q.id) === s.ticketId);
      if (!t) continue;
      const needLegs = t.legs.length !== s.legs.length || (pool.data && t.legs.some((l) => !l.sb_event_id) && pool.data.items.some((x) => s.legs.some((l) => l.id === x.id && x.sb_event_id)));
      if (t.p_ticket == null || needLegs)
        actions.saveTicket({ ...t, p_ticket: s.legs.reduce((a, l) => a * l.p, 1), legs_count: s.legs.length, ...(needLegs ? { legs: ticketLegs(s.legs, pool.data?.items).map((l, k) => ({ ...l, result: t.legs[k]?.result })) } : {}) } as Ticket);
    }
  }, [mp, pool.data]);

  const play = (s: MPStep) => {
    if (!mp) return;
    if (s.played && s.ticketId) {
      actions.removeTicket(s.ticketId);
      actions.saveManualPyr({ ...mp, history: mp.history.map((h) => (h.n === s.n ? { ...h, played: false, ticketId: undefined } : h)) });
      toast('Scos din „Biletele mele”'); return;
    }
    const st = getState(), budget = st.settings.weeklyBudget ?? 50, spent = weekSpent(st.myTickets, new Date(), budget);
    const fresh = s.n === 1 ? s.stake : 0; // doar miza de start e bani noi; treptele următoare = câștig rulat
    if (budget && fresh > budget - spent && !window.confirm(`Bugetul săptămânii: mai ai ${lei(Math.max(0, budget - spent))} din ${lei(budget)}. O joci totuși?`)) return;
    const id = `${mp.id}-t${s.n}-${mp.cycles.length}`;
    const odds = s.legs.reduce((a, l) => a * l.odds, 1);
    actions.saveTicket({ id, kind: 'pyramid', variant: 'manual_pyr', variant_label: `Piramida mea · T${s.n}`, created_by: 'user', date: s.date, created_at: new Date().toISOString(),
      total_odds: odds, target_odds: mp.target, status: 'pending', followed: true, played_at: new Date().toISOString(), stake: s.stake, stake_lei: fresh,
      ...(s.n > 1 ? { pyr_action: 'Reinvestește', pyr_step: s.n } : { pyr_step: 1 }),
      p_ticket: s.legs.reduce((a, l) => a * l.p, 1), legs_count: s.legs.length, settled_legs: 0,
      legs: ticketLegs(s.legs, pool.data?.items) } as Ticket);
    actions.saveManualPyr({ ...mp, history: mp.history.map((h) => (h.n === s.n ? { ...h, played: true, ticketId: id } : h)) });
    toast.success(fresh ? `Îl joc: ${lei(fresh)} din buget` : 'Îl joc: treaptă reinvestită (nu consumă bugetul)');
  };
  const restart = (result: 'lost' | 'done' | 'reset') => {
    if (!mp || !state) return;
    if (result === 'reset' && !window.confirm('Repornești piramida de la treapta 1? Treptele de acum trec în istoric.')) return;
    actions.saveManualPyr({ ...mp, history: [], cycles: [{ date: todayRo(), steps: state.st.filter((x) => x.status === 'won').length, result, payout: state.payout, start: mp.start }, ...mp.cycles] });
  };
  const del = () => { if (mp && window.confirm(`Ștergi „${mp.name}”?`)) { actions.removeManualPyr(mp.id); setCur(list.find((x) => x.id !== mp.id)?.id ?? null); setCreating(list.length <= 1); } };

  return (
    <div className="space-y-4">
      <div className="flex gap-1.5 overflow-x-auto pb-0.5" role="group" aria-label="Piramidele mele">
        {list.map((x) => <button key={x.id} type="button" className={cn('chip chip-sm shrink-0', !creating && cur === x.id && 'chip-on')} onClick={() => { setCur(x.id); setCreating(false); }}>{x.name}</button>)}
        <button type="button" className={cn('chip chip-sm shrink-0', creating && 'chip-on')} onClick={() => setCreating(true)}><Plus className="h-3.5 w-3.5" />Nouă</button>
      </div>
      {creating || !mp || !state ? <NewForm onDone={(id) => { setCur(id); setCreating(false); }} /> : (
        <>
          <Card className="p-4">
            <div className="mb-1 flex items-start justify-between gap-2">
              <div className="min-w-0"><div className="eyebrow">Manuală · tu alegi</div><h2 className="truncate text-lg font-extrabold">{mp.name}</h2></div>
              <div className="flex shrink-0 gap-1">
                <button type="button" className="slip-ico" aria-label="Repornește de la treapta 1" onClick={() => restart('reset')}><RotateCcw className="h-4 w-4" /></button>
                <button type="button" className="slip-ico" aria-label="Șterge piramida" onClick={del}><Trash2 className="h-4 w-4" /></button>
              </div>
            </div>
            <p className="mb-3 text-xs text-muted-foreground">Start {lei(mp.start)} · {mp.steps} trepte la cota ~{fo(mp.target)} · treapta {Math.min(state.phase === 'pending' ? mp.history.length : state.next, mp.steps)}/{mp.steps}{state.phase === 'pending' ? ' (în joc)' : ''} · miza acum <b className="text-foreground">{lei(state.stake)}</b></p>
            <Steps mp={mp} st={state.st} phase={state.phase} />
          </Card>
          {state.phase === 'lost' && <Card className="p-3 text-sm">Treapta {state.st.length} a pierdut. <button type="button" className="btn btn-primary mt-2 w-full" onClick={() => restart('lost')}>Reia cu {lei(mp.start)} de la treapta 1</button></Card>}
          {state.phase === 'done' && <Card className="p-3 text-sm">Toate cele {mp.steps} trepte au ieșit: <b className="text-win">{lei(state.payout)}</b>. Încasează pe Superbet. <button type="button" className="btn btn-primary mt-2 w-full" onClick={() => restart('done')}>Încasat · pornesc din nou</button></Card>}
          {state.st.slice().reverse().map((x) => (
            <Card key={x.s.n} className="p-3">
              <div className="mb-1 flex items-center justify-between gap-2">
                <b className="text-sm">Treapta {x.s.n} · {lei(x.s.stake)} × {fo(x.odds)}</b>
                <Badge tone={x.status === 'won' ? 'win' : x.status === 'lost' ? 'loss' : 'pending'}>{x.status === 'won' ? 'câștigat' : x.status === 'lost' ? 'pierdut' : `în curs ${x.settled}/${x.s.legs.length}`}</Badge>
              </div>
              <ul className="divide-y text-xs">{x.s.legs.map((l, k) => (
                <li key={l.id} className="flex items-center gap-2 py-1.5">
                  <div className="min-w-0 flex-1">
                    <div className="truncate font-semibold">{l.home} – {l.away}</div>
                    <div className="truncate text-[11px] text-muted-foreground"><span className="num">{roTime(l.kickoff_utc)}</span> · {l.label}</div>
                  </div>
                  <span className="num shrink-0 font-bold">{fo(l.odds)}</span>
                  <Badge tone={x.rs[k] === 'w' ? 'win' : x.rs[k] === 'l' ? 'loss' : x.rs[k] === 'v' ? 'muted' : 'pending'}>{x.rs[k] === 'w' ? 'câștigat' : x.rs[k] === 'l' ? 'pierdut' : x.rs[k] === 'v' ? 'anulat' : 'în așteptare'}</Badge>
                </li>))}
              </ul>
              {x.status === 'pending' && (
                <div className="mt-2 flex gap-1.5">
                  <button type="button" className={cn('btn h-9 min-h-0 flex-1 rounded-xl text-xs', x.s.played ? 'border border-[hsl(var(--win))] text-win' : 'btn-primary')} onClick={() => play(x.s)}>{x.s.played ? 'Jucat ✓' : 'Îl joc'}</button>
                  {!x.s.played && x.settled === 0 && <button type="button" className="btn btn-outline h-9 min-h-0 rounded-xl text-xs" onClick={() => actions.saveManualPyr({ ...mp, history: mp.history.filter((h) => h.n !== x.s.n) })}>Refac pasul</button>}
                </div>)}
            </Card>))}
          {state.phase === 'build' && <Picker key={`${mp.id}-${state.next}`} mp={mp} stake={state.stake} n={state.next} onSaved={() => undefined} />}
          {mp.cycles.length > 0 && (
            <Card className="p-3 text-xs"><b className="text-sm">Serii încheiate</b>
              <ul className="mt-1 space-y-0.5">{mp.cycles.map((c, i) => <li key={i} className="flex justify-between"><span>{c.date} · {c.steps}/{mp.steps} trepte · {c.result === 'done' ? 'încasat' : c.result === 'lost' ? 'pierdut' : 'repornit'}</span><b className="num">{c.result === 'done' ? lei(c.payout) : `−${lei(c.start)}`}</b></li>)}</ul>
            </Card>)}
        </>
      )}
      <p className="text-[11px] text-muted-foreground">Piramidele manuale stau doar pe telefonul tău (și în sincronizarea cloud, dacă e pornită). Doar „Îl joc” pe treapta 1 intră în bugetul săptămânii.</p>
    </div>
  );
}
