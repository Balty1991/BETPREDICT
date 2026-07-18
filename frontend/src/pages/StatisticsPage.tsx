import React, { useMemo, useState } from 'react';
import { ChevronDown, ChevronUp, Trash2, Target, TrendingUp, TrendingDown, Bookmark, Ticket } from 'lucide-react';
import { AreaChart, Area, BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid } from 'recharts';
import { useSavedPredictions } from '@/hooks/useSavedPredictions';
import { useSavedTickets } from '@/hooks/useSavedTickets';
import { formatDate, formatTicketProb, MIN_DISPLAY_ODDS } from '@/utils/filters';
import { profitUnits } from '@/utils/settlement';
import type { SavedPrediction, SavedTicket } from '@/types/betpredict';

const RISK_LABELS: Record<string, string> = {
  foarte_sigur: 'Foarte sigur', sigur: 'Sigur', moderat: 'Moderat', riscant: 'Riscant',
};
const RISK_LABEL_COLORS: Record<string, string> = {
  'Foarte sigur': '#00e87a', 'Sigur': '#4a9eff', 'Moderat': '#f5a623', 'Riscant': '#ff5c7a',
};

interface Breakdown { label: string; count: number; wins: number; wr: number; roi: number }

function buildBreakdown(settled: SavedPrediction[], keyFn: (p: SavedPrediction) => string): Breakdown[] {
  const map = new Map<string, { count: number; wins: number; profit: number }>();
  for (const p of settled) {
    const k = keyFn(p);
    const cur = map.get(k) ?? { count: 0, wins: 0, profit: 0 };
    cur.count++;
    if (p.status === 'won') cur.wins++;
    cur.profit += profitUnits(p.status as 'won' | 'lost', p.odds);
    map.set(k, cur);
  }
  return Array.from(map.entries())
    .map(([label, v]) => ({
      label, count: v.count, wins: v.wins,
      wr: Math.round((v.wins / v.count) * 100),
      roi: Math.round((v.profit / v.count) * 1000) / 10,
    }))
    .sort((a, b) => b.count - a.count);
}

function buildRecommendations(settled: SavedPrediction[], byMarket: Breakdown[], byRisk: Breakdown[]): string[] {
  if (settled.length < 5) {
    return [`Mai salvează ${5 - settled.length} predicții decontate ca să vezi tendințe fiabile.`];
  }
  const tips: string[] = [];
  const eligible = byMarket.filter(m => m.count >= 3);
  const best = [...eligible].sort((a, b) => b.wr - a.wr)[0];
  if (best) tips.push(`Cel mai bun win rate: "${best.label}" — ${best.wr}% din ${best.count} predicții salvate.`);
  const worst = [...eligible].sort((a, b) => a.wr - b.wr)[0];
  if (worst && worst.wr < 45 && worst.label !== best?.label) {
    tips.push(`Win rate scăzut pe "${worst.label}" (${worst.wr}%) — ai grijă la acest tip de piață.`);
  }
  const foarteSigur = byRisk.find(r => r.label === 'Foarte sigur');
  if (foarteSigur && foarteSigur.count >= 3) {
    tips.push(
      foarteSigur.wr >= 70
        ? `Verdictele "Foarte sigur" confirmă încrederea: ${foarteSigur.wr}% win rate din ${foarteSigur.count}.`
        : `Verdictele "Foarte sigur" au doar ${foarteSigur.wr}% win rate — sub așteptări pentru acest nivel de risc.`
    );
  }
  const overallRoi = settled.reduce((acc, p) => acc + profitUnits(p.status as 'won' | 'lost', p.odds), 0) / settled.length;
  tips.push(
    overallRoi > 0
      ? `ROI general pozitiv (+${Math.round(overallRoi * 1000) / 10}%/pariu) — strategia curentă funcționează.`
      : `ROI general negativ (${Math.round(overallRoi * 1000) / 10}%/pariu) — ia în calcul doar verdicte "sigur"/"foarte sigur".`
  );
  return tips;
}

