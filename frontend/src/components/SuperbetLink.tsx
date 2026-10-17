import { useState } from 'react';
import { ExternalLink } from 'lucide-react';
import { getSbMode, setSbMode, type SbMode } from '@/lib/native';
import { betslipAppLink, openSuperbet, resolveOdd, type SbBetRef } from '@/lib/superbet';
import { toast } from 'sonner';

/** Buton „Superbet”: cu id-urile selecției o pune pe biletul din aplicația Superbet; fără ele, meciul pe superbet.ro. */
export function SuperbetLink({ url, eventId, className, bets }: { url: string; eventId?: string | null; className?: string; bets?: SbBetRef[] }) {
  const eid = eventId ?? /-(\d+)(?:\?|$)/.exec(url)?.[1];
  // cu id-urile selecției: direct pe biletul din aplicație (linkul spre meci deschide aplicația doar pe Acasă); altfel site-ul
  const app = bets?.length && eid ? betslipAppLink(bets) : null;
  return (
    <a href={url} target="_blank" rel="noopener noreferrer" className={className}
      onClick={(e) => { e.preventDefault(); e.stopPropagation(); openSuperbet(app ?? url, url, app ? undefined : 'web'); }}>
      Superbet <ExternalLink className="h-3 w-3" />
    </a>
  );
}

export function SuperbetModeSetting() {
  const [m, setM] = useState<SbMode>(getSbMode());
  const pick = (v: SbMode) => { setSbMode(v); setM(v); };
  return (
    <div className="flex flex-wrap items-center gap-2">
      <span className="text-sm font-medium">Link Superbet:</span>
      {(['web', 'app'] as const).map((v) => (
        <button key={v} className={v === m ? 'btn btn-primary px-3 text-xs' : 'btn btn-outline px-3 text-xs'} onClick={() => pick(v)} aria-pressed={v === m}>
          {v === 'web' ? 'Browser' : 'Aplicația Superbet (recomandat)'}
        </button>
      ))}
      {m === 'app' && <span className="text-[11px] text-muted-foreground">Dacă aplicația se deschide pe Acasă în loc de meci, alege Browser.</span>}
    </div>
  );
}

type Pick = { market: string; outcome: string; ref?: string };
const fromRef = (eventId: string, p: Pick): SbBetRef | null => {
  const r = p.ref?.split(',');
  return r && r.length >= 3 && /^\d+$/.test(r[0]) ? { eventId, outcomeId: Number(r[0]), sbv: r.slice(1, -1).join(','), uuid: r[r.length - 1] } : null;
};

/** „Pe Superbet” pe o predicție: o pune direct pe biletul din aplicația Superbet (Bet Builder: picioarele lui).
 *  Cu id-urile publicate de Robot merge fără să citim oferta; altfel le căutăm în oferta meciului. */
export function SbPickButton({ eventId, picks, webUrl, className }: { eventId?: string | null; picks?: Pick[] | null; webUrl?: string | null; className?: string }) {
  const [busy, setBusy] = useState(false);
  if (!eventId || !picks?.length) return null;
  const go = async () => {
    setBusy(true);
    let bets = picks.map((p) => fromRef(eventId, p));
    if (bets.some((b) => !b)) {
      const rs = await Promise.all(picks.map((p) => resolveOdd({ eventId, market: 'ss', selection: '', pick: p })));
      bets = rs.map((r) => (r ? { eventId, outcomeId: r.outcomeId, sbv: r.sbv, uuid: r.uuid } : null));
    }
    setBusy(false);
    if (bets.some((b) => !b)) {
      toast.error('Selecția nu mai e în oferta Superbet');
      if (webUrl) openSuperbet(webUrl, webUrl, 'web');
      return;
    }
    openSuperbet(betslipAppLink(bets as SbBetRef[]), webUrl ?? 'https://superbet.ro/pariuri-sportive/fotbal', 'app');
  };
  return (
    <button type="button" disabled={busy} onClick={(e) => { e.preventDefault(); e.stopPropagation(); void go(); }}
      className={className ?? 'inline-flex min-h-8 items-center gap-1 text-[11px] font-semibold text-[hsl(0_75%_55%)]'}>
      {busy ? 'Se deschide…' : picks.length > 1 ? 'Bet Builder pe Superbet' : 'Pe Superbet'} <ExternalLink className="h-3 w-3" />
    </button>
  );
}
