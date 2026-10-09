import { CalendarCheck, TrendingUp } from 'lucide-react';
import { useAsync } from '@/lib/fetcher';
import { loadWeekly } from '@/lib/data';
import { Badge, Card, Empty, InfoTip, Loading, Stat } from '@/components/kit';
import { marketTitle } from '@/lib/markets';
import { pct, signed } from '@/lib/format';
import type { ClvDoc, ClvStat, StatBlock } from '@/lib/types';

const clvTxt = (v?: number | null) => (v == null ? '—' : `${v > 0 ? '+' : ''}${(v * 100).toFixed(1)}%`);
const tone = (v?: number | null): 'win' | 'loss' | undefined => (v == null ? undefined : v >= 0 ? 'win' : 'loss');
const KIND: Record<string, string> = { acca_safe: 'Bilet sigur', acca_50: 'Bilet ~50', acca_100: 'Bilet ~100', acca_500: 'Bilet ~500', pyramid: 'Piramidă' };
const CHANGE: Record<string, string> = {
  segment: 'Segment ligă × piață', threshold: 'Prag EV', calibration: 'Calibrare', champion_cycle: 'Campion vs. challenger',
  ticket_strategy: 'Strategie bilete', leg_bias: 'Bilete: corecție selecții', ticket_shrink: 'Bilete: model vs piață',
  leg_block: 'Bilete: tip exclus', variant_weights: 'Bilete: ponderi variante', tier_min_p: 'Bilete: prag pe nivel',
  league_penalty: 'Penalizare ligă', exclude_market: 'Piață exclusă', include_market: 'Piață reactivată', bsd_weight: 'Pondere BSD',
};

/** CLV (closing line value): indicatorul timpuriu al valorii reale. */
export function ClvCard({ clv }: { clv?: ClvDoc | null }) {
  if (!clv) return null;
  const rows: Array<[string, ClvStat]> = [['Toate', clv.all], ['Pick-uri', clv.picks], ['Recomandate', clv.recommended], ['Valoare (EV>0)', clv.value]];
  return (
    <Card className="p-4">
      <h2 className="mb-2 flex items-center gap-2 text-sm font-semibold"><TrendingUp className="h-4 w-4 text-primary" />CLV — am bătut cota de închidere?{clv.help && <InfoTip text={clv.help} label="Ce e CLV?" />}</h2>
      {!clv.all?.n ? <p className="text-sm text-muted-foreground">Se adună: CLV-ul apare după startul meciurilor publicate (cota de închidere e capturată orar și la :50).</p> : (
        <>
          <div className="grid grid-cols-2 gap-2 md:grid-cols-4">
            {rows.map(([k, s]) => (
              <div key={k} className="rounded-xl bg-muted/40 p-3">
                <div className="text-xs text-muted-foreground">{k}</div>
                <div className={`num text-xl font-extrabold ${tone(s?.avg) === 'win' ? 'text-win' : tone(s?.avg) === 'loss' ? 'text-loss' : ''}`}>{clvTxt(s?.avg)}</div>
                <div className="text-[11px] text-muted-foreground">{s?.n ?? 0} selecții · bat închiderea {pct(s?.beat_rate ?? null)}</div>
              </div>
            ))}
          </div>
          {clv.by_market?.length ? (
            <div className="mt-3 overflow-x-auto"><table className="w-full text-sm">
              <thead className="text-xs text-muted-foreground"><tr><th className="py-1 text-left">Piață</th><th className="text-right">n</th><th className="text-right">CLV</th><th className="text-right">bat închiderea</th></tr></thead>
              <tbody>{clv.by_market.slice(0, 10).map((m) => <tr key={m.key} className="border-t"><td className="py-1.5">{marketTitle(m.key ?? '')}</td><td className="text-right">{m.n}</td><td className={`text-right font-semibold ${tone(m.avg) === 'win' ? 'text-win' : 'text-loss'}`}>{clvTxt(m.avg)}</td><td className="text-right">{pct(m.beat_rate)}</td></tr>)}</tbody>
            </table></div>
          ) : null}
          {clv.by_source?.length ? <p className="mt-2 text-xs text-muted-foreground">Pe sursă: {clv.by_source.map((s) => `${s.key === 'superbet' ? 'Superbet' : 'consens'} ${clvTxt(s.avg)} (${s.n})`).join(' · ')}</p> : null}
        </>
      )}
    </Card>
  );
}

function Block({ title, b }: { title: string; b?: StatBlock }) {
  const dec = (b?.won ?? 0) + (b?.lost ?? 0);
  return (
    <div className="rounded-xl bg-muted/40 p-3">
      <div className="text-xs text-muted-foreground">{title}</div>
      <div className={`num text-xl font-extrabold ${tone(b?.roi_pct) === 'win' ? 'text-win' : tone(b?.roi_pct) === 'loss' ? 'text-loss' : ''}`}>{b?.roi_pct == null ? '—' : signed(b.roi_pct, 1, '%')}</div>
      <div className="text-[11px] text-muted-foreground">{dec ? `${b?.won}/${dec} câștigate (${pct(b?.win_rate ?? null)})` : 'nedecontate'}{b?.clv_n ? ` · CLV ${clvTxt(b.clv_avg)}` : ''}</div>
    </div>
  );
}

