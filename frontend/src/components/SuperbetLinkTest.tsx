import { useEffect, useState } from 'react';
import { FlaskConical, Loader2 } from 'lucide-react';
import { Card } from './kit';
import { betslipAppLink, eventLinkVariants, openSuperbet } from '@/lib/superbet';

/** TEMPORAR: test linkuri Superbet pe un meci real din oferta de azi/mâine. De șters după confirmare. */
type Ev = { eventId: number; betradarId?: string; matchName: string; matchDate: string; odds?: Array<{ uuid: string; marketId: number; outcomeId: number; name: string; price: number; status?: string; specialBetValue?: string }> };
const day = (d: Date) => d.toISOString().slice(0, 10);

export function SuperbetLinkTest() {
  const [open, setOpen] = useState(false);
  const [ev, setEv] = useState<Ev | null | undefined>(undefined);
  useEffect(() => {
    if (!open || ev !== undefined) return;
    const now = new Date(); const end = new Date(now.getTime() + 2 * 86400e3);
    fetch(`https://production-superbet-offer-ro.freetls.fastly.net/v2/ro-RO/events/by-date?currentStatus=active&offerState=prematch&startDate=${day(now)}+00:00:00&endDate=${day(end)}+23:59:00&sportId=5`)
      .then((r) => r.json()).then((j) => {
        const list = ((j?.data ?? []) as Ev[]).filter((e) => new Date(e.matchDate.replace(' ', 'T') + 'Z').getTime() > Date.now() + 30 * 60e3);
        setEv(list.find((e) => e.betradarId) ?? list[0] ?? null);
      }).catch(() => setEv(null));
  }, [open, ev]);
  const web = ev ? `https://superbet.ro/cote/fotbal/meci-${ev.eventId}` : '';
  const home = ev?.odds?.find((o) => o.marketId === 547 && o.name === '1' && (o.status ?? 'active') === 'active');
  return (
    <Card className="space-y-3 p-4">
      <button className="flex w-full items-center gap-2 text-left font-semibold" onClick={() => setOpen((o) => !o)}>
        <FlaskConical className="h-4 w-4 text-primary" />Test linkuri Superbet (temporar) <span className="ml-auto text-xs text-muted-foreground">{open ? 'ascunde' : 'arată'}</span>
      </button>
      {open && (ev === undefined ? <Loader2 className="h-4 w-4 animate-spin" /> : !ev ? <p className="text-sm text-muted-foreground">Nu am găsit un meci în oferta Superbet.</p> : (
        <div className="space-y-2">
          <p className="text-sm">Meci: <b>{ev.matchName.replace('·', ' – ')}</b> <span className="text-xs text-muted-foreground">({ev.matchDate} UTC · id {ev.eventId}{ev.betradarId ? ` · BR ${ev.betradarId}` : ''})</span></p>
          <p className="text-[11px] text-muted-foreground">Atinge fiecare variantă și spune-mi litera care deschide direct acest meci în aplicație.</p>
          {eventLinkVariants(ev.eventId, ev.betradarId).map((v) => (
            <button key={v.key} className="btn btn-outline w-full justify-start text-left" onClick={() => openSuperbet(v.link, web, 'app')}>
              <b className="w-5">{v.key}</b><span className="min-w-0 flex-1"><span className="block text-xs font-semibold">{v.label}</span><span className="block truncate font-mono text-[10px] text-muted-foreground">{v.link}</span></span>
            </button>
          ))}
          {home && (() => { const link = betslipAppLink([{ eventId: ev.eventId, outcomeId: home.outcomeId, sbv: home.specialBetValue ?? '', uuid: home.uuid }]); return (
            <button className="btn btn-outline w-full justify-start text-left" onClick={() => openSuperbet(link, web, 'app')}>
              <b className="w-5">S</b><span className="min-w-0 flex-1"><span className="block text-xs font-semibold">Bilet precompletat: „1” @ {home.price}</span><span className="block truncate font-mono text-[10px] text-muted-foreground">{link}</span></span>
            </button>); })()}
        </div>
      ))}
    </Card>
  );
}
