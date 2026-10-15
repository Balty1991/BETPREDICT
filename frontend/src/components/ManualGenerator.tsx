import { useMemo, useState } from 'react';
import { Bot, ChevronRight, Wand2 } from 'lucide-react';
import { useDays } from '@/lib/hooks';
import { useStore } from '@/lib/store';
import { buildPool, beamSearch, makeTicket, type Candidate } from '@/lib/robot';
import { isLostTicket } from '@/lib/board';
import { addDays } from '@/lib/format';
import { TicketCard } from './TicketCard';
import type { Ticket } from '@/lib/types';

/** Generatorul cu regulile tale. Încarcă meciurile zilei doar când e deschis. */
export function ManualGenerator({ date }: { date: string }) {
  const [open, setOpen] = useState(false);
  return (
    <details className="card group p-4" onToggle={(e) => setOpen(e.currentTarget.open)}>
      <summary className="flex min-h-[44px] cursor-pointer list-none items-center gap-2 font-bold"><Wand2 className="h-4 w-4 text-primary" />Generator cu regulile tale<ChevronRight className="ml-auto h-4 w-4 text-muted-foreground transition-transform group-open:rotate-90" /></summary>
      {open && <GeneratorBody date={date} />}
    </details>
  );
}

function GeneratorBody({ date }: { date: string }) {
  const [span, setSpan] = useState(3);
  const days = useDays(useMemo(() => Array.from({ length: span }, (_, i) => addDays(date, i)), [date, span]));
  const settings = useStore((s) => s.settings);
  const pool: Candidate[] = useMemo(() => (days.data ? buildPool(days.data.filter(Boolean) as never, { minOdds: settings.minOdds, allowEstimated: settings.allowEstimatedOdds }) : []), [days.data, settings.minOdds, settings.allowEstimatedOdds]);
  const [target, setTarget] = useState(20);
  const [nMin, setNMin] = useState(3);
  const [nMax, setNMax] = useState(8);
  const [markets, setMarkets] = useState<'all' | 'goals' | 'results'>('all');
  const [minP, setMinP] = useState(0.55);
  const [res, setRes] = useState<Ticket | null>(null);
  const [err, setErr] = useState('');
  const run = () => {
    const f = pool.filter((c) => c.pAdj >= minP * 0.9 && (markets === 'all' || (markets === 'goals' ? ['over_under', 'btts'].includes(c.p.market) : ['1x2', 'double_chance', 'draw_no_bet'].includes(c.p.market))));
    const legs = beamSearch(f, { min: target * 0.85, max: target * 1.25, nMin, nMax }, (c) => -c.lp / c.lo, new Set());
    if (!legs) {
      const nm = new Set(f.map((c) => c.m.id)).size;
      setRes(null);
      setErr(nm < nMin
        ? `Doar ${nm} meciuri neîncepute au o selecție cu șansă ≥ ${Math.round(minP * 100)}% și cotă ≥ ${settings.minOdds} în ${span === 1 ? 'ziua aleasă' : `următoarele ${span} zile`}; ai cerut cel puțin ${nMin}. Ia mai multe zile, scade șansa minimă sau cota minimă din Setări.`
        : `Sunt ${nm} meciuri potrivite, dar nu ies ${nMin}–${nMax} selecții la cota ~${target}. Schimbă cota țintă sau numărul de meciuri.`);
      return;
    }
    setErr('');
    setRes(makeTicket(legs, { kind: 'manual_robot', variant: 'personalizat', variant_label: `Personalizat ~${target}`, target, date, created_by: 'robot', reasons: [`Reguli: ${nMin}–${nMax} meciuri, p ≥ ${Math.round(minP * 100)}%, ${markets === 'all' ? 'toate piețele' : markets === 'goals' ? 'doar goluri' : 'doar rezultat'}`] }));
  };
  return (
    <div className="mt-3">
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-6">
        <label className="text-xs text-muted-foreground">Cotă țintă<input type="number" min={1.5} step={1} className="input mt-1" value={target} onChange={(e) => setTarget(Math.max(1.5, Number(e.target.value) || 2))} /></label>
        <label className="text-xs text-muted-foreground">Min. meciuri<input type="number" min={1} max={30} className="input mt-1" value={nMin} onChange={(e) => setNMin(Math.min(30, Number(e.target.value) || 1))} /></label>
        <label className="text-xs text-muted-foreground">Max. meciuri<input type="number" min={1} max={30} className="input mt-1" value={nMax} onChange={(e) => setNMax(Math.min(30, Number(e.target.value) || 1))} /></label>
        <label className="text-xs text-muted-foreground">Meciuri din<select className="input mt-1" value={span} onChange={(e) => setSpan(Number(e.target.value))}><option value={1}>Ziua aleasă</option><option value={2}>Ziua aleasă + mâine</option><option value={3}>Următoarele 3 zile</option><option value={7}>Următoarele 7 zile</option></select></label>
        <label className="text-xs text-muted-foreground">Piețe<select className="input mt-1" value={markets} onChange={(e) => setMarkets(e.target.value as 'all')}><option value="all">Toate</option><option value="goals">Doar goluri</option><option value="results">Doar rezultat (1X2/DC/DNB)</option></select></label>
        <label className="text-xs text-muted-foreground">Șansă minimă / selecție: <b className="text-foreground">{Math.round(minP * 100)}%</b><input type="range" min={0.4} max={0.9} step={0.05} className="mt-2 w-full" value={minP} onChange={(e) => setMinP(Number(e.target.value))} /></label>
      </div>
      <button className="btn btn-primary mt-3" disabled={days.loading} onClick={run}><Bot className="h-4 w-4" />{days.loading ? 'Se încarcă meciurile…' : 'Generează'}</button>
      {err && <p className="mt-2 text-sm text-warn">{err}</p>}
      {res && !isLostTicket(res) && <div className="mt-3"><TicketCard t={res} /></div>}
    </div>
  );
}
