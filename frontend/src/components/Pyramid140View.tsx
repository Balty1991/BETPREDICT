import { useState } from 'react';
import { leiRo } from '@/components/YourStake';
import { useAsync } from '@/lib/fetcher';
import { loadPyramid140, loadPyramidMici, loadPyramidMix, loadPyramidRisk, loadPyramidSafe } from '@/lib/data';
import { odds as fo, pct, lei } from '@/lib/format';
import { Card, Loading, Stat, SectionTitle, Badge, Notice, PriceNote } from '@/components/kit';
import { TicketCard, isLostTicket } from '@/components/TicketCard';
import type { PyramidBacktest } from '@/lib/types';
import { cn } from '@/lib/utils';
import { ActionCard, type PyrAction } from '@/components/PyramidAction';

/** Miza mea de start pe piramidă (lei), aleasă manual; ținută pe telefon. Implicit 2 lei (minimul Superbet). */
function useMyStart(track: string): [number, (v: number) => void] {
  const key = `bp.pyr.start.${track}`;
  const [v, setV] = useState<number>(() => { try { const x = Number(localStorage.getItem(key)); return x > 0 ? x : 2; } catch { return 2; } });
  return [v, (x) => { setV(x); try { localStorage.setItem(key, String(x)); } catch { /* fără stocare */ } }];
}

/** Seria mea: pornesc de la treapta 1 într-o zi aleasă (pe biletele Robotului). Se ține pe telefon; se încheie singură
 *  când seria Robotului se rupe (alt run). */
type MyBase = { run: number; step: number; bank: number; date: string; amount?: number };
function useMyBase(track: string): [MyBase | null, (v: MyBase | null) => void] {
  const key = `bp.pyr.base.${track}`;
  const [v, setV] = useState<MyBase | null>(() => { try { const x = localStorage.getItem(key); return x ? JSON.parse(x) as MyBase : null; } catch { return null; } });
  return [v, (x) => { setV(x); try { if (x) localStorage.setItem(key, JSON.stringify(x)); else localStorage.removeItem(key); } catch { /* fără stocare */ } }];
}

/** Retragerile mele parțiale din seria curentă (lei), cu banca Robotului din momentul retragerii, ca restul să se
 *  recalculeze: banii rămași cresc la fel cu seria de acolo încolo. */
type MyWd = { run: number; bank: number; amount: number; date: string };
function useMyWd(track: string): [MyWd[], (v: MyWd[]) => void] {
  const key = `bp.pyr.wd.${track}`;
  const [v, setV] = useState<MyWd[]>(() => { try { return JSON.parse(localStorage.getItem(key) || '[]') as MyWd[]; } catch { return []; } });
  return [v, (x) => { setV(x); try { localStorage.setItem(key, JSON.stringify(x)); } catch { /* fără stocare */ } }];
}

/** Sunt deja mai sus (ex. seria mea a continuat când a Robotului s-a oprit): treapta mea de azi și cât am în joc. */
function MyStepField({ def, onSet }: { def: number; onSet: (step: number, amount: number) => void }) {
  const [open, setOpen] = useState(false);
  const [st, setSt] = useState('');
  const [am, setAm] = useState('');
  const u = Math.round(Number(st)), a = Number(am.replace(',', '.'));
  const ok = u >= 1 && u <= 30 && a > 0;
  if (!open) return <div className="mt-1 text-center"><button type="button" className="text-[11px] font-semibold text-primary" onClick={() => setOpen(true)}>Sunt deja la altă treaptă…</button></div>;
  return (
    <div className="mt-2 flex flex-wrap items-center justify-center gap-1.5 text-[12px]">
      <span>Treapta</span>
      <input inputMode="numeric" className="input h-9 w-14 min-h-0 py-0 text-center" value={st} onChange={(e) => setSt(e.target.value)} placeholder="5" aria-label="Treapta mea de azi" />
      <span>cu</span>
      <input inputMode="decimal" className="input h-9 w-20 min-h-0 py-0 text-center" value={am} onChange={(e) => setAm(e.target.value)} placeholder={String(Math.round(def * 2))} aria-label="Lei în joc azi" />
      <span>lei în joc</span>
      <button type="button" disabled={!ok} className="btn h-9 px-3 text-xs" onClick={() => { onSet(u, a); setOpen(false); }}>Setează</button>
    </div>
  );
}

function WithdrawField({ max, onWithdraw }: { max: number; onWithdraw: (v: number) => void }) {
  const [t, setT] = useState('');
  const n = Number(t.replace(',', '.'));
  const ok = n > 0 && n <= max + 0.001;
  return (
    <div className="mt-2 flex items-center justify-center gap-2 text-xs text-muted-foreground">
      Retrag acum
      <input type="text" inputMode="decimal" enterKeyHint="done" className="input h-9 w-20 text-center font-bold" aria-label="Retrag acum (lei)" placeholder="0"
        value={t} onChange={(e) => setT(e.target.value.replace(/[^\d.,]/g, ''))} />
      lei
      <button type="button" className="btn h-9 px-3 text-xs" disabled={!ok} onClick={() => { onWithdraw(Math.round(n * 100) / 100); setT(''); }}>Retrag</button>
    </div>
  );
}

