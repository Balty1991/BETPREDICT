import React, { useEffect, useMemo, useRef, useState } from 'react';
import { Wand2, RefreshCw } from 'lucide-react';
import { useAppData } from '@/context/DataContext';
import { AccumulatorTicketCard } from '@/pages/PredictionsPage';
import type { ClaudeAccumulator, ClaudeVerdict } from '@/types/betpredict';
import {
  isBlacklistedMarket, isVolumeOver15,
  MIN_ACCA_LEG_ODDS, MAX_QUALIFIED_ODDS,
} from '@/utils/filters';

function stars(score: number): number {
  if (score >= 80) return 5; if (score >= 60) return 4; if (score >= 40) return 3; if (score >= 25) return 2; return 1;
}

type MarketGroup = 'Goluri' | 'BTTS' | '1X2';
function marketGroup(m?: string): MarketGroup | null {
  if (!m) return null;
  const s = m.toLowerCase();
  if (s.includes('over') || s.includes('under')) return 'Goluri';
  if (s.includes('btts')) return 'BTTS';
  if (s.includes('home') || s.includes('away') || s.includes('draw')) return '1X2';
  return null;
}

interface Cand {
  v: ClaudeVerdict; odds: number; stars: number; reliable: boolean;
  isValue: boolean; sharp: boolean; edgePp: number; group: MarketGroup | null;
  realProb: number;
  quality: number;
}

const ODDS_TARGETS = [20, 50, 100, 200];
const MAX_LEGS_OPTS = [4, 5, 6, 8];
const STAR_OPTS: { label: string; min: number }[] = [
  { label: 'Orice', min: 0 }, { label: '★★+', min: 2 }, { label: '★★★+', min: 3 }, { label: '★★★★+', min: 4 },
];
const EDGE_OPTS: { label: string; min: number }[] = [
  { label: '+4pp', min: 4 }, { label: '+6pp', min: 6 }, { label: '≥ 0', min: 0 },
];
const MARKET_OPTS: MarketGroup[] = ['Goluri', 'BTTS', '1X2'];

function leagueDay(v: ClaudeVerdict): string {
  const d = v.event_date ? new Date(v.event_date) : null;
  const ymd = d && !Number.isNaN(d.getTime())
    ? `${d.getFullYear()}-${d.getMonth() + 1}-${d.getDate()}`
    : '?';
  return `${v.league || '?'}|${ymd}`;
}

