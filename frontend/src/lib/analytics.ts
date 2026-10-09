import type { JournalRow, StatBlock, SeriesRow, CalibrationMarket, Recommendation, PyramidHistoryRow, Ticket } from './types';
import type { Settings, Withdrawal } from './store';
import { marketTitle } from './markets';

export function block(rows: JournalRow[], key?: string, name?: string): StatBlock {
  let won = 0, lost = 0, vd = 0, pending = 0, profit = 0, so = 0, sp = 0, np = 0, brier = 0, nb = 0;
  for (const r of rows) {
    if (r.result === 'won' || r.result === 'half_won') won++;
    else if (r.result === 'lost' || r.result === 'half_lost') lost++;
    else if (r.result === 'void') vd++;
    else { pending++; continue; }
    profit += r.profit ?? 0;
    so += r.odds;
    if (r.p != null) {
      sp += r.p; np++;
      if (r.result !== 'void') { const y = r.result === 'won' || r.result === 'half_won' ? 1 : 0; brier += (r.p - y) ** 2; nb++; }
    }
  }
  const settled = won + lost + vd;
  return {
    key, name, n: settled, won, lost, void: vd, pending,
    win_rate: won + lost ? won / (won + lost) : null,
    roi_pct: settled ? (profit / settled) * 100 : null,
    profit: Math.round(profit * 100) / 100,
    avg_odds: settled ? so / settled : null,
    avg_p: np ? sp / np : null,
    brier: nb ? brier / nb : null,
  };
}

function groupBy<T>(rows: T[], f: (r: T) => string): Map<string, T[]> {
  const m = new Map<string, T[]>();
  for (const r of rows) { const k = f(r); m.set(k, [...(m.get(k) ?? []), r]); }
  return m;
}

export function series(rows: JournalRow[], by: 'day' | 'month'): SeriesRow[] {
  const g = groupBy(rows, (r) => (by === 'day' ? r.date : r.date.slice(0, 7)));
  return [...g.entries()].map(([k, v]) => ({ ...block(v, k), key: k })).filter((r) => r.n > 0).sort((a, b) => a.key.localeCompare(b.key));
}

export function groups(rows: JournalRow[], f: (r: JournalRow) => string, label?: (k: string) => string): StatBlock[] {
  return [...groupBy(rows, f).entries()].map(([k, v]) => block(v, k, label ? label(k) : k)).filter((b) => b.n > 0).sort((a, b) => b.n - a.n);
}

export const ODDS_BANDS: Array<[number, number]> = [[1.0, 1.3], [1.3, 1.5], [1.5, 1.8], [1.8, 2.2], [2.2, 3], [3, 100]];
export function oddsBand(o: number): string {
  const b = ODDS_BANDS.find(([lo, hi]) => o >= lo && o < hi) ?? ODDS_BANDS[ODDS_BANDS.length - 1];
  return b[1] >= 100 ? `${b[0].toFixed(2)}+` : `${b[0].toFixed(2)}–${b[1].toFixed(2)}`;
}

export function calibration(rows: JournalRow[], keyOf: (r: JournalRow) => string = () => 'toate'): CalibrationMarket[] {
  const out: CalibrationMarket[] = [];
  for (const [k, v] of groupBy(rows.filter((r) => r.p != null && (r.result === 'won' || r.result === 'lost')), keyOf)) {
    const bins: CalibrationMarket['bins'] = [];
    let ece = 0;
    for (let lo = 0; lo < 1; lo += 0.1) {
      const hi = lo + 0.1;
      const b = v.filter((r) => r.p! >= lo && (r.p! < hi || (hi >= 1 && r.p! <= 1)));
      if (!b.length) continue;
      const pAvg = b.reduce((a, r) => a + r.p!, 0) / b.length;
      const hit = b.filter((r) => r.result === 'won').length / b.length;
      bins.push({ lo, hi, n: b.length, p_avg: pAvg, hit_rate: hit });
      ece += (b.length / v.length) * Math.abs(pAvg - hit);
    }
    out.push({ key: k, n: v.length, ece, healthy: v.length >= 20 && ece <= 0.08, bins });
  }
  return out.sort((a, b) => b.n - a.n);
}

