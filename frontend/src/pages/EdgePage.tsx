import { useMemo, useState } from 'react';
import { Link, useLocation, useNavigate } from 'react-router';
import { Crosshair, Wallet } from 'lucide-react';
import { LazyChart } from '@/components/LazyChart';
import { Card, Segmented, Stat, Badge, Loading, Empty, Notice } from '@/components/kit';
import { useDays } from '@/lib/hooks';
import { useAsync } from '@/lib/fetcher';
import { loadUpcomingTickets } from '@/lib/data';
import { addDays, todayRo, pct, signed, odds as fo, roKickoff, dayLabel } from '@/lib/format';
import { safetyOf } from '@/lib/ui';
import { isRecommended } from '@/lib/rules';
import { suggestedStake } from '@/lib/robot';
import { cn } from '@/lib/utils';

const tip = { contentStyle: { background: 'hsl(var(--popover))', border: '1px solid hsl(var(--border))', fontSize: 12, borderRadius: 12 } };
const ax = { fontSize: 11, fill: 'hsl(var(--muted-foreground))' };
const DAILY_CAP = 5; // u/zi — plafonul de expunere al Robotului
const BANK_KEY = 'bp.bank.lei';

interface Edge { id: string; match_id: number; date: string; kickoff: string; match: string; league: string; label: string; odds: number; p: number; ev: number; safety: number; rec: boolean; book?: string | null; score: number; stake: number }

function useEdges(days: number) {
  const t = todayRo();
  const dates = useMemo(() => Array.from({ length: days }, (_, i) => addDays(t, i)), [t, days]);
  const res = useDays(dates);
  const [now] = useState(() => Date.now());
  const edges = useMemo(() => {
    const out: Edge[] = [];
    for (const d of res.data ?? []) for (const m of d?.matches ?? []) {
      if (Date.parse(m.kickoff_utc) < now) continue;
      for (const p of m.predictions ?? []) {
        if (p.odds == null || p.odds <= 1 || p.p == null) continue;
        const ev = p.ev ?? p.p * p.odds - 1;
        const s = safetyOf(p);
        out.push({ id: `${m.id}-${p.market}-${p.line ?? ''}-${p.selection}`, match_id: m.id, date: d!.date, kickoff: m.kickoff_utc, match: `${m.home.name} – ${m.away.name}`, league: m.league.name,
          label: p.label, odds: p.odds, p: p.p, ev, safety: s, rec: isRecommended(p), book: p.bookmaker, score: Math.max(0, ev) * s, stake: suggestedStake(p.p, p.odds, 2) });
      }
    }
    return out;
  }, [res.data, now]);
  return { edges, loading: res.loading };
}

function EdgeBoard() {
  const [days, setDays] = useState<'1' | '3' | '7'>('3');
  const [only, setOnly] = useState<'value' | 'rec' | 'all'>('value');
  const { edges, loading } = useEdges(Number(days));
  const list = useMemo(() => edges.filter((e) => (only === 'all' ? true : only === 'rec' ? e.rec : e.ev > 0)).sort((a, b) => b.score - a.score || b.ev - a.ev), [edges, only]);
  const pts = list.slice(0, 400).map((e) => ({ x: e.safety, y: +(e.ev * 100).toFixed(2), z: e.odds, rec: e.rec, name: `${e.match} · ${e.label}` }));
  if (loading) return <Loading />;
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <Segmented size="sm" value={days} onChange={setDays} options={[{ value: '1', label: 'Azi' }, { value: '3', label: '3 zile' }, { value: '7', label: '7 zile' }]} />
        <Segmented size="sm" value={only} onChange={setOnly} options={[{ value: 'value', label: 'Valoare (EV>0)' }, { value: 'rec', label: 'Recomandate' }, { value: 'all', label: 'Toate' }]} />
      </div>
      <Card className="p-4">
        <h3 className="text-sm font-semibold">EV × Siguranță</h3>
        <p className="mb-2 text-xs text-muted-foreground">Dreapta-sus = valoare mare și siguranță mare. Verde = recomandat de Robot.</p>
        {!pts.length ? <p className="text-sm text-muted-foreground">Nicio selecție.</p> : <LazyChart className="h-72">{(R) => <R.ResponsiveContainer><R.ScatterChart margin={{ left: 0, right: 8 }}><R.CartesianGrid strokeDasharray="2 6" opacity={0.25} /><R.XAxis type="number" dataKey="x" name="Siguranță" domain={[0, 100]} tick={ax} /><R.YAxis type="number" dataKey="y" name="EV" unit="%" tick={ax} /><R.ZAxis dataKey="z" range={[30, 160]} name="cotă" /><R.Tooltip {...tip} cursor={{ strokeDasharray: '3 3' }} formatter={(v: number, n: string) => (n === 'EV' ? `${v}%` : v)} labelFormatter={() => ''} /><R.ReferenceLine y={0} stroke="#888" /><R.ReferenceLine x={70} stroke="hsl(var(--primary))" strokeDasharray="4 4" />
          <R.Scatter data={pts}>{pts.map((p, i) => <R.Cell key={i} fill={p.rec ? 'hsl(var(--win))' : p.y > 0 ? 'hsl(var(--glow-2))' : 'hsl(var(--muted-foreground))'} fillOpacity={0.75} />)}</R.Scatter></R.ScatterChart></R.ResponsiveContainer>}</LazyChart>}
      </Card>
      <Card className="overflow-hidden">
        <h3 className="px-4 pt-3 text-sm font-semibold">Clasament ({list.length})</h3>
        {!list.length ? <div className="p-4"><Empty title="Nicio selecție pentru filtrele alese" /></div> : (
          <div className="overflow-x-auto"><table className="pro-table w-full text-sm">
            <thead><tr><th className="text-left">Meci · pariu</th><th>Cotă</th><th>Șansă</th><th>EV</th><th>Sig.</th><th>Miză</th></tr></thead>
            <tbody>{list.slice(0, 60).map((e) => (
              <tr key={e.id}><td className="text-left"><Link to={`/meci/${e.match_id}`} className="block max-w-[260px] hover:text-primary"><span className="block truncate font-semibold">{e.label} {e.rec && <Badge tone="win">recomandat</Badge>}</span><span className="block truncate text-[11px] text-muted-foreground">{e.match} · {roKickoff(e.kickoff)}</span></Link></td>
                <td>{fo(e.odds)}{e.book === 'Superbet' && <span className="block text-[10px] text-muted-foreground">Superbet</span>}</td><td>{pct(e.p)}</td>
                <td className={e.ev >= 0 ? 'text-win' : 'text-loss'}>{signed(e.ev * 100, 1, '%')}</td><td>{e.safety}</td><td>{e.stake ? `${e.stake}u` : '—'}</td></tr>
            ))}</tbody></table></div>
        )}
      </Card>
    </div>
  );
}

