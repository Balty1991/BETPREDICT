import { useState } from 'react';
import { ExternalLink } from 'lucide-react';
import { getSbMode, setSbMode, type SbMode } from '@/lib/native';
import { eventAppLink, openSuperbet } from '@/lib/superbet';

/** Buton „Superbet”: implicit deschide meciul în aplicația Superbet (dacă lipsește: superbet.ro); browserul se poate alege din Setări. */
export function SuperbetLink({ url, eventId, className }: { url: string; eventId?: string | null; className?: string }) {
  const eid = eventId ?? /-(\d+)(?:\?|$)/.exec(url)?.[1];
  return (
    <a href={url} target="_blank" rel="noopener noreferrer" className={className}
      onClick={(e) => { e.preventDefault(); e.stopPropagation(); openSuperbet(eid ? eventAppLink(eid) : url, url); }}>
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
