import { useEffect, useState, type MouseEvent } from 'react';
import { CheckCircle2, Circle, ExternalLink, Loader2, AlertTriangle } from 'lucide-react';
import { Sheet } from './kit';
import type { Ticket, TicketLeg } from '@/lib/types';
import { getJSON } from '@/lib/fetcher';
import { plainPick } from '@/lib/markets';
import { odds as fo, roKickoff } from '@/lib/format';
import { getSbMode, isNativeApp } from '@/lib/native';
import { betslipAppLink, openSuperbet, resolveOdd, type SbResolved, type SbBetRef } from '@/lib/superbet';
import { cn } from '@/lib/utils';

type R = SbResolved | null | undefined;
const slug = (x: string) => (x || '').normalize('NFKD').replace(/[\u0300-\u036f]/g, '').replace(/[^ -~]/g, '').toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '');
/** URL-ul real al meciului (slug + id, ca în publish/day.py). „meci-<id>” fără slug deschidea mereu același meci. */
export const legWebUrl = (l: { sb_event_id?: string | null; home: string; away: string; superbet_url?: string | null }) =>
  l.superbet_url || `https://superbet.ro/cote/fotbal/${slug(l.home)}-vs-${slug(l.away)}-${l.sb_event_id}`;

/**
 * „Joacă pe Superbet”: deschide biletul precompletat în aplicația Superbet (rosuperbetsport://betslip),
 * plus un ghid pas-cu-pas pe selecții. Nu plasează nimic: miza și confirmarea le faci tu în aplicație.
 */
type LegX = Pick<TicketLeg, 'sb_pick' | 'bb_picks' | 'bb_steps' | 'sb_event_id'>;
const lkey = (match: number, market: string, sel: string) => `${match}|${market}|${sel}`;
let fresh: Promise<Map<string, LegX>> | null = null;
/** Id-urile Superbet publicate acum de Robot (bilete active + selecțiile Stil din generator), pentru biletele salvate
 *  înainte să existe sau care nu se mai actualizează (copiile „Îl joc”). */
function freshPicks(): Promise<Map<string, LegX>> {
  if (!fresh) {
    type Gen = { rows: Array<{ m: number; k: string; pk?: LegX['sb_pick']; bp?: LegX['bb_picks']; bs?: string[] }> };
    fresh = Promise.all([
      getJSON<{ tickets: Ticket[] }>('api/tickets/upcoming.json').catch(() => null),
      getJSON<Gen>('api/supersocial/generator.json').catch(() => null),
    ]).then(([up, gen]) => {
      const m = new Map<string, LegX>();
      for (const r of gen?.rows ?? []) m.set(lkey(r.m, 'ss', r.k), { sb_pick: r.pk ?? null, bb_picks: r.bp ?? null, bb_steps: r.bs ?? null });
      for (const tk of up?.tickets ?? []) for (const l of tk.legs) {
        if (l.sb_pick || l.bb_picks?.length) m.set(lkey(l.match_id, l.market, l.selection), { sb_pick: l.sb_pick, bb_picks: l.bb_picks, bb_steps: l.bb_steps, sb_event_id: l.sb_event_id });
      }
      return m;
    });
    setTimeout(() => { fresh = null; }, 10 * 60 * 1000);
  }
  return fresh;
}