export const StatisticsPage: React.FC = () => {
  const { predictions: allPredictions, remove } = useSavedPredictions();
  const { tickets, remove: removeTicket } = useSavedTickets();

  // Nu contorizăm predicțiile cu cotă sub prag (ex. @1.04) — nici la W/L, nici la ROI.
  const predictions = useMemo(
    () => allPredictions.filter(p => (p.odds ?? 0) >= MIN_DISPLAY_ODDS),
    [allPredictions]
  );

  const settledTickets = useMemo(
    () => tickets.filter(t => t.status !== 'pending').sort((a, b) => (b.settled_at ?? '').localeCompare(a.settled_at ?? '')),
    [tickets]
  );
  const pendingTickets = useMemo(
    () => tickets.filter(t => t.status === 'pending'),
    [tickets]
  );
  const ticketWins = settledTickets.filter(t => t.status === 'won').length;
  const ticketLosses = settledTickets.filter(t => t.status === 'lost').length;
  const ticketWinRate = settledTickets.length ? Math.round((ticketWins / settledTickets.length) * 100) : null;
  const ticketProfit = settledTickets.reduce((acc, t) => acc + profitUnits(t.status as 'won' | 'lost', t.combined_odds), 0);
  const ticketRoi = settledTickets.length ? Math.round((ticketProfit / settledTickets.length) * 1000) / 10 : null;

  const settled = useMemo(
    () => predictions.filter(p => p.status !== 'pending').sort((a, b) => (b.settled_at ?? '').localeCompare(a.settled_at ?? '')),
    [predictions]
  );
  const pending = useMemo(
    () => predictions.filter(p => p.status === 'pending').sort((a, b) => new Date(a.event_date).getTime() - new Date(b.event_date).getTime()),
    [predictions]
  );

  const wins = settled.filter(p => p.status === 'won').length;
  const losses = settled.filter(p => p.status === 'lost').length;
  const winRate = settled.length ? Math.round((wins / settled.length) * 100) : null;
  const totalProfit = settled.reduce((acc, p) => acc + profitUnits(p.status as 'won' | 'lost', p.odds), 0);
  const roi = settled.length ? Math.round((totalProfit / settled.length) * 1000) / 10 : null;

  const cumulativeData = useMemo(() => {
    const chrono = [...settled].sort((a, b) => (a.settled_at ?? '').localeCompare(b.settled_at ?? ''));
    let cum = 0;
    return chrono.map((p, i) => {
      cum += profitUnits(p.status as 'won' | 'lost', p.odds);
      return { i: i + 1, profit: Math.round(cum * 100) / 100 };
    });
  }, [settled]);

  const byMarket = useMemo(() => buildBreakdown(settled, p => p.market_label), [settled]);
  const byRisk = useMemo(() => buildBreakdown(settled, p => RISK_LABELS[p.risk_tier] ?? p.risk_tier), [settled]);
  const recommendations = useMemo(() => buildRecommendations(settled, byMarket, byRisk), [settled, byMarket, byRisk]);

  if (predictions.length === 0 && tickets.length === 0) {
    return <EmptyJournal />;
  }

  return (
    <div className="pt-4 pb-4 flex flex-col gap-4">
      <div>
        <h2 className="text-lg font-extrabold text-[#e8eeff]">📊 Statistici</h2>
        <p className="text-[10px] text-[#6b7a9e]">
          {predictions.length} predicții salvate · {settled.length} decontate · {pending.length} în așteptare
        </p>
      </div>

      <div className="grid grid-cols-4 gap-2">
        <StatTile label="W" value={String(wins)} color="#00e87a" />
        <StatTile label="L" value={String(losses)} color="#ff3d5a" />
        <StatTile label="WR" value={winRate != null ? `${winRate}%` : '—'} color={winRate != null && winRate >= 55 ? '#00e87a' : '#f5a623'} />
        <StatTile label="ROI" value={roi != null ? `${roi > 0 ? '+' : ''}${roi}%` : '—'} color={roi != null && roi > 0 ? '#00e87a' : '#ff3d5a'} />
      </div>

      {settled.length > 0 && (
        <div className="rounded-[22px] p-4" style={{ background: 'var(--bp-card)', border: '1px solid var(--bp-border)' }}>
          <div className="flex items-center justify-between mb-2">
            <p className="text-[10px] font-bold uppercase tracking-widest text-[#6b7a9e]">Curba de profit (unități, miză 1u/pariu)</p>
            <span className="text-sm font-black" style={{ color: totalProfit >= 0 ? '#00e87a' : '#ff3d5a' }}>
              {totalProfit >= 0 ? '+' : ''}{totalProfit.toFixed(2)}u
            </span>
          </div>
          <ResponsiveContainer width="100%" height={140}>
            <AreaChart data={cumulativeData} margin={{ top: 5, right: 5, bottom: 0, left: -20 }}>
              <defs>
                <linearGradient id="profitGradient" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor={totalProfit >= 0 ? '#00e87a' : '#ff3d5a'} stopOpacity={0.4} />
                  <stop offset="100%" stopColor={totalProfit >= 0 ? '#00e87a' : '#ff3d5a'} stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--bp-border)" vertical={false} />
              <XAxis dataKey="i" tick={{ fill: '#6b7a9e', fontSize: 9 }} />
              <YAxis tick={{ fill: '#6b7a9e', fontSize: 9 }} />
              <Tooltip contentStyle={{ background: 'var(--bp-card)', border: '1px solid var(--bp-border2)', borderRadius: 8, fontSize: 11, color: 'var(--bp-text)' }} />
              <Area type="monotone" dataKey="profit" stroke={totalProfit >= 0 ? '#00e87a' : '#ff3d5a'} strokeWidth={2} fill="url(#profitGradient)" />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      )}

      <Accordion title="Performanță pe tip de piață" defaultOpen={byMarket.length > 0}>
        {byMarket.length === 0 ? (
          <p className="text-[#6b7a9e] text-xs text-center py-3">Salvează și decontează predicții ca să vezi acest breakdown.</p>
        ) : (
          <>
            <ResponsiveContainer width="100%" height={Math.max(120, byMarket.length * 34)}>
              <BarChart data={byMarket} layout="vertical" margin={{ top: 0, right: 20, bottom: 0, left: 0 }}>
                <XAxis type="number" domain={[0, 100]} tick={{ fill: '#6b7a9e', fontSize: 9 }} />
                <YAxis type="category" dataKey="label" width={110} tick={{ fill: '#e8eeff', fontSize: 9 }} />
                <Tooltip contentStyle={{ background: 'var(--bp-card)', border: '1px solid var(--bp-border2)', borderRadius: 8, fontSize: 11, color: 'var(--bp-text)' }} formatter={(v: number) => [`${v}%`, 'Win rate']} />
                <Bar dataKey="wr" fill="#4a9eff" radius={[0, 4, 4, 0]} />
              </BarChart>
            </ResponsiveContainer>
            <BreakdownList rows={byMarket} />
          </>
        )}
      </Accordion>

      <Accordion title="Performanță pe nivel de risc">
        {byRisk.length === 0 ? (
          <p className="text-[#6b7a9e] text-xs text-center py-3">Date insuficiente</p>
        ) : (
          <>
            <ResponsiveContainer width="100%" height={Math.max(100, byRisk.length * 34)}>
              <BarChart data={byRisk} layout="vertical" margin={{ top: 0, right: 20, bottom: 0, left: 0 }}>
                <XAxis type="number" domain={[0, 100]} tick={{ fill: '#6b7a9e', fontSize: 9 }} />
                <YAxis type="category" dataKey="label" width={90} tick={{ fill: '#e8eeff', fontSize: 9 }} />
                <Tooltip contentStyle={{ background: 'var(--bp-card)', border: '1px solid var(--bp-border2)', borderRadius: 8, fontSize: 11, color: 'var(--bp-text)' }} formatter={(v: number) => [`${v}%`, 'Win rate']} />
                <Bar dataKey="wr" fill="#a78bfa" radius={[0, 4, 4, 0]} />
              </BarChart>
            </ResponsiveContainer>
            <BreakdownList rows={byRisk} colorFor={label => RISK_LABEL_COLORS[label]} />
          </>
        )}
      </Accordion>

      <div className="rounded-[22px] p-4 flex flex-col gap-2.5" style={{ background: 'var(--bp-card)', border: '1px solid #a78bfa33' }}>
        <div className="flex items-center gap-1.5">
          <Target className="w-3.5 h-3.5" style={{ color: '#a78bfa' }} />
          <p className="text-[10px] font-bold uppercase tracking-widest" style={{ color: '#a78bfa' }}>Recomandări</p>
        </div>
        {recommendations.map((tip, i) => (
          <div key={i} className="flex items-start gap-2 text-xs text-[#e8eeff] leading-relaxed">
            {tip.includes('negativ') || tip.includes('scăzut') ? (
              <TrendingDown className="w-3.5 h-3.5 flex-shrink-0 mt-0.5" style={{ color: '#ff3d5a' }} />
            ) : (
              <TrendingUp className="w-3.5 h-3.5 flex-shrink-0 mt-0.5" style={{ color: '#00e87a' }} />
            )}
            <span>{tip}</span>
          </div>
        ))}
      </div>

      <Accordion title={`În așteptare (${pending.length})`} defaultOpen={pending.length > 0}>
        {pending.length === 0 ? (
          <p className="text-[#6b7a9e] text-xs text-center py-3">Nimic în așteptare — salvează un verdict din tab-ul Predicții.</p>
        ) : (
          <div className="flex flex-col gap-2">
            {pending.map(p => <SavedCard key={p.id} p={p} onRemove={() => remove(p.id)} />)}
          </div>
        )}
      </Accordion>

      {settled.length > 0 && (
        <Accordion title={`Istoric decontat (${settled.length})`}>
          <div className="flex flex-col gap-2">
            {settled.map(p => <SavedCard key={p.id} p={p} onRemove={() => remove(p.id)} />)}
          </div>
        </Accordion>
      )}

      {tickets.length > 0 && (
        <>
          <div className="flex items-center gap-1.5 mt-1">
            <Ticket className="w-3.5 h-3.5" style={{ color: '#a78bfa' }} />
            <h3 className="text-sm font-extrabold text-[#e8eeff]">Bilete plasate</h3>
          </div>

          <div className="grid grid-cols-4 gap-2">
            <StatTile label="W" value={String(ticketWins)} color="#00e87a" />
            <StatTile label="L" value={String(ticketLosses)} color="#ff3d5a" />
            <StatTile label="WR" value={ticketWinRate != null ? `${ticketWinRate}%` : '—'} color={ticketWinRate != null && ticketWinRate >= 50 ? '#00e87a' : '#f5a623'} />
            <StatTile label="ROI" value={ticketRoi != null ? `${ticketRoi > 0 ? '+' : ''}${ticketRoi}%` : '—'} color={ticketRoi != null && ticketRoi > 0 ? '#00e87a' : '#ff3d5a'} />
          </div>

          <Accordion title={`Bilete în așteptare (${pendingTickets.length})`} defaultOpen={pendingTickets.length > 0}>
            {pendingTickets.length === 0 ? (
              <p className="text-[#6b7a9e] text-xs text-center py-3">Niciun bilet în așteptare — plasează unul din tab-ul Acumulator AI.</p>
            ) : (
              <div className="flex flex-col gap-2">
                {pendingTickets.map(t => <SavedTicketCard key={t.id} t={t} onRemove={() => removeTicket(t.id)} />)}
              </div>
            )}
          </Accordion>

          {settledTickets.length > 0 && (
            <Accordion title={`Bilete decontate (${settledTickets.length})`}>
              <div className="flex flex-col gap-2">
                {settledTickets.map(t => <SavedTicketCard key={t.id} t={t} onRemove={() => removeTicket(t.id)} />)}
              </div>
            </Accordion>
          )}
        </>
      )}
    </div>
  );
};

