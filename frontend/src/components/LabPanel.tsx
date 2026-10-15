import { FlaskConical } from 'lucide-react';
import { useAsync, getJSON } from '@/lib/fetcher';
import { Card, Loading, Empty, Badge, Notice } from '@/components/kit';

/* eslint-disable @typescript-eslint/no-explicit-any */
type M = { n: number; hit_rate: number; roi: number; roi_se?: number | null; max_drawdown_u: number; longest_losing_streak: number; profit_u: number };
type S = { name: string; market_set: string; band: number[]; tier: number; system: number; avg_legs: number; train: M; test: M };
type Lab = { matches: number; configs_tested: number; configs_eligible: number; test_positive: number; train_positive: number; both_positive: number;
  both_positive_expected_by_chance: number; both_positive_significant_test_t2: number; split: string; overround: number;
  tiers: Record<string, { configs: number; median_test_roi: number; share_test_positive: number }>; super: S[]; robust: S[];
  tipster?: { source: string; configs_tested: number; both_positive: number; both_positive_expected_by_chance: number; verdict: string; not_covered: string; patterns: Record<string, { configs: number; median_test_roi: number; share_test_positive: number; median_test_hit: number }> };
  stil_supersocial_live?: { tickets: Record<string, { n: number; won: number; lost: number; pending: number; staked_u: number; profit_u: number }>; legs: Record<string, { n: number; won: number; hit: number; avg_odds: number; roi_single: number }>; wave?: { key: string; label: string; n: number; hit: number; avg_odds: number; roi_single: number }[]; wave_min_n?: number; wave_min_roi?: number;
    lift?: Record<string, { n: number; hit: number; implied: number; lift: number; se?: number; clv?: number; clv_n?: number }>; lift_min_n?: number; lift_drop?: number };
  live?: Record<string, { n: number; won: number; lost: number; pending: number; staked_u: number; profit_u: number }> };

const P = (x: number) => `${x >= 0 ? '+' : ''}${(x * 100).toFixed(0)}%`;
const SETS: Record<string, string> = { sigure_mix: 'Mix sigure', goluri_peste: 'Goluri peste', goluri_sub: 'Goluri sub', sansa_dubla: 'Șansă dublă', favoriti_1x2: 'Favoriți 1X2', goluri_mix: 'Goluri mix' };
const SEL: Record<string, string> = { H13x2: '1–3 în fiecare repriză', R1R2: 'Gol în ambele reprize', BB_H13x2_O15: '1–3 reprize și peste 1.5',
  R1O15: 'R1 0.5 și meci 1.5', R1O25: 'R1 0.5 și meci 2.5', GGO25: 'GG sau Peste 2.5', GG: 'Ambele marchează (GG)', YC35: 'Cartonașe Peste 3.5', YC45: 'Cartonașe Peste 4.5', YCU45: 'Cartonașe Sub 4.5', YCU55: 'Cartonașe Sub 5.5', BOTH15: 'Fiecare echipă 1.5+ cartonașe', HY15: 'Cartonașe gazde 1.5+', AY15: 'Cartonașe oaspeți 1.5+', HY25: 'Cartonașe gazde 2.5+', AY25: 'Cartonașe oaspeți 2.5+', HO05: 'Gazdele marchează', HO15: 'Gazde 1.5+ goluri', AO05: 'Oaspeții marchează', AO15: 'Oaspeți 1.5+ goluri', DCX2_O15: 'X2 & Peste 1.5', H1O05: 'R1 Peste 0.5', H1O15: 'R1 Peste 1.5', H2G13: 'R2 1–3 goluri', G13: 'Interval 1–3', G24: 'Interval 2–4', G25: 'Interval 2–5',
  H1CLT5: 'R1 cornere sub 5', H1C56: 'R1 cornere 5–6', H1C7P: 'R1 cornere 7+', H1C25: 'R1 cornere peste 2.5', H1C35: 'R1 cornere peste 3.5',
  BB_H1C25_U65: 'R1 cornere 3–6 (estimat)', C65: 'Cornere peste 6.5', C75: 'Cornere peste 7.5', C85: 'Cornere peste 8.5', C95: 'Cornere peste 9.5',
  BB_C65_U145: 'Cornere 6.5 și sub 14.5', CU145: 'Cornere sub 14.5', H1U65: 'R1 cornere sub 6.5' };