export function PlayOnSuperbet({ t, open, onClose }: { t: Ticket; open: boolean; onClose: () => void }) {
  const [extra, setExtra] = useState<Map<string, LegX> | null>(null);
  const legs = t.legs.filter((l) => !l.result).map((l) => {
    if (l.sb_pick || l.bb_picks?.length) return l;
    const x = extra?.get(lkey(l.match_id, l.market, l.selection));
    return x ? { ...l, ...x, sb_event_id: l.sb_event_id ?? x.sb_event_id } : l;
  });
  const needFresh = t.legs.some((l) => !l.result && !l.sb_pick && !l.bb_picks?.length);
  useEffect(() => {
    if (!open || !needFresh || extra) return;
    let alive = true;
    freshPicks().then((m) => { if (alive) setExtra(m); });
    return () => { alive = false; };
  }, [open, needFresh, extra]);
  const ready0 = !needFresh || !!extra;
  const [res, setRes] = useState<R[]>([]);
  // Bet Builder: picioarele lui ca selecții simple din același meci (încercare: aplicația Superbet le poate combina)
  const [bb, setBb] = useState<Array<SbResolved[] | null>>([]);
  const [done, setDone] = useState<Set<number>>(new Set());
  useEffect(() => {
    if (!open || !ready0) return;
    let alive = true;
    Promise.all(legs.map((l) => (l.sb_event_id ? resolveOdd({ eventId: l.sb_event_id, market: l.market, line: l.line, selection: l.selection, pick: l.sb_pick }) : Promise.resolve(null))))
      .then((r) => { if (alive) setRes(r); });
    Promise.all(legs.map((l) => (l.sb_event_id && l.bb_picks?.length
      ? Promise.all(l.bb_picks.map((p) => resolveOdd({ eventId: l.sb_event_id!, market: 'ss', selection: '', pick: p }))).then((xs) => (xs.every(Boolean) ? (xs as SbResolved[]) : null))
      : Promise.resolve(null))))
      .then((r) => { if (alive) setBb(r); });
    return () => { alive = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, t.id, ready0]);
  const now = Date.now();
  const started = (i: number) => { const k = legs[i].kickoff_utc; return !!k && Date.parse(k) <= now; };
  const legBets = legs.map((l, i): Array<SbBetRef & { eventId: string }> => {
    if (!l.sb_event_id || started(i)) return [];
    const rs = res[i] ? [res[i]!] : bb[i] ?? [];
    return rs.map((r) => ({ eventId: l.sb_event_id!, outcomeId: r.outcomeId, sbv: r.sbv, uuid: r.uuid }));
  });
  const ready = legBets.flat();
  const nReady = legBets.filter((b) => b.length).length;
  const loading = open && (res.length !== legs.length || bb.length !== legs.length);
  const total = legs.reduce((a, l, i) => (started(i) ? a : a * (res[i]?.price || l.odds || 1)), 1);
  const begun = legs.filter((_, i) => started(i));
  const totalTxt = total >= 100 ? String(Math.round(total)) : total.toFixed(2);
  const openLeg = (e: MouseEvent, i: number) => {
    const eid = legs[i].sb_event_id;
    if (!eid || started(i)) { e.preventDefault(); return; }
    setDone((d) => new Set(d).add(i));
    // aplicația Superbet nu deschide meciul din link (doar Acasă), dar primește biletul: selecția se pune direct pe bilet;
    // fără id-uri, meciul se deschide pe superbet.ro (linkul nativ <a target=unic>, fiecare meci în tabul lui)
    if (legBets[i].length && (isNativeApp() || getSbMode() === 'app')) { e.preventDefault(); openSuperbet(betslipAppLink(legBets[i]), legWebUrl(legs[i]), 'app'); }
  };
  return (
    <Sheet open={open} onClose={onClose} title="Joacă pe Superbet" subtitle="Tu alegi miza și confirmi în aplicație. BetPredict nu plasează pariuri.">
      <div className="space-y-3">
        <button className="btn btn-primary w-full" disabled={loading || !ready.length}
          onClick={() => openSuperbet(betslipAppLink(ready), ready.length ? legWebUrl(legs.find((l) => l.sb_event_id === ready[0].eventId)!) : 'https://superbet.ro/pariuri-sportive/fotbal', 'app')}>
          {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <ExternalLink className="h-4 w-4" />}
          Deschide biletul precompletat ({nReady}/{legs.length - begun.length}) · cotă {totalTxt}
        </button>
        {begun.length > 0 && (
          <div className="rounded-lg bg-warn px-2.5 py-1.5 text-[11px] text-warn">
            <p className="font-semibold">{begun.length === 1 ? 'Un meci a început' : `${begun.length} meciuri au început`} și nu mai intră pe bilet (Superbet nu le mai primește înainte de start). Biletul se deschide cu celelalte {legs.length - begun.length}, la cota de mai sus:</p>
            <ul className="mt-0.5 list-disc pl-4">{begun.map((l) => <li key={`${l.match_id}-${l.selection}`}>{l.home} – {l.away} · {roKickoff(l.kickoff_utc)}: {plainPick(l.market, l.line, l.selection, l.label)}</li>)}</ul>
          </div>
        )}
        {legs.some((l) => l.bb_steps?.length) && (
          <p className="rounded-lg bg-info px-2.5 py-1.5 text-[11px] text-info">Bet Builder-ele le trimitem pe bilet ca selecții din același meci; dacă aplicația Superbet nu le combină singură, atinge meciul, deschide <b>Bet Builder</b> și bifează ce scrie sub selecție.</p>
        )}
        {legs.some((l) => l.market === 'boost') && (
          <p className="rounded-lg bg-info px-2.5 py-1.5 text-[11px] text-info">Cotele mărite (Super Cota, Cote mărite) le trimitem și ele pe bilet; dacă lipsesc (Superbet le retrage repede), deschide meciul și caută secțiunea <b>Cote mărite</b> sau <b>Super Cota</b>. „Super Cota 1” = câștigă gazdele, „2” = câștigă oaspeții, la cota mărită.</p>
        )}
        {!loading && nReady < legs.filter((l, i) => l.market !== 'boost' && !started(i)).length && (
          <p className="flex items-start gap-1.5 rounded-lg bg-warn px-2.5 py-1.5 text-[11px] text-warn"><AlertTriangle className="mt-px h-3.5 w-3.5 shrink-0" />Unele selecții nu au fost găsite în oferta Superbet (s-au închis sau s-au schimbat); verifică-le cu pașii de mai jos.</p>
        )}
        <p className="text-[11px] text-muted-foreground">Biletul precompletat se deschide doar în <b>aplicația Superbet</b> (instalată, cu contul logat); site-ul superbet.ro nu primește bilete prin link. Dacă se deschide doar un meci pe site, nu ai aplicația sau telefonul a ales browserul pentru ea.</p>
        <p className="text-[11px] text-muted-foreground">Sau pas cu pas: atinge o selecție și intră pe biletul din aplicația Superbet; cele fără id (cote mărite retrase, Bet Builder manual) deschid meciul pe superbet.ro.</p>
        <ol className="divide-y rounded-2xl border">
          {legs.map((l, i) => (
            <li key={`${l.match_id}-${i}`}>
              <a href={l.sb_event_id && !started(i) ? legWebUrl(l) : undefined} target={l.sb_event_id ? `sb_${l.sb_event_id}` : undefined} rel="noopener noreferrer"
                aria-disabled={!l.sb_event_id || started(i)}
                className={cn('flex w-full items-center gap-3 px-3 py-2.5 text-left hover:bg-accent/40', (!l.sb_event_id || started(i)) && 'pointer-events-none opacity-50')} onClick={(e) => openLeg(e, i)}>
                {done.has(i) ? <CheckCircle2 className="h-5 w-5 shrink-0 text-win" /> : <Circle className="h-5 w-5 shrink-0 text-muted-foreground" />}
                <span className="min-w-0 flex-1">
                  <span className="block text-sm font-semibold">{i + 1}. {plainPick(l.market, l.line, l.selection, l.label)}</span>
                  <span className="block break-words text-xs text-muted-foreground">{l.home} – {l.away} · {roKickoff(l.kickoff_utc)}</span>
                  {l.bb_steps?.length ? <span className="block text-[11px] font-semibold text-info">În meci › Bet Builder: {l.bb_steps.join(' + ')}</span> : null}
                  {l.market === 'boost' && <span className="block text-[11px] font-semibold text-info">În meci: {/super cota/i.test(l.selection) ? `Super Cota › ${/\b2\b/.test(l.selection) ? '2 (oaspeții câștigă)' : /\bX\b/.test(l.selection) ? 'X (egal)' : '1 (gazdele câștigă)'}` : `Cote mărite › ${l.selection}`}</span>}
                </span>
                <span className="text-right">
                  <span className="num block text-sm font-extrabold">{fo(res[i]?.price || l.odds)}</span>
                  <span className={cn('block text-[10px]', res[i] ? 'text-[hsl(0_75%_55%)]' : 'text-muted-foreground')}>{started(i) ? 'început' : !l.sb_event_id ? 'nu e în Superbet' : res[i] ? (res[i]!.fromRef ? 'pe bilet' : 'Superbet acum') : l.market === 'boost' ? 'cotă mărită' : bb[i] ? 'Bet Builder' : l.bb_steps?.length ? 'Bet Builder manual' : loading ? '…' : 'negăsit'}</span>
                </span>
              </a>
            </li>
          ))}
        </ol>
      </div>
    </Sheet>
  );
}
