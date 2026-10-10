import { useEffect, useState } from 'react';
import { CheckCircle2, Circle, ExternalLink, Loader2, AlertTriangle } from 'lucide-react';
import { Sheet } from './kit';
import type { Ticket } from '@/lib/types';
import { plainPick } from '@/lib/markets';
import { odds as fo, roKickoff } from '@/lib/format';
import { betslipAppLink, eventAppLink, openSuperbet, resolveOdd } from '@/lib/superbet';
import { cn } from '@/lib/utils';

type R = { uuid: string; price: number } | null | undefined;
const webOf = (eid: string) => `https://superbet.ro/cote/fotbal/meci-${eid}`;

/**
 * „Joacă pe Superbet”: deschide biletul precompletat în aplicația Superbet (rosuperbetsport://betslip),
 * plus un ghid pas-cu-pas pe selecții. Nu plasează nimic: miza și confirmarea le faci tu în aplicație.
 */
export function PlayOnSuperbet({ t, open, onClose }: { t: Ticket; open: boolean; onClose: () => void }) {
  const legs = t.legs.filter((l) => !l.result);
  const [res, setRes] = useState<R[]>([]);
  const [done, setDone] = useState<Set<number>>(new Set());
  useEffect(() => {
    if (!open) return;
    let alive = true;
    Promise.all(legs.map((l) => (l.sb_event_id ? resolveOdd({ eventId: l.sb_event_id, market: l.market, line: l.line, selection: l.selection }) : Promise.resolve(null))))
      .then((r) => { if (alive) setRes(r); });
    return () => { alive = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, t.id]);
  const ready = legs.map((l, i) => (l.sb_event_id && res[i] ? { eventId: l.sb_event_id, uuid: res[i]!.uuid } : null)).filter(Boolean) as Array<{ eventId: string; uuid: string }>;
  const loading = open && res.length !== legs.length;
  const total = legs.reduce((a, l, i) => a * (res[i]?.price ?? l.odds), 1);
  const openLeg = (i: number) => {
    const eid = legs[i].sb_event_id; if (!eid) return;
    openSuperbet(eventAppLink(eid), webOf(eid));
    setDone((d) => new Set(d).add(i));
  };
  return (
    <Sheet open={open} onClose={onClose} title="Joacă pe Superbet" subtitle="Tu alegi miza și confirmi în aplicație. BetPredict nu plasează pariuri.">
      <div className="space-y-3">
        <button className="btn btn-primary w-full" disabled={loading || !ready.length}
          onClick={() => openSuperbet(betslipAppLink(ready), ready[0] ? webOf(ready[0].eventId) : 'https://superbet.ro/pariuri-sportive/fotbal')}>
          {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <ExternalLink className="h-4 w-4" />}
          Deschide biletul precompletat ({ready.length}/{legs.length}) · cotă {fo(total)}
        </button>
        {!loading && ready.length < legs.length && (
          <p className="flex items-start gap-1.5 rounded-lg bg-warn px-2.5 py-1.5 text-[11px] text-warn"><AlertTriangle className="mt-px h-3.5 w-3.5 shrink-0" />Unele selecții nu au fost găsite în oferta Superbet; adaugă-le manual cu pașii de mai jos.</p>
        )}
        <p className="text-[11px] text-muted-foreground">Sau pas cu pas: atinge fiecare meci, adaugă selecția în aplicație, revino aici.</p>
        <ol className="divide-y rounded-2xl border">
          {legs.map((l, i) => (
            <li key={`${l.match_id}-${i}`}>
              <button className="flex w-full items-center gap-3 px-3 py-2.5 text-left hover:bg-accent/40 disabled:opacity-60" disabled={!l.sb_event_id} onClick={() => openLeg(i)}>
                {done.has(i) ? <CheckCircle2 className="h-5 w-5 shrink-0 text-win" /> : <Circle className="h-5 w-5 shrink-0 text-muted-foreground" />}
                <span className="min-w-0 flex-1">
                  <span className="block text-sm font-semibold">{i + 1}. {plainPick(l.market, l.line, l.selection, l.label)}</span>
                  <span className="block truncate text-xs text-muted-foreground">{l.home} – {l.away} · {roKickoff(l.kickoff_utc)}</span>
                </span>
                <span className="text-right">
                  <span className="num block text-sm font-extrabold">{fo(res[i]?.price ?? l.odds)}</span>
                  <span className={cn('block text-[10px]', res[i] ? 'text-[hsl(0_75%_55%)]' : 'text-muted-foreground')}>{!l.sb_event_id ? 'nu e în Superbet' : res[i] ? 'Superbet acum' : loading ? '…' : 'negăsit'}</span>
                </span>
              </button>
            </li>
          ))}
        </ol>
      </div>
    </Sheet>
  );
}
