import React, { useState } from 'react';
import { ChevronDown, ChevronUp } from 'lucide-react';
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell } from 'recharts';
import { useBetPredictData } from '@/hooks/useBetPredictData';
import { journalStats, marketLabel, formatDate, effectiveScore, gradeColor } from '@/utils/filters';
import type { JournalEntry } from '@/types/betpredict';

type MainTab = 'predictii' | 'premium';

export const StatisticsPage: React.FC = () => {
  const { journal, signals, loading } = useBetPredictData();
  const [mainTab, setMainTab] = useState<MainTab>('predictii');
  const stats = journalStats(journal);

  return (
    <div className="pt-4 pb-4 flex flex-col gap-4">
      <div>
        <h2 className="text-lg font-extrabold text-[#e8eeff]">📊 Statistici</h2>
        <p className="text-[10px] text-[#6b7a9e]">Performanță completă · {stats.settled} pariuri decontate</p>
      </div>

      <div className="flex rounded-xl overflow-hidden border border-white/10">
        {(['predictii', 'premium'] as MainTab[]).map(t => (
          <button
            key={t}
            onClick={() => setMainTab(t)}
            className="flex-1 py-2.5 text-xs font-bold uppercase tracking-wider transition-colors"
            style={{
              background: mainTab === t ? 'var(--bp-card2)' : 'transparent',
              color: mainTab === t ? 'var(--bp-text)' : 'var(--bp-muted)',
              borderRight: t === 'predictii' ? '1px solid var(--bp-border)' : undefined,
            }}
          >
            {t === 'predictii' ? 'Predicții' : 'Premium'}
          </button>
        ))}
      </div>

      {mainTab === 'predictii' ? (
        <PredictiiStats stats={stats} journal={journal} signals={signals} loading={loading} />
      ) : (
        <PremiumStats journal={journal} signals={signals} loading={loading} />
      )}
    </div>
  );
};

const PREMIUM_GRADES = new Set(['A+', 'A']);