function StartField({ value, onChange }: { value: number; onChange: (v: number) => void }) {
  const [t, setT] = useState<string | null>(null);
  const commit = () => { if (t !== null) { const n = Number(t.replace(',', '.')); if (n > 0) onChange(Math.round(n * 100) / 100); setT(null); } };
  // se salvează pe loc, la fiecare cifră validă (nu doar la ieșirea din câmp)
  const type = (v: string) => { setT(v); const n = Number(v.replace(',', '.')); if (n > 0) onChange(Math.round(n * 100) / 100); };
  return (
    <label className="flex items-center justify-center gap-2 text-xs text-muted-foreground">
      Miza mea de start
      <input type="text" inputMode="decimal" enterKeyHint="done" className="input h-9 w-20 text-center font-bold" aria-label="Miza mea de start (lei)"
        value={t ?? String(value)} onFocus={(e) => { setT(String(value)); e.currentTarget.select(); }}
        onChange={(e) => type(e.target.value.replace(/[^\d.,]/g, ''))} onBlur={commit} onKeyDown={(e) => { if (e.key === 'Enter') e.currentTarget.blur(); }} />
      lei
    </label>
  );
}

export type Track = '1.20' | '1.40' | '1.60' | 'boost' | 'mici' | 'r5' | 'r10' | 'r100' | 'mix140' | 'mix25';
export function useP140(track: Track = '1.40') {
  return useAsync(() => (track === 'mici' ? loadPyramidMici() : track === 'mix140' || track === 'mix25' ? loadPyramidMix(track) : track === 'r5' || track === 'r10' || track === 'r100' ? loadPyramidRisk(track)
    : track === '1.20' || track === '1.60' || track === 'boost' ? loadPyramidSafe(track) : loadPyramid140()), [track]);
}
type RiskBt = { tickets: number; won: number; hit: number | null; expected_hit: number | null; avg_odds: number | null; flat_roi: number | null; invested_lei: number; returned_lei: number; from: string; to: string; note?: string };
function RiskBacktest({ bt }: { bt?: RiskBt | null }) {
  if (!bt) return null;
  return (
    <Card className="p-4">
      <h2 className="mb-1 font-semibold">Backtest walk-forward ({bt.from} → {bt.to})</h2>
      <div className="grid grid-cols-3 gap-2">
        <Stat label="Bilete" value={bt.tickets} sub={`${bt.won} câștigate`} />
        <Stat label="Rată reală" value={bt.hit != null ? pct(bt.hit) : '—'} sub={`estimat ${bt.expected_hit != null ? pct(bt.expected_hit) : '—'}`} />
        <Stat label="Cotă medie" value={bt.avg_odds != null ? fo(bt.avg_odds) : '—'} />
      </div>
      <p className="mt-2 text-xs text-muted-foreground">Miză 2 lei pe serie: băgat {lei(bt.invested_lei)}, scos {lei(bt.returned_lei)}. {bt.note}</p>
    </Card>
  );
}
const COPY: Record<Track, { eyebrow: string; title: string; text: string; lost: string }> = {
  '1.20': { eyebrow: 'Cotă în jur de 1.20', title: 'Piramida 1.20',
    text: 'Un singur meci pe zi la cota 1.16–1.25 (≥ 75%). Întâi un meci la care cota a scăzut cu cel puțin 2% de la deschidere (piața confirmă), altfel cel mai sigur, corectat cu cât intră de fapt fiecare piață. Pe istoric: 83% pași câștigați, serie medie 5, record 47, 15% din serii trec de 10 pași. Reinvestești tot; încasarea e doar propusă.',
    lost: 'Mâine Piramida 1.20 reîncepe de la treapta 1.' },
  '1.40': { eyebrow: 'Cotă în jur de 1.40', title: 'Piramida 1.40',
    text: 'Un singur meci pe zi la cota 1.35–1.40 (≥ 65%), cel mai sigur, corectat cu cât intră de fapt fiecare piață; doar dacă nu există, 2 selecții de cel mult 1.40. Pe istoric: 72% pași câștigați, record 17. Reinvestești tot; încasarea e doar propusă.',
    lost: 'Mâine Piramida 1.40 reîncepe de la treapta 1.' },
  '1.60': { eyebrow: 'Cotă în jur de 1.60', title: 'Piramida 1.60',
    text: '2 selecții de cel mult 1.40 fiecare (≥ 70%), combinația cu cea mai mare șansă. Pe istoric: 60% pași câștigați, record 13 — serii mai scurte decât la 1.20 și 1.40. Reinvestești tot; încasarea e doar propusă.',
    lost: 'Mâine Piramida 1.60 reîncepe de la treapta 1.' },
  boost: { eyebrow: 'Cote mărite Superbet · EV pozitiv', title: 'Piramida Cote mărite',
    text: 'Un singur pariu pe zi: caută întâi o cotă mărită obișnuită cu EV pozitiv și șansă cât mai mare (1.25–3.20); dacă nu există, încearcă Super Cota doar ca rezervă și numai dacă trece filtrele. Graficul folosește media cotelor efective decontate din această pistă, nu ținta nominală 2.00. Istoricul este scurt și trebuie interpretat prudent; fără candidat potrivit, ziua este pauză.',
    lost: 'Mâine Piramida Cote mărite reîncepe de la treapta 1.' },
  mici: { eyebrow: 'Cotă în jur de 2.00', title: 'Piramida 2.00 Ligi mici',
    text: 'Favoriți din League One, League Two și National League. Reinvestești tot. După 7 câștiguri încasezi tot. După o pierdere reiei de la treapta 1.',
    lost: 'Mâine Piramida Ligi mici reîncepe de la treapta 1.' },
  r5: { eyebrow: 'Riscant · cotă în jur de 5', title: 'Piramida ~5',
    text: 'Din 25.10: 2–4 selecții, fiecare cu cota de cel puțin 1.40, EV realist ≥ −3% (altfel nu se publică), fără meciuri cu start între 00:00 și 07:00 ora României; cota totală ~5, câte una pe meci și pe ligă. Pornești cu 2 lei din bugetul săptămânal și reinvestești; încasarea e doar propusă. După o pierdere evită familia de piață pierdută și reia cu 2 lei. Niciodată mize mai mari după pierderi.',
    lost: 'Mâine Piramida ~5 se reorganizează și reia cu 2 lei.' },
  r10: { eyebrow: 'Riscant · cotă în jur de 10', title: 'Piramida ~10',
    text: 'Din 25.10: 2–4 selecții, fiecare cu cota de cel puțin 1.40, EV realist ≥ −3% (altfel nu se publică), fără meciuri cu start între 00:00 și 07:00 ora României; cota totală ~10, câte una pe meci și pe ligă. Pornești cu 2 lei; încasarea e doar propusă. După o pierdere se reorganizează și reia cu 2 lei. Niciodată mize mai mari după pierderi.',
    lost: 'Mâine Piramida ~10 se reorganizează și reia cu 2 lei.' },
  r100: { eyebrow: 'Experimental · pe hârtie · 5 pași la ~2.5', title: 'Piramida 100+',
    text: 'Un bilet pe zi la cota ~2.5 din cele mai mici cote la Gazdele 1-3 goluri și Cartonașe Sub 4.5/5.5 (cota Superbet), câte una pe meci, fără ligile slabe și fără meciuri de noapte. Reinvestești tot 5 pași (2 lei → ~200+ lei); după o pierdere reiei cu 2 lei. Doar urmărire până avem rezultate live.',
    lost: 'Mâine Piramida 100+ reia cu 2 lei de la treapta 1.' },
  mix140: { eyebrow: 'Cotă 1.35–1.45 · Robot + Supersocial', title: 'Piramida Mix 1.40',
    text: 'O selecție cu probabilitate prudentă ridicată; numai cote Superbet reale. Amestecă piețele principale ale Robotului cu selecții Supersocial doar dacă există minimum 100 de rezultate istorice și lift de cel puțin 1.00. Praguri mai stricte decât pista veche; dacă nu există combinație suficient de bună, ziua rămâne pauză. Miza de start implicită este 2 lei și nu crește după pierdere.',
    lost: 'Mâine seria Mix 1.40 reîncepe de la treapta 1.' },
  mix25: { eyebrow: 'Risc ridicat · cotă 2.50–3.125 · 5 pași', title: 'Piramida Mix 2.5×5',
    text: 'Ținta de cotă rămâne ~2.5 pe pas. Combină piețele Robotului (1X2, egal returnat, GG) cu Supersocial doar pe piețe cu cel puțin 100 de rezultate și lift ≥1.00; maximum 4 selecții, din meciuri și familii diferite, maximum 2 pe ligă. Folosește cote Superbet reale și probabilitate prudentă; publică bilet numai la șansă estimată ≥42% și EV estimat ≥+2%. Dacă nu trece filtrul, este pauză, nu forțăm. Miza de start implicită: 2 lei; fără martingale. Câștigurile și șansa nu sunt garantate.',
    lost: 'Seria Mix 2.5×5 reîncepe de la treapta 1 cu miza ta de start.' },
};
type P100Tp = { steps: number; p_complete: number; multiplier: number; roi_cycle: number; payout_2lei: number; weeks_to_complete: number | null; reach: number[] };
type P100St = { n: number; w: number; wr: number; roi: number; odds: number; legs: number; days: number } | null;
type P100Bt = { rule: string; from: string; to: string; split: string; legs_pool: number; verdict: string;
  targets: { target: number; train: P100St; test: P100St; step_roi_ci90: [number, number]; days_with_ticket: number; take_profit: P100Tp[] }[] };
