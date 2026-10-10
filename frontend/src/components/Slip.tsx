import { useState } from 'react';
import { Trash2, Save, AlertTriangle, ChevronUp } from 'lucide-react';
import { Sheet } from '@/components/kit';
import { useCountUp } from '@/lib/gestures';
import { useStore, actions } from '@/lib/store';
import { odds as fo, pct, signed, roKickoff, todayRo } from '@/lib/format';
import { plainPick } from '@/lib/markets';
import { cn } from '@/lib/utils';
import { toast } from 'sonner';
import { manualTicketMetrics } from '@/lib/robot';

/** Bara de bilet (stil Superbet): în fluxul app shell-ului, deasupra meniului; crește când adaugi selecții. */
export function SlipBar() {
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
      {slip.length > 0 && <SlipStrip n={slip.length} total={total} payout={stake * total} last={slip[slip.length - 1]} onOpen={() => setOpen(true)} />}
      <Sheet open={open} onClose={() => setOpen(false)} title="Biletul meu" subtitle={`${slip.length} selecții · cotă ${fo(total)}`}>
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
      </Sheet>
    </>
  );
}

function SlipStrip({ n, total, payout, last, onOpen }: { n: number; total: number; payout: number; last: { home?: string; away?: string; label?: string; market: string; line?: number | null; selection: string; odds: number }; onOpen: () => void }) {
  const t = useCountUp(total, 450), w = useCountUp(payout, 450);
  return (
    <div className="slip-strip relative z-[79] shrink-0 px-3 pt-2 md:mx-auto md:w-full md:max-w-6xl md:px-6">
      <button type="button" onClick={onOpen} aria-label={`Deschide biletul: ${n} selecții, cotă ${total.toFixed(2)}`}
        className="slip-bar press flex w-full items-center gap-3 rounded-2xl px-3.5 py-2.5 text-left">
        <span key={n} className="slip-count num grid h-9 w-9 shrink-0 place-items-center rounded-xl text-sm font-extrabold">{n}</span>
        <span className="min-w-0 flex-1">
          <span className="block truncate text-[13px] font-bold">{plainPick(last.market, last.line ?? null, last.selection, last.label ?? '')} <span className="font-medium opacity-80">· {last.home} – {last.away}</span></span>
          <span className="block text-[11px] opacity-80">Câștig posibil <b className="num">{w.toFixed(2)} lei</b></span>
        </span>
        <span className="text-right"><span className="block text-[10px] font-semibold uppercase tracking-wider opacity-80">Cotă</span><span className="num block text-lg font-extrabold leading-none">{t.toFixed(2)}</span></span>
        <ChevronUp className="h-4 w-4 opacity-80" aria-hidden />
      </button>
    </div>
  );
}
