import { useState } from 'react';
import { ExternalLink, Smartphone, Globe } from 'lucide-react';
import { Sheet } from './kit';
import { canOpenSuperbetApp, getSbMode, openInSuperbet, setSbMode, type SbMode } from '@/lib/native';

/** Buton „Superbet”: la prima atingere (pe Android) întreabă aplicație vs browser și ține minte alegerea pe dispozitiv. */
export function SuperbetLink({ url, className }: { url: string; className?: string }) {
  const [ask, setAsk] = useState(false);
  const go = (m?: SbMode) => { if (m) setSbMode(m); setAsk(false); openInSuperbet(url, m); };
  return (
    <>
      <a href={url} target="_blank" rel="noopener noreferrer" className={className}
        onClick={(e) => { e.preventDefault(); e.stopPropagation(); if (canOpenSuperbetApp() && !getSbMode()) setAsk(true); else go(); }}>
        Superbet <ExternalLink className="h-3 w-3" />
      </a>
      <Sheet open={ask} onClose={() => setAsk(false)} title="Unde deschid meciul?" subtitle="Alegerea se ține minte pe acest dispozitiv; o poți schimba din Setări.">
        <div className="grid gap-2">
          <button className="btn btn-primary justify-start" onClick={() => go('app')}><Smartphone className="h-4 w-4" />Deschide în aplicația Superbet</button>
          <p className="-mt-1 px-1 text-[11px] text-muted-foreground">Dacă aplicația nu e instalată, se deschide site-ul.</p>
          <button className="btn btn-outline justify-start" onClick={() => go('web')}><Globe className="h-4 w-4" />Deschide în browser</button>
        </div>
      </Sheet>
    </>
  );
}

export function SuperbetModeSetting() {
  const [m, setM] = useState<SbMode | null>(getSbMode());
  const pick = (v: SbMode) => { setSbMode(v); setM(v); };
  return (
    <div className="flex flex-wrap items-center gap-2">
      <span className="text-sm font-medium">Link Superbet:</span>
      {(['app', 'web'] as const).map((v) => (
        <button key={v} className={v === (m ?? 'app') ? 'btn btn-primary px-3 text-xs' : 'btn btn-outline px-3 text-xs'} onClick={() => pick(v)} aria-pressed={v === m}>
          {v === 'app' ? 'Aplicația Superbet' : 'Browser'}
        </button>
      ))}
      {!m && <span className="text-[11px] text-muted-foreground">(se întreabă la prima atingere)</span>}
    </div>
  );
}