function P100Backtest({ bt }: { bt?: P100Bt | null }) {
  if (!bt?.targets) return null;
  const main = bt.targets.find((t) => t.target === 2.5) ?? bt.targets[0];
  const tp5 = main.take_profit.find((x) => x.steps === 5);
  return (
    <Card className="p-4">
      <h2 className="mb-1 font-semibold">Backtest walk-forward ({bt.from} → {bt.to})</h2>
      <p className="mb-2 text-[11px] text-muted-foreground">Reguli fixate pe zilele până la {bt.split}, testate după. {bt.legs_pool} selecții la cota Superbet urmărită.</p>
      {tp5 && (
        <div aria-label="Șansa de a ajunge la fiecare treaptă" className="mb-3">
          <div className="mb-1 text-xs font-semibold">Ținta 2.5 · șansa de a trece fiecare treaptă</div>
          <div className="flex items-end gap-2">{tp5.reach.map((p, i) => (
            <div key={i} className="flex min-w-0 flex-1 flex-col items-center justify-end gap-1">
              <span className="num text-[10px] font-bold">{(p * 100).toFixed(p < 0.1 ? 1 : 0)}%</span>
              <div className="w-full rounded-t-md bg-[hsl(var(--primary))]" style={{ height: `${Math.max(3, Math.round(p * 150))}px` }} />
              <span className="num text-center text-[10px] leading-tight text-muted-foreground">T{i + 1}<br />×{(Math.pow(tp5.multiplier, (i + 1) / 5)).toFixed(0)}</span>
            </div>))}
          </div>
        </div>
      )}
      <table className="w-full text-xs">
        <thead><tr className="text-muted-foreground"><th className="py-1 text-left font-medium">Țintă</th><th className="text-right font-medium">Pas test</th><th className="text-right font-medium">ROI pas</th><th className="text-right font-medium">5 pași</th><th className="text-right font-medium">Săpt.</th></tr></thead>
        <tbody>{bt.targets.map((t) => { const k5 = t.take_profit.find((x) => x.steps === 5); return (
          <tr key={t.target} className="border-t"><td className="py-1.5">~{t.target}</td><td className="text-right num">{t.test ? `${t.test.w}/${t.test.n}` : '—'}</td>
            <td className="text-right num">{t.test ? pct(t.test.roi) : '—'}</td><td className="text-right num">{k5 ? `${(k5.p_complete * 100).toFixed(1)}% ×${k5.multiplier.toFixed(0)}` : '—'}</td>
            <td className="text-right num">{k5?.weeks_to_complete ?? '—'}</td></tr>); })}
        </tbody>
      </table>
      <p className="mt-2 text-[11px] text-muted-foreground">{bt.verdict}</p>
    </Card>
  );
}

