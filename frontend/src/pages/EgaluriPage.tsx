import { useMemo } from 'react';
import { Link } from 'react-router';
import { Equal, FlaskConical, ListChecks, Trophy } from 'lucide-react';
import { useAsync } from '@/lib/fetcher';
import { loadSoftDraw, loadTicketsHistory, loadUpcomingTickets } from '@/lib/data';
import { dayLabel, odds as fo, roTime } from '@/lib/format';
import { Badge, Card, Empty, Skeleton } from '@/components/kit';
import { TicketCard } from '@/components/TicketCard';
import { SuperbetLink } from '@/components/SuperbetLink';
import type { SoftDrawEvent, SoftDrawLive, SoftDrawStat, Ticket } from '@/lib/types';
import { cn } from '@/lib/utils';

const pc = (x: number | null | undefined, sign = false) => (x == null ? '–' : `${sign && x > 0 ? '+' : ''}${(x * 100).toFixed(1)}%`);
const tone = (x: number | null | undefined) => (x == null ? '' : x > 0 ? 'text-win' : x < 0 ? 'text-loss' : '');

/** Proiectul Egaluri: regula, proba pe istoric, rezultatele reale și egalurile de azi. */
export default function EgaluriPage() {
  const scan = useAsync(loadSoftDraw, []);
  const up = useAsync(loadUpcomingTickets, []);
  const hist = useAsync(loadTicketsHistory, []);
  const d = scan.data;
  const open = (up.data?.tickets ?? []).filter((t) => t.kind === 'acca_soft' && (t.status === 'pending' || !t.status)) as Ticket[];
  const done = (hist.data ?? []).filter((t) => t.kind === 'acca_soft' && (t.status === 'won' || t.status === 'lost')).slice(0, 10) as Ticket[];
  const byDay = useMemo(() => {
    const m = new Map<string, SoftDrawEvent[]>();
    for (const e of d?.events ?? []) { const k = e.day ?? ''; m.set(k, [...(m.get(k) ?? []), e]); }
    return [...m.entries()].sort(([a], [b]) => a.localeCompare(b));
  }, [d]);
  const bt = d?.backtest;
  return (
    <div className="space-y-4">
      <header className="space-y-1">
        <p className="text-[11px] font-bold uppercase tracking-widest text-muted-foreground">Proiect</p>
        <h1 className="flex items-center gap-2"><Equal className="h-6 w-6 text-primary" />Proiectul Egaluri</h1>
        <p className="text-sm text-muted-foreground">Egaluri la care Superbet plătește peste piață, în meciuri strânse și cu puține goluri așteptate.</p>
      </header>

      <Card className="space-y-2 p-4">
        <h2 className="flex items-center gap-2 text-base font-bold"><ListChecks className="h-4 w-4 text-primary" />Regula</h2>
        <ul className="space-y-1.5 text-sm">
          <li><Badge tone="win">A</Badge> <span className="text-muted-foreground">{d?.rule_a ?? 'Superbet peste mediană, meci strâns, puține goluri așteptate.'}</span></li>
          <li><Badge>B</Badge> <span className="text-muted-foreground">Doar regula de bază: egal 2,80–3,60, Superbet cu cel puțin 2% peste mediana pieței. De urmărit, nu intră pe bilete.</span></li>
        </ul>
        <p className="text-xs text-muted-foreground">Biletele au câte două egaluri A din aceeași zi. Un bilet în joc nu se mai schimbă.</p>
      </Card>

      <Card className="space-y-3 p-4">
        <h2 className="flex items-center gap-2 text-base font-bold"><Trophy className="h-4 w-4 text-warn" />Rezultate reale (cote Superbet)</h2>
        {!d ? <Skeleton className="h-16 w-full" /> : (
          <div className="grid grid-cols-3 gap-2 text-center">
            <LiveCell label="Egaluri A" s={d.live?.singles.A} />
            <LiveCell label="Egaluri B" s={d.live?.singles.B} />
            <div className="rounded-xl bg-muted/50 p-2">
              <div className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground">Bilete</div>
              <div className="num text-lg font-extrabold">{d.live?.tickets.won ?? 0}/{d.live?.tickets.n ?? 0}</div>
              <div className={cn('num text-xs font-bold', tone(d.live?.tickets.roi))}>ROI {pc(d.live?.tickets.roi, true)}</div>
            </div>
          </div>
        )}
        <p className="text-xs text-muted-foreground">Fiecare egal A/B e urmărit de la prima cotă văzută până la final (miză 1 pe egal). Abia după câteva sute de meciuri se poate spune dacă regula ține și la Superbet.</p>
      </Card>

      {bt && (
        <Card className="space-y-3 p-4">
          <h2 className="flex items-center gap-2 text-base font-bold"><FlaskConical className="h-4 w-4 text-primary" />Proba pe istoric</h2>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead><tr className="text-left text-[11px] uppercase tracking-wider text-muted-foreground"><th className="py-1 font-bold"> </th><th className="font-bold">Până în {bt.split.slice(0, 7)}</th><th className="font-bold">După</th></tr></thead>
              <tbody>
                <BtRow label="Egal în bandă (bază)" a={bt.base.train} b={bt.base.test} />
                <BtRow label="Egal A" a={bt.a.train} b={bt.a.test} strong />
              </tbody>
            </table>
          </div>
          {bt.good_test && bt.rest_test && (
            <p className="text-sm">Ligile alese pe prima perioadă au dat după: <b className={tone(bt.good_test.roi)}>{pc(bt.good_test.roi, true)}</b> ({bt.good_test.n} meciuri), restul <b className={tone(bt.rest_test.roi)}>{pc(bt.rest_test.roi, true)}</b> ({bt.rest_test.n}).</p>
          )}
          {bt.ht_draw && <p className="text-xs text-muted-foreground">Testat și: {bt.ht_draw}</p>}
          {bt.leagues.length > 0 && (
            <details className="group">
              <summary className="cursor-pointer text-sm font-semibold text-primary">Pe ligi (egal A, tot istoricul)</summary>
              <ul className="mt-2 divide-y text-sm">
                {bt.leagues.map((l) => (
                  <li key={l.div} className="flex items-center justify-between gap-2 py-1.5">
                    <span className="min-w-0 truncate">{l.league}{l.tag && <Badge tone={l.tag === 'bună' ? 'win' : 'loss'} className="ml-1.5">{l.tag}</Badge>}</span>
                    <span className="num shrink-0 text-xs text-muted-foreground">{l.n} · {pc(l.hit)} egal · <b className={tone(l.roi)}>{pc(l.roi, true)}</b></span>
                  </li>
                ))}
              </ul>
            </details>
          )}
          <p className="text-xs text-muted-foreground">{bt.source}. Cota cea mai bună din piață e mai mare decât cea Superbet, deci la Superbet rezultatul va fi mai mic: tocmai de aceea contează rezultatele reale de mai sus.</p>
        </Card>
      )}

      <section className="space-y-3">
        <h2 className="text-base font-bold">Biletele în joc</h2>
        {up.loading && !up.data ? <Skeleton className="h-32 w-full rounded-2xl" />
          : open.length ? open.map((t) => <TicketCard key={t.id} t={t} compact />)
          : <Empty title="Niciun bilet acum" icon={<Equal className="h-8 w-8" />}>Un bilet se face când în aceeași zi sunt cel puțin două egaluri A.</Empty>}
      </section>

      <section className="space-y-3">
        <h2 className="text-base font-bold">Egalurile din următoarele zile</h2>
        {scan.loading && !d ? <Skeleton className="h-32 w-full rounded-2xl" />
          : byDay.length === 0 ? <Empty title="Niciun egal în regulă acum" icon={<Equal className="h-8 w-8" />} />
          : byDay.map(([day, evs]) => (
            <Card key={day} className="p-3">
              <div className="mb-1 text-xs font-bold uppercase tracking-wider text-muted-foreground">{day ? dayLabel(day) : '—'}</div>
              <ul className="divide-y">
                {evs.map((e) => (
                  <li key={e.match_id} className="flex items-center gap-3 py-2.5">
                    <Badge tone={e.tier === 'A' ? 'win' : 'muted'}>{e.tier ?? 'B'}</Badge>
                    <div className="min-w-0 flex-1">
                      <Link to={`/meci/${e.match_id}`} className="block break-words font-semibold">{e.home} – {e.away}</Link>
                      <div className="text-xs text-muted-foreground">{e.league_tag && <Badge tone={e.league_tag === 'bună' ? 'win' : 'loss'} className="mr-1">ligă {e.league_tag}</Badge>}{roTime(e.kickoff_utc)}{e.league ? ` · ${e.league}` : ''} · mediana {fo(e.median)}{e.o25 ? ` · Peste 2,5 la ${fo(e.o25)}` : ''}</div>
                    </div>
                    <div className="text-right">
                      <div className="num font-bold text-primary">{fo(e.odds)}</div>
                      <div className="text-[11px] text-win">+{(e.gap * 100).toFixed(1)}%</div>
                      {e.superbet_url && <SuperbetLink url={e.superbet_url} className="mt-1 inline-flex items-center gap-1 text-[11px] font-semibold text-[hsl(0_75%_62%)]" />}
                    </div>
                  </li>
                ))}
              </ul>
            </Card>
          ))}
      </section>

      {done.length > 0 && (
        <section className="space-y-3">
          <h2 className="text-base font-bold">Ultimele bilete terminate</h2>
          {done.map((t) => <TicketCard key={t.id} t={t} compact />)}
        </section>
      )}
    </div>
  );
}

function LiveCell({ label, s }: { label: string; s?: SoftDrawLive }) {
  return (
    <div className="rounded-xl bg-muted/50 p-2">
      <div className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground">{label}</div>
      <div className="num text-lg font-extrabold">{s?.won ?? 0}/{s?.n ?? 0}</div>
      <div className={cn('num text-xs font-bold', tone(s?.roi))}>ROI {pc(s?.roi, true)}</div>
    </div>
  );
}

function BtRow({ label, a, b, strong }: { label: string; a: SoftDrawStat | null; b: SoftDrawStat | null; strong?: boolean }) {
  const cell = (s: SoftDrawStat | null) => s ? <><span className={cn('num font-bold', tone(s.roi))}>{pc(s.roi, true)}</span><span className="block text-[11px] text-muted-foreground">{s.n} meciuri · {pc(s.hit)} egal</span></> : '–';
  return (
    <tr className={cn('border-t', strong && 'font-semibold')}>
      <td className="py-2 pr-2">{label}</td><td className="py-2">{cell(a)}</td><td className="py-2">{cell(b)}</td>
    </tr>
  );
}