function Bankroll() {
  const [bank, setBank] = useState<number>(() => Number(localStorage.getItem(BANK_KEY)) || 1000);
  const unit = bank / 100;
  const { edges, loading } = useEdges(7);
  const up = useAsync(loadUpcomingTickets, []);
  const byDay = useMemo(() => {
    const m = new Map<string, { singles: number; tickets: number; n: number; nt: number }>();
    const get = (d: string) => m.get(d) ?? (m.set(d, { singles: 0, tickets: 0, n: 0, nt: 0 }), m.get(d)!);
    for (const e of edges) if (e.rec && e.stake > 0) { const g = get(e.date); g.singles += e.stake; g.n++; }
    for (const t of up.data?.tickets ?? []) if (t.status === 'pending' && t.date) { const g = get(t.date); g.tickets += t.stake_units ?? 0; g.nt++; }
    return [...m.entries()].sort(([a], [b]) => a.localeCompare(b)).map(([d, g]) => ({ day: d, label: dayLabel(d), ...g, total: Math.min(DAILY_CAP, g.singles + g.tickets), raw: g.singles + g.tickets }));
  }, [edges, up.data]);
  const today = byDay.find((d) => d.day === todayRo());
  if (loading) return <Loading />;
  return (
    <div className="space-y-4">
      <Card className="p-4">
        <label className="block text-xs font-medium text-muted-foreground" htmlFor="bank">Banca ta (lei)</label>
        <input id="bank" type="number" inputMode="decimal" min={0} className="input mt-1 max-w-[220px]" value={bank} onChange={(e) => { const v = Number(e.target.value) || 0; setBank(v); localStorage.setItem(BANK_KEY, String(v)); }} />
        <p className="mt-1 text-xs text-muted-foreground">1 unitate (u) = 1% din bancă = <b className="num text-foreground">{unit.toFixed(2)} lei</b>. Se salvează doar pe acest dispozitiv.</p>
      </Card>
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <Stat label="Expunere azi" value={`${(today?.raw ?? 0).toFixed(2)}u`} sub={`${((today?.raw ?? 0) * unit).toFixed(0)} lei · plafon ${DAILY_CAP}u`} tone={(today?.raw ?? 0) > DAILY_CAP ? 'warn' : undefined} />
        <Stat label="Single-uri recomandate azi" value={today?.n ?? 0} sub={`${(today?.singles ?? 0).toFixed(2)}u (¼ Kelly)`} />
        <Stat label="Bilete active azi" value={today?.nt ?? 0} sub={`${(today?.tickets ?? 0).toFixed(2)}u`} />
        <Stat label="Expunere 7 zile" value={`${byDay.reduce((a, d) => a + d.total, 0).toFixed(1)}u`} sub={`${(byDay.reduce((a, d) => a + d.total, 0) * unit).toFixed(0)} lei, plafonat pe zi`} />
      </div>
      <Card className="p-4"><h3 className="text-sm font-semibold">Expunere pe zile</h3>
        <p className="mb-2 text-xs text-muted-foreground">Single-uri recomandate (¼ Kelly) + biletele Robotului. Linia = plafonul zilnic de {DAILY_CAP}u.</p>
        {!byDay.length ? <p className="text-sm text-muted-foreground">Nicio miză planificată.</p> : <LazyChart className="h-56">{(R) => <R.ResponsiveContainer><R.BarChart data={byDay}><R.CartesianGrid strokeDasharray="2 6" opacity={0.25} /><R.XAxis dataKey="label" tick={ax} /><R.YAxis tick={ax} unit="u" /><R.Tooltip {...tip} formatter={(v: number) => `${v.toFixed(2)}u · ${(v * unit).toFixed(0)} lei`} /><R.Legend wrapperStyle={{ fontSize: 11 }} /><R.ReferenceLine y={DAILY_CAP} stroke="hsl(var(--warn))" strokeDasharray="4 4" /><R.Bar dataKey="singles" stackId="a" name="single-uri" fill="hsl(var(--primary))" /><R.Bar dataKey="tickets" stackId="a" name="bilete" fill="hsl(var(--glow-3))" radius={[4, 4, 0, 0]} /></R.BarChart></R.ResponsiveContainer>}</LazyChart>}
      </Card>
      <Card className="overflow-hidden"><h3 className="px-4 pt-3 text-sm font-semibold">Mize Kelly pentru azi</h3>
        <div className="overflow-x-auto"><table className="pro-table w-full text-sm"><thead><tr><th className="text-left">Pariu</th><th>Cotă</th><th>EV</th><th>Miză</th><th>Lei</th></tr></thead>
          <tbody>{edges.filter((e) => e.rec && e.stake > 0 && e.date === todayRo()).sort((a, b) => b.stake - a.stake).map((e) => (
            <tr key={e.id}><td className="text-left"><span className="block max-w-[240px] truncate font-semibold">{e.label}</span><span className="block max-w-[240px] truncate text-[11px] text-muted-foreground">{e.match}</span></td><td>{fo(e.odds)}</td><td className="text-win">{signed(e.ev * 100, 1, '%')}</td><td>{e.stake}u</td><td>{(e.stake * unit).toFixed(0)}</td></tr>
          ))}</tbody></table></div>
      </Card>
      <Card className="p-4 text-sm">
        <h3 className="mb-2 text-sm font-semibold">Planul de mize</h3>
        <ul className="list-disc space-y-1 pl-5 text-muted-foreground">
          <li><b className="text-foreground">Single-uri recomandate:</b> ¼ Kelly, max. 2u pe pariu.</li>
          <li><b className="text-foreground">Bilete de valoare (2–4 selecții):</b> ⅛ Kelly, max. 1u pe bilet.</li>
          <li><b className="text-foreground">Loterie (~50 … ~2000):</b> miză fixă 0,10–0,25u — o pierdere aproape sigură, joacă doar distracție.</li>
          <li><b className="text-foreground">Bilete sigure:</b> doar informativ (0u) — pierd pe termen lung.</li>
          <li><b className="text-foreground">Plafon:</b> {DAILY_CAP}u pe zi în total. Recalculează unitatea lunar, nu după fiecare pierdere.</li>
        </ul>
      </Card>
      <Notice>Mizele sunt orientative. Kelly presupune că șansele Robotului sunt corecte; de aceea folosim doar o fracțiune (¼ sau ⅛).</Notice>
    </div>
  );
}

export default function EdgePage() {
  const loc = useLocation();
  const nav = useNavigate();
  const tab: 'edge' | 'bank' = /tab=banca/.test(loc.search) ? 'bank' : 'edge';
  const setTab = (v: 'edge' | 'bank') => nav(v === 'bank' ? '/edge?tab=banca' : '/edge', { replace: true });
  return (
    <div className="space-y-4">
      <div>
        <h1 className="flex items-center gap-2">{tab === 'edge' ? <Crosshair className="h-7 w-7 text-primary" aria-hidden /> : <Wallet className="h-7 w-7 text-primary" aria-hidden />}{tab === 'edge' ? 'Edge Board' : 'Banca'}</h1>
        <p className="text-sm text-muted-foreground">{tab === 'edge' ? 'Toate selecțiile cu cotă, ordonate după valoare × siguranță.' : 'Mize Kelly, expunere zilnică și planul de mize.'}</p>
      </div>
      <Segmented value={tab} onChange={setTab} className={cn('w-full')} options={[{ value: 'edge', label: 'Edge Board' }, { value: 'bank', label: 'Banca' }]} />
      {tab === 'edge' ? <EdgeBoard /> : <Bankroll />}
    </div>
  );
}