type MiciBt = { train: { days: number; win_rate: number; runs: number; net: number; roi_pct: number }; test: { days: number; win_rate: number; avg_odds: number; runs: number; staked: number; returned: number; net: number; roi_pct: number; max_steps: number; cashouts_at_7: number }; note?: string };
function MiciBacktest({ bt }: { bt?: MiciBt | null }) {
  if (!bt?.test) return null;
  const t = bt.test;
  return (
    <Card className="p-4">
      <h2 className="mb-1 font-semibold">Backtest pe istoric (iul. 2024 → azi, 100 lei/serie)</h2>
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
        <Stat label="Pași câștigați" value={pct(t.win_rate, 0)} sub={`${t.days} zile · cotă medie ${fo(t.avg_odds)}`} />
        <Stat label="Serii" value={t.runs} sub={`${t.cashouts_at_7} încasări la pasul 7`} />
        <Stat label="Investit / încasat" value={`${lei(t.staked)}`} sub={`încasat ${lei(t.returned)}`} />
        <Stat label="Rezultat net" value={lei(t.net)} tone={t.net >= 0 ? 'win' : 'loss'} sub={`antrenare 2021–24: ${lei(bt.train.net)}`} />
      </div>
      {bt.note && <p className="mt-2 text-[11px] text-muted-foreground">{bt.note}</p>}
    </Card>
  );
}

export function BacktestCard({ bt, title = '1.40' }: { bt?: PyramidBacktest | null; title?: string }) {
  if (!bt?.distribution?.length) return null;
  const reach = bt.reach_probability ?? {};
  const mx = Math.max(1, ...bt.distribution.map((d) => d.runs));
  return (
    <Card className="p-4">
      <h2 className="mb-1 font-semibold">Backtest {title} pe istoric</h2>
      <p className="mb-3 text-xs text-muted-foreground">{bt.days} zile de joc ({bt.from} → {bt.to}), football-data, aceleași reguli ca Robotul: cea mai mare șansă comună în banda de cotă, corectată cu cât a intrat fiecare piață până în ziua aceea.</p>
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
        <Stat label="Pași câștigați" value={pct(bt.win_rate ?? 0, 1)} sub={`cotă medie ${fo(bt.avg_odds ?? 0)} · ${bt.avg_legs} sel.`} />
        <Stat label="Pași / serie (medie)" value={bt.avg_steps ?? '—'} sub={`mediană ${bt.median_steps ?? '—'}`} />
        <Stat label="Cea mai lungă serie" value={bt.max_steps ?? '—'} sub={`${bt.runs} serii`} />
        <Stat label="Ajunge la pasul 5" value={pct(reach['5'] ?? 0, 1)} sub={`pasul 10: ${pct(reach['10'] ?? 0, 1)} · 17: ${pct(reach['17'] ?? 0, 1)} · 20: ${pct(reach['20'] ?? 0, 1)}`} />
      </div>
      <div className="mt-3 space-y-1" aria-label="Distribuția seriilor">
        {bt.distribution.map((d) => (
          <div key={String(d.steps)} className="flex items-center gap-2 text-xs">
            <span className="num w-10 text-right text-muted-foreground">{d.steps} p.</span>
            <span className="h-3 rounded bg-primary/70" style={{ width: `${(d.runs / mx) * 75}%` }} />
            <span className="num text-muted-foreground">{d.runs}</span>
          </div>
        ))}
      </div>
      {bt.bank_sim && <p className="mt-2 text-[11px] text-muted-foreground">Simulare 100 lei/serie cu retragere 50% din profit: investit {lei(bt.bank_sim.restarts_cost)}, retras {lei(bt.bank_sim.withdrawn)}, net {lei(bt.bank_sim.net)}. Marja casei se adună la fiecare pas.</p>}
    </Card>
  );
}