/** Raportul săptămânal (luni, după reantrenare). */
export function WeeklyPanel() {
  const w = useAsync(loadWeekly, []);
  if (w.loading) return <Loading />;
  const r = w.data?.latest;
  if (!r) return <Empty title="Primul raport apare luni">După reantrenarea de luni, Robotul publică ROI-ul, CLV-ul și ce a schimbat.</Empty>;
  const p = r.blocks.pick;
  return (
    <div className="space-y-4">
      <Card className="p-4">
        <div className="mb-3 flex items-start gap-2">
          <CalendarCheck className="mt-0.5 h-5 w-5 text-primary" />
          <div className="min-w-0 flex-1"><h2 className="font-semibold">{r.title}</h2><p className="text-xs text-muted-foreground">{r.notify.body}</p></div>
        </div>
        <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
          <Stat label="ROI pick-uri" value={p?.roi_pct == null ? '—' : signed(p.roi_pct, 1, '%')} tone={tone(p?.roi_pct)} sub={`${p?.won ?? 0}V / ${p?.lost ?? 0}Î`} />
          <Stat label="Rată de câștig" value={pct(p?.win_rate ?? null, 1)} sub={`${(p?.won ?? 0) + (p?.lost ?? 0)} decontate`} />
          <Stat label="CLV pick-uri" value={clvTxt(p?.clv_avg)} tone={tone(p?.clv_avg)} sub={`${p?.clv_n ?? 0} cu închidere`} />
          <Stat label="Cote Superbet" value={r.superbet_share == null ? '—' : pct(r.superbet_share)} sub="din pick-uri (cote jucabile)" />
        </div>
        <div className="mt-3 grid grid-cols-2 gap-2 md:grid-cols-4">
          <Block title="Toate" b={r.blocks.toate} /><Block title="Pick-uri" b={r.blocks.pick} /><Block title="Recomandate" b={r.blocks.recomandate} /><Block title="Valoare (EV>0)" b={r.blocks.valoare} />
        </div>
        {r.vs_previous && <p className="mt-2 text-xs text-muted-foreground">Față de săptămâna trecută: ROI {r.vs_previous.roi_pct[0] == null ? '—' : signed(r.vs_previous.roi_pct[0], 1, '%')} → {r.vs_previous.roi_pct[1] == null ? '—' : signed(r.vs_previous.roi_pct[1], 1, '%')} · CLV {clvTxt(r.vs_previous.clv_avg[0])} → {clvTxt(r.vs_previous.clv_avg[1])}</p>}
      </Card>
      {r.tickets.length ? (
        <Card className="p-4"><h2 className="mb-2 text-sm font-semibold">Bilete</h2>
          <div className="overflow-x-auto"><table className="w-full text-sm"><thead className="text-xs text-muted-foreground"><tr><th className="py-1 text-left">Tip</th><th className="text-right">n</th><th className="text-right">V/Î</th><th className="text-right">ROI</th><th className="text-right">CLV</th></tr></thead>
            <tbody>{r.tickets.map((t) => <tr key={t.kind} className="border-t"><td className="py-1.5">{KIND[t.kind] ?? t.kind}</td><td className="text-right">{t.n}</td><td className="text-right">{t.won}/{t.lost}</td><td className="text-right">{t.roi_pct == null ? '—' : signed(t.roi_pct, 1, '%')}</td><td className="text-right">{clvTxt(t.clv_avg)}</td></tr>)}</tbody></table></div>
        </Card>
      ) : null}
      {(r.segments.off.length || r.segments.boost.length) ? (
        <Card className="p-4"><h2 className="mb-2 text-sm font-semibold">Focus: segmente ligă × piață</h2>
          <ul className="space-y-1.5 text-sm">
            {r.segments.boost.map((s) => <li key={s.key} className="flex flex-wrap items-center gap-2"><Badge tone="win">întărit</Badge>{s.league ?? s.key.split('|')[0]} · {marketTitle(s.key.split('|')[1])}<span className="text-xs text-muted-foreground">CLV {clvTxt(s.clv_post)} · ROI {signed(s.roi_post * 100, 1, '%')}</span></li>)}
            {r.segments.off.map((s) => <li key={s.key} className="flex flex-wrap items-center gap-2"><Badge tone="loss">oprit</Badge>{s.league ?? s.key.split('|')[0]} · {marketTitle(s.key.split('|')[1])}<span className="text-xs text-muted-foreground">CLV {clvTxt(s.clv_post)} · ROI {signed(s.roi_post * 100, 1, '%')}</span></li>)}
          </ul>
        </Card>
      ) : null}
      <Card className="p-4"><h2 className="mb-2 text-sm font-semibold">Ce a schimbat Robotul ({r.changes.length})</h2>
        {r.changes.length ? <ol className="space-y-2">{r.changes.map((c, i) => (
          <li key={i} className="rounded-lg bg-muted/40 px-3 py-2 text-sm"><b>{CHANGE[c.type] ?? c.type}</b>{c.market ? <span className="ml-1 text-muted-foreground">{c.market}</span> : null}
            {c.why ? <div className="text-xs">{c.why}</div> : <div className="text-xs text-muted-foreground">{String(c.before ?? '')} → {String(c.after ?? '')}</div>}</li>
        ))}</ol> : <p className="text-sm text-muted-foreground">Nicio ajustare în această săptămână.</p>}
      </Card>
      {w.data && w.data.history.length > 1 && (
        <Card className="p-4"><h2 className="mb-2 text-sm font-semibold">Săptămânile anterioare</h2>
          <ul className="divide-y text-sm">{w.data.history.slice(1).map((h) => <li key={h.id} className="flex items-center justify-between py-1.5"><span>{h.title.replace('Raport săptămânal ', '')}</span><span className="text-xs text-muted-foreground">ROI {h.pick.roi_pct == null ? '—' : signed(h.pick.roi_pct, 1, '%')} · CLV {clvTxt(h.pick.clv_avg)} · {h.changes} ajustări</span></li>)}</ul>
        </Card>
      )}
    </div>
  );
}