const StatTile: React.FC<{ label: string; value: string; color: string }> = ({ label, value, color }) => (
  <div className="flex flex-col items-center gap-0.5 rounded-xl py-2.5 border-t-2" style={{ background: 'var(--bp-surface)', borderTopColor: color }}>
    <span className="text-[9px] font-bold uppercase tracking-widest text-[#6b7a9e]">{label}</span>
    <span className="text-base font-bold" style={{ color }}>{value}</span>
  </div>
);

const BreakdownList: React.FC<{ rows: Breakdown[]; colorFor?: (label: string) => string | undefined }> = ({ rows, colorFor }) => (
  <div className="flex flex-col gap-1.5 mt-3 pt-2 border-t border-white/5">
    {rows.map((m, i) => (
      <div key={i} className="flex items-center justify-between py-1.5 px-3 rounded-lg bg-white/[0.03]">
        <div className="flex items-center gap-1.5 min-w-0">
          {colorFor?.(m.label) && <div className="w-2 h-2 rounded-full flex-shrink-0" style={{ background: colorFor(m.label) }} />}
          <span className="text-xs text-[#e8eeff] truncate">{m.label}</span>
          <span className="text-[9px] text-[#6b7a9e] flex-shrink-0">{m.count}</span>
        </div>
        <div className="flex items-center gap-2 flex-shrink-0">
          <span className="text-[10px] text-[#6b7a9e]">{m.wr}% WR</span>
          <span className="text-[10px] font-bold" style={{ color: m.roi >= 0 ? '#00e87a' : '#ff3d5a' }}>
            {m.roi >= 0 ? '+' : ''}{m.roi}%
          </span>
        </div>
      </div>
    ))}
  </div>
);