/** Suma scurtă pentru interiorul treptei: 2,76 · 12,8 · 245 · 1,2k */
function short(v: number): string {
  if (v >= 10000) return `${Math.round(v / 1000)}k`;
  if (v >= 1000) return `${(v / 1000).toFixed(1).replace('.', ',')}k`;
  if (v >= 100) return String(Math.round(v));
  if (v >= 10) return v.toFixed(1).replace('.', ',');
  return v.toFixed(2).replace('.', ',');
}

function StepBars({ current, p, n = 8, money }: { current: number; p: number; n?: number; money?: (k: number) => number | null }) {
  const base = Math.min(0.97, Math.max(0.05, p));
  const bars = Array.from({ length: n }, (_, i) => i + 1).map((k) => ({ k, p: Math.pow(base, k) }));
  const wide = n > 10; // piramidele lungi (20–30 de pași): bandă derulabilă cu toate treptele, centrată pe treapta curentă
  return (
    <>
      <div className={cn('mt-5', wide && '-mx-1 overflow-x-auto px-1 pb-1')} ref={(el) => {
        if (el && wide) { const li = el.querySelector<HTMLElement>(`[data-step="${current}"]`); if (li) el.scrollLeft = li.offsetLeft - el.clientWidth / 2 + li.clientWidth / 2; }
      }}>
        <ol className="grid items-end gap-1.5" style={{ gridTemplateColumns: wide ? `repeat(${n}, 30px)` : `repeat(${n}, minmax(0, 1fr))` }} aria-label="Treptele piramidei">
          {bars.map(({ k, p: chance }) => {
            const on = k === current, done = k < current;
            return (
              <li key={k} data-step={k} className="flex flex-col items-center gap-1">
                <span className="num text-[10px] text-muted-foreground">{chance >= 0.995 ? '' : chance < 0.01 ? '<1%' : pct(chance)}</span>
                <span className={cn('pyr-step flex w-full items-start justify-center overflow-hidden rounded-t-lg pt-1', done ? 'pyr-done' : on ? 'pyr-on' : '')} style={{ height: `${30 + Math.min(k, 12) * 7}px` }}>
                  {(() => { const v = money?.(k); return done ? <span className="text-[10px] font-bold text-foreground/80">✓</span> : v != null && v > 0 ? <span className={cn('num text-[9px] font-bold leading-none', on ? 'text-white' : 'text-win')}>{short(v)}</span> : null; })()}
                </span>
                <span className={cn('num text-[11px] font-bold', on ? 'text-primary' : 'text-muted-foreground')}>{k}</span>
              </li>
            );
          })}
        </ol>
      </div>
      <p className="mt-1 text-center text-[11px] text-muted-foreground">Treapta curentă: <b className="text-foreground">{current}</b> din {n} · deasupra: șansa de a ajunge acolo{money ? ' · în treaptă: cât ai dacă o câștigi (lei)' : ''}</p>
    </>
  );
}

