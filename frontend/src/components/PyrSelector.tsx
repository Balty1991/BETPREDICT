import { useAsync } from '@/lib/fetcher';
import { loadPyramid, loadPyramid140, loadPyramidGoal130, loadPyramidMici, loadPyramidMix, loadPyramidRisk, loadPyramidSafe } from '@/lib/data';
import type { PyramidState } from '@/lib/types';
import { cn } from '@/lib/utils';

export type PyrId = '2.00' | '1.20' | '1.40' | '1.60' | 'boost' | 'mici' | 'r5' | 'r10' | 'r100' | 'mix140' | 'mix25' | 'goal130' | 'manual';
type Meta = { id: PyrId; name: string; target: string; risk: 'low' | 'med' | 'high'; info?: boolean };
// Piste active. R100-ul vechi rămâne numai în istoricul/API; noile variante Mix sunt jucabile cu miză aleasă de utilizator.
const ALL: Meta[] = [
  { id: 'boost', name: 'Cote mărite', target: '+EV', risk: 'med' },
  { id: '1.20', name: 'Foarte sigură', target: '~1.20', risk: 'low' },
  { id: 'goal130', name: 'Goluri sigure', target: '1.20–1.30', risk: 'low' },
  { id: '1.40', name: 'Scurtă', target: '~1.40', risk: 'low' },
  { id: '1.60', name: 'Piramida 1.60', target: '~1.60', risk: 'med' },
  { id: 'mix140', name: 'Mix 1.40', target: 'Robot + SS', risk: 'low' },
  { id: 'mix25', name: 'Mix 2.5×5', target: '~100×', risk: 'high' },
  { id: 'manual', name: 'Manuală · a mea', target: 'tu alegi', risk: 'med' },
];
const RISK = { low: ['Risc mic', 'bg-[hsl(var(--win))]'], med: ['Risc mediu', 'bg-[hsl(var(--warn))]'], high: ['Risc mare', 'bg-[hsl(var(--loss))]'] } as const;

function load(id: PyrId): Promise<PyramidState | null> {
  if (id === 'manual') return Promise.resolve(null);
  if (id === 'goal130') return loadPyramidGoal130();
  return id === 'mici' ? loadPyramidMici() : id === 'mix140' || id === 'mix25' ? loadPyramidMix(id) : id === 'r5' || id === 'r10' || id === 'r100' ? loadPyramidRisk(id) : id === '1.20' || id === '1.60' || id === 'boost' ? loadPyramidSafe(id) : id === '1.40' ? loadPyramid140() : loadPyramid();
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
  const s = m.id === 'manual' ? { text: 'Creezi tu treptele', tone: 'primary' as const } : status(d);
  return (
    <button type="button" onClick={onPick} aria-pressed={on} ref={(el) => { if (on && el) el.scrollIntoView({ block: 'nearest', inline: 'center' }); }}
      className={cn('pyr-card', on && 'pyr-card-on', m.info && 'pyr-card-info')}>
      <span className="flex items-center justify-between gap-2">
        <span className="flex min-w-0 items-center gap-1 text-[13px] font-extrabold leading-tight">{m.name}{m.info && <span className="rounded-full bg-muted px-1.5 py-px text-[9px] font-bold uppercase tracking-wider text-muted-foreground">info</span>}</span>
        <span className="flex shrink-0 items-center gap-1 text-[10px] font-semibold text-muted-foreground" title={RISK[m.risk][0]}><i className={cn('h-2 w-2 rounded-full', RISK[m.risk][1])} />{RISK[m.risk][0].replace('Risc ', '')}</span>
      </span>
      <span className="big-num mt-1 block text-[22px] leading-none">{m.target}</span>
      <span className="num mt-1.5 block truncate text-[11px] text-muted-foreground">Treapta {step}{cap ? `/${cap}` : ''}{(d?.record?.steps ?? 0) > 0 ? ` · record ${d!.record!.steps}` : ''}</span>
      <span className={cn('mt-0.5 flex min-w-0 items-center gap-1 text-[11px] font-bold', s.tone === 'win' ? 'text-win' : 'text-muted-foreground')}>
        <i className={cn('h-1.5 w-1.5 shrink-0 rounded-full', s.tone === 'win' ? 'bg-[hsl(var(--win))]' : 'bg-muted-foreground/50')} /><span className="truncate">{s.text}</span>
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
