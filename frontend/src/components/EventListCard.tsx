import React, { useState } from 'react';
import { ChevronDown, ChevronUp, Sparkles } from 'lucide-react';
import { TeamLogo } from './TeamLogo';
import { formatDate } from '@/utils/filters';
import type { RawEvent, PredictionRow, TeamFormEntry, H2HEntry, EventDeepInfo, ClaudeVerdict } from '@/types/betpredict';

interface EventListCardProps {
  event: RawEvent;
  prediction?: PredictionRow;
  homeForm?: TeamFormEntry;
  awayForm?: TeamFormEntry;
  h2h?: H2HEntry;
  deep?: EventDeepInfo;
  leagueName?: string;
  claudeVerdict?: ClaudeVerdict;
}

const RISK_LABELS: Record<string, string> = {
  foarte_sigur: 'Foarte sigur',
  sigur: 'Sigur',
  moderat: 'Moderat',
  riscant: 'Riscant',
};

export const EventListCard: React.FC<EventListCardProps> = ({
  event: e, prediction, homeForm, awayForm, h2h, deep, leagueName, claudeVerdict,
}) => {
  const [expanded, setExpanded] = useState(false);

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

  return (
    <div
      className="rounded-2xl overflow-hidden"
      style={{ background: 'var(--bp-card)', border: '1px solid rgba(255,255,255,0.08)' }}
    >
      <div className="flex items-center justify-between px-3 pt-3 pb-1">
        <span className="text-[10px] text-[#6b7a9e] font-medium tracking-wide truncate max-w-[70%]">
          {leagueName ?? 'Ligă necunoscută'} · {formatDate(e.event_date)}
        </span>
        {weather?.icon && (
          <span className="text-[10px] text-[#6b7a9e] flex-shrink-0">
            {weather.icon} {weather.temperature_c != null ? `${Math.round(weather.temperature_c)}°` : ''}
          </span>
        )}
      </div>

      <div className="flex items-center justify-between px-3 py-2">
        <div className="flex items-center gap-2 flex-1 min-w-0">
          <TeamLogo id={e.home_team_id} size={28} />
          <span className="text-sm font-bold text-[#e8eeff] truncate">{e.home_team}</span>
        </div>
        <span className="text-[10px] font-bold text-[#303d57] mx-2 flex-shrink-0">VS</span>
        <div className="flex items-center gap-2 flex-1 min-w-0 justify-end">
          <span className="text-sm font-bold text-[#e8eeff] truncate text-right">{e.away_team}</span>
          <TeamLogo id={e.away_team_id} size={28} />
        </div>
      </div>

      <div className="mx-3 mb-2.5 rounded-xl p-3" style={{ background: 'var(--bp-card2)' }}>
        {hasProbs ? (
          <div className="flex items-center divide-x divide-white/10">
            <ProbCol label="1" value={mr!.prob_home} />
            <ProbCol label="X" value={mr!.prob_draw} />
            <ProbCol label="2" value={mr!.prob_away} />
            {mostLikely && (
              <div className="flex-1 flex flex-col items-center gap-0.5 px-1.5">
                <span className="text-[8px] font-bold uppercase tracking-wider text-[#6b7a9e]">SCOR</span>
                <span className="text-sm font-bold text-[#4a9eff]">{mostLikely}</span>
              </div>
            )}
          </div>
        ) : (
          <p className="text-[10px] text-[#6b7a9e] text-center py-1">Predicție AI încă indisponibilă pentru acest meci</p>
        )}
      </div>

      {claudeVerdict && (
        <div
          className="mx-3 mb-2.5 rounded-xl p-3 border"
          style={{ borderColor: '#a78bfa55', background: '#a78bfa14' }}
        >
          <div className="flex items-center gap-1.5 mb-1.5">
            <Sparkles className="w-3 h-3" style={{ color: '#a78bfa' }} />
            <span className="text-[9px] font-bold uppercase tracking-widest" style={{ color: '#a78bfa' }}>
              Verdict Claude AI
            </span>
            {claudeVerdict.accumulator_eligible && (
              <span className="ml-auto text-[8px] font-bold px-1.5 py-0.5 rounded-full bg-[#00e87a22] text-[#00e87a]">
                ★ ACUMULATOR
              </span>
            )}
          </div>
          <div className="flex items-center justify-between">
            <span className="text-sm font-bold text-[#e8eeff]">{claudeVerdict.market_label}</span>
            <span className="text-lg font-black" style={{ color: '#a78bfa' }}>
              {claudeVerdict.probability.toFixed(0)}%
            </span>
          </div>
          <p className="text-[10px] text-[#6b7a9e] leading-relaxed mt-1">{claudeVerdict.rationale}</p>

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

          <div className="flex items-center justify-between mt-1.5 text-[9px] text-[#6b7a9e]">
            <span>Risc: {RISK_LABELS[claudeVerdict.risk_tier] ?? claudeVerdict.risk_tier}</span>
            {claudeVerdict.odds != null && (
              <span>
                @{claudeVerdict.odds.toFixed(2)}
                {claudeVerdict.odds_is_market && claudeVerdict.bookmaker ? ` · ${claudeVerdict.bookmaker}` : ''}
                {!claudeVerdict.odds_is_market && ' (fair)'}
              </span>
            )}
          </div>
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
  );
};

const ProbCol: React.FC<{ label: string; value?: number }> = ({ label, value }) => (
  <div className="flex-1 flex flex-col items-center gap-0.5 px-1.5">
    <span className="text-[8px] font-bold uppercase tracking-wider text-[#6b7a9e]">{label}</span>
    <span className="text-sm font-bold text-[#e8eeff]">{value != null ? `${value.toFixed(0)}%` : '—'}</span>
  </div>
);

const MiniStat: React.FC<{ label: string; value: string; positive?: boolean }> = ({ label, value, positive }) => (
  <div className="rounded-lg py-1 flex flex-col items-center" style={{ background: 'var(--bp-surface)' }}>
    <span className="text-[7px] font-bold uppercase tracking-wider text-[#6b7a9e]">{label}</span>
    <span
      className="text-[11px] font-bold"
      style={{ color: positive === true ? '#00e87a' : positive === false ? '#ff5c7a' : '#e8eeff' }}
    >
      {value}
    </span>
  </div>
);

const TinyChip: React.FC<{ text: string }> = ({ text }) => (
  <span className="text-[8px] px-1.5 py-0.5 rounded-md text-[#a78bfa]" style={{ background: '#a78bfa1f' }}>
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