const title = (s: S) => `${SETS[s.market_set] ?? s.market_set} ${s.band[0].toFixed(2)}–${s.band[1].toFixed(2)} · ~${s.tier} · ${s.system ? `sistem N−${s.system}/N` : 'acumulator'}`;

function StratCard({ s, live }: { s: S; live?: { n: number; won: number; lost: number; pending: number; staked_u: number; profit_u: number } }) {
  const t = s.test;
  return (
    <Card className="p-4">
      <div className="mb-2 flex items-start justify-between gap-2"><h3 className="text-sm font-semibold leading-snug">{title(s)}</h3><Badge tone={t.roi > 0 ? 'win' : 'loss'}>{P(t.roi)}</Badge></div>
      <div className="grid grid-cols-3 gap-2 text-center text-xs">
        <div><div className="text-muted-foreground">Lovit (test)</div><div className="text-base font-semibold">{(t.hit_rate * 100).toFixed(1)}%</div></div>
        <div><div className="text-muted-foreground">Bilete test</div><div className="text-base font-semibold">{t.n}</div></div>
        <div><div className="text-muted-foreground">Selecții</div><div className="text-base font-semibold">~{s.avg_legs}</div></div>
        <div><div className="text-muted-foreground">Drawdown</div><div className="font-semibold">{t.max_drawdown_u}u</div></div>
        <div><div className="text-muted-foreground">Șir pierderi</div><div className="font-semibold">{t.longest_losing_streak}</div></div>
        <div><div className="text-muted-foreground">ROI antrenare</div><div className="font-semibold">{P(s.train.roi)}</div></div>
      </div>
      {t.roi_se ? <p className="mt-2 text-xs text-muted-foreground">Incertitudine ROI test: ± {(t.roi_se * 100).toFixed(0)}% — câteva bilete câștigate fac tot rezultatul.</p> : null}
      {live ? <p className="mt-1 text-xs">Live: {live.n} bilete · {live.won} câștigate · {live.lost} pierdute · profit {live.profit_u.toFixed(2)}u</p> : null}
    </Card>
  );
}

/** Ce a învățat robotul: pe piață, cât intră față de cât promite cota. Așa alege biletele de ~100. */
function LiftTable({ live }: { live: NonNullable<Lab['stil_supersocial_live']> }) {
  const minN = live.lift_min_n ?? 10, drop = live.lift_drop ?? 0.97;
  const rows = Object.entries(live.lift ?? {}).sort((a, b) => b[1].lift - a[1].lift);
  if (!rows.length) return null;
  return (
    <div className="mt-3 rounded-2xl border border-primary/25 bg-primary/5 p-3">
      <h3 className="text-sm font-semibold">Ce a învățat robotul</h3>
      <p className="mt-1 text-xs text-muted-foreground">Pe fiecare piață, din toate selecțiile Supersocial cu preț Superbet (nu doar cele de pe bilete): cât intră față de cât promite cota. Peste 1 = intră mai des decât spune cota, și robotul o preferă. De la {minN} rezultate, sub {drop.toFixed(2)} piața iese din bilete. Cu puține rezultate, corecția stă aproape de 0,95 (marja casei). Sub corecție: marja de eroare (95%); la șansa biletelor robotul folosește capătul prudent. CLV = cât a scăzut cota de când a văzut-o robotul până la start; pozitiv înseamnă că piața i-a dat dreptate, înainte de rezultat.</p>
      <div className="mt-2 overflow-x-auto">
        <table className="w-full text-xs">
          <thead className="text-muted-foreground"><tr><th className="py-1 text-left">Piață</th><th className="text-right">n</th><th className="text-right">Intră</th><th className="text-right">Cota promite</th><th className="text-right">Corecție</th><th className="text-right">CLV</th><th className="pl-2 text-right">Pe bilete</th></tr></thead>
          <tbody>{rows.map(([k, v]) => {
            const judged = v.n >= minN, out = judged && v.lift < drop;
            return (
              <tr key={k} className="border-t">
                <td className="py-1.5 pr-2">{SEL[k] ?? k}</td><td className="text-right">{v.n}</td><td className="text-right">{v.n ? `${(v.hit * 100).toFixed(0)}%` : '—'}</td>
                <td className="text-right text-muted-foreground">{v.n ? `${(v.implied * 100).toFixed(0)}%` : '—'}</td>
                <td className={judged ? (v.lift >= 1 ? 'text-right font-semibold text-win' : v.lift < drop ? 'text-right font-semibold text-loss' : 'text-right') : 'text-right text-muted-foreground'}>{v.lift.toFixed(2)}{v.se ? <span className="block text-[10px] font-normal text-muted-foreground">±{(2 * v.se).toFixed(2)}</span> : null}</td>
                <td className={v.clv == null ? 'text-right text-muted-foreground' : v.clv > 0 ? 'text-right text-win' : 'text-right text-loss'} title={v.clv_n ? `${v.clv_n} meciuri` : undefined}>{v.clv == null ? '—' : `${v.clv > 0 ? '+' : ''}${(v.clv * 100).toFixed(1)}%`}</td>
                <td className="pl-2 text-right">{!judged ? <span className="text-muted-foreground">încă învață</span> : out ? <Badge tone="loss">scoasă</Badge> : <Badge tone="win">{v.lift >= 1 ? 'preferată' : 'folosită'}</Badge>}</td>
              </tr>
            );
          })}</tbody>
        </table>
      </div>
    </div>
  );
}

