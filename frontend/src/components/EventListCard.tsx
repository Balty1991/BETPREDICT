import React, { useState } from 'react';
import { ChevronDown, ChevronUp, Sparkles, Bookmark, BookmarkCheck, Calculator } from 'lucide-react';
import { TeamLogo } from './TeamLogo';
import { EdgeBadge } from './EdgeBadge';
import { formatDate, isEdgePass, isAccaLeg, blockedReason } from '@/utils/filters';
import type { RawEvent, PredictionRow, TeamFormEntry, H2HEntry, EventDeepInfo, ClaudeVerdict, LocalPick, V7Edge, DataConfidence } from '@/types/betpredict';

const CONF_STYLE: Record<string, { c: string; dot: string }> = {
  COMPLETE: { c: '#00e87a', dot: '🟢' },
  PARTIAL: { c: '#4a9eff', dot: '🔵' },
  REDUS: { c: '#f5a623', dot: '🟠' },
  INSUFICIENT: { c: '#ff5c7a', dot: '🔴' },
};

// ── Consens/divergență între cele 2 sugestii (Edge v7 vs Model Local) ────────
type MktDir = { axis: 'goals' | 'winner' | 'btts'; dir: string } | null;
function parseMarketDir(m?: string): MktDir {
  if (!m) return null;
  const s = m.toLowerCase();
  if (s.includes('no_btts') || s === 'btts_no' || s === 'nobtts') return { axis: 'btts', dir: 'no' };
  if (s.includes('over')) return { axis: 'goals', dir: 'over' };
  if (s.includes('under')) return { axis: 'goals', dir: 'under' };
  if (s.includes('btts')) return { axis: 'btts', dir: 'yes' };
  if (s.includes('home')) return { axis: 'winner', dir: 'home' };
  if (s.includes('away')) return { axis: 'winner', dir: 'away' };
  if (s.includes('draw')) return { axis: 'winner', dir: 'draw' };
  return null; // șansă dublă / necunoscut — nu comparăm
}
function thesisWord(d: MktDir): string {
  if (!d) return '';
  if (d.axis === 'goals') return d.dir === 'over' ? 'goluri' : 'puține goluri';
  if (d.axis === 'btts') return d.dir === 'yes' ? 'ambele înscriu' : 'nu ambele înscriu';
  return d.dir === 'home' ? 'victorie gazdă' : d.dir === 'away' ? 'victorie oaspete' : 'egal';
}
function suggestionAgreement(a: MktDir, b: MktDir): { level: 'CONSENS' | 'DIVERGENTA'; thesis: string } | null {
  if (!a || !b) return null;
  if (a.axis === b.axis) {
    if (a.dir === b.dir) return { level: 'CONSENS', thesis: thesisWord(a) };
    return { level: 'DIVERGENTA', thesis: '' };
  }
  // Cross-axis: goluri vs BTTS (aceeași „temă" de goluri)
  const pos = (d: MktDir) => !!d && ((d.axis === 'goals' && d.dir === 'over') || (d.axis === 'btts' && d.dir === 'yes'));
  const neg = (d: MktDir) => !!d && ((d.axis === 'goals' && d.dir === 'under') || (d.axis === 'btts' && d.dir === 'no'));
  if (pos(a) && pos(b)) return { level: 'CONSENS', thesis: 'goluri' };
  if (neg(a) && neg(b)) return { level: 'CONSENS', thesis: 'puține goluri' };
  if ((pos(a) && neg(b)) || (neg(a) && pos(b))) return { level: 'DIVERGENTA', thesis: '' };
  return null; // axe diferite (ex. câștigător vs goluri) — nu se compară
}

// Scor 0-100 -> 1..5 steluțe de încredere
function confStars(score: number): number {
  if (score >= 80) return 5;
  if (score >= 60) return 4;
  if (score >= 40) return 3;
  if (score >= 25) return 2;
  return 1;
}
const StarRating: React.FC<{ n: number; color: string }> = ({ n, color }) => (
  <span className="tracking-[-0.5px] text-[10px]" aria-label={`${n} din 5 stele încredere`}>
    <span style={{ color }}>{'★'.repeat(n)}</span>
    <span style={{ color: '#334155' }}>{'★'.repeat(5 - n)}</span>
  </span>
);

