import { useAsync } from '@/lib/fetcher';
import { loadPyramid, loadPyramid140, loadPyramidMici, loadPyramidRisk } from '@/lib/data';
import type { PyramidState } from '@/lib/types';
import { cn } from '@/lib/utils';

export type PyrId = '2.00' | '1.40' | 'mici' | 'r5' | 'r10';
type Meta = { id: PyrId; name: string; target: string; risk: 'low' | 'med' | 'high'; info?: boolean };
const ALL: Meta[] = [
  { id: '1.40', name: 'Scurtă', target: '~1.40', risk: 'low', info: true },
  { id: 'mici', name: 'Ligi mici', target: '~2.00', risk: 'low' },
  { id: '2.00', name: 'Clasică', target: '~2.00', risk: 'low', info: true },
  { id: 'r5', name: 'Riscant', target: '~5', risk: 'med' },
  { id: 'r10', name: 'Riscant', target: '~10', risk: 'high' },
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
    <button type="button" onClick={onPick} aria-pressed={on} ref={(el) => { if (on && el) el.scrollIntoView({ block: 'nearest', inline: 'center' }); }}
      className={cn('pyr-card', on && 'pyr-card-on', m.info && 'pyr-card-info')}>
      <span className="flex items-center justify-between gap-2">
        <span className="flex min-w-0 items-center gap-1 text-[13px] font-extrabold leading-tight">{m.name}{m.info && <span className="rounded-full bg-muted px-1.5 py-px text-[9px] font-bold uppercase tracking-wider text-muted-foreground">info</span>}</span>
        <span className="flex shrink-0 items-center gap-1 text-[10px] font-semibold text-muted-foreground" title={RISK[m.risk][0]}><i className={cn('h-2 w-2 rounded-full', RISK[m.risk][1])} />{RISK[m.risk][0].replace('Risc ', '')}</span>
      </span>
      <span className="big-num mt-1 block text-[22px] leading-none">{m.target}</span>
      <span className="mt-1.5 flex items-center justify-between gap-2 text-[11px]">
        <span className="num whitespace-nowrap text-muted-foreground">Treapta {step}{cap ? `/${cap}` : ''}</span>
        <span className={cn('whitespace-nowrap rounded-full px-1.5 py-px font-bold', s.tone === 'win' ? 'bg-win text-win' : 'bg-muted text-muted-foreground')}>{s.text}</span>
      </span>
    </button>
  );
}

export function PyrSelector({ value, onChange }: { value: PyrId; onChange: (v: PyrId) => void }) {
  return (
    <div className="pyr-strip" role="group" aria-label="Alege piramida">
      {ALL.map((m) => <PyrCard key={m.id} m={m} on={value === m.id} onPick={() => onChange(m.id)} />)}
    </div>
  );
}
