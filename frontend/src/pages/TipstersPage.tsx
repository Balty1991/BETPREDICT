import { useMemo, useState } from 'react';
import { CheckCircle2, ChevronRight, Clock, MinusCircle, Users, XCircle } from 'lucide-react';
import { useAsync } from '@/lib/fetcher';
import { loadTipsters, oneIn, type TipLeg, type TipTicket } from '@/lib/tipsters';
import { odds as fo } from '@/lib/format';
import { Panel } from '@/components/dash';
import { Empty, Segmented, Skeleton } from '@/components/kit';
import { cn } from '@/lib/utils';

type Status = 'toate' | 'won' | 'lost';
const MARGIN = 1.05;
const pct0 = (v: number | null) => (v == null ? '—' : `${Math.round(v * 100)}%`);
const longDate = new Intl.DateTimeFormat('ro-RO', { timeZone: 'UTC', weekday: 'short', day: 'numeric', month: 'short' });

function Icon({ r }: { r: string }) {
  if (r === 'won') return <CheckCircle2 className="h-4 w-4 shrink-0 text-win" aria-label="câștigat" />;
  if (r === 'lost') return <XCircle className="h-4 w-4 shrink-0 text-loss" aria-label="pierdut" />;
  if (r === 'void') return <MinusCircle className="h-4 w-4 shrink-0 text-warn" aria-label="anulat" />;
  return <Clock className="h-4 w-4 shrink-0 text-muted-foreground" aria-label="în așteptare" />;
}

/** Pe piețe, din biletele alese: câte au intrat, cât promitea cota (fără marja casei), ce dădea robotul. */
function byMarket(tickets: TipTicket[]) {
  const m = new Map<string, { key: string; label: string; n: number; won: number; imp: number; rp: number[] }>();
  for (const t of tickets) for (const l of t.legs) {
    if (l.result !== 'won' && l.result !== 'lost') continue;
    const x = m.get(l.key) ?? { key: l.key, label: l.label, n: 0, won: 0, imp: 0, rp: [] };
    x.n += 1; x.won += l.result === 'won' ? 1 : 0; x.imp += 1 / l.odds / MARGIN;
    if (l.robot_p != null) x.rp.push(l.robot_p);
    m.set(l.key, x);
  }
  return [...m.values()].sort((a, b) => b.n - a.n);
}

function Leg({ l }: { l: TipLeg }) {
  return (
    <li className="flex items-center gap-2 py-1.5">
      <Icon r={l.result} />
      <span className="min-w-0 flex-1">
        <span className="block break-words text-[13px] font-semibold leading-snug">{l.home} – {l.away}</span>
        <span className="block text-[11px] text-muted-foreground">
          <b className="text-primary">{l.label}</b>
          {l.corners != null ? ` · ${l.corners} ${l.stat ?? 'cornere'}` : ''}
          {l.corners_ours != null && l.corners_ours !== l.corners ? ` (la noi ${l.corners_ours})` : ''}
        </span>
      </span>
      <span className="flex shrink-0 flex-col items-end">
        <span className="num text-sm font-extrabold">{fo(l.odds)}</span>
        <span className="num text-[11px] text-muted-foreground">{l.robot_p != null ? `robot ${Math.round(l.robot_p * 100)}%` : 'robot —'}</span>
      </span>
    </li>
  );
}

function TicketRow({ t }: { t: TipTicket }) {
  const lost = t.legs.filter((l) => l.result === 'lost').length;
  return (
    <details className="card group">
      <summary className="flex cursor-pointer list-none items-center gap-3 px-4 py-3">
        <Icon r={t.status} />
        <span className="min-w-0 flex-1">
          <span className="block text-sm font-bold">{t.tipster}</span>
          <span className="block text-[11px] text-muted-foreground">
            {longDate.format(new Date(`${t.date}T12:00:00Z`))} · {t.n} selecții{lost ? ` · ${lost} ${lost === 1 ? 'pierdută' : 'pierdute'}` : ''} · după cote, o dată la ~{oneIn(t.p_market)}
          </span>
        </span>
        <span className={cn('num shrink-0 text-base font-extrabold', t.status === 'won' ? 'text-win' : t.status === 'lost' ? 'text-loss' : '')}>{fo(t.odds)}</span>
        <ChevronRight className="h-4 w-4 shrink-0 text-muted-foreground transition-transform group-open:rotate-90" />
      </summary>
      <ul className="divide-y px-4 pb-3">{t.legs.map((l, i) => <Leg key={i} l={l} />)}</ul>
    </details>
  );
}

