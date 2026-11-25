import { useState } from 'react';
import { ShieldCheck } from 'lucide-react';
import type { Ticket } from '@/lib/types';
import { plainPick } from '@/lib/markets';
import { useStore } from '@/lib/store';

type Leg = Ticket['legs'][number];

// marja Superbet pe o selecție la cota live (~5%): cota live spune șansa, după ce scoatem marja
const LIVE_MARGIN = 0.95;
const isDone = (l: Leg) => l.result === 'won' || l.result === 'void' || l.result === 'half_won';

/** Rezultatul opus pe care îl poți juca pe Superbet ca să acoperi selecția rămasă (null = nu există unul singur). */
export function opposite(l: Leg): string | null {
  const s = l.selection;
  if (l.market === 'ss') {
    if (s === 'H1U15') return 'Prima repriză – Total goluri: Peste 1.5';
    if (s === 'H1U05') return 'Prima repriză – Total goluri: Peste 0.5';
    if (s === 'H2G13') return 'A doua repriză – Interval goluri: 0 sau 4+ (două pariuri)';
    if (s === 'H2G12') return 'A doua repriză – Interval goluri: 0 sau 3+ (două pariuri)';
    return null;
  }
  if (l.market === '1x2') return s === 'HOME' ? 'Șansă dublă X2' : s === 'AWAY' ? 'Șansă dublă 1X' : 'Șansă dublă 12';
  if (l.market === 'double_chance') return s === '1X' ? '2 (oaspeții câștigă)' : s === 'X2' ? '1 (gazdele câștigă)' : 'X (egal)';
  if (l.market === 'over_under' && l.line != null) return `Total goluri: ${s === 'OVER' ? 'Sub' : 'Peste'} ${l.line}`;
  if (l.market === 'btts') return s === 'YES' ? 'Ambele marchează: Nu (NG)' : 'Ambele marchează: Da (GG)';
  return null;
}

/** Calcule pure (testabile): cât valorează biletul acum și cât pui pe rezultatul opus ca să iei sigur bani. */
export function insureMath(payout: number, liveOdds: number[], cashOffer: number | null, oppOdds: number | null, stake: number) {
  const pNow = liveOdds.reduce((a, o) => a * Math.min(1, LIVE_MARGIN / Math.max(1.01, o)), 1);
  const value = payout * pNow;
  const cash = cashOffer != null && cashOffer > 0 ? { offer: cashOffer, better: cashOffer >= value, diff: cashOffer - value } : null;
  // acoperire pe ultima selecție: H pe opus la cota o, H = payout / o → dacă selecția intră primești payout, dacă pică H·o = payout;
  // în ambele cazuri rămâi cu payout − H
  let hedge: { h: number; sure: number; net: number } | null = null;
  if (oppOdds && oppOdds > 1 && liveOdds.length === 1) {
    const h = payout / oppOdds;
    const sure = payout - h; // ce primești sigur (net de pariul de acoperire), oricum se termină
    hedge = { h, sure, net: sure - stake };
  }
  return { pNow, value, cash, hedge };
}

const lei = (x: number) => `${x.toLocaleString('ro-RO', { maximumFractionDigits: x >= 100 ? 0 : 2 })} lei`;

