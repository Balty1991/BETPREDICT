import { useAsync } from '@/lib/fetcher';
import { loadPyramid, loadPyramid140, loadPyramidMici, loadPyramidRisk } from '@/lib/data';
import type { PyramidState } from '@/lib/types';
import { cn } from '@/lib/utils';

export type PyrId = '2.00' | '1.40' | 'mici' | 'r5' | 'r10';
type Meta = { id: PyrId; name: string; target: string; risk: 'low' | 'med' | 'high'; info?: boolean };
const ACTIVE: Meta[] = [
  { id: 'mici', name: 'Ligi mici', target: '~2.00', risk: 'low' },
  { id: 'r5', name: 'Riscant', target: '~5', risk: 'med' },
  { id: 'r10', name: 'Riscant', target: '~10', risk: 'high' },
];
const INFO: Meta[] = [
  { id: '2.00', name: 'Clasică', target: '~2.00', risk: 'low', info: true },
  { id: '1.40', name: 'Scurtă', target: '~1.40', risk: 'low', info: true },
];
const RISK = { low: ['Risc mic', 'bg-[hsl(var(--win))]'], med: ['Risc mediu', 'bg-[hsl(var(--warn))]'], high: ['Risc mare', 'bg-[hsl(var(--loss))]'] } as const;

function load(id: PyrId): Promise<PyramidState | null> {
  return id === 'mici' ? loadPyramidMici() : id === 'r5' || id === 'r10' ? loadPyramidRisk(id) : id === '1.40' ? loadPyramid140() : loadPyramid();
}

function status(d: PyramidState | null | undefined): { text: string; tone: 'win' | 'muted' | 'primary' } {
  if (!d) return { text: '—', tone: 'muted' };
  if (d.today?.main) return { text: d.today.main.status === 'pending' ? 'Bilet azi' : d.today.main.status === 'won' ? 'Câștigat' : 'Pierdut', tone: d.today.main.status === 'lost' ? 'muted' : 'win' };
  return { text: 'Pauză azi', tone: 'muted' };
}

function PyrCard({ m, on, onPick }: { m: Meta; on: boolean; onPick: () => void }) {
  const d = useAsync(() => load(m.id), [m.id]).data;
  const ms = (d?.rules as { max_steps?: number } | undefined)?.max_steps; const cap = ms && ms < 100 ? ms : null;
  const step = (d?.action?.step ?? (d?.run?.status === 'active' ? (d.run.step ?? 0) + 1 : 1)) || 1;
  const s = status(d);
  return (
    <button type="button" onClick={onPick} aria-pressed={on}
      className={cn('pyr-card', on && 'pyr-card-on', m.info && 'pyr-card-info')}>
      <span className="flex items-center justify-between gap-2">
        <span className="text-[13px] font-extrabold leading-tight">{m.name}</span>
        <span className="flex items-center gap-1 text-[10px] font-semibold text-muted-foreground"><i className={cn('h-2 w-2 rounded-full', RISK[m.risk][1])} />{RISK[m.risk][0]}</span>
      </span>
      <span className="big-num mt-1 block text-[22px] leading-none">{m.target}</span>
      <span className="mt-1.5 flex items-center justify-between gap-2 text-[11px]">
        <span className="num text-muted-foreground">Treapta {step}{cap ? `/${cap}` : ''}</span>
        <span className={cn('rounded-full px-1.5 py-px font-bold', s.tone === 'win' ? 'bg-win text-win' : 'bg-muted text-muted-foreground')}>{s.text}</span>
      </span>
    </button>
  );
}

export function PyrSelector({ value, onChange }: { value: PyrId; onChange: (v: PyrId) => void }) {
  return (
    <div className="space-y-2">
      <div className="pyr-strip" role="group" aria-label="Alege piramida">
        {ACTIVE.map((m) => <PyrCard key={m.id} m={m} on={value === m.id} onPick={() => onChange(m.id)} />)}
      </div>
      <div className="flex items-center gap-2 text-[11px] text-muted-foreground">
        <span className="font-semibold uppercase tracking-wider">Doar informativ</span>
        {INFO.map((m) => (
          <button key={m.id} type="button" aria-pressed={value === m.id} onClick={() => onChange(m.id)}
            className={cn('rounded-full border px-2.5 py-1 font-semibold', value === m.id ? 'border-primary text-primary' : 'border-[hsl(var(--glass-border))]')}>{m.name} {m.target}</button>
        ))}
      </div>
    </div>
  );
}