export function equity(rows: JournalRow[]): Array<{ key: string; profit: number; cum: number; dd: number }> {
  const daily = series(rows, 'day');
  let cum = 0, peak = 0;
  return daily.map((d) => { cum += d.profit; peak = Math.max(peak, cum); return { key: d.key, profit: d.profit, cum: Math.round(cum * 100) / 100, dd: Math.round((cum - peak) * 100) / 100 }; });
}

/** Recomandări de îmbunătățire generate din reguli, cu eșantionul afișat. */
export function recommendations(rows: JournalRow[], extra: { tickets?: Ticket[]; withdrawals?: Withdrawal[]; pyramidRuns?: number } = {}): Recommendation[] {
  const rec: Recommendation[] = [];
  const settled = rows.filter((r) => r.result !== 'pending');
  if (settled.length < 30) rec.push({ severity: 'info', text: `Eșantion mic (${settled.length} selecții decontate). Concluziile devin solide după ~200 de selecții.`, evidence: { n: settled.length } });
  const all = block(settled);
  if (all.win_rate != null && all.roi_pct != null && all.win_rate > 0.6 && all.roi_pct < 0) {
    rec.push({ severity: 'warn', text: `Rată de câștig ${(all.win_rate * 100).toFixed(0)}%, dar ROI ${all.roi_pct.toFixed(1)}% → câștigi des, dar cotele sunt prea mici pentru riscul asumat. Crește pragul de EV pentru ancore.`, evidence: { n: all.n } });
  }
  for (const b of groups(settled, (r) => r.market, marketTitle)) {
    if (b.n < 20 || b.roi_pct == null) continue;
    if (b.roi_pct <= -8) rec.push({ severity: 'critical', text: `${b.name}: ROI ${b.roi_pct.toFixed(1)}% pe n=${b.n} → scoate piața din bilete până la recalibrare.`, evidence: { n: b.n, roi: b.roi_pct } });
    else if (b.roi_pct >= 4) rec.push({ severity: 'info', text: `${b.name}: ROI +${b.roi_pct.toFixed(1)}% pe n=${b.n} → merită pondere mai mare în bilete (verifică dacă se menține).`, evidence: { n: b.n, roi: b.roi_pct } });
  }
  for (const b of groups(settled, (r) => oddsBand(r.odds))) {
    if (b.n < 25 || b.roi_pct == null || b.win_rate == null) continue;
    if (b.roi_pct < -5) rec.push({ severity: 'warn', text: `Cote ${b.key}: rată de câștig ${(b.win_rate * 100).toFixed(0)}%, ROI ${b.roi_pct.toFixed(1)}% (n=${b.n}) → evită intervalul sau cere EV mai mare.`, evidence: { n: b.n } });
  }
  for (const c of calibration(settled, (r) => r.market)) {
    if (c.n >= 20 && (c.ece ?? 0) > 0.08) rec.push({ severity: 'warn', text: `${marketTitle(c.key)}: calibrare slabă (ECE ${(c.ece ?? 0).toFixed(2)}, n=${c.n}) → probabilitățile afișate nu se confirmă; Robotul o tratează ca piață nesigură.`, evidence: { n: c.n, ece: c.ece } });
  }
  const leagueBad = groups(settled, (r) => r.league).filter((b) => b.n >= 15 && (b.roi_pct ?? 0) < -15).slice(0, 3);
  for (const b of leagueBad) rec.push({ severity: 'warn', text: `${b.key}: ROI ${b.roi_pct!.toFixed(1)}% pe n=${b.n} → penalizează liga în bilete.`, evidence: { n: b.n } });
  if (extra.tickets?.length) {
    const done = extra.tickets.filter((t) => t.status === 'won' || t.status === 'lost');
    if (done.length >= 10 && done.every((t) => t.status === 'lost')) rec.push({ severity: 'info', text: `${done.length} bilete mari decontate, niciunul câștigător — normal statistic pentru cote 50+, dar păstrează mize mici și fixe.`, evidence: { n: done.length } });
  }
  if ((extra.pyramidRuns ?? 0) >= 3 && !(extra.withdrawals?.length)) rec.push({ severity: 'warn', text: `Ai ${extra.pyramidRuns} run-uri de piramidă fără nicio retragere manuală → activează retragerea automată după pasul 3.` });
  if (!rec.length) rec.push({ severity: 'info', text: 'Nicio problemă semnificativă detectată pe eșantionul curent.' });
  return rec;
}

