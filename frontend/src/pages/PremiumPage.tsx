import React, { useState, useMemo } from 'react';
import { Shield } from 'lucide-react';
import { SignalCard } from '@/components/SignalCard';
import { useBetPredictData } from '@/hooks/useBetPredictData';
import { effectiveGrade, effectiveScore, effectiveEV, gradeColor, vbSetFromList } from '@/utils/filters';

const GRADES = ['A+', 'A', 'B', 'C', 'D'];

export const PremiumPage: React.FC = () => {
  const { signals, valueBets, loading } = useBetPredictData();
  const vbSet = vbSetFromList(valueBets);

  const [gradeFilter, setGradeFilter] = useState<string[]>(['A+', 'A', 'B']);
  const [minEdge, setMinEdge] = useState(0);
  const [minScore, setMinScore] = useState(50);
  const [maxOdds, setMaxOdds] = useState(3.5);

  const filtered = useMemo(() => {
    return signals.filter(s => {
      const grade = effectiveGrade(s);
      const sc = effectiveScore(s);
      const ev = effectiveEV(s);
      const odds = s.odds ?? 0;
      return (
        gradeFilter.includes(grade) &&
        sc >= minScore &&
        ev * 100 >= minEdge &&
        odds <= maxOdds &&
        odds >= 1.2
      );
    }).sort((a, b) => effectiveScore(b) - effectiveScore(a));
  }, [signals, gradeFilter, minEdge, minScore, maxOdds]);

  const toggleGrade = (g: string) => {
    setGradeFilter(prev => prev.includes(g) ? prev.filter(x => x !== g) : [...prev, g]);
  };

  return (
    <div className="pt-4 pb-4 flex flex-col gap-4">

      <div className="flex items-center gap-3">
        <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-[#ffb830] to-[#ff6b35] flex items-center justify-center flex-shrink-0">
          <Shield className="w-5 h-5 text-white" />
        </div>
        <div>
          <h2 className="text-lg font-extrabold text-[#e8eeff]">Premium</h2>
          <p className="text-[10px] text-[#6b7a9e]">{filtered.length} semnale · filtre avansate</p>
        </div>
      </div>

      <div className="grid grid-cols-3 gap-2">
        <MiniKpi label="Total" value={String(signals.length)} color="#4a9eff" />
        <MiniKpi label="Filtrate" value={String(filtered.length)} color="#00e87a" />
        <MiniKpi label="Value" value={String(valueBets.length)} color="#ffb830" />
      </div>

      {/* Filter panel */}
      <div className="rounded-2xl p-4 flex flex-col gap-4" style={{ background: '#0d1322', border: '1px solid rgba(255,255,255,.06)' }}>
        <span className="text-sm font-bold text-[#e8eeff]">ALGORITMI PREMIUM</span>

        <div>
          <label className="text-[9px] font-bold uppercase tracking-wider text-[#6b7a9e] mb-2 block">Grade selector</label>
          <div className="flex gap-2 flex-wrap">
            {GRADES.map(g => (
              <button
                key={g}
                onClick={() => toggleGrade(g)}
                className="px-3 py-1.5 rounded-full text-[10px] font-bold transition-all"
                style={
                  gradeFilter.includes(g)
                    ? { background: gradeColor(g), color: '#05080f' }
                    : { background: 'rgba(255,255,255,0.06)', color: '#6b7a9e' }
                }
              >
                {g}
              </button>
            ))}
          </div>
        </div>

        <SliderRow label="Edge minim" value={minEdge} min={0} max={30} unit="%" onChange={setMinEdge} color="#00e87a" />
        <SliderRow label="SmartBet score min" value={minScore} min={40} max={95} unit="" onChange={setMinScore} color="#4a9eff" />
        <SliderRow
          label="Cotă maximă"
          value={maxOdds}
          min={1.2} max={5.0} step={0.1} unit=""
          onChange={setMaxOdds}
          color="#ffb830"
          format={v => v.toFixed(1)}
        />
      </div>

      {loading ? (
        <div className="flex flex-col gap-3">
          {[1,2,3].map(i => <div key={i} className="h-40 rounded-2xl bg-white/5 animate-pulse" />)}
        </div>
      ) : filtered.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-12 gap-3">
          <Shield className="w-10 h-10 text-[#303d57]" />
          <p className="text-[#6b7a9e] text-sm text-center">Niciun semnal corespunde filtrelor selectate</p>
        </div>
      ) : (
        <div className="flex flex-col gap-3">
          {filtered.slice(0, 20).map((s, i) => (
            <SignalCard
              key={`${s.event_id}_${s.market}_${i}`}
              signal={s}
              isValue={vbSet.has(`${s.event_id}_${s.market}`)}
            />
          ))}
        </div>
      )}
    </div>
  );
};

const MiniKpi: React.FC<{ label: string; value: string; color: string }> = ({ label, value, color }) => (
  <div className="rounded-xl p-2.5 flex flex-col gap-1" style={{ background: '#0d1322', border: '1px solid rgba(255,255,255,.06)' }}>
    <span className="text-[8px] font-bold uppercase tracking-wider text-[#6b7a9e]">{label}</span>
    <span className="text-lg font-bold" style={{ color }}>{value}</span>
  </div>
);

const SliderRow: React.FC<{
  label: string;
  value: number;
  min: number;
  max: number;
  step?: number;
  unit: string;
  color: string;
  format?: (v: number) => string;
  onChange: (v: number) => void;
}> = ({ label, value, min, max, step = 1, unit, color, format, onChange }) => (
  <div>
    <div className="flex items-center justify-between mb-1.5">
      <label className="text-[9px] font-bold uppercase tracking-wider text-[#6b7a9e]">{label}</label>
      <span className="text-[11px] font-bold" style={{ color }}>
        {format ? format(value) : value}{unit}
      </span>
    </div>
    <input
      type="range"
      min={min}
      max={max}
      step={step}
      value={value}
      onChange={e => onChange(parseFloat(e.target.value))}
      className="w-full h-1.5 rounded-full appearance-none cursor-pointer"
      style={{ accentColor: color }}
    />
    <div className="flex justify-between mt-0.5">
      <span className="text-[8px] text-[#303d57]">{format ? format(min) : min}{unit}</span>
      <span className="text-[8px] text-[#303d57]">{format ? format(max) : max}{unit}</span>
    </div>
  </div>
);