export default function Pyramid140View({ track = '1.40' }: { track?: Track }) {
  const api = useP140(track);
  const cp = COPY[track];
  const [myStartRaw, setMyStart] = useMyStart(track);
  const [myBase, setMyBase] = useMyBase(track);
  const [myWd, setMyWd] = useMyWd(track);
  if (api.loading) return <Loading />;
  const d = api.data;
  const expected = track;
  if (d?.track && d.track !== expected) return <Loading />;
  if (!d) return <Notice>{cp.title} pornește la următoarea rulare a robotului.</Notice>;
  const main = d.today?.status === 'pick' ? d.today.main : null;
  const paper = (d.rules as { paper?: boolean } | undefined)?.paper === true;
  // pe hârtie: miza e a regulii (start 2 lei, reinvestit), nu miza ta — un singur număr peste tot
  const myStart = paper ? Number((d.rules as unknown as { start_bank?: number }).start_bank ?? 2) : myStartRaw;
  const run = d.run;
  const restart = !run || run.status === 'lost' || run.status === 'completed';
  // treapta biletului de azi (aceeași ca în „Ce faci azi”); fără bilet azi: următoarea treaptă a seriei
  const robotStep = (d.action?.step as number | null | undefined) ?? (restart ? 1 : (run!.step ?? 0) + 1);
  const startBank = (d.rules as unknown as { start_bank?: number }).start_bank ?? 100;
  const bank = restart ? startBank : run!.bank ?? startBank;
  // seria mea: dacă am pornit de la treapta 1 într-o zi (și seria Robotului nu s-a rupt de atunci), număr de acolo
  const base = myBase && !restart && run?.id === myBase.run && robotStep >= myBase.step ? myBase : null;
  const step = base ? robotStep - base.step + 1 : robotStep;
  const ref = base ? base.bank : (run?.start_bank || startBank);
  // miza mea de azi: miza mea de start × cât a crescut seria de când am pornit (aceleași bilete, aceeași reinvestire)
  // „Sunt la treapta N cu X lei”: suma mea de atunci crește la fel cu seria Robotului
  const gross = base?.amount ? base.amount * (bank / base.bank) : myStart * (bank / ref);
  // retragerile mele din seria curentă: fiecare scade din bani cât ar fi crescut suma retrasă de atunci încoace
  const wds = !restart && run?.id != null ? myWd.filter((w) => w.run === run.id && (!base || w.bank >= base.bank)) : [];
  const out = wds.reduce((a, w) => a + w.amount * (bank / w.bank), 0);
  const mine = Math.max(0, gross - out);
  const withdrawn = wds.reduce((a, w) => a + w.amount, 0);
  const boostSettledOdds = track === 'boost' ? (d.history ?? [])
    .filter((row) => row.status === 'pick' && (row.result === 'won' || row.result === 'lost') && Number(row.odds) > 1)
    .map((row) => Number(row.odds)) : [];
  const boostRealizedAvg = boostSettledOdds.length
    ? boostSettledOdds.reduce((sum, value) => sum + value, 0) / boostSettledOdds.length : null;
  const avgOdds = (d.backtest as PyramidBacktest | undefined)?.avg_odds
    || (track === 'boost' ? boostRealizedAvg : null)
    || main?.total_odds
    || Number((d.rules as { target_odds?: number } | undefined)?.target_odds)
    || 1.4;
  const money = (k: number) => (k < step ? null : mine * (main?.total_odds ?? avgOdds) * Math.pow(avgOdds, k - step));
  const nSteps = Math.min(30, Math.max(1, Number((d.rules as { max_steps?: number } | undefined)?.max_steps) || (track === 'r5' || track === 'r100' ? 5 : track === 'r10' ? 4 : track === '1.20' ? 30 : track === '1.40' ? 20 : track === '1.60' ? 15 : track === 'boost' ? 10 : 9)));
  return (
    <div className="space-y-5">
      <section className="page-hero">
        <div className="flex items-end justify-between gap-3">
          <div className="min-w-0">
            <div className="eyebrow">{cp.eyebrow}</div>
            <h1 className="mt-1 text-[22px] leading-tight">{cp.title}</h1>
          </div>
          <div className="slip-odds shrink-0 rounded-2xl px-3 py-2 text-center">
            <div className="text-[10px] font-extrabold uppercase tracking-wider text-primary-foreground/75">Azi</div>
            <div className="num text-[28px] font-extrabold leading-none text-primary-foreground">{main ? fo(main.total_odds) : 'Pauză'}</div>
          </div>
        </div>
        <div className="mt-4 grid grid-cols-3 gap-2 text-center">
          <div className="pyr-tile pyr-a rounded-xl bg-[hsl(var(--elevated))] px-1.5 py-2"><div className="text-[10px] font-bold uppercase text-muted-foreground">Treapta</div><div className="num mt-0.5 whitespace-nowrap text-base font-extrabold">{step}</div></div>
          <div className="pyr-tile pyr-b rounded-xl bg-[hsl(var(--elevated))] px-1.5 py-2"><div className="text-[10px] font-bold uppercase text-muted-foreground">{paper ? 'Miză pe hârtie' : 'Miza ta azi'}</div><div className="num mt-0.5 whitespace-nowrap text-base font-extrabold">{main ? leiRo(mine) : '—'}</div></div>
          <div className="pyr-tile pyr-c rounded-xl bg-[hsl(var(--elevated))] px-1.5 py-2"><div className="text-[10px] font-bold uppercase text-muted-foreground">Dacă intră</div><div className={cn('num mt-0.5 whitespace-nowrap text-base font-extrabold', main ? 'text-win' : 'text-muted-foreground')}>{main ? leiRo(mine * main.total_odds) : 'pauză'}</div></div>
        </div>
        <StepBars current={step} n={nSteps} money={mine > 0 ? money : undefined} p={main?.p_ticket ?? (track === 'mici' ? (d.backtest as MiciBt | undefined)?.test?.win_rate : (d.backtest as PyramidBacktest | undefined)?.win_rate) ?? (track === '1.20' ? 0.82 : track === '1.40' ? 0.7 : track === '1.60' ? 0.62 : track === 'boost' ? 0.6 : track === 'r5' ? 0.2 : track === 'r100' ? 0.48 : track === 'r10' ? 0.1 : track === 'mix140' ? 0.66 : track === 'mix25' ? 0.42 : 0.5)} />
        {track === 'boost' && <p className="mt-1 text-center text-[11px] text-muted-foreground">Proiecția folosește {boostRealizedAvg != null ? `media cotelor efective ${fo(boostRealizedAvg)} din ${boostSettledOdds.length} bilete câștigate/pierdute` : main ? `cota efectivă a biletului de azi (${fo(main.total_odds)})` : `ținta 2.00 până există bilete decontate`}.</p>}
      </section>
      <div className="card px-4 py-3">
        {paper ? <p className="text-center text-[11px] text-muted-foreground">Pe hârtie: pornește cu {leiRo(myStart)} (regula de repornire), reinvestește tot; la treapta {step} miza e {leiRo(mine)}. Nu folosește bugetul tău.</p> : <><StartField value={myStart} onChange={setMyStart} />
        <p className="mt-1 text-center text-[11px] text-muted-foreground">Miza ta urmează seria Robotului: la treapta {step} pui {leiRo(mine)}{step > 1 ? ` (start ${leiRo(myStart)} × ${(bank / ref).toFixed(2)}${withdrawn > 0 ? ', minus ce ai retras' : ''})` : ''}. După o pierdere reiei cu miza de start. Piramida are {nSteps} trepte{nSteps > 10 ? ' (glisează treptele de sus ca să le vezi pe toate)' : ''}.</p></>}
        {!restart && run?.id != null && step > 1 && mine > 0 && <WithdrawField max={mine} onWithdraw={(v) => setMyWd([...myWd.filter((w) => w.run === run.id), { run: run.id!, bank, amount: v, date: d.date }])} />}
        {withdrawn > 0 && <p className="mt-1 text-center text-[11px] text-win">Ai retras {leiRo(withdrawn)} din seria asta{mine > 0 ? `; pe treapta ${step} rămân în joc ${leiRo(mine)}` : ' — ai retras tot, seria ta s-a încheiat'}. <button type="button" className="font-semibold text-primary" onClick={() => setMyWd(myWd.filter((w) => w.run !== run?.id))}>Șterge retragerile</button></p>}
        {!restart && run?.id != null && (base
          ? <p className="mt-1 text-center text-[11px] text-muted-foreground">{base.amount ? `Seria ta: setată pe ${base.date} cu ${leiRo(base.amount)} în joc; de atunci crește cu seria Robotului.` : `Seria ta a pornit pe ${base.date} (treapta ${base.step} a Robotului).`} <button type="button" className="font-semibold text-primary" onClick={() => setMyBase(null)}>Anulează</button></p>
          : <>
            {robotStep > 1 && <div className="mt-2 text-center"><button type="button" className="btn h-9 px-3 text-xs" onClick={() => setMyBase({ run: run.id!, step: robotStep, bank, date: d.date })}>Încep de azi de la treapta 1</button></div>}
            {!paper && <MyStepField def={myStart} onSet={(u, amount) => setMyBase({ run: run.id!, step: robotStep - u + 1, bank, date: d.date, amount })} />}
          </>)}
        <Record d={d} track={track} />
      </div>
      <ActionCard a={(d as unknown as { action?: PyrAction }).action} scale={bank > 0 ? mine / bank : myStart / ref} stepShift={base ? base.step - 1 : 0} />
      <section>
        <SectionTitle title="Biletul de azi" />
        {!main ? <Notice tone="warn">{d.today?.reason ?? 'Azi fără bilet.'}</Notice>
          : isLostTicket(main) ? <Notice>Biletul de azi a pierdut. {cp.lost}</Notice> : <>{track === 'r100' && d.today?.reason && <p className="mb-2 text-xs text-muted-foreground">{d.today.reason}</p>}<PriceNote ev={main.ev} /><TicketCard t={main} /></>}
      </section>
      {track === 'mici' ? <MiciBacktest bt={d.backtest as unknown as MiciBt} /> : track === 'r100' ? <P100Backtest bt={d.backtest as unknown as P100Bt} /> : track === 'r5' || track === 'r10' ? <RiskBacktest bt={d.backtest as unknown as RiskBt} /> : <BacktestCard bt={d.backtest} title={track} />}
      <GridCard grid={(d as unknown as { grid?: PyramidGrid }).grid} />
      <Card className="overflow-hidden">
        <h2 className="p-3 font-semibold">Serii (run-uri)</h2>
        <table className="w-full text-sm"><thead className="text-xs text-muted-foreground"><tr><th className="px-3 py-1 text-left">#</th><th className="text-left">Perioadă</th><th className="text-right">Pași</th><th className="px-3 text-right">Retras</th></tr></thead>
          <tbody>{(d.runs ?? []).map((r) => (
            <tr key={r.id} className="border-t"><td className="px-3 py-1.5">{r.id}</td><td className="text-xs text-muted-foreground">{r.start_date} → {r.end_date ?? 'acum'}</td><td className="text-right">{r.steps}</td><td className="px-3 text-right">{lei(r.withdrawn ?? 0)}</td></tr>
          ))}</tbody></table>
        {!(d.runs ?? []).length && <p className="p-3 text-xs text-muted-foreground">Prima serie începe cu primul bilet.</p>}
      </Card>
    </div>
  );
}