function StilBody({ live }: { live: NonNullable<Lab['stil_supersocial_live']> }) {
  const tickets = Object.entries(live.tickets ?? {});
  const legs = Object.entries(live.legs ?? {});
  const wave = live.wave ?? [];
  const won = tickets.reduce((s, [, v]) => s + v.won, 0);
  const lost = tickets.reduce((s, [, v]) => s + v.lost, 0);
  const pending = tickets.reduce((s, [, v]) => s + v.pending, 0);
  const profit = tickets.reduce((s, [, v]) => s + (v.profit_u || 0), 0);
  if (!tickets.length && !legs.length) return null;
  return (
    <Card className="p-4">
      <h2 className="text-sm font-semibold">Pe val</h2>
      <p className="mt-1 text-xs text-muted-foreground">Intră la bilete doar tipurile cu cel puțin {live.wave_min_n ?? 30} selecții și ROI peste {Math.round((live.wave_min_roi ?? 0.1) * 100)}%. Dacă lista nu se schimbă, biletele de azi rămân. Hârtie, miză 0,05 unități.</p>
      <LiftTable live={live} />
      <h3 className="mt-3 text-sm font-semibold">Bilete întregi</h3>
      <p className="mt-1 text-xs text-muted-foreground">{won} câștigate · {lost} pierdute · {pending} în joc · {profit >= 0 ? '+' : ''}{profit.toFixed(2)}u. Un bilet cu multe meciuri se pierde la o singură selecție. Asta nu e același lucru cu ROI-ul de mai jos.</p>
      <ul className="mt-2 space-y-1 text-sm">
        {tickets.map(([k, v]) => (
          <li key={k} className="flex flex-wrap gap-x-2"><b className="min-w-0 flex-1">{k}</b><span className="text-muted-foreground">{v.won} câștigate · {v.lost} pierdute · {v.pending} în joc · {v.profit_u >= 0 ? '+' : ''}{v.profit_u.toFixed(2)}u</span></li>
        ))}
      </ul>
      <h3 className="mt-4 text-sm font-semibold">Selecții care intră la bilete</h3>
      {wave.length ? (
        <div className="mt-2 overflow-x-auto">
          <table className="w-full text-xs">
            <thead className="text-muted-foreground"><tr><th className="py-1 text-left">Tip</th><th className="text-right">n</th><th className="text-right">Intrate</th><th className="text-right">Cotă</th><th className="text-right">ROI selecție</th></tr></thead>
            <tbody>{wave.map((v) => <tr key={v.key} className="border-t"><td className="py-1">{SEL[v.key] ?? v.label}</td><td className="text-right">{v.n}</td><td className="text-right">{(v.hit * 100).toFixed(0)}%</td><td className="text-right">{v.avg_odds.toFixed(2)}</td><td className="text-right text-win">{P(v.roi_single)}</td></tr>)}</tbody>
          </table>
        </div>
      ) : <p className="mt-2 text-xs text-muted-foreground">Niciun tip nu trece pragul. Până atunci rămâne catalogul experimental.</p>}
      <h3 className="mt-4 text-sm font-semibold">Toate selecțiile urmărite</h3>
      {legs.length ? (
        <div className="mt-3 overflow-x-auto">
          <table className="w-full text-xs">
            <thead className="text-muted-foreground"><tr><th className="py-1 text-left">Selecție</th><th className="text-right">n</th><th className="text-right">Intrate</th><th className="text-right">Cotă</th><th className="text-right">ROI</th></tr></thead>
            <tbody>{legs.map(([k, v]) => <tr key={k} className="border-t"><td className="py-1">{SEL[k] ?? k}</td><td className="text-right">{v.n}</td><td className="text-right">{(v.hit * 100).toFixed(0)}%</td><td className="text-right">{v.avg_odds.toFixed(2)}</td><td className={v.roi_single >= 0 ? 'text-right text-win' : 'text-right text-loss'}>{P(v.roi_single)}</td></tr>)}</tbody>
          </table>
        </div>
      ) : <p className="mt-2 text-xs text-muted-foreground">Încă nicio selecție decontată.</p>}
    </Card>
  );
}