interface EventListCardProps {
  event: RawEvent;
  prediction?: PredictionRow;
  homeForm?: TeamFormEntry;
  awayForm?: TeamFormEntry;
  h2h?: H2HEntry;
  deep?: EventDeepInfo;
  leagueName?: string;
  claudeVerdict?: ClaudeVerdict;
  localPick?: LocalPick | null;
  isVerdictSaved?: boolean;
  onToggleSaveVerdict?: (v: ClaudeVerdict) => void;
  v7Edge?: V7Edge;
  dataConf?: DataConfidence;
}

const RISK_LABELS: Record<string, string> = {
  foarte_sigur: 'Foarte sigur',
  sigur: 'Sigur',
  moderat: 'Moderat',
  riscant: 'Riscant',
};

const EventListCardImpl: React.FC<EventListCardProps> = ({
  event: e, prediction, homeForm, awayForm, h2h, deep, leagueName, claudeVerdict, localPick,
  isVerdictSaved, onToggleSaveVerdict, v7Edge, dataConf,
}) => {
  const [expanded, setExpanded] = useState(false);
  const conf = dataConf ? (CONF_STYLE[dataConf.tier] ?? CONF_STYLE.INSUFICIENT) : null;
  // Acord între cele 2 sugestii: Edge Real v7 vs Model Local (verdict).
  const agreement = suggestionAgreement(
    parseMarketDir(v7Edge?.market),
    parseMarketDir(claudeVerdict?.market),
  );

  const mr = prediction?.markets?.match_result;
  const hasProbs = mr && (mr.prob_home != null || mr.prob_draw != null || mr.prob_away != null);
  const ou = prediction?.markets?.over_under;
  const xg = prediction?.markets?.expected_goals;
  const btts = prediction?.markets?.btts;
  const mostLikely = prediction?.markets?.score?.most_likely;

  const lineups = deep?.lineups?.lineups;
  const hasLineups = !!(lineups?.home?.players?.length || lineups?.away?.players?.length);
  const hasForm = !!(homeForm || awayForm);
  const hasH2H = !!(h2h && (h2h.sample ?? 0) > 0);
  const hasDetails = hasForm || hasH2H || hasLineups || !!ou || !!xg;

  const weather = e.weather_context;

  const blocked = !!(claudeVerdict && !isEdgePass(claudeVerdict));
  const accaOk = !!(claudeVerdict && isAccaLeg(claudeVerdict));
  const blockNote = blocked ? blockedReason(claudeVerdict) : null;

  const glow = blocked
    ? '#ff5c7a'
    : accaOk
      ? '#00e87a'
      : claudeVerdict?.risk_tier === 'foarte_sigur' && !blocked
        ? '#a78bfa'
        : null;

  return (
    <div className="relative">
      {glow && (
        // Static glow (no animation) — a continuously-animated box-shadow/opacity here
        // was still causing scroll jank on real phones with many glowing cards at once.
        <div
          className="absolute inset-0 rounded-[26px] pointer-events-none"
          style={{ boxShadow: `0 0 20px 1px ${glow}60` }}
        />
      )}
      <div
        className="rounded-[26px] overflow-hidden relative"
        style={
          glow
            ? { background: 'var(--bp-card)', border: `1px solid ${glow}77` }
            : { background: 'var(--bp-card)', border: '1px solid var(--bp-border2)' }
        }
      >
        {glow && (
          <div
            className="absolute top-0 left-0 right-0 h-[2px]"
            style={{ background: `linear-gradient(90deg, transparent, ${glow}, transparent)` }}
          />
        )}
        <div className="flex items-center justify-between gap-2 px-3.5 pt-3.5 pb-1">
        {/* Doar numele ligii se scurtează; data + stelele rămân mereu vizibile. */}
        <div className="flex items-baseline gap-1 min-w-0 flex-1 text-[10px] text-[#6b7a9e] font-medium tracking-wide">
          <span className="truncate min-w-0">{leagueName ?? 'Ligă necunoscută'}</span>
          <span className="flex-shrink-0 whitespace-nowrap">· {formatDate(e.event_date)}</span>
        </div>
        <div className="flex items-center gap-1.5 flex-shrink-0">
          {conf && (
            <span
              className="inline-flex items-center gap-1 text-[9px] font-bold px-1.5 py-0.5 rounded-full"
              style={{ background: `${conf.c}1f`, color: conf.c }}
              title={`Încredere date: ${dataConf!.label} (${dataConf!.score}/100) · formă ${dataConf!.form_sample.home}/${dataConf!.form_sample.away} · lineup ${dataConf!.has_lineup ? 'da' : 'nu'} · xG ${dataConf!.has_xg ? 'da' : 'nu'}`}
            >
              <StarRating n={confStars(dataConf!.score)} color={conf.c} />
            </span>
          )}
          {weather?.icon && (
            <span className="text-[10px] text-[#6b7a9e]">
              {weather.icon} {weather.temperature_c != null ? `${Math.round(weather.temperature_c)}°` : ''}
            </span>
          )}
        </div>
      </div>

      <div className="flex items-center justify-between px-3.5 py-2.5">
        <div className="flex items-center gap-2.5 flex-1 min-w-0">
          <TeamLogo id={e.home_team_id} size={32} />
          <span className="text-[15px] font-bold text-[#e8eeff] truncate">{e.home_team}</span>
        </div>
        <span className="text-[10px] font-bold text-[#303d57] mx-2 flex-shrink-0">VS</span>
        <div className="flex items-center gap-2.5 flex-1 min-w-0 justify-end">
          <span className="text-[15px] font-bold text-[#e8eeff] truncate text-right">{e.away_team}</span>
          <TeamLogo id={e.away_team_id} size={32} />
        </div>
      </div>

      {/* Caseta 1x2 — o afișăm doar dacă avem probabilități. Dacă nu, dar există
          verdict / pick local / edge v7, sărim caseta (info-ul e mai jos) în loc
          să arătăm „indisponibilă". Placeholderul apare doar când chiar nu e nimic. */}
      {hasProbs ? (
        <div className="mx-3.5 mb-3 rounded-2xl p-3.5" style={{ background: 'var(--bp-card2)' }}>
          <div className="flex items-center divide-x divide-white/10">
            <ProbCol label="1" value={mr!.prob_home} />
            <ProbCol label="X" value={mr!.prob_draw} />
            <ProbCol label="2" value={mr!.prob_away} />
            {mostLikely && (
              <div className="flex-1 flex flex-col items-center gap-0.5 px-1.5">
                <span className="text-[9px] font-bold uppercase tracking-wider text-[#6b7a9e]">SCOR</span>
                <span className="text-sm font-bold text-[#4a9eff]">{mostLikely}</span>
              </div>
            )}
          </div>
          <ProbBar home={mr!.prob_home} draw={mr!.prob_draw} away={mr!.prob_away} />
        </div>
      ) : (!claudeVerdict && !localPick && !v7Edge) ? (
        <div className="mx-3.5 mb-3 rounded-2xl p-3.5" style={{ background: 'var(--bp-card2)' }}>
          <p className="text-[10px] text-[#6b7a9e] text-center py-1">Predicție AI încă indisponibilă pentru acest meci</p>
        </div>
      ) : null}

      {agreement && (
        <div
          className="mx-3.5 mb-2 rounded-lg px-2.5 py-1.5 flex items-center gap-1.5 text-[10px] font-bold"
          style={agreement.level === 'CONSENS'
            ? { background: 'rgba(0,232,122,.12)', color: '#00e87a', border: '1px solid rgba(0,232,122,.3)' }
            : { background: 'rgba(245,166,35,.12)', color: '#f5a623', border: '1px solid rgba(245,166,35,.3)' }}
        >
          {agreement.level === 'CONSENS' ? (
            <span>✓✓ Consens — ambele motoare indică <b>{agreement.thesis}</b></span>
          ) : (
            <span>⚠ Divergență — cele 2 sugestii se contrazic (prudență)</span>
          )}
        </div>
      )}

      <EdgeBadge edge={v7Edge} />

      {claudeVerdict && (
        <div
          className="mx-3 mb-2.5 rounded-xl p-3 border relative overflow-hidden"
          style={
            glow
              ? { borderColor: `${glow}88`, background: `${glow}14`, boxShadow: `0 0 18px -4px ${glow}55` }
              : { borderColor: '#a78bfa55', background: '#a78bfa14' }
          }
        >
          <div className="flex items-center gap-1.5 mb-1.5">
            {claudeVerdict.source === 'local_model' ? (
              <Calculator className="w-3 h-3" style={{ color: glow ?? '#a78bfa' }} />
            ) : (
              <Sparkles className="w-3 h-3" style={{ color: glow ?? '#a78bfa' }} />
            )}
            <span className="text-[9px] font-bold uppercase tracking-widest" style={{ color: glow ?? '#a78bfa' }}>
              {claudeVerdict.source === 'local_model' ? 'Model Local (Istoric)' : 'Verdict Claude AI'}
            </span>
            {accaOk && (
              <span className="ml-auto text-[9px] font-bold px-1.5 py-0.5 rounded-full bg-[#00e87a22] text-[#00e87a]">
                ★ ACCA 50×
              </span>
            )}
            {blocked && (
              <span className="ml-auto text-[9px] font-black px-1.5 py-0.5 rounded-full bg-[#ff5c7a22] text-[#ff5c7a] tracking-wider">
                BLOCHEAZĂ
              </span>
            )}
          </div>
          <div className="flex items-center justify-between gap-2">
            <div className="flex-1 min-w-0">
              <span className="text-sm font-bold text-[#e8eeff] block truncate mb-0.5">{claudeVerdict.market_label}</span>
              <span
                className="text-[34px] font-black leading-none tabular-nums block"
                style={{
                  backgroundImage: `linear-gradient(135deg, ${glow ?? '#a78bfa'}, ${glow ?? '#a78bfa'}cc)`,
                  WebkitBackgroundClip: 'text',
                  backgroundClip: 'text',
                  color: 'transparent',
                }}
              >
                {claudeVerdict.probability.toFixed(0)}%
              </span>
            </div>
            {claudeVerdict.odds != null && (
              <div
                className="flex-shrink-0 rounded-lg px-2.5 py-1.5 text-center border"
                style={
                  glow
                    ? { borderColor: `${glow}aa`, background: `${glow}1f`, boxShadow: `0 0 14px -3px ${glow}88` }
                    : { borderColor: 'var(--bp-border2)', background: 'var(--bp-surface)' }
                }
              >
                <span className="text-base font-black block" style={{ color: glow ?? '#e8eeff' }}>
                  @{claudeVerdict.odds.toFixed(2)}
                </span>
                <span className="text-[9px] font-bold uppercase tracking-wider text-[#6b7a9e]">
                  {claudeVerdict.odds_is_market && claudeVerdict.bookmaker ? claudeVerdict.bookmaker : 'fair'}
                </span>
              </div>
            )}
          </div>
          <p className="text-[10px] text-[#6b7a9e] leading-relaxed mt-1.5">{claudeVerdict.rationale}</p>
          {blockNote && (
            <p className="text-[11px] font-bold leading-relaxed mt-1.5" style={{ color: '#ff5c7a' }}>
              {blockNote} Banca se joacă pe simple 1.50–3.30. Acca = loterie, nu piramidă.
            </p>
          )}

          {(claudeVerdict.edge_pp != null || claudeVerdict.value_pct != null || claudeVerdict.fair_odds != null) && (
            <div className="grid grid-cols-3 gap-1.5 mt-2">
              {claudeVerdict.edge_pp != null && (
                <MiniStat label="EDGE" value={`${claudeVerdict.edge_pp > 0 ? '+' : ''}${claudeVerdict.edge_pp.toFixed(1)}pp`} positive={claudeVerdict.edge_pp > 0} />
              )}
              {claudeVerdict.value_pct != null && (
                <MiniStat label="VALUE" value={`${claudeVerdict.value_pct > 0 ? '+' : ''}${claudeVerdict.value_pct.toFixed(1)}%`} positive={claudeVerdict.value_pct > 0} />
              )}
              {claudeVerdict.fair_odds != null && (
                <MiniStat label="FAIR" value={claudeVerdict.fair_odds.toFixed(2)} />
              )}
            </div>
          )}

          {(claudeVerdict.form_home?.form || claudeVerdict.form_away?.form || (claudeVerdict.h2h?.sample ?? 0) > 0 || claudeVerdict.is_local_derby) && (
            <div className="flex flex-wrap gap-1 mt-1.5">
              {claudeVerdict.form_home?.form && <TinyChip text={`Gazdă ${claudeVerdict.form_home.form}`} />}
              {claudeVerdict.form_away?.form && <TinyChip text={`Oaspete ${claudeVerdict.form_away.form}`} />}
              {(claudeVerdict.h2h?.sample ?? 0) > 0 && (
                <TinyChip text={`H2H ${claudeVerdict.h2h!.home_wins ?? 0}-${claudeVerdict.h2h!.draws ?? 0}-${claudeVerdict.h2h!.away_wins ?? 0}`} />
              )}
              {claudeVerdict.is_local_derby && <TinyChip text="⚡ Derby local" />}
            </div>
          )}

          <div className="flex items-center justify-between mt-1.5">
            <span className="text-[9px] text-[#6b7a9e]">
              Risc: {RISK_LABELS[claudeVerdict.risk_tier] ?? claudeVerdict.risk_tier}
            </span>
            {onToggleSaveVerdict && (
              <button
                onClick={() => onToggleSaveVerdict(claudeVerdict)}
                className="flex items-center gap-1 text-[9px] font-bold px-2 py-1 rounded-full transition-colors"
                style={
                  isVerdictSaved
                    ? { background: '#00e87a22', color: '#00e87a' }
                    : { background: 'var(--bp-surface2)', color: 'var(--bp-muted)' }
                }
              >
                {isVerdictSaved ? <BookmarkCheck className="w-3 h-3" /> : <Bookmark className="w-3 h-3" />}
                {isVerdictSaved ? 'Salvat' : 'Salvează'}
              </button>
            )}
          </div>
        </div>
      )}

      {!claudeVerdict && localPick && (
        <div className="mx-3.5 mb-3 rounded-2xl p-3 border" style={{ borderColor: 'rgba(74,158,255,0.3)', background: 'rgba(74,158,255,0.06)' }}>
          <div className="flex items-center gap-1.5 mb-1">
            <Calculator className="w-3 h-3 text-[#4a9eff]" />
            <span className="text-[9px] font-bold uppercase tracking-widest text-[#4a9eff]">Analiză rapidă (locală, fără AI)</span>
          </div>
          <div className="flex items-center justify-between">
            <span className="text-sm font-bold text-[#e8eeff]">{localPick.market_label}</span>
            <span className="text-lg font-black text-[#4a9eff]">{localPick.probability.toFixed(0)}%</span>
          </div>
          {(localPick.xg_home != null && localPick.xg_away != null) && (
            <p className="text-[10px] text-[#6b7a9e] mt-0.5">xG estimat: {localPick.xg_home.toFixed(2)} – {localPick.xg_away.toFixed(2)}</p>
          )}
          {(localPick.edge_pp != null || localPick.odds != null) && (
            <div className="flex items-center justify-between mt-1.5 text-[9px] text-[#6b7a9e]">
              {localPick.edge_pp != null ? (
                <span style={{ color: localPick.edge_pp > 0 ? '#00e87a' : '#ff5c7a' }}>
                  Edge {localPick.edge_pp > 0 ? '+' : ''}{localPick.edge_pp.toFixed(1)}pp
                </span>
              ) : <span />}
              {localPick.odds != null && (
                <span>
                  @{localPick.odds.toFixed(2)}
                  {localPick.odds_is_market && localPick.bookmaker ? ` · ${localPick.bookmaker}` : ''}
                  {!localPick.odds_is_market && ' (fair)'}
                </span>
              )}
            </div>
          )}
        </div>
      )}

      {hasDetails && (
        <>
          <button
            onClick={() => setExpanded(v => !v)}
            className="w-full flex items-center justify-center gap-1.5 py-2.5 border-t border-white/5 text-[10px] text-[#6b7a9e] hover:text-[#e8eeff] hover:bg-white/[0.02] transition-colors"
          >
            <span>Detalii complete</span>
            {expanded ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
          </button>

          {expanded && (
            <div className="px-3 pb-3 flex flex-col gap-2.5">
              {(ou || xg || btts) && (
                <Section title="Piețe & xG așteptat">
                  <div className="flex flex-wrap gap-1.5">
                    {xg?.home != null && xg?.away != null && (
                      <StatChip label="xG" value={`${xg.home.toFixed(2)} – ${xg.away.toFixed(2)}`} />
                    )}
                    {ou?.prob_over_15 != null && <StatChip label="Over 1.5" value={`${ou.prob_over_15.toFixed(0)}%`} />}
                    {ou?.prob_over_25 != null && <StatChip label="Over 2.5" value={`${ou.prob_over_25.toFixed(0)}%`} />}
                    {ou?.prob_over_35 != null && <StatChip label="Over 3.5" value={`${ou.prob_over_35.toFixed(0)}%`} />}
                    {btts?.prob_yes != null && <StatChip label="BTTS" value={`${btts.prob_yes.toFixed(0)}%`} />}
                  </div>
                </Section>
              )}

              {hasForm && (
                <Section title="Formă echipe (ultimele 5)">
                  <div className="grid grid-cols-2 gap-2">
                    <FormBlock name={e.home_team} form={homeForm} />
                    <FormBlock name={e.away_team} form={awayForm} />
                  </div>
                </Section>
              )}

              {hasH2H && (
                <Section title={`Head-to-Head (${h2h!.sample} meciuri)`}>
                  <div className="flex flex-wrap gap-1.5 mb-1.5">
                    <StatChip label="Gazdă" value={`${h2h!.home_wins ?? 0}W`} />
                    <StatChip label="Egal" value={`${h2h!.draws ?? 0}`} />
                    <StatChip label="Oaspete" value={`${h2h!.away_wins ?? 0}W`} />
                    {h2h!.avg_goals != null && <StatChip label="Media goluri" value={h2h!.avg_goals.toFixed(1)} />}
                    {h2h!.btts_pct != null && <StatChip label="BTTS" value={`${h2h!.btts_pct.toFixed(0)}%`} />}
                  </div>
                  {h2h!.matches?.slice(0, 3).map((m, i) => (
                    <div key={i} className="flex items-center justify-between text-[10px] text-[#6b7a9e] py-0.5">
                      <span className="truncate max-w-[65%]">{m.home_team} vs {m.away_team}</span>
                      <span className="font-bold text-[#e8eeff]">{m.score ?? '—'}</span>
                    </div>
                  ))}
                </Section>
              )}

              {hasLineups && (
                <Section title="Aliniere probabilă">
                  <div className="grid grid-cols-2 gap-2">
                    <LineupBlock label={e.home_team} team={lineups?.home} />
                    <LineupBlock label={e.away_team} team={lineups?.away} />
                  </div>
                </Section>
              )}
            </div>
          )}
        </>
      )}
      </div>
    </div>
  );
};

// Memoizat: la paginare / re-render de pagină, doar cardurile cu props schimbate
// se re-randează (nu toate cele vizibile).
export const EventListCard = React.memo(EventListCardImpl);

const ProbBar: React.FC<{ home?: number; draw?: number; away?: number }> = ({ home, draw, away }) => {
  const h = home ?? 0, d = draw ?? 0, a = away ?? 0;
  const total = h + d + a;
  if (total <= 0) return null;
  return (
    <div className="flex h-1.5 rounded-full overflow-hidden mt-2.5" style={{ background: 'var(--bp-surface2)' }}>
      <div style={{ width: `${(h / total) * 100}%`, background: '#00e87a' }} />
      <div style={{ width: `${(d / total) * 100}%`, background: '#f5a623' }} />
      <div style={{ width: `${(a / total) * 100}%`, background: '#4a9eff' }} />
    </div>
  );
};

const ProbCol: React.FC<{ label: string; value?: number }> = ({ label, value }) => (
  <div className="flex-1 flex flex-col items-center gap-0.5 px-1.5">
    <span className="text-[9px] font-bold uppercase tracking-wider text-[#6b7a9e]">{label}</span>
    <span className="text-sm font-bold text-[#e8eeff]">{value != null ? `${value.toFixed(0)}%` : '—'}</span>
  </div>
);

const MiniStat: React.FC<{ label: string; value: string; positive?: boolean }> = ({ label, value, positive }) => {
  const accent = positive === true ? '#00e87a' : positive === false ? '#ff5c7a' : '#4a9eff';
  return (
    <div
      className="rounded-lg py-1.5 flex flex-col items-center border-t-2"
      style={{ background: 'var(--bp-surface)', borderTopColor: accent }}
    >
      <span className="text-[9px] font-bold uppercase tracking-wider text-[#6b7a9e]">{label}</span>
      <span className="text-[12px] font-bold" style={{ color: accent }}>
        {value}
      </span>
    </div>
  );
};

const TinyChip: React.FC<{ text: string }> = ({ text }) => (
  <span className="text-[9px] px-1.5 py-0.5 rounded-md text-[#a78bfa]" style={{ background: '#a78bfa1f' }}>
    {text}
  </span>
);

const Section: React.FC<{ title: string; children: React.ReactNode }> = ({ title, children }) => (
  <div>
    <p className="text-[9px] font-bold uppercase tracking-widest text-[#6b7a9e] mb-1.5">{title}</p>
    {children}
  </div>
);

const StatChip: React.FC<{ label: string; value: string }> = ({ label, value }) => (
  <span className="text-[9px] px-2 py-1 rounded-lg" style={{ background: 'var(--bp-surface)' }}>
    <span className="text-[#6b7a9e]">{label} </span>
    <span className="font-bold text-[#e8eeff]">{value}</span>
  </span>
);

const FormBlock: React.FC<{ name: string; form?: TeamFormEntry }> = ({ name, form }) => (
  <div className="rounded-lg p-2" style={{ background: 'var(--bp-surface)' }}>
    <p className="text-[10px] font-semibold text-[#e8eeff] truncate mb-1">{name}</p>
    {form ? (
      <>
        <p className="text-[11px] font-bold tracking-widest text-[#4a9eff]">{form.form_string || '—'}</p>
        <p className="text-[9px] text-[#6b7a9e] mt-0.5">
          {form.avg_goals_scored_last5 != null ? `${form.avg_goals_scored_last5.toFixed(1)} marcate` : ''}
          {form.avg_goals_conceded_last5 != null ? ` · ${form.avg_goals_conceded_last5.toFixed(1)} primite` : ''}
        </p>
      </>
    ) : (
      <p className="text-[9px] text-[#6b7a9e]">Indisponibilă</p>
    )}
  </div>
);

const LineupBlock: React.FC<{
  label: string;
  team?: { formation?: string; confidence?: number; players?: Array<{ name: string; short_name?: string; position?: string }> };
}> = ({ label, team }) => (
  <div className="rounded-lg p-2" style={{ background: 'var(--bp-surface)' }}>
    <div className="flex items-center justify-between mb-1">
      <p className="text-[10px] font-semibold text-[#e8eeff] truncate">{label}</p>
      {team?.formation && <span className="text-[9px] text-[#4a9eff] font-bold">{team.formation}</span>}
    </div>
    {team?.players?.length ? (
      <ul className="flex flex-col gap-0.5">
        {team.players.slice(0, 11).map((p, i) => (
          <li key={i} className="text-[9px] text-[#6b7a9e] truncate">
            {p.position ? `${p.position} · ` : ''}{p.short_name ?? p.name}
          </li>
        ))}
      </ul>
    ) : (
      <p className="text-[9px] text-[#6b7a9e]">Indisponibilă</p>
    )}
  </div>
);