/** „Asigură câștigul”: la un bilet căruia îi mai rămân 1–3 selecții (și n-a pierdut nimic) — merită cash out-ul? cât pui pe opus? */
export function InsurePanel({ t }: { t: Ticket }) {
  const defStake = useStore((s) => s.settings.defaultStake);
  const open = t.legs.filter((l) => !isDone(l));
  const lost = t.legs.some((l) => l.result === 'lost' || l.result === 'half_lost');
  const [show, setShow] = useState(false);
  const [stake, setStake] = useState<number>(t.stake ?? defStake ?? 2);
  const [live, setLive] = useState<Record<number, string>>({});
  const [cash, setCash] = useState('');
  const [opp, setOpp] = useState('');
  if (t.status !== 'pending' || lost || open.length < 1 || open.length > 3 || t.legs.length < 3) return null;
  const bonus = t.superbonus ?? 0;
  const payout = stake * (t.total_odds + bonus * (t.total_odds - 1));
  const liveOdds = open.map((l, i) => Number((live[i] ?? '').replace(',', '.')) || l.odds);
  const m = insureMath(payout, liveOdds, Number(cash.replace(',', '.')) || null, Number(opp.replace(',', '.')) || null, stake);
  const last = open.length === 1 ? open[0] : null;
  const opText = last ? opposite(last) : null;
  return (
    <div className="mx-4 mb-3 rounded-2xl border border-[hsl(var(--win)/0.4)] bg-[hsl(var(--win)/0.08)] p-3 text-xs">
      <button type="button" className="flex w-full items-center justify-between gap-2 text-left" onClick={() => setShow(!show)} aria-expanded={show}>
        <span className="flex items-center gap-1.5 text-sm font-extrabold text-win"><ShieldCheck className="h-4 w-4" />Asigură câștigul</span>
        <span className="text-muted-foreground">{open.length === 1 ? 'mai e 1 selecție' : `mai sunt ${open.length} selecții`} · {show ? 'ascunde' : 'deschide'}</span>
      </button>
      {show && (
        <div className="mt-2 space-y-2.5">
          <label className="flex items-center justify-between gap-2">Miza ta (lei)
            <input inputMode="decimal" className="input h-9 w-24 text-right" value={stake} onChange={(e) => setStake(Number(e.target.value.replace(',', '.')) || 0)} />
          </label>
          <div className="text-muted-foreground">Dacă intră tot: <b className="text-foreground">{lei(payout)}</b>{bonus ? ` (cu SuperBonus ${Math.round(bonus * 100)}%)` : ''}</div>
          {open.map((l, i) => (
            <label key={`${l.match_id}-${l.selection}`} className="flex items-center justify-between gap-2">
              <span className="min-w-0 flex-1"><span className="block truncate font-semibold">{plainPick(l.market, l.line, l.selection, l.label)}</span>
                <span className="block truncate text-muted-foreground">{l.home} – {l.away} · cota acum pe Superbet:</span></span>
              <input inputMode="decimal" placeholder={l.odds.toFixed(2)} className="input h-9 w-20 text-right" value={live[i] ?? ''} onChange={(e) => setLive({ ...live, [i]: e.target.value })} />
            </label>
          ))}
          <div className="rounded-xl bg-background/60 px-3 py-2">
            Biletul valorează acum ~<b className="text-foreground">{lei(m.value)}</b> <span className="text-muted-foreground">(șansă ~{Math.round(m.pNow * 100)}% să intre tot)</span>
            <div className="mt-0.5 text-[11px] text-muted-foreground">Scrie cota live a selecției rămase (din meciul live pe Superbet) ca să fie exact.</div>
          </div>
          <label className="flex items-center justify-between gap-2">Cash out oferit de Superbet (lei)
            <input inputMode="decimal" className="input h-9 w-24 text-right" value={cash} onChange={(e) => setCash(e.target.value)} />
          </label>
          {m.cash && (
            <p className={m.cash.better ? 'font-bold text-win' : 'font-bold text-warn'}>
              {m.cash.better ? `Ia cash out-ul: e cu ${lei(m.cash.diff)} peste cât valorează biletul acum.` : `Ține biletul: cash out-ul e cu ${lei(-m.cash.diff)} sub valoarea lui.`}
            </p>
          )}
          {last && (
            <>
              <div className="pt-1 font-semibold">Sau acoperă ultima selecție pe Superbet{opText ? <>: <span className="text-primary">{opText}</span></> : ''}</div>
              {opText ? (
                <label className="flex items-center justify-between gap-2">Cota rezultatului opus
                  <input inputMode="decimal" className="input h-9 w-24 text-right" value={opp} onChange={(e) => setOpp(e.target.value)} />
                </label>
              ) : <p className="text-muted-foreground">Selecția asta n-are un singur rezultat opus pe Superbet: folosește cash out-ul.</p>}
              {m.hedge && (
                <p className="rounded-xl bg-background/60 px-3 py-2">
                  Pune <b className="text-foreground">{lei(m.hedge.h)}</b> pe opus. Oricum se termină meciul, primești <b className="text-win">{lei(m.hedge.sure)}</b>
                  {' '}(câștig sigur <b className={m.hedge.net >= 0 ? 'text-win' : 'text-loss'}>{lei(m.hedge.net)}</b> față de miza biletului).
                </p>
              )}
            </>
          )}
          <p className="text-[11px] text-muted-foreground">Calcul informativ: cota live include marja casei (~5%), pe care o scoatem. Nu plasează nimic.</p>
        </div>
      )}
    </div>
  );
}