export function StilLiveCard({ live }: { live?: Lab['stil_supersocial_live'] } = {}) {
  if (live) return <StilBody live={live} />;
  return <StilLiveFetch />;
}

function StilLiveFetch() {
  const lab = useAsync(() => getJSON<Lab>('api/lab/results.json'), []);
  if (lab.loading || !lab.data?.stil_supersocial_live) return null;
  return <StilBody live={lab.data.stil_supersocial_live} />;
}

export function LabPanel() {
  const lab = useAsync(() => getJSON<Lab>('api/lab/results.json'), []);
  if (lab.loading) return <Loading />;
  const d = lab.data;
  if (!d) return <Empty title="Laboratorul nu are încă rezultate" />;
  return (
    <div className="space-y-4">
      <Card className="p-4">
        <h2 className="mb-2 flex items-center gap-2 text-sm font-semibold"><FlaskConical className="h-4 w-4" />Laboratorul de strategii</h2>
        <p className="text-xs text-muted-foreground">{d.configs_tested.toLocaleString('ro-RO')} strategii de bilete lungi testate pe {d.matches.toLocaleString('ro-RO')} meciuri ({d.split}). Selecție doar cu informații dinainte de meci, cote de închidere cu marjă tip Superbet ({((d.overround - 1) * 100).toFixed(0)}%).</p>
        <div className="mt-3 grid grid-cols-3 gap-2 text-center text-xs">
          <div><div className="text-muted-foreground">Pozitive în test</div><div className="text-base font-semibold">{d.test_positive}/{d.configs_eligible}</div></div>
          <div><div className="text-muted-foreground">Pozitive în ambele</div><div className="text-base font-semibold">{d.both_positive}</div></div>
          <div><div className="text-muted-foreground">Așteptat din noroc</div><div className="text-base font-semibold">{d.both_positive_expected_by_chance}</div></div>
        </div>
      </Card>
      <Notice tone="warn">Concluzie onestă: biletele lungi pierd în medie (ROI median în test între {P(Math.max(...Object.values(d.tiers).map((x) => x.median_test_roi)))} și {P(Math.min(...Object.values(d.tiers).map((x) => x.median_test_roi)))}). Strategiile „pozitive” nu sunt mai multe decât ar da întâmplarea și niciuna nu e semnificativă statistic. Super biletele sunt jucate cu risc asumat, miză fixă mică.</Notice>
      <Card className="overflow-hidden"><h2 className="p-3 text-sm font-semibold">Pe țintă de cotă (doar perioada de test)</h2>
        <table className="w-full text-sm"><thead className="text-xs text-muted-foreground"><tr><th className="px-3 py-1 text-left">Cotă</th><th className="text-right">Strategii</th><th className="text-right">ROI median</th><th className="px-3 text-right">Pozitive</th></tr></thead>
          <tbody>{Object.entries(d.tiers).map(([k, v]) => <tr key={k} className="border-t"><td className="px-3 py-1.5">~{k}</td><td className="text-right">{v.configs}</td><td className="text-right">{P(v.median_test_roi)}</td><td className="px-3 text-right">{(v.share_test_positive * 100).toFixed(0)}%</td></tr>)}</tbody></table>
      </Card>
      {d.tipster ? (
        <Card className="overflow-hidden"><h2 className="p-3 pb-1 text-sm font-semibold">Tipare de tipster testate</h2>
          <p className="px-3 text-xs text-muted-foreground">{d.tipster.source} · {d.tipster.configs_tested} strategii · pozitive în ambele perioade {d.tipster.both_positive} (din noroc ~{d.tipster.both_positive_expected_by_chance})</p>
          <table className="mt-2 w-full text-sm"><thead className="text-xs text-muted-foreground"><tr><th className="px-3 py-1 text-left">Tipar</th><th className="text-right">Lovit</th><th className="text-right">ROI median</th><th className="px-3 text-right">Pozitive</th></tr></thead>
            <tbody>{Object.entries(d.tipster.patterns).map(([k, v]) => <tr key={k} className="border-t"><td className="px-3 py-1.5">{k.replace(/_/g, ' ')}</td><td className="text-right">{(v.median_test_hit * 100).toFixed(1)}%</td><td className="text-right">{P(v.median_test_roi)}</td><td className="px-3 text-right">{(v.share_test_positive * 100).toFixed(0)}%</td></tr>)}</tbody></table>
          <p className="p-3 text-xs">{d.tipster.verdict}</p><p className="px-3 pb-3 text-xs text-muted-foreground">{d.tipster.not_covered}</p>
        </Card>
      ) : null}
      <MarketsLabCard />
      <StilLiveCard live={d.stil_supersocial_live} />
      <h2 className="text-sm font-semibold">Strategiile folosite la Super bilete</h2>
      {d.super.map((s) => <StratCard key={s.name} s={s} live={d.live?.[s.name] as any} />)}
    </div>
  );
}