/** Recordul piramidei: cei mai mulți pași câștigați la rând (live), față de backtest și de recordul tău. */
const MY_RECORD: Partial<Record<Track, string>> = { '1.40': 'recordul tău manual: 17', '1.20': 'ținta: peste 20 la rând' };
function Record({ d, track }: { d: { record?: { steps: number; since?: string | null }; backtest?: unknown }; track: Track }) {
  const rec = d.record?.steps ?? 0;
  const bt = (d.backtest as PyramidBacktest | undefined)?.max_steps;
  return (
    <p className="mt-2 flex flex-wrap items-center justify-center gap-x-3 gap-y-1 text-[11px] text-muted-foreground">
      <span>🏆 Record live: <b className="text-foreground">{rec} {rec === 1 ? 'pas' : 'pași'}</b>{d.record?.since ? ` (serie din ${d.record.since})` : ''}</span>
      {bt ? <span>backtest: <b className="text-foreground">{bt}</b></span> : null}
      {MY_RECORD[track] ? <span>{MY_RECORD[track]}</span> : null}
    </p>
  );
}

export function Pyramid140Stats({ track = '1.40' }: { track?: Track }) {
  const api = useP140(track);
  const d = api.data;
  const expected = track;
  if (api.loading || (d?.track && d.track !== expected)) return <Loading />;
  if (!d) return <Notice>Încă nu există date pentru {COPY[track].title}.</Notice>;
  const h = d.history ?? [];
  const won = h.filter((x) => x.result === 'won').length, lost = h.filter((x) => x.result === 'lost').length;
  return (
    <div className="space-y-3">
      <div className="grid grid-cols-2 gap-2 sm:gap-3 lg:grid-cols-4">
        <Stat label="Zile urmărite" value={h.length} sub={`${h.filter((x) => x.status === 'pick').length} cu bilet`} />
        <Stat label="Pași" value={`${won} / ${lost}`} sub="câștigați / pierduți" />
        <Stat label="Serii" value={(d.runs ?? []).length} sub={`cel mai bun pas: ${Math.max(0, ...(d.runs ?? []).map((r) => r.steps ?? 0))}`} />
        <Stat label="Total retras" value={lei((d.runs ?? []).reduce((s, r) => s + (r.withdrawn ?? 0), 0))} />
      </div>
      <Card className="overflow-hidden"><table className="w-full text-sm"><tbody>{h.slice(0, 60).map((r) => (
        <tr key={r.date} className="border-t"><td className="px-3 py-1.5 text-xs">{r.date}</td><td className="text-right">{r.odds ? fo(r.odds) : '—'}</td><td className="text-right">{r.p != null ? pct(r.p) : ''}</td>
          <td className="px-3 text-right"><Badge tone={r.result === 'won' ? 'win' : r.result === 'lost' ? 'loss' : 'muted'}>{r.status === 'no_bet' ? 'pauză' : r.result === 'won' ? 'câștigat' : r.result === 'lost' ? 'pierdut' : 'în curs'}</Badge></td></tr>
      ))}</tbody></table></Card>
      {track === 'mici' ? <MiciBacktest bt={d.backtest as unknown as MiciBt} /> : track === 'r100' ? <P100Backtest bt={d.backtest as unknown as P100Bt} /> : track === 'r5' || track === 'r10' ? <RiskBacktest bt={d.backtest as unknown as RiskBt} /> : <BacktestCard bt={d.backtest} title={track} />}
    </div>
  );
}

