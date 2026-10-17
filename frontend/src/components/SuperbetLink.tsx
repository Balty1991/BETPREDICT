import { useState } from 'react';
import { ExternalLink } from 'lucide-react';
import { getSbMode, setSbMode, type SbMode } from '@/lib/native';
import { betslipAppLink, openSuperbet, type SbBetRef } from '@/lib/superbet';

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
