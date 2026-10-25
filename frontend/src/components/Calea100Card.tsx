import { Link } from 'react-router';
import { Target } from 'lucide-react';
import { getJSON, useAsync } from '@/lib/fetcher';
import { odds as fo } from '@/lib/format';
import { Panel } from '@/components/dash';

type Roll = {
  start: string; target: number; start_lei: number;
  active: { step: number; odds: number; stake_lei: number; steps_left: number; p_reach_lo: number; p_reach_hi: number; today?: { day: string; odds: number } | null };
  record: { chains: number; won: number; best_steps: number; staked_lei: number; returned_lei: number };
};
export type Calea = {
  version: string; start: string;
  today?: { ticket_id: number; odds: number; p_honest: number; ev_bonus: number; superbonus: number } | null;
  bonus_record: { played: number; won: number; staked_u: number; returned_u_no_bonus: number; roi_no_bonus: number | null };
  roll: Roll;
};

const pc = (p: number) => (p >= 0.01 ? `${(p * 100).toFixed(1)}%` : `${(p * 100).toFixed(2)}%`);
const oneIn = (p: number) => (p > 0 ? `1 din ${Math.round(1 / p)}` : '—');

export function useCalea() {
  return useAsync(() => getJSON<Calea>('api/calea100.json'), []);
}

/** Calea 100+: cele două drumuri alese după cercetare (biletul SuperBonus și rularea Pontului), cu șansa ONESTĂ. */
export function Calea100Card({ compact = false }: { compact?: boolean }) {
  const { data } = useCalea();
  if (!data) return null;
  const r = data.roll;
  const t = data.today;
  return (
    <Panel title="Calea 100+" icon={<Target className="h-4 w-4" />} right={<span className="text-[11px] font-semibold text-muted-foreground">reguli fixe · din {data.start.slice(8, 10)}.{data.start.slice(5, 7)}</span>}>
      <div className="space-y-2.5 text-sm">
        <Link to="/bilete?k=calea" className="hot-ticket press">
          <span className="min-w-0 flex-1">
            <span className="block text-[15px] font-bold leading-snug">Biletul SuperBonus</span>
            <span className="mt-1 block text-[11px] text-muted-foreground">
              {t ? <>8–14 selecții 1.35–2.20 · SuperBonus +{Math.round((t.superbonus ?? 0) * 100)}% · șansă onestă <b>~{pc(t.p_honest)}</b> ({oneIn(t.p_honest)}) · 1 leu</>
                : <>Azi nu s-a strâns cota 100 din selecții cu marjă mică → nu se joacă.</>}
            </span>
          </span>
          {t && <span className="big-num neon-text text-[24px]">{Math.round(t.odds)}</span>}
        </Link>
        <div className="rounded-xl border px-3 py-2">
          <div className="flex items-center justify-between gap-2">
            <b>Rularea Pontului</b>
            <span className="num text-xs text-muted-foreground">pasul {r.active.step} · cotă {fo(r.active.odds)} / {r.target}</span>
          </div>
          <p className="mt-1 text-[12px] text-muted-foreground">
            {r.active.today ? <>Pune <b className="text-foreground">{r.active.stake_lei.toFixed(2)} lei</b> pe Pontul zilei ({fo(r.active.today.odds)}), tot câștigul merge pe Pontul următor.</>
              : <>Următorul pas: {r.active.stake_lei.toFixed(2)} lei pe Pontul zilei, când apare.</>}
            {' '}Mai sunt ~{r.active.steps_left} pași; șansa să ajungi la 100: <b className="text-foreground">{pc(r.active.p_reach_lo)}–{pc(r.active.p_reach_hi)}</b>. O pierdere → reiei cu {r.start_lei} lei.
          </p>
        </div>
        {!compact && (
          <p className="text-[11px] leading-snug text-muted-foreground">
            Adevărul: la cota 100 șansa e ~1% chiar fără marjă; marja Superbet (~4% pe selecție la cote 1.35–2, 20–35% la scor corect)
            o scade. Niciun filtru n-a arătat avantaj sigur, așa că se așteaptă ~1 câștig la 100–200 de încercări.
            Bilanț din {data.start.slice(8, 10)}.{data.start.slice(5, 7)}: SuperBonus {data.bonus_record.won}/{data.bonus_record.played},
            rulări {r.record.won}/{r.record.chains} (cel mai lung: {r.record.best_steps} pași).
          </p>
        )}
      </div>
    </Panel>
  );
}