/** Toate biletele transcrise din Supersocial (și cele jucate de mine), pe tipster, cu piețele și verificarea datelor. */
export default function TipstersPage() {
  const doc = useAsync(loadTipsters, []);
  const [who, setWho] = useState('toti');
  const [status, setStatus] = useState<Status>('toate');
  const all = useMemo(() => doc.data?.tickets ?? [], [doc.data]);
  const names = useMemo(() => [...new Set(all.map((t) => t.tipster))].sort((a, b) => all.filter((t) => t.tipster === b).length - all.filter((t) => t.tipster === a).length), [all]);
  const mine = all.filter((t) => who === 'toti' || t.tipster === who);
  const shown = mine.filter((t) => status === 'toate' || t.status === status);
  const markets = byMarket(mine);
  const won = mine.filter((t) => t.status === 'won').length;
  const lost = mine.filter((t) => t.status === 'lost').length;
  const legsLost = mine.flatMap((t) => (t.status === 'lost' ? t.legs.filter((l) => l.result === 'lost') : [])).length;
  const check = doc.data?.data_check;
  return (
    <div className="space-y-5">
      <header>
        <h1 className="flex items-center gap-2"><Users className="h-6 w-6 text-primary" />Tipsteri</h1>
        <p className="text-sm text-muted-foreground">Biletele trimise de tine, transcrise din Supersocial, puse lângă robot pe aceleași meciuri.</p>
      </header>
      {doc.loading ? <Skeleton className="h-40 w-full rounded-2xl" /> : !all.length ? (
        <Empty title="Niciun bilet încă" icon={<Users className="h-8 w-8" />}>Apar după următoarea rulare a robotului.</Empty>
      ) : (
        <>
          <Panel glow="c" className="!p-4">
            <div className="grid grid-cols-3 gap-2 text-center">
              <div><div className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground">Bilete</div><div className="num text-2xl font-extrabold">{mine.length}</div></div>
              <div><div className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground">Câștigate</div><div className="num text-2xl font-extrabold text-win">{won}</div></div>
              <div><div className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground">Pierdute</div><div className="num text-2xl font-extrabold text-loss">{lost}</div></div>
            </div>
            <p className="mt-3 text-[11px] text-muted-foreground">
              {lost > 0 && `Biletele pierdute au căzut la ${legsLost} ${legsLost === 1 ? 'selecție' : 'selecții'} în total, în medie ${(legsLost / lost).toFixed(1).replace('.', ',')} pe bilet. `}
              Câștigurile sunt mai multe decât în realitate: tipsterii păstrează pe profil biletele câștigate și le șterg des pe cele pierdute.
              {check && check.compared > 0 && ` Cornerele de pe bilete se potrivesc cu ale noastre la ${check.compared - check.mismatches.length} din ${check.compared} meciuri.`}
            </p>
          </Panel>

          <div className="flex gap-2 overflow-x-auto pb-1 scrollbar-none">
            {['toti', ...names].map((n) => (
              <button key={n} type="button" onClick={() => setWho(n)}
                className={cn('press shrink-0 rounded-full border px-3 py-1.5 text-xs font-bold', who === n ? 'border-primary bg-primary text-primary-foreground' : 'text-muted-foreground')}>
                {n === 'toti' ? 'Toți' : n} <span className="num opacity-70">{n === 'toti' ? all.length : all.filter((t) => t.tipster === n).length}</span>
              </button>
            ))}
          </div>

          <Panel title="Pe piețe" right={<span className="text-xs text-muted-foreground">selecții decontate</span>}>
            <div className="overflow-x-auto">
              <table className="w-full text-xs">
                <thead className="text-muted-foreground"><tr><th className="py-1 text-left">Piață</th><th className="text-right">✓/✗</th><th className="text-right">Intră</th><th className="text-right">Cota</th><th className="text-right">Robot</th></tr></thead>
                <tbody>{markets.map((m) => {
                  const hit = m.n ? m.won / m.n : null;
                  const imp = m.n ? m.imp / m.n : null;
                  return (
                    <tr key={m.key} className="border-t">
                      <td className="py-1.5 pr-2">{m.label}</td>
                      <td className="num text-right"><span className="text-win">{m.won}</span>/<span className="text-loss">{m.n - m.won}</span></td>
                      <td className={cn('num text-right font-bold', hit != null && imp != null && hit >= imp ? 'text-win' : 'text-loss')}>{pct0(hit)}</td>
                      <td className="num text-right text-muted-foreground">{pct0(imp)}</td>
                      <td className="num text-right text-muted-foreground">{m.rp.length ? pct0(m.rp.reduce((a, b) => a + b, 0) / m.rp.length) : '—'}</td>
                    </tr>
                  );
                })}</tbody>
              </table>
            </div>
            <p className="mt-2 text-[11px] text-muted-foreground">„Cota” = cât de des ar trebui să intre după prețul Superbet, fără marja casei. „Robot” = șansa robotului pe aceleași meciuri, unde le-a urmărit (de la 13 oct.).</p>
          </Panel>

          <section aria-label="Bilete" className="space-y-3">
            <div className="flex items-center justify-between gap-2">
              <h2 className="text-base">Bilete</h2>
              <Segmented<Status> size="sm" value={status} onChange={setStatus} options={[{ value: 'toate', label: 'Toate' }, { value: 'won', label: 'Câștigate' }, { value: 'lost', label: 'Pierdute' }]} />
            </div>
            {shown.length ? <div className="space-y-2">{shown.map((t) => <TicketRow key={t.id} t={t} />)}</div>
              : <p className="text-sm text-muted-foreground">Niciun bilet aici.</p>}
          </section>
        </>
      )}
    </div>
  );
}