const PremiumStats: React.FC<{ journal: JournalEntry[]; signals: SignalsArray; loading: boolean }> = ({ journal, signals, loading }) => {
  const isPremiumEntry = (e: JournalEntry) => {
    const sig = signals.find(s => String(s.event_id) === String(e.event_id) && s.market === e.market);
    if (!sig) return false;
    const grade = sig.quality_grade_v6 ?? sig.quality_grade ?? '';
    return PREMIUM_GRADES.has(grade);
  };

  const premiumSignals = signals.filter(s => {
    const grade = s.quality_grade_v6 ?? s.quality_grade ?? '';
    return PREMIUM_GRADES.has(grade);
  });

  const pending = journal.filter(e => e.status === 'pending' && isPremiumEntry(e));
  const settled = journal.filter(e => e.status === 'settled' && isPremiumEntry(e)).sort((a, b) => {
    const da = a.settled_at ?? a.event_date ?? '';
    const db = b.settled_at ?? b.event_date ?? '';
    return db.localeCompare(da);
  });

  const stats = journalStats(settled.concat(pending));
  const gradeData = buildGradeData(settled);
  const evData = buildEvData(settled);
  const scoreData = buildScoreData(premiumSignals);
  const marketData = buildMarketData(settled);

  return (
    <div className="flex flex-col gap-3">
      <Accordion title="Performanță generală" defaultOpen>
        <div className="grid grid-cols-4 gap-2 mb-3">
          <StatPill label="W" value={String(stats.wins)} color="#00e87a" />
          <StatPill label="L" value={String(stats.losses)} color="#ff3d5a" />
          <StatPill label="WR" value={stats.wr != null ? `${stats.wr}%` : '—'} color={stats.wr != null && stats.wr >= 55 ? '#00e87a' : '#ffb830'} />
          <StatPill label="ROI" value={stats.roi != null ? `${stats.roi > 0 ? '+' : ''}${stats.roi}%` : '—'} color={stats.roi != null && stats.roi > 0 ? '#00e87a' : '#ff3d5a'} />
        </div>
        {stats.settled > 0 && (
          <div className="flex items-center justify-between pt-2 border-t border-white/5">
            <span className="text-[10px] text-[#6b7a9e]">{stats.settled} decontate · {stats.pending} în așteptare</span>
            <span className="text-[10px] font-bold" style={{ color: stats.profit >= 0 ? '#00e87a' : '#ff3d5a' }}>
              {stats.profit >= 0 ? '+' : ''}{stats.profit.toFixed(2)}u
            </span>
          </div>
        )}
      </Accordion>

      <Accordion title="Distribuție grade">
        {gradeData.length === 0 ? (
          <p className="text-[#6b7a9e] text-xs text-center py-3">Date insuficiente</p>
        ) : (
          <ResponsiveContainer width="100%" height={140}>
            <BarChart data={gradeData} margin={{ top: 5, right: 5, bottom: 5, left: -20 }}>
              <XAxis dataKey="grade" tick={{ fill: '#6b7a9e', fontSize: 10 }} />
              <YAxis tick={{ fill: '#6b7a9e', fontSize: 9 }} />
              <Tooltip contentStyle={{ background: 'var(--bp-card)', border: '1px solid var(--bp-border2)', borderRadius: 8, fontSize: 11, color: 'var(--bp-text)' }} />
              <Bar dataKey="count" radius={[4, 4, 0, 0]}>
                {gradeData.map((entry, i) => (
                  <Cell key={i} fill={gradeColor(entry.grade)} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        )}
        <GradeLegend />
      </Accordion>

      <Accordion title="Distribuție scoruri SmartBet">
        {scoreData.length === 0 ? (
          <p className="text-[#6b7a9e] text-xs text-center py-3">Date insuficiente</p>
        ) : (
          <ResponsiveContainer width="100%" height={140}>
            <BarChart data={scoreData} margin={{ top: 5, right: 5, bottom: 5, left: -20 }}>
              <XAxis dataKey="range" tick={{ fill: '#6b7a9e', fontSize: 9 }} />
              <YAxis tick={{ fill: '#6b7a9e', fontSize: 9 }} />
              <Tooltip contentStyle={{ background: 'var(--bp-card)', border: '1px solid var(--bp-border2)', borderRadius: 8, fontSize: 11, color: 'var(--bp-text)' }} />
              <Bar dataKey="count" fill="#ffb830" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        )}
      </Accordion>

      <Accordion title="Distribuție EV">
        {evData.length === 0 ? (
          <p className="text-[#6b7a9e] text-xs text-center py-3">Date insuficiente</p>
        ) : (
          <ResponsiveContainer width="100%" height={140}>
            <BarChart data={evData} margin={{ top: 5, right: 5, bottom: 5, left: -20 }}>
              <XAxis dataKey="range" tick={{ fill: '#6b7a9e', fontSize: 9 }} />
              <YAxis tick={{ fill: '#6b7a9e', fontSize: 9 }} />
              <Tooltip contentStyle={{ background: 'var(--bp-card)', border: '1px solid var(--bp-border2)', borderRadius: 8, fontSize: 11, color: 'var(--bp-text)' }} />
              <Bar dataKey="count" fill="#00e87a" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        )}
      </Accordion>

      <Accordion title="Performanță per piață">
        {marketData.length === 0 ? (
          <p className="text-[#6b7a9e] text-xs text-center py-3">Date insuficiente</p>
        ) : (
          <div className="flex flex-col gap-2">
            {marketData.map((m, i) => (
              <div key={i} className="flex items-center justify-between py-2 px-3 rounded-xl bg-white/[0.03]">
                <div>
                  <span className="text-xs text-[#e8eeff]">{m.label}</span>
                  <span className="text-[9px] text-[#6b7a9e] ml-2">{m.count} pariuri</span>
                </div>
                <div className="flex items-center gap-2">
                  <span className="text-[10px] text-[#6b7a9e]">{m.wr}% WR</span>
                  <span className="text-[10px] font-bold" style={{ color: m.roi >= 0 ? '#00e87a' : '#ff3d5a' }}>
                    {m.roi >= 0 ? '+' : ''}{m.roi}%
                  </span>
                </div>
              </div>
            ))}
          </div>
        )}
      </Accordion>

      <Accordion title={`Pariuri în așteptare (${pending.length})`} defaultOpen>
        {loading ? (
          <div className="flex flex-col gap-2">
            {[1,2,3].map(i => <div key={i} className="h-14 rounded-xl bg-white/5 animate-pulse" />)}
          </div>
        ) : pending.length === 0 ? (
          <p className="text-[#6b7a9e] text-xs text-center py-3">Niciun pariu în așteptare</p>
        ) : (
          <div className="flex flex-col gap-2">
            {pending.map((e, i) => <JournalCard key={i} entry={e} />)}
          </div>
        )}
      </Accordion>

      {settled.length > 0 && (
        <Accordion title={`Istoric decontat (${settled.length})`}>
          <div className="flex flex-col gap-2">
            {settled.map((e, i) => <JournalCard key={i} entry={e} />)}
          </div>
        </Accordion>
      )}

      <Accordion title="Status componente ML">
        <div className="flex flex-col gap-2">
          {[
            { label: 'Engine v6 (CatBoost)', status: 'ACTIV', color: '#00e87a' },
            { label: 'VEYRA v5', status: 'ACTIV', color: '#00e87a' },
            { label: 'Calibrare probabilități', status: 'ACTIV', color: '#00e87a' },
            { label: 'EV Calculator', status: 'ACTIV', color: '#00e87a' },
            { label: 'Value Bet Detector', status: 'ACTIV', color: '#00e87a' },
            { label: 'Context Intelligence', status: 'ACTIV', color: '#00e87a' },
          ].map((item, i) => (
            <div key={i} className="flex items-center justify-between py-1.5 px-3 rounded-lg bg-white/[0.02]">
              <span className="text-xs text-[#6b7a9e]">{item.label}</span>
              <span className="text-[9px] font-bold px-2 py-0.5 rounded-full"
                style={{ color: item.color, background: `${item.color}22` }}>
                {item.status}
              </span>
            </div>
          ))}
        </div>
      </Accordion>
    </div>
  );
};

type SignalsArray = ReturnType<typeof useBetPredictData>['signals'];

const PredictiiStats: React.FC<{
  stats: ReturnType<typeof journalStats>;
  journal: JournalEntry[];
  signals: SignalsArray;
  loading: boolean;
}> = ({ stats, journal, signals, loading }) => {
  const settled = journal.filter(e => e.status === 'settled').sort((a, b) => {
    const da = a.settled_at ?? a.event_date ?? '';
    const db = b.settled_at ?? b.event_date ?? '';
    return db.localeCompare(da);
  });
  const pending = journal.filter(e => e.status === 'pending');

  const gradeData = buildGradeData(settled);
  const evData = buildEvData(settled);
  const scoreData = buildScoreData(signals);
  const marketData = buildMarketData(settled);

  return (
    <div className="flex flex-col gap-3">
      <Accordion title="Performanță generală" defaultOpen>
        <div className="grid grid-cols-4 gap-2 mb-3">
          <StatPill label="W" value={String(stats.wins)} color="#00e87a" />
          <StatPill label="L" value={String(stats.losses)} color="#ff3d5a" />
          <StatPill label="WR" value={stats.wr != null ? `${stats.wr}%` : '—'} color={stats.wr != null && stats.wr >= 55 ? '#00e87a' : '#ffb830'} />
          <StatPill label="ROI" value={stats.roi != null ? `${stats.roi > 0 ? '+' : ''}${stats.roi}%` : '—'} color={stats.roi != null && stats.roi > 0 ? '#00e87a' : '#ff3d5a'} />
        </div>
        {stats.settled > 0 && (
          <div className="flex items-center justify-between pt-2 border-t border-white/5">
            <span className="text-[10px] text-[#6b7a9e]">{stats.settled} decontate · {stats.pending} în așteptare</span>
            <span className="text-[10px] font-bold" style={{ color: stats.profit >= 0 ? '#00e87a' : '#ff3d5a' }}>
              {stats.profit >= 0 ? '+' : ''}{stats.profit.toFixed(2)}u
            </span>
          </div>
        )}
      </Accordion>

      <Accordion title="Distribuție grade">
        {gradeData.length === 0 ? (
          <p className="text-[#6b7a9e] text-xs text-center py-3">Date insuficiente</p>
        ) : (
          <ResponsiveContainer width="100%" height={140}>
            <BarChart data={gradeData} margin={{ top: 5, right: 5, bottom: 5, left: -20 }}>
              <XAxis dataKey="grade" tick={{ fill: '#6b7a9e', fontSize: 10 }} />
              <YAxis tick={{ fill: '#6b7a9e', fontSize: 9 }} />
              <Tooltip contentStyle={{ background: 'var(--bp-card)', border: '1px solid var(--bp-border2)', borderRadius: 8, fontSize: 11, color: 'var(--bp-text)' }} />
              <Bar dataKey="count" radius={[4, 4, 0, 0]}>
                {gradeData.map((entry, i) => (
                  <Cell key={i} fill={gradeColor(entry.grade)} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        )}
        <GradeLegend />
      </Accordion>

      <Accordion title="Distribuție scoruri SmartBet">
        {scoreData.length === 0 ? (
          <p className="text-[#6b7a9e] text-xs text-center py-3">Date insuficiente</p>
        ) : (
          <ResponsiveContainer width="100%" height={140}>
            <BarChart data={scoreData} margin={{ top: 5, right: 5, bottom: 5, left: -20 }}>
              <XAxis dataKey="range" tick={{ fill: '#6b7a9e', fontSize: 9 }} />
              <YAxis tick={{ fill: '#6b7a9e', fontSize: 9 }} />
              <Tooltip contentStyle={{ background: 'var(--bp-card)', border: '1px solid var(--bp-border2)', borderRadius: 8, fontSize: 11, color: 'var(--bp-text)' }} />
              <Bar dataKey="count" fill="#4a9eff" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        )}
      </Accordion>

      <Accordion title="Distribuție EV">
        {evData.length === 0 ? (
          <p className="text-[#6b7a9e] text-xs text-center py-3">Date insuficiente</p>
        ) : (
          <ResponsiveContainer width="100%" height={140}>
            <BarChart data={evData} margin={{ top: 5, right: 5, bottom: 5, left: -20 }}>
              <XAxis dataKey="range" tick={{ fill: '#6b7a9e', fontSize: 9 }} />
              <YAxis tick={{ fill: '#6b7a9e', fontSize: 9 }} />
              <Tooltip contentStyle={{ background: 'var(--bp-card)', border: '1px solid var(--bp-border2)', borderRadius: 8, fontSize: 11, color: 'var(--bp-text)' }} />
              <Bar dataKey="count" fill="#00e87a" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        )}
      </Accordion>

      <Accordion title="Performanță per piață">
        {marketData.length === 0 ? (
          <p className="text-[#6b7a9e] text-xs text-center py-3">Date insuficiente</p>
        ) : (
          <div className="flex flex-col gap-2">
            {marketData.map((m, i) => (
              <div key={i} className="flex items-center justify-between py-2 px-3 rounded-xl bg-white/[0.03]">
                <div>
                  <span className="text-xs text-[#e8eeff]">{m.label}</span>
                  <span className="text-[9px] text-[#6b7a9e] ml-2">{m.count} pariuri</span>
                </div>
                <div className="flex items-center gap-2">
                  <span className="text-[10px] text-[#6b7a9e]">{m.wr}% WR</span>
                  <span className="text-[10px] font-bold" style={{ color: m.roi >= 0 ? '#00e87a' : '#ff3d5a' }}>
                    {m.roi >= 0 ? '+' : ''}{m.roi}%
                  </span>
                </div>
              </div>
            ))}
          </div>
        )}
      </Accordion>

      <Accordion title={`Pariuri în așteptare (${pending.length})`} defaultOpen>
        {loading ? (
          <div className="flex flex-col gap-2">
            {[1,2,3].map(i => <div key={i} className="h-14 rounded-xl bg-white/5 animate-pulse" />)}
          </div>
        ) : pending.length === 0 ? (
          <p className="text-[#6b7a9e] text-xs text-center py-3">Niciun pariu în așteptare</p>
        ) : (
          <div className="flex flex-col gap-2">
            {pending.map((e, i) => <JournalCard key={i} entry={e} />)}
          </div>
        )}
      </Accordion>

      <Accordion title="Status componente ML">
        <div className="flex flex-col gap-2">
          {[
            { label: 'Engine v6 (CatBoost)', status: 'ACTIV', color: '#00e87a' },
            { label: 'VEYRA v5', status: 'ACTIV', color: '#00e87a' },
            { label: 'Calibrare probabilități', status: 'ACTIV', color: '#00e87a' },
            { label: 'EV Calculator', status: 'ACTIV', color: '#00e87a' },
            { label: 'Value Bet Detector', status: 'ACTIV', color: '#00e87a' },
            { label: 'Context Intelligence', status: 'ACTIV', color: '#00e87a' },
          ].map((item, i) => (
            <div key={i} className="flex items-center justify-between py-1.5 px-3 rounded-lg bg-white/[0.02]">
              <span className="text-xs text-[#6b7a9e]">{item.label}</span>
              <span className="text-[9px] font-bold px-2 py-0.5 rounded-full"
                style={{ color: item.color, background: `${item.color}22` }}>
                {item.status}
              </span>
            </div>
          ))}
        </div>
      </Accordion>
    </div>
  );
};

const Accordion: React.FC<{ title: string; children: React.ReactNode; defaultOpen?: boolean }> = ({ title, children, defaultOpen = false }) => {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div className="rounded-2xl overflow-hidden" style={{ background: 'var(--bp-card)', border: '1px solid var(--bp-border)' }}>
      <button onClick={() => setOpen(o => !o)} className="w-full flex items-center justify-between px-4 py-3">
        <span className="text-sm font-bold text-[#e8eeff]">{title}</span>
        {open ? <ChevronUp className="w-4 h-4 text-[#6b7a9e]" /> : <ChevronDown className="w-4 h-4 text-[#6b7a9e]" />}
      </button>
      {open && <div className="px-4 pb-4">{children}</div>}
    </div>
  );
};

const StatPill: React.FC<{ label: string; value: string; color: string }> = ({ label, value, color }) => (
  <div className="flex flex-col items-center gap-0.5 rounded-xl py-2 bg-white/[0.03]">
    <span className="text-[8px] font-bold uppercase tracking-widest text-[#6b7a9e]">{label}</span>
    <span className="text-base font-bold" style={{ color }}>{value}</span>
  </div>
);

const GradeLegend: React.FC = () => (
  <div className="mt-3 pt-2 border-t border-white/5">
    <p className="text-[9px] text-[#6b7a9e] font-bold uppercase tracking-wider mb-2">Legenda gradelor</p>
    <div className="flex flex-wrap gap-2">
      {[['A+', '#00e87a'], ['A', '#22c55e'], ['B', '#4a9eff'], ['C', '#fbbf24'], ['D', '#fb923c']].map(([g, c]) => (
        <div key={g} className="flex items-center gap-1">
          <div className="w-2.5 h-2.5 rounded-full" style={{ background: c }} />
          <span className="text-[9px] text-[#6b7a9e]">{g}</span>
        </div>
      ))}
    </div>
  </div>
);

const JournalCard: React.FC<{ entry: JournalEntry }> = ({ entry: e }) => {
  const isWin = e.result === 'WIN';
  const isLoss = e.result === 'LOSS';
  const statusColor = isWin ? '#00e87a' : isLoss ? '#ff3d5a' : '#ffb830';
  const statusLabel = isWin ? 'WIN' : isLoss ? 'LOSS' : 'PENDING';
  const mkt = e.market_label ?? marketLabel(e.market);
  const profit = e.profit_units;

  return (
    <div className="rounded-xl p-3 flex flex-col gap-1.5 mb-2" style={{ background: 'var(--bp-card2)', border: `1px solid ${statusColor}22` }}>
      <div className="flex items-center justify-between">
        <span className="text-[10px] text-[#6b7a9e] truncate max-w-[60%]">
          {e.league ? `${e.league} · ` : ''}{formatDate(e.event_date)}
        </span>
        <div className="flex items-center gap-2">
          {e.score_ft && <span className="text-[10px] font-mono text-[#6b7a9e]">{e.score_ft}</span>}
          <span className="text-[9px] font-bold px-2 py-0.5 rounded-full"
            style={{ color: statusColor, background: `${statusColor}22` }}>
            {statusLabel}
          </span>
        </div>
      </div>
      <div className="flex items-center justify-between">
        <div className="flex flex-col gap-0.5 flex-1 min-w-0">
          <span className="text-sm font-bold text-[#e8eeff] truncate">
            {e.home_team} <span className="text-[#303d57]">vs</span> {e.away_team}
          </span>
          <span className="text-[10px] text-[#6b7a9e]">⚡ {mkt} · @{e.odds?.toFixed(2) ?? '—'}</span>
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

function buildGradeData(settled: JournalEntry[]) {
  const counts: Record<string, number> = {};
  for (const e of settled) {
    const g = (e as { grade?: string }).grade ?? (e.strategy_label?.match(/[A-D][+]?/)?.[0]);
    if (g) counts[g] = (counts[g] ?? 0) + 1;
  }
  return Object.entries(counts).map(([grade, count]) => ({ grade, count }));
}

function buildEvData(settled: JournalEntry[]) {
  if (settled.length === 0) return [];
  const buckets: Record<string, number> = { '<0%': 0, '0-5%': 0, '5-10%': 0, '10-20%': 0, '>20%': 0 };
  for (const e of settled) {
    const ev = (e as { ev_pct?: number }).ev_pct ?? 0;
    if (ev < 0) buckets['<0%']++;
    else if (ev < 5) buckets['0-5%']++;
    else if (ev < 10) buckets['5-10%']++;
    else if (ev < 20) buckets['10-20%']++;
    else buckets['>20%']++;
  }
  return Object.entries(buckets).map(([range, count]) => ({ range, count }));
}

function buildScoreData(signals: SignalsArray) {
  if (signals.length === 0) return [];
  const buckets: Record<string, number> = { '40-50': 0, '50-60': 0, '60-70': 0, '70-80': 0, '80-90': 0, '90+': 0 };
  for (const s of signals) {
    const sc = effectiveScore(s);
    if (sc < 50) buckets['40-50']++;
    else if (sc < 60) buckets['50-60']++;
    else if (sc < 70) buckets['60-70']++;
    else if (sc < 80) buckets['70-80']++;
    else if (sc < 90) buckets['80-90']++;
    else buckets['90+']++;
  }
  return Object.entries(buckets).map(([range, count]) => ({ range, count }));
}

function buildMarketData(settled: JournalEntry[]) {
  const byMarket: Record<string, { wins: number; total: number; profit: number }> = {};
  for (const e of settled) {
    const m = e.market;
    if (!byMarket[m]) byMarket[m] = { wins: 0, total: 0, profit: 0 };
    byMarket[m].total++;
    if (e.result === 'WIN') byMarket[m].wins++;
    byMarket[m].profit += e.profit_units ?? 0;
  }
  return Object.entries(byMarket)
    .filter(([, v]) => v.total >= 2)
    .map(([market, v]) => ({
      label: marketLabel(market),
      count: v.total,
      wr: Math.round((v.wins / v.total) * 100),
      roi: Math.round((v.profit / v.total) * 100),
    }))
    .sort((a, b) => b.count - a.count);
}