export const TicketGenerator: React.FC<{
  onSave: (t: ClaudeAccumulator) => void;
  isSaved: (t: ClaudeAccumulator) => boolean;
}> = ({ onSave, isSaved }) => {
  const { claude: { verdictsByEvent }, dataConfidence, v7Edge } = useAppData();

  const [targetOdds, setTargetOdds] = useState(50);
  const [maxLegs, setMaxLegs] = useState(8);
  const [minStars, setMinStars] = useState(0);
  const [minEdge, setMinEdge] = useState(4);
  const [onlyValue, setOnlyValue] = useState(false);
  const [onlySharp, setOnlySharp] = useState(false);
  const [markets, setMarkets] = useState<MarketGroup[]>([]);
  const [ticket, setTicket] = useState<ClaudeAccumulator | null>(null);
  const [note, setNote] = useState<string>('');
  const autoRef = useRef(false);

  const pool = useMemo<Cand[]>(() => {
    const rows: Cand[] = [];
    verdictsByEvent.forEach((v) => {
      const odds = Number(v.odds);
      if (!odds || odds < MIN_ACCA_LEG_ODDS || odds > MAX_QUALIFIED_ODDS) return;
      if (isBlacklistedMarket(v.market)) return;
      if (isVolumeOver15(v.market, odds)) return;
      const dc = dataConfidence.get(String(v.event_id));
      const edge = v7Edge.get(String(v.event_id));
      const implied = 1 / odds;
      const model = (Number(v.probability) || implied * 100) / 100;
      const realProb = Math.max(0.01, Math.min(0.99, 0.7 * Math.min(0.985, implied * 0.96) + 0.3 * model));
      const st = stars(dc?.score ?? 0);
      rows.push({
        v, odds, stars: st, reliable: dc?.reliable ?? false,
        isValue: edge?.is_value ?? false, sharp: edge?.sharp_confirmed ?? false,
        edgePp: Number(v.edge_pp) || 0, group: marketGroup(v.market), realProb,
        quality: realProb * 100 + st * 6 + (edge?.sharp_confirmed ? 15 : 0) + Math.max(0, Number(v.edge_pp) || 0) * 1.5,
      });
    });
    rows.sort((a, b) => b.quality - a.quality);
    return rows;
  }, [verdictsByEvent, dataConfidence, v7Edge]);

  const generate = (tgt = targetOdds) => {
    const cand = pool.filter((r) =>
      (minStars === 0 || r.stars >= minStars) &&
      r.edgePp >= minEdge &&
      (!onlyValue || r.isValue) &&
      (!onlySharp || r.sharp) &&
      (markets.length === 0 || (r.group && markets.includes(r.group)))
    );
    const legs: Cand[] = [];
    const usedEvents = new Set<string>();
    const usedLeagueDay = new Set<string>();

    const absorb = (allowDupLeague: boolean) => {
      for (const r of cand) {
        if (legs.length >= maxLegs) break;
        const eid = String(r.v.event_id);
        if (usedEvents.has(eid)) continue;
        const lk = leagueDay(r.v);
        if (!allowDupLeague && usedLeagueDay.has(lk)) continue;
        legs.push(r);
        usedEvents.add(eid);
        usedLeagueDay.add(lk);
        const combined = legs.reduce((a, x) => a * x.odds, 1);
        if (legs.length >= 4 && combined >= tgt) break;
      }
    };
    absorb(false);
    let combined = legs.reduce((a, x) => a * x.odds, 1);
    if (combined < tgt) absorb(true);
    combined = legs.reduce((a, x) => a * x.odds, 1);
    while (combined > tgt * 1.55 && legs.length > 5) {
      legs.pop();
      combined = legs.reduce((a, x) => a * x.odds, 1);
    }
    if (legs.length < 4 || combined < tgt * 0.75) {
      setTicket(null);
      setNote('Prea puține picioare +EV în fereastra 1.60–3.30. Relaxează edge-ul sau așteaptă meciuri noi — nu umplem cu @1.14.');
      return;
    }
    legs.sort((a, b) => (a.v.event_date || '').localeCompare(b.v.event_date || ''));
    combined = legs.reduce((a, r) => a * r.odds, 1);
    const combinedProb = legs.reduce((acc, r) => acc * r.realProb, 1);
    const adjP = legs.reduce((acc, r) => {
      const implied = 1 / Math.max(r.odds, 1.01);
      return acc * (implied + Math.max(0, r.realProb - implied) * 0.35);
    }, 1);
    const avgEdge = legs.reduce((a, r) => a + r.edgePp, 0) / legs.length;
    const nSharp = legs.filter((r) => r.sharp).length;
    const isLongshot = tgt >= 50;
    const t: ClaudeAccumulator = {
      label: isLongshot ? `Acca ${tgt}× loterie` : `Bilet · țintă @${tgt}`,
      risk_level: isLongshot ? 'longshot' : 'safe',
      combined_odds: Math.round(combined * 100) / 100,
      combined_probability_pct: Math.round(adjP * 10000) / 100,
      avg_edge_pp: Math.round(avgEdge * 10) / 10,
      n_sharp_confirmed: nSharp,
      claude_highlight: false,
      claude_concern: isLongshot
        ? `LOTERIE Edge v8, NU piramidă. Miză 0.4–1% din bancă (4–10 lei din 1000). Un picior greșit anulează tot. Prob. brută ${(combinedProb * 100).toFixed(2)}% · ajustată ${(adjP * 100).toFixed(2)}%.`
        : combined < tgt
          ? `Cea mai mare cotă atinsă cu criteriile date: @${(Math.round(combined * 100) / 100).toFixed(2)} (sub ținta @${tgt}).`
          : null,
      legs: legs.map((r) => ({
        event_id: r.v.event_id, home_team: r.v.home_team, away_team: r.v.away_team,
        league: r.v.league, event_date: r.v.event_date, market: r.v.market,
        market_label: r.v.market_label, odds: r.odds, probability: Math.round(r.realProb * 1000) / 10,
        rationale: `${r.stars}★ date · ${r.v.risk_tier}${r.edgePp > 0 ? ` · edge +${r.edgePp.toFixed(1)}pp` : ''}${r.sharp ? ' · confirmat sharp' : ''}`,
        bookmaker: r.v.bookmaker,
      })),
    };
    setTicket(t);
    setNote('');
  };

  useEffect(() => {
    if (autoRef.current) return;
    if (pool.length < 4) return;
    autoRef.current = true;
    generate(50);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pool]);

  return (
    <div className="rounded-2xl p-3.5 flex flex-col gap-3" style={{ background: 'var(--bp-card)', border: '1px solid #a78bfa44' }}>
      <div className="flex items-center gap-1.5">
        <Wand2 className="w-4 h-4" style={{ color: '#a78bfa' }} />
        <span className="text-sm font-black text-[#e8eeff]">Acca 50× / 100× / 200×</span>
      </div>
      <p className="text-[10px] text-[#8a97b8] leading-relaxed -mt-1">
        Picioare +EV 1.60–3.30. Fără piramidă @1.14. Miză loterie 0.4–1% din bancă.
      </p>

      <Row label="Cotă țintă">
        {ODDS_TARGETS.map((o) => (
          <Chip key={o} active={targetOdds === o} onClick={() => { setTargetOdds(o); }}>{o}×</Chip>
        ))}
      </Row>
      <Row label="Max selecții">
        {MAX_LEGS_OPTS.map((n) => (
          <Chip key={n} active={maxLegs === n} onClick={() => setMaxLegs(n)}>{n}</Chip>
        ))}
      </Row>
      <Row label="Încredere">
        {STAR_OPTS.map((s) => (
          <Chip key={s.label} active={minStars === s.min} onClick={() => setMinStars(s.min)}>{s.label}</Chip>
        ))}
      </Row>
      <Row label="Edge min">
        {EDGE_OPTS.map((s) => (
          <Chip key={s.label} active={minEdge === s.min} onClick={() => setMinEdge(s.min)}>{s.label}</Chip>
        ))}
      </Row>
      <Row label="Piețe">
        {MARKET_OPTS.map((m) => (
          <Chip key={m} active={markets.includes(m)} onClick={() =>
            setMarkets((cur) => cur.includes(m) ? cur.filter((x) => x !== m) : [...cur, m])
          }>{m}</Chip>
        ))}
      </Row>
      <Row label="Doar">
        <Chip active={onlyValue} onClick={() => setOnlyValue((v) => !v)}>💎 Value</Chip>
        <Chip active={onlySharp} onClick={() => setOnlySharp((v) => !v)}>✓ Sharp</Chip>
      </Row>

      <button
        onClick={() => generate(targetOdds)}
        className="w-full flex items-center justify-center gap-2 py-2.5 rounded-xl text-[13px] font-black transition-all active:scale-[0.98]"
        style={{ background: 'linear-gradient(135deg,#a78bfa,#7c6cf0)', color: '#0b0f1a' }}
      >
        {ticket ? <RefreshCw className="w-4 h-4" /> : <Wand2 className="w-4 h-4" />}
        {ticket ? `Regenerează ${targetOdds}×` : `Generează ${targetOdds}×`}
      </button>

      {note && <p className="text-[11px] text-[#f5a623] leading-relaxed">{note}</p>}
      {ticket && (
        <AccumulatorTicketCard ticket={ticket} isPlaced={isSaved(ticket)} onTogglePlace={() => onSave(ticket)} />
      )}
    </div>
  );
};

const Row: React.FC<{ label: string; children: React.ReactNode }> = ({ label, children }) => (
  <div className="flex items-center gap-2.5">
    <span className="text-[9px] font-bold uppercase tracking-[0.1em] text-[#8a97b8] w-[70px] flex-shrink-0">{label}</span>
    <div className="flex gap-2 overflow-x-auto scrollbar-hide">{children}</div>
  </div>
);

const Chip: React.FC<{ active: boolean; onClick: () => void; children: React.ReactNode }> = ({ active, onClick, children }) => (
  <button
    onClick={onClick}
    className="flex-shrink-0 rounded-full px-3 py-1.5 text-[11px] font-bold border transition-all"
    style={active
      ? { background: 'linear-gradient(135deg,#a78bfa,#7c6cf0)', color: '#0b0f1a', borderColor: 'transparent' }
      : { background: 'var(--bp-surface)', color: 'var(--bp-text)', borderColor: 'var(--bp-border)' }}
  >
    {children}
  </button>
);
