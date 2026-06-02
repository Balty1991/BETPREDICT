import React from 'react';
import { Zap } from 'lucide-react';
import { SignalCard } from '@/components/SignalCard';
import { useBetPredictData } from '@/hooks/useBetPredictData';
import { filteredSignals, vbSetFromList, isVeyra, effectiveEV } from '@/utils/filters';

export const PredictionsPage: React.FC = () => {
  const { signals, valueBets, loading } = useBetPredictData();
  const vbSet = vbSetFromList(valueBets);
  const picks = filteredSignals(signals, vbSet);

  const veyraCount = picks.filter(s => isVeyra(s)).length;
  const evPlus = picks.filter(s => effectiveEV(s) > 0).length;
  const engineLabel = veyraCount > 0
    ? `VEYRA v5: ${veyraCount} · Engine v6: ${picks.length - veyraCount}`
    : `${picks.length} semnale`;

  if (loading) return <LoadingState />;

  return (
    <div className="pt-4 pb-4">
      <p className="text-[10px] text-[#6b7a9e] text-center mb-4 font-medium tracking-wide">
        {engineLabel} · cotă 1.35–3.50 · {evPlus} EV+
      </p>
      {picks.length === 0 ? (
        <EmptyState />
      ) : (
        <div className="flex flex-col gap-3">
          {picks.map((s, i) => (
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

const LoadingState: React.FC = () => (
  <div className="flex flex-col items-center justify-center py-20 gap-3">
    <div className="w-8 h-8 border-2 border-[#00e87a] border-t-transparent rounded-full animate-spin" />
    <p className="text-[#6b7a9e] text-sm">Se încarcă predicțiile...</p>
  </div>
);

const EmptyState: React.FC = () => (
  <div className="flex flex-col items-center justify-center py-16 gap-3">
    <div className="w-14 h-14 rounded-2xl bg-[#131c2e] flex items-center justify-center">
      <Zap className="w-6 h-6 text-[#303d57]" />
    </div>
    <p className="text-[#e8eeff] font-semibold">Nicio predicție calificată</p>
    <p className="text-[#6b7a9e] text-sm text-center max-w-[240px] leading-relaxed">
      VEYRA Supreme Engine v5 se actualizează orar. Revin când găsește oportunități cu EV pozitiv.
    </p>
  </div>
);