type GridRow = { markets: string; real_prices: boolean; leagues: string; drift_filter: boolean; min_leg_p: number; max_legs: number; withdraw: number; label?: string;
  test: { days: number; win_rate: number | null; max_step: number; reach: Record<string, number>; roi_pct: number; flat_roi_pct: number | null; avg_odds: number | null } };
export type PyramidGrid = { matches: number; split: string; tested: number; both_positive: number; baseline?: GridRow | null; top: GridRow[]; verdict?: string };
const MK: Record<string, string> = { '1x2_fav': 'Favoriți 1X2', ou25_real: 'Peste/Sub 2.5', real_mix: '1X2 + O/U 2.5', sansa_dubla: 'Șansă dublă', 'peste_0.5_1.5': 'Peste 0.5/1.5', 'sub_3.5_4.5': 'Sub 3.5/4.5', mix_tot: 'Mix toate' };
const LG: Record<string, string> = { toate: 'toate ligile', top: 'ligi top', liga2: 'ligi 2', altele: 'ligi mici' };

export function GridCard({ grid }: { grid?: PyramidGrid | null }) {
  if (!grid?.top) return null;
  const rows = [...(grid.baseline ? [{ ...grid.baseline, label: 'Regula live' }] : []), ...grid.top];
  return (
    <Card className="overflow-hidden p-0">
      <div className="p-3"><h2 className="font-semibold">Variante testate ({grid.tested})</h2>
        <p className="text-xs text-muted-foreground">{grid.matches.toLocaleString('ro-RO')} meciuri; variantele alese pe 2021–2024, rezultatele de mai jos pe perioada de test ({grid.split} → azi). * = cote modelate, nu reale.</p></div>
      <div className="overflow-x-auto"><table className="w-full whitespace-nowrap text-xs">
        <thead className="text-muted-foreground"><tr><th className="px-3 text-left">Variantă</th><th className="text-right">Pași câșt.</th><th className="text-right">Max</th><th className="text-right">≥3 / 5 / 7 / 10 / 15</th><th className="text-right">ROI fix</th><th className="px-3 text-right">ROI piramidă</th></tr></thead>
        <tbody>{rows.map((r, i) => (
          <tr key={i} className={cn('border-t', r.label && 'bg-[hsl(var(--elevated))]')}>
            <td className="px-3 py-1.5">{r.label ? <b>{r.label}: </b> : null}{MK[r.markets] ?? r.markets}{r.real_prices ? '' : '*'} · {LG[r.leagues] ?? r.leagues} · ≥{Math.round(r.min_leg_p * 100)}% · max {r.max_legs} · {r.drift_filter ? 'fără cote în creștere' : 'orice cotă'} · retras {Math.round(r.withdraw * 100)}%</td>
            <td className="num text-right">{pct(r.test.win_rate ?? 0, 0)}</td><td className="num text-right">{r.test.max_step}</td>
            <td className="num text-right">{['3', '5', '7', '10', '15'].map((k) => pct(r.test.reach[k] ?? 0, 0)).join(' / ')}</td>
            <td className={cn('num text-right', (r.test.flat_roi_pct ?? 0) >= 0 ? 'text-win' : 'text-loss')}>{(r.test.flat_roi_pct ?? 0) > 0 ? '+' : ''}{r.test.flat_roi_pct}%</td>
            <td className={cn('num px-3 text-right', r.test.roi_pct >= 0 ? 'text-win' : 'text-loss')}>{r.test.roi_pct > 0 ? '+' : ''}{r.test.roi_pct}%</td></tr>
        ))}</tbody></table></div>
      {grid.verdict && <p className="p-3 text-xs text-muted-foreground">{grid.verdict}</p>}
    </Card>
  );
}