const Accordion: React.FC<{ title: string; children: React.ReactNode; defaultOpen?: boolean }> = ({ title, children, defaultOpen = false }) => {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div className="rounded-[22px] overflow-hidden" style={{ background: 'var(--bp-card)', border: '1px solid var(--bp-border)' }}>
      <button onClick={() => setOpen(o => !o)} className="w-full flex items-center justify-between px-4 py-3.5">
        <span className="text-sm font-bold text-[#e8eeff]">{title}</span>
        {open ? <ChevronUp className="w-4 h-4 text-[#6b7a9e]" /> : <ChevronDown className="w-4 h-4 text-[#6b7a9e]" />}
      </button>
      {open && <div className="px-4 pb-4">{children}</div>}
    </div>
  );
};

const SavedCard: React.FC<{ p: SavedPrediction; onRemove: () => void }> = ({ p, onRemove }) => {
  const isWin = p.status === 'won';
  const isLoss = p.status === 'lost';
  const statusColor = isWin ? '#00e87a' : isLoss ? '#ff3d5a' : '#f5a623';
  const statusLabel = isWin ? 'WIN' : isLoss ? 'LOSS' : 'PENDING';
  const profit = p.status !== 'pending' ? profitUnits(p.status as 'won' | 'lost', p.odds) : null;

  return (
    <div className="rounded-xl p-3 flex flex-col gap-1.5" style={{ background: 'var(--bp-card2)', border: `1px solid ${statusColor}22` }}>
      <div className="flex items-center justify-between">
        <span className="text-[10px] text-[#6b7a9e] truncate max-w-[55%]">
          {p.league ? `${p.league} · ` : ''}{formatDate(p.event_date)}
        </span>
        <div className="flex items-center gap-2">
          {p.final_score && <span className="text-[10px] font-mono text-[#6b7a9e]">{p.final_score}</span>}
          <span className="text-[9px] font-bold px-2 py-0.5 rounded-full" style={{ color: statusColor, background: `${statusColor}22` }}>
            {statusLabel}
          </span>
          <button onClick={onRemove} aria-label="Șterge predicția salvată" className="p-2 -m-2 text-[#6b7a9e] hover:text-[#ff3d5a] transition-colors">
            <Trash2 className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>
      <div className="flex items-center justify-between">
        <div className="flex flex-col gap-0.5 flex-1 min-w-0">
          <span className="text-sm font-bold text-[#e8eeff] truncate">
            {p.home_team} <span className="text-[#303d57]">vs</span> {p.away_team}
          </span>
          <span className="text-[10px] text-[#6b7a9e]">⚡ {p.market_label} · {p.probability.toFixed(0)}% · @{p.odds.toFixed(2)}</span>
        </div>
        {profit != null && (
          <span className="text-sm font-bold ml-3 flex-shrink-0" style={{ color: profit >= 0 ? '#00e87a' : '#ff3d5a' }}>
            {profit > 0 ? '+' : ''}{profit.toFixed(2)}u
          </span>
        )}
      </div>
    </div>
  );
};

