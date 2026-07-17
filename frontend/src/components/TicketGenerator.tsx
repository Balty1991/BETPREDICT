import React, { useMemo, useState } from 'react';
import { Wand2, RefreshCw } from 'lucide-react';
import { useAppData } from '@/context/DataContext';
import { AccumulatorTicketCard } from '@/pages/PredictionsPage';
import type { ClaudeAccumulator, ClaudeVerdict } from '@/types/betpredict';

// Scor 0-100 -> 1..5 stele (aliniat cu EventListCard).
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
  realProb: number; // probabilitate ancorată pe piață (0-1)
  quality: number;
}

const ODDS_TARGETS = [2, 5, 10, 20, 50, 100, 500];
const MAX_LEGS_OPTS = [3, 5, 8, 15, 25, 40];
const STAR_OPTS: { label: string; min: number }[] = [
  { label: 'Orice', min: 0 }, { label: '★★+', min: 2 }, { label: '★★★+', min: 3 }, { label: '★★★★+', min: 4 },
];
const MARKET_OPTS: MarketGroup[] = ['Goluri', 'BTTS', '1X2'];

export const TicketGenerator: React.FC<{
  onSave: (t: ClaudeAccumulator) => void;
  isSaved: (t: ClaudeAccumulator) => boolean;
}> = ({ onSave, isSaved }) => {
  const { claude: { verdictsByEvent }, dataConfidence, v7Edge } = useAppData();

  const [targetOdds, setTargetOdds] = useState(5);
  const [maxLegs, setMaxLegs] = useState(5);
  const [minStars, setMinStars] = useState(0);
  const [onlyValue, setOnlyValue] = useState(false);
  const [onlySharp, setOnlySharp] = useState(false);
  const [markets, setMarkets] = useState<MarketGroup[]>([]);
  const [ticket, setTicket] = useState<ClaudeAccumulator | null>(null);
  const [note, setNote] = useState<string>('');

  const pool = useMemo<Cand[]>(() => {
    const rows: Cand[] = [];
    verdictsByEvent.forEach((v) => {
      const odds = Number(v.odds);
      if (!odds || odds < 1.15) return;
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

  const generate = () => {
    let cand = pool.filter((r) =>
      (minStars === 0 || r.stars >= minStars) &&
      (!onlyValue || r.isValue) &&
      (!onlySharp || r.sharp) &&
      (markets.length === 0 || (r.group && markets.includes(r.group)))
    );
    const legs: Cand[] = [];
    const usedEvents = new Set<string>();
    const leagueCount: Record<string, number> = {};
    let combined = 1;
    for (const r of cand) {
      if (legs.length >= maxLegs) break;
      const eid = String(r.v.event_id);
      if (usedEvents.has(eid)) continue;
      const lg = r.v.league || '?';
      if ((leagueCount[lg] || 0) >= 2) continue;
      legs.push(r); usedEvents.add(eid); leagueCount[lg] = (leagueCount[lg] || 0) + 1;
      combined *= r.odds;
      if (legs.length >= 2 && combined >= targetOdds) break;
    }
    if (legs.length < 2) {
      setTicket(null);
      setNote('Prea puține selecții pentru criteriile alese. Relaxează filtrele (mai puține stele / fără doar-value).');
      return;
    }
    const combinedProb = legs.reduce((acc, r) => acc * r.realProb, 1);
    const avgEdge = legs.reduce((a, r) => a + r.edgePp, 0) / legs.length;
    const nSharp = legs.filter((r) => r.sharp).length;
    const t: ClaudeAccumulator = {
      label: `Bilet la comandă · țintă @${targetOdds}`,
      risk_level: 'safe',
      combined_odds: Math.round(combined * 100) / 100,
      combined_probability_pct: Math.round(combinedProb * 10000) / 100,
      avg_edge_pp: Math.round(avgEdge * 10) / 10,
      n_sharp_confirmed: nSharp,
      claude_highlight: false,
      claude_concern: combined < targetOdds
        ? `Cea mai mare cotă atinsă cu criteriile date: @${(Math.round(combined * 100) / 100).toFixed(2)} (sub ținta @${targetOdds}).`
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

  return (
    <div className="rounded-2xl p-3.5 flex flex-col gap-3" style={{ background: 'var(--bp-card)', border: '1px solid #a78bfa44' }}>
      <div className="flex items-center gap-1.5">
        <Wand2 className="w-4 h-4" style={{ color: '#a78bfa' }} />
        <span className="text-sm font-black text-[#e8eeff]">Generează bilet la comandă</span>
      </div>

      <Row label="Cotă țintă">
        <NumInput value={targetOdds} min={1.1} max={100000} step={1} prefix="@"
          onChange={(v) => setTargetOdds(Math.max(1.1, v))} />
        {ODDS_TARGETS.map((o) => (
          <Chip key={o} active={targetOdds === o} onClick={() => setTargetOdds(o)}>@{o}</Chip>
        ))}
      </Row>
      <Row label="Max selecții">
        <NumInput value={maxLegs} min={2} max={40} step={1}
          onChange={(v) => setMaxLegs(Math.max(2, Math.min(40, Math.round(v))))} />
        {MAX_LEGS_OPTS.map((n) => (
          <Chip key={n} active={maxLegs === n} onClick={() => setMaxLegs(n)}>{n}</Chip>
        ))}
      </Row>
      <Row label="Încredere">
        {STAR_OPTS.map((s) => (
          <Chip key={s.label} active={minStars === s.min} onClick={() => setMinStars(s.min)}>{s.label}</Chip>
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
        onClick={generate}
        className="w-full flex items-center justify-center gap-2 py-2.5 rounded-xl text-[13px] font-black transition-all active:scale-[0.98]"
        style={{ background: 'linear-gradient(135deg,#a78bfa,#7c6cf0)', color: '#0b0f1a' }}
      >
        {ticket ? <RefreshCw className="w-4 h-4" /> : <Wand2 className="w-4 h-4" />}
        {ticket ? 'Regenerează' : 'Generează biletul'}
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

const NumInput: React.FC<{ value: number; min: number; max: number; step: number; prefix?: string; onChange: (v: number) => void }> =
  ({ value, min, max, step, prefix, onChange }) => (
  <div className="flex-shrink-0 flex items-center rounded-full px-2.5 py-1" style={{ background: 'rgba(167,139,250,.14)', border: '1px solid #a78bfa66' }}>
    {prefix && <span className="text-[11px] font-black text-[#a78bfa]">{prefix}</span>}
    <input
      type="number" inputMode="decimal" value={value} min={min} max={max} step={step}
      onChange={(e) => { const v = parseFloat(e.target.value); if (!Number.isNaN(v)) onChange(v); }}
      className="w-[52px] bg-transparent text-[12px] font-black text-[#e8eeff] outline-none text-center"
      style={{ MozAppearance: 'textfield' as React.CSSProperties['MozAppearance'] }}
    />
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