/* ───────────── Piramida: simulare bancă cu regulile utilizatorului ───────────── */

export interface PyramidSimStep { date: string; step: number; run: number; stake: number; odds: number | null; result: string; bankAfter: number; withdrawn: number; cumWithdrawn: number; status: string; label?: string }
export interface PyramidSim { steps: PyramidSimStep[]; bank: number; step: number; run: number; totalWithdrawn: number; runs: Array<{ run: number; start: string; end: string | null; steps: number; maxBank: number; withdrawn: number; status: 'activ' | 'pierdut' | 'țintă' }>; reach: Array<{ step: number; p: number; n: number }> }

export function simulatePyramid(history: PyramidHistoryRow[], rules: Settings['pyramid'], withdrawals: Withdrawal[]): PyramidSim {
  const rows = [...history].sort((a, b) => a.date.localeCompare(b.date));
  const start = rules.startBank;
  let bank = start, step = 0, run = 1, cumW = 0, runW = 0, maxBank = start, runStart = rows[0]?.date ?? '';
  const steps: PyramidSimStep[] = [];
  const runs: PyramidSim['runs'] = [];
  const reachCount = new Map<number, number>();
  const wByDate = new Map<string, number>();
  for (const w of withdrawals) wByDate.set(w.date, (wByDate.get(w.date) ?? 0) + w.amount);
  for (const r of rows) {
    let withdrawn = 0;
    if (r.status === 'pick' && (r.result === 'won' || r.result === 'lost')) {
      const stake = bank;
      if (r.result === 'won' && r.odds) {
        bank = bank * r.odds; step++;
        reachCount.set(step, (reachCount.get(step) ?? 0) + 1);
        maxBank = Math.max(maxBank, bank);
        if (rules.withdrawSteps.includes(step)) { withdrawn += bank * rules.withdrawPct; }
        if (bank - withdrawn >= start * rules.targetMultiple) { withdrawn += (bank - withdrawn) * rules.targetWithdrawPct; }
        bank -= withdrawn;
        steps.push({ date: r.date, step, run, stake, odds: r.odds, result: 'won', bankAfter: bank, withdrawn, cumWithdrawn: cumW + withdrawn, status: r.status, label: r.label });
        cumW += withdrawn; runW += withdrawn;
      } else {
        steps.push({ date: r.date, step: step + 1, run, stake, odds: r.odds ?? null, result: 'lost', bankAfter: 0, withdrawn: 0, cumWithdrawn: cumW, status: r.status, label: r.label });
        runs.push({ run, start: runStart, end: r.date, steps: step, maxBank, withdrawn: runW, status: 'pierdut' });
        run++; bank = start; step = 0; runW = 0; maxBank = start; runStart = r.date;
      }
    } else {
      steps.push({ date: r.date, step, run, stake: 0, odds: r.odds ?? null, result: r.status === 'no_bet' ? 'pauză' : r.result === 'void' ? 'anulat' : 'în așteptare', bankAfter: bank, withdrawn: 0, cumWithdrawn: cumW, status: r.status, label: r.label });
    }
    const manual = wByDate.get(r.date);
    if (manual && bank > 0) { const w = Math.min(bank, manual); bank -= w; cumW += w; runW += w; steps[steps.length - 1].withdrawn += w; steps[steps.length - 1].bankAfter = bank; steps[steps.length - 1].cumWithdrawn = cumW; wByDate.delete(r.date); }
  }
  // retrageri manuale în zile fără pas
  for (const [, amount] of wByDate) { const w = Math.min(bank, amount); bank -= w; cumW += w; runW += w; }
  runs.push({ run, start: runStart, end: null, steps: step, maxBank, withdrawn: runW, status: 'activ' });
  const totalRuns = runs.length;
  const reach = [...reachCount.entries()].sort((a, b) => a[0] - b[0]).map(([s, n]) => ({ step: s, n, p: n / totalRuns }));
  return { steps, bank, step, run, totalWithdrawn: cumW, runs: runs.reverse(), reach };
}