const SavedTicketCard: React.FC<{ t: SavedTicket; onRemove: () => void }> = ({ t, onRemove }) => {
  const [open, setOpen] = useState(false);
  const isWin = t.status === 'won';
  const isLoss = t.status === 'lost';
  const statusColor = isWin ? '#00e87a' : isLoss ? '#ff3d5a' : '#f5a623';
  const statusLabel = isWin ? 'WIN' : isLoss ? 'LOSS' : 'PENDING';
  const profit = t.status !== 'pending' ? profitUnits(t.status as 'won' | 'lost', t.combined_odds) : null;

  return (
    <div className="rounded-xl p-3 flex flex-col gap-1.5" style={{ background: 'var(--bp-card2)', border: `1px solid ${statusColor}22` }}>
      <div className="flex items-center justify-between">
        <span className="text-[10px] text-[#6b7a9e] truncate max-w-[55%]">{t.label} · {t.legs.length} selecții</span>
        <div className="flex items-center gap-2">
          <span className="text-[9px] font-bold px-2 py-0.5 rounded-full" style={{ color: statusColor, background: `${statusColor}22` }}>
            {statusLabel}
          </span>
          <button onClick={onRemove} aria-label="Șterge biletul salvat" className="p-2 -m-2 text-[#6b7a9e] hover:text-[#ff3d5a] transition-colors">
            <Trash2 className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>
      <div className="flex items-center justify-between">
        <span className="text-sm font-bold text-[#e8eeff]">@{t.combined_odds.toFixed(2)} · {formatTicketProb(t.combined_probability_pct)}</span>
        {profit != null && (
          <span className="text-sm font-bold flex-shrink-0" style={{ color: profit >= 0 ? '#00e87a' : '#ff3d5a' }}>
            {profit > 0 ? '+' : ''}{profit.toFixed(2)}u
          </span>
        )}
      </div>
      <button onClick={() => setOpen(v => !v)} className="text-[9px] text-[#6b7a9e] text-left mt-0.5">
        {open ? 'Ascunde selecțiile' : 'Arată selecțiile'} {open ? <ChevronUp className="w-3 h-3 inline" /> : <ChevronDown className="w-3 h-3 inline" />}
      </button>
      {open && (
        <div className="flex flex-col gap-1 mt-1 pt-1.5 border-t border-white/5">
          {t.legs.map((leg, i) => {
            const legIsWin = leg.status === 'won';
            const legIsLoss = leg.status === 'lost';
            const legColor = legIsWin ? '#00e87a' : legIsLoss ? '#ff3d5a' : '#6b7a9e';
            const legLabel = legIsWin ? 'WIN' : legIsLoss ? 'LOSS' : 'PENDING';
            return (
              <div key={i} className="flex items-center justify-between text-[10px] py-0.5 gap-2">
                <span className="text-[#e8eeff] truncate flex-1 min-w-0">{leg.home_team} vs {leg.away_team}</span>
                <span className="text-[#6b7a9e] flex-shrink-0">{leg.market_label} · @{leg.odds.toFixed(2)}</span>
                <span className="flex items-center gap-1 flex-shrink-0">
                  {leg.final_score && <span className="font-mono text-[#6b7a9e]">{leg.final_score}</span>}
                  <span className="font-bold px-1.5 py-0.5 rounded-full" style={{ color: legColor, background: `${legColor}22` }}>
                    {legLabel}
                  </span>
                </span>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
};

const EmptyJournal: React.FC = () => (
  <div className="pt-4 pb-4 flex flex-col gap-4">
    <div>
      <h2 className="text-lg font-extrabold text-[#e8eeff]">📊 Statistici</h2>
      <p className="text-[10px] text-[#6b7a9e]">Jurnalul tău personal de predicții</p>
    </div>
    <div className="flex flex-col items-center justify-center py-16 gap-4">
      <div className="w-16 h-16 rounded-2xl flex items-center justify-center" style={{ background: '#a78bfa1a', border: '1px solid #a78bfa33' }}>
        <Bookmark className="w-7 h-7" style={{ color: '#a78bfa' }} />
      </div>
      <div className="text-center">
        <p className="font-bold text-[#e8eeff] mb-1">Nicio predicție salvată încă</p>
        <p className="text-[#6b7a9e] text-sm max-w-[260px] leading-relaxed">
          Din tab-ul Predicții, apasă „Salvează" pe orice verdict Claude AI ca să-l urmărești aici —
          win/lose, win rate, ROI și recomandări, actualizate automat pe măsură ce meciurile se termină.
        </p>
      </div>
    </div>
  </div>
);