type MPer = { n: number; hit?: number; implied?: number; lift?: number | null; lift_z?: number; roi?: number };
type MStrat = { name: string; set: string; markets: string[]; band: number[]; league: string; tier: number; avg_legs: number;
  train: { n: number; roi: number; hit_rate: number }; test: { n: number; roi: number; hit_rate: number } };
type MarketsLab = { generated_at: string; matches: number; split: string; configs_tested: number; both_positive: number;
  both_positive_expected_by_chance: number; significant_both: number; candidates: string[];
  markets: Array<{ key: string; label: string; family: string; price: string; train: MPer; test: MPer }>;
  robust: MStrat[]; tiers: Record<string, { configs: number; median_test_roi: number; share_test_positive: number; best_test_hit: number }> };
const LEAGUE: Record<string, string> = { all: 'toate ligile', lower: 'ligi mici', top: 'ligi mari' };

/** Laboratorul de piețe: piețele Superbet calculabile din scor/pauză/cornere, testate pe istoric (api/lab/markets.json). */
function MarketsLabCard() {
  const q = useAsync(() => getJSON<MarketsLab>('api/lab/markets.json'), []);
  const d = q.data;
  if (q.loading) return null;
  if (!d) return <Card className="p-4"><h2 className="text-sm font-semibold">Piețe noi pe istoric</h2><p className="mt-1 text-xs text-muted-foreground">Rezultatele apar după rularea săptămânală de învățare (luni dimineața sau Actions → „learn”).</p></Card>;
  const byLift = [...d.markets].filter((m) => (m.test.n ?? 0) >= 200 && m.test.lift != null).sort((a, b) => (b.test.lift ?? 0) - (a.test.lift ?? 0));
  const label = Object.fromEntries(d.markets.map((m) => [m.key, m.label]));
  return (
    <Card className="p-4">
      <h2 className="text-sm font-semibold">Piețe noi pe istoric</h2>
      <p className="mt-1 text-xs text-muted-foreground">{d.markets.length} piețe Superbet calculate din scor, pauză și cornere, pe {d.matches.toLocaleString('ro-RO')} meciuri ({d.split}). {d.configs_tested.toLocaleString('ro-RO')} strategii de bilete, pozitive în ambele perioade {d.both_positive} (din noroc ~{d.both_positive_expected_by_chance}), semnificative {d.significant_both}.</p>
      <div className="mt-3"><Notice tone={d.candidates.length ? 'info' : 'warn'}>{d.candidates.length
        ? `Candidate (intră peste preț în ambele perioade): ${d.candidates.map((k) => label[k] ?? k).join(', ')}. Se confirmă doar urmărite zilnic la cotele Superbet reale.`
        : 'Nicio piață nu intră constant peste preț în ambele perioade. La cotele estimate, niciuna nu are avantaj sigur.'}</Notice></div>
      <h3 className="mt-3 text-xs font-semibold text-muted-foreground">Intră față de cât promite prețul (test)</h3>
      <table className="mt-1 w-full text-xs"><thead className="text-muted-foreground"><tr><th className="py-1 text-left">Piață</th><th className="text-right">Intră</th><th className="text-right">Preț</th><th className="text-right">Raport</th></tr></thead>
        <tbody>{byLift.slice(0, 12).map((m) => (
          <tr key={m.key} className="border-t"><td className="py-1 pr-2">{m.label}{m.price === 'reală' ? '' : ' *'}</td>
            <td className="text-right">{((m.test.hit ?? 0) * 100).toFixed(0)}%</td><td className="text-right text-muted-foreground">{((m.test.implied ?? 0) * 100).toFixed(0)}%</td>
            <td className={(m.test.lift ?? 0) >= 1 ? 'text-right text-win' : 'text-right text-loss'}>{(m.test.lift ?? 0).toFixed(2)}</td></tr>
        ))}</tbody></table>
      <p className="mt-1 text-[11px] text-muted-foreground">* preț estimat din model + marjă Superbet (fără cote istorice pentru piața asta).</p>
      <h3 className="mt-3 text-xs font-semibold text-muted-foreground">Bilete pe țintă de cotă (test)</h3>
      <table className="mt-1 w-full text-xs"><thead className="text-muted-foreground"><tr><th className="py-1 text-left">Cotă</th><th className="text-right">Strategii</th><th className="text-right">ROI median</th><th className="text-right">Cel mai des intrat</th></tr></thead>
        <tbody>{Object.entries(d.tiers).map(([t, v]) => (
          <tr key={t} className="border-t"><td className="py-1">~{Number(t).toLocaleString('ro-RO')}</td><td className="text-right">{v.configs}</td><td className="text-right">{P(v.median_test_roi)}</td>
            <td className="text-right">{v.best_test_hit > 0 ? `1 din ${Math.round(1 / v.best_test_hit)}` : 'niciodată'}</td></tr>
        ))}</tbody></table>
      {d.robust.length > 0 && <>
        <h3 className="mt-3 text-xs font-semibold text-muted-foreground">Cele mai stabile (pozitive în ambele perioade)</h3>
        <ul className="mt-1 space-y-1 text-xs">{d.robust.slice(0, 6).map((s) => (
          <li key={s.name} className="flex flex-wrap gap-x-2 border-t pt-1"><b className="min-w-0 flex-1">{s.markets.map((k) => label[k] ?? k).join(' / ')} · cote {s.band[0]}–{s.band[1]} · {LEAGUE[s.league] ?? s.league} · ~{s.tier}</b>
            <span className="text-muted-foreground">{s.avg_legs} sel. · test {P(s.test.roi)} pe {s.test.n} bilete, intrat {(s.test.hit_rate * 100).toFixed(1)}%</span></li>
        ))}</ul></>}
    </Card>
  );
}
