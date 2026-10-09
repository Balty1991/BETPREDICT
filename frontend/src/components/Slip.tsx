import { useState } from 'react';
import { Ticket as TicketIcon, X, Trash2, Save, AlertTriangle } from 'lucide-react';
import { useStore, actions } from '@/lib/store';
import { odds as fo, pct, signed, roKickoff, todayRo } from '@/lib/format';
import { plainPick } from '@/lib/markets';
import { cn } from '@/lib/utils';
import { toast } from 'sonner';
import { manualTicketMetrics } from '@/lib/robot';

export function Slip() {
  const slip = useStore((s) => s.slip);
  const minOdds = useStore((s) => s.settings.minOdds);
  const stakeDef = useStore((s) => s.settings.defaultStake);
  const [open, setOpen] = useState(false);
  const [stake, setStake] = useState<number>(stakeDef);
  if (!slip.length && !open) return null;
  const total = slip.reduce((a, l) => a * l.odds, 1);
  // probabilitate prudentă (model 50% spre piață), ca la biletele Robotului; miza sugerată ¼ Kelly
  const { pAdj: p, evAdj: ev, stakeUnits } = manualTicketMetrics(slip);
  const leagues = new Map<string, number>();
  slip.forEach((l) => leagues.set(l.league ?? '', (leagues.get(l.league ?? '') ?? 0) + 1));
  const warnings: string[] = [];
  if (slip.some((l) => l.odds < minOdds)) warnings.push(`Selecții sub cota minimă ${minOdds.toFixed(2)}`);
  if ([...leagues.values()].some((v) => v > 2)) warnings.push('Peste 2 selecții din aceeași ligă (corelație)');
  if (slip.some((l) => l.grade === 'D' || l.grade === 'C')) warnings.push('Conține selecții de grad C/D');
  const save = () => {
    actions.saveTicket({
      id: `manual-${Date.now().toString(36)}`, kind: 'manual', variant: 'manual', variant_label: 'Bilet manual', created_by: 'user',
      date: todayRo(), created_at: new Date().toISOString(), total_odds: Math.round(total * 100) / 100, p_ticket: p, ev, status: 'pending',
      legs: [...slip].sort((a, b) => (a.kickoff_utc ?? '').localeCompare(b.kickoff_utc ?? '')), legs_count: slip.length, settled_legs: 0, stake, stake_units: stakeUnits || null,
    });
    actions.clearSlip();
    setOpen(false);
    toast.success('Bilet salvat în „Biletele mele” și în Statistici › Bilete (Manual). Se decontează automat.');
  };
  return (
    <>
      <button onClick={() => setOpen(true)} className="btn-primary press fixed bottom-[calc(84px+env(safe-area-inset-bottom))] right-4 z-40 flex min-h-[48px] items-center gap-2 rounded-full px-4 py-3 text-sm font-bold md:bottom-6">
        <TicketIcon className="h-4 w-4" /> Bilet ({slip.length}) · {fo(total)}
      </button>
      {open && (
        <div className="fixed inset-0 z-50 flex items-end justify-center bg-black/50 md:items-center" onClick={() => setOpen(false)}>
          <div className="card pb-safe sheet-enter max-h-[85vh] w-full max-w-lg overflow-y-auto rounded-b-none p-4 md:rounded-2xl" onClick={(e) => e.stopPropagation()}>
            <div className="mb-3 flex items-center justify-between">
              <h3 className="font-semibold">Constructor bilet manual</h3>
              <button className="btn btn-ghost px-2" onClick={() => setOpen(false)}><X className="h-4 w-4" /></button>
            </div>
            {!slip.length && <p className="text-sm text-muted-foreground">Adaugă selecții din pagina Predicții cu butonul „+”.</p>}
            <ul className="divide-y">
              {slip.map((l) => (
                <li key={`${l.match_id}-${l.market}-${l.selection}`} className="flex items-start gap-2 py-2 text-sm">
                  <div className="min-w-0 flex-1">
                    <div className="font-medium leading-snug [overflow-wrap:anywhere]">{l.home} – {l.away}</div>
                    <div className="text-xs font-semibold">{plainPick(l.market, l.line, l.selection, l.label)}</div>
                    <div className="text-xs text-muted-foreground">{roKickoff(l.kickoff_utc)}{l.league ? ` · ${l.league}` : ''}</div>
                  </div>
                  <div className="text-right"><div className="font-semibold">{fo(l.odds)}</div>{l.p != null && <div className="text-[11px] text-muted-foreground">{pct(l.p)}</div>}</div>
                  <button className="btn btn-ghost px-1.5" onClick={() => actions.toggleSlip(l)}><Trash2 className="h-4 w-4" /></button>
                </li>
              ))}
            </ul>
            {slip.length > 0 && (
              <div className="mt-3 space-y-2">
                <div className="grid grid-cols-3 gap-2 text-center text-sm">
                  <div className="rounded-lg bg-muted p-2"><div className="text-[11px] text-muted-foreground">Cotă totală</div><div className="font-bold">{fo(total)}</div></div>
                  <div className="rounded-lg bg-muted p-2"><div className="text-[11px] text-muted-foreground">Prob. prudentă</div><div className="font-bold">{pct(p, p != null && p < 0.1 ? 1 : 0)}</div></div>
                  <div className="rounded-lg bg-muted p-2"><div className="text-[11px] text-muted-foreground">EV prudent</div><div className={cn('font-bold', (ev ?? 0) > 0 ? 'text-win' : 'text-loss')}>{signed(ev != null ? ev * 100 : null, 1, '%')}</div></div>
                </div>
                <div className="rounded-lg border px-2 py-1.5 text-xs text-muted-foreground" title="¼ Kelly pe probabilitatea prudentă, plafonat după cota totală. 1u = 1% din banca ta.">
                  {stakeUnits > 0 ? <>Miză sugerată: <b className="text-foreground">{stakeUnits}u</b> ({stakeUnits}% din bancă) · probabilitate prudentă (model tras 50% spre piață)</> : <>EV prudent ≤ 0 — miza sugerată este <b className="text-foreground">0</b>. Biletul nu are valoare după ajustarea spre piață.</>}
                </div>
                {warnings.map((w) => <div key={w} className="flex items-center gap-2 rounded-lg bg-warn px-2 py-1.5 text-xs text-warn"><AlertTriangle className="h-3.5 w-3.5" />{w}</div>)}
                <label className="flex items-center gap-2 text-sm">Miză (lei)
                  <input type="number" min={1} className="input w-24" value={stake} onChange={(e) => setStake(Number(e.target.value) || 0)} />
                  <span className="ml-auto text-muted-foreground">Câștig posibil: <b className="text-foreground">{(stake * total).toFixed(2)} lei</b></span>
                </label>
                <div className="flex gap-2">
                  <button className="btn btn-outline flex-1" onClick={() => actions.clearSlip()}>Golește</button>
                  <button className="btn btn-primary flex-1" onClick={save}><Save className="h-4 w-4" />Salvează biletul meu</button>
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </>
  );
}
