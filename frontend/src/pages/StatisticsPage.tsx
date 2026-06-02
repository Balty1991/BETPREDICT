import React, { useState } from 'react';
import { BarChart3 } from 'lucide-react';
import { useBetPredictData } from '@/hooks/useBetPredictData';
import { journalStats, marketLabel, formatDate } from '@/utils/filters';
import type { JournalEntry } from '@/types/betpredict';

type TabId = 'pending' | 'settled';

export const StatisticsPage: React.FC = () => {
  const { journal, loading } = useBetPredictData();
  const [tab, setTab] = useState<TabId>('settled');

  const stats = journalStats(journal);
  const pending = journal.filter(e => e.status === 'pending');
  const settled = journal.filter(e => e.status === 'settled').sort((a, b) => {
    const da = a.settled_at ?? a.event_date ?? '';
    const db = b.settled_at ?? b.event_date ?? '';
    return db.localeCompare(da);
  });

  const roiColor = stats.roi == null ? '#6b7a9e' : stats.roi > 0 ? '#00e87a' : stats.roi > -20 ? '#ffb830' : '#ff3d5a';

  return (
    <div className="pt-4 pb-4 flex flex-col gap-4">

      {/* Stats header */}
      <div className="rounded-2xl p-4 flex flex-col gap-3" style={{ background: '#0d1322', border: '1px solid rgba(255,255,255,.06)' }}>
        <div className="flex items-center gap-2">
          <BarChart3 className="w-4 h-4 text-[#4a9eff]" />
          <span className="text-sm font-bold text-[#e8eeff]">Performanță Globală</span>
        </div>
        <div className="grid grid-cols-4 gap-2">
          <StatPill label="W" value={String(stats.wins)} color="#00e87a" />
          <StatPill label="L" value={String(stats.losses)} color="#ff3d5a" />
          <StatPill label="WR" value={stats.wr != null ? `${stats.wr}%` : '—'} color={stats.wr != null && stats.wr >= 55 ? '#00e87a' : '#ffb830'} />
          <StatPill label="ROI" value={stats.roi != null ? `${stats.roi > 0 ? '+' : ''}${stats.roi}%` : '—'} color={roiColor} />
        </div>
        {stats.settled > 0 && (
          <div className="flex items-center justify-between pt-1 border-t border-white/5">
            <span className="text-[10px] text-[#6b7a9e]">{stats.settled} pariuri decontate · {stats.pending} în așteptare</span>
            <span className="text-[10px] font-bold" style={{ color: stats.profit >= 0 ? '#00e87a' : '#ff3d5a' }}>
              {stats.profit >= 0 ? '+' : ''}{stats.profit.toFixed(2)}u profit
            </span>
          </div>
        )}
      </div>

      {/* Tabs */}
      <div className="flex rounded-xl overflow-hidden border border-white/10">
        {(['settled', 'pending'] as TabId[]).map(t => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className="flex-1 py-2.5 text-xs font-bold uppercase tracking-wider transition-colors"
            style={{
              background: tab === t ? '#0d1322' : 'transparent',
              color: tab === t ? '#e8eeff' : '#6b7a9e',
              borderRight: t === 'settled' ? '1px solid rgba(255,255,255,.1)' : undefined,
            }}
          >
            {t === 'settled' ? `Decontate (${stats.settled})` : `În așteptare (${stats.pending})`}
          </button>
        ))}
      </div>

      {/* List */}
      {loading ? (
        <div className="flex flex-col gap-2">
          {[1,2,3,4,5].map(i => <div key={i} className="h-16 rounded-xl bg-white/5 animate-pulse" />)}
        </div>
      ) : tab === 'settled' ? (
        settled.length === 0
          ? <Empty text="Nicio pariere decontată încă" />
          : <div className="flex flex-col gap-2">{settled.map((e, i) => <JournalCard key={i} entry={e} />)}</div>
      ) : (
        pending.length === 0
          ? <Empty text="Nicio pariere în așteptare" />
          : <div className="flex flex-col gap-2">{pending.map((e, i) => <JournalCard key={i} entry={e} />)}</div>
      )}
    </div>
  );
};

const StatPill: React.FC<{ label: string; value: string; color: string }> = ({ label, value, color }) => (
  <div className="flex flex-col items-center gap-0.5 rounded-xl py-2 bg-white/[0.03]">
    <span className="text-[8px] font-bold uppercase tracking-widest text-[#6b7a9e]">{label}</span>
    <span className="text-base font-bold" style={{ color }}>{value}</span>
  </div>
);

const Empty: React.FC<{ text: string }> = ({ text }) => (
  <div className="flex items-center justify-center py-12">
    <p className="text-[#6b7a9e] text-sm">{text}</p>
  </div>
);

const JournalCard: React.FC<{ entry: JournalEntry }> = ({ entry: e }) => {
  const isWin = e.result === 'WIN';
  const isLoss = e.result === 'LOSS';
  const isPending = e.status === 'pending';
  const statusColor = isWin ? '#00e87a' : isLoss ? '#ff3d5a' : '#ffb830';
  const statusLabel = isWin ? 'WIN' : isLoss ? 'LOSS' : 'PENDING';
  const mkt = e.market_label ?? marketLabel(e.market);
  const profit = e.profit_units;

  return (
    <div className="rounded-xl p-3 flex flex-col gap-1.5" style={{ background: '#0d1322', border: `1px solid ${statusColor}22` }}>
      <div className="flex items-center justify-between">
        <span className="text-xs text-[#6b7a9e] truncate max-w-[60%]">
          {e.league ? `${e.league} · ` : ''}{formatDate(e.event_date)}
        </span>
        <div className="flex items-center gap-2">
          {!isPending && e.score_ft && (
            <span className="text-[10px] font-mono text-[#6b7a9e]">{e.score_ft}</span>
          )}
          <span
            className="text-[9px] font-bold px-2 py-0.5 rounded-full"
            style={{ color: statusColor, background: `${statusColor}22` }}
          >
            {statusLabel}
          </span>
        </div>
      </div>

      <div className="flex items-center justify-between">
        <div className="flex flex-col gap-0.5 flex-1 min-w-0">
          <span className="text-sm font-bold text-[#e8eeff] truncate">
            {e.home_team} <span className="text-[#303d57]">vs</span> {e.away_team}
          </span>
          <span className="text-[10px] text-[#6b7a9e]">
            ⚡ {mkt} · @{e.odds?.toFixed(2) ?? '—'}
          </span>
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
