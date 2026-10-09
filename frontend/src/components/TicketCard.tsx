import { useState } from 'react';
import { Link } from 'react-router';
import { ChevronDown, ChevronUp, PlayCircle as Save, Trash2, Copy, CheckCircle2, XCircle, Clock, MinusCircle } from 'lucide-react';
import type { Ticket } from '@/lib/types';
import { odds as fo, pct, signed, roTime, roDay, dayLabel } from '@/lib/format';
import { Badge, GradeBadge } from './kit';
import { cn } from '@/lib/utils';
import { actions, getState } from '@/lib/store';
import { toast } from 'sonner';

function LegIcon({ r }: { r?: string | null }) {
  if (r === 'won' || r === 'half_won') return <CheckCircle2 className="h-4 w-4 text-win" />;
  if (r === 'lost' || r === 'half_lost') return <XCircle className="h-4 w-4 text-loss" />;
  if (r === 'void') return <MinusCircle className="h-4 w-4 text-warn" />;
  return <Clock className="h-4 w-4 text-muted-foreground" />;
}

export function statusTone(s?: string) { return s === 'won' ? 'win' : s === 'lost' ? 'loss' : s === 'void' ? 'warn' : 'pending'; }
export function statusText(s?: string) { return s === 'won' ? 'Câștigat' : s === 'lost' ? 'Pierdut' : s === 'void' ? 'Anulat' : 'În curs'; }

export function TicketCard({ t, saved, onRemove, compact }: { t: Ticket; saved?: boolean; onRemove?: () => void; compact?: boolean }) {
  const [open, setOpen] = useState(!compact);
  const [why, setWhy] = useState<number | null>(null);
  const tone = statusTone(t.status);
  const copy = () => {
    const txt = [`BETPREDICT · ${t.variant_label ?? t.kind} · cotă ${fo(t.total_odds)}`, ...t.legs.map((l) => `${roTime(l.kickoff_utc)} ${l.home} – ${l.away}: ${l.label} @ ${fo(l.odds)}`)].join('\n');
    navigator.clipboard?.writeText(txt).then(() => toast.success('Bilet copiat'), () => toast.error('Nu am putut copia'));
  };
  return (
    <div className={cn('card overflow-hidden', t.status === 'won' && 'border-emerald-500/50', t.status === 'lost' && 'opacity-80')}>
      <div className="flex items-start gap-3 p-3">
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-1.5">
            <span className="font-semibold">{t.variant_label ?? t.variant ?? t.kind}</span>
            {t.target_odds && t.kind !== 'pyramid' && <Badge tone="outline">țintă ~{t.target_odds}</Badge>}
            <Badge tone={tone as 'win'}>{statusText(t.status)}</Badge>
            {t.created_by === 'user' && <Badge tone="primary">manual</Badge>}{t.followed && <Badge tone="primary">jucat de mine</Badge>}
            {t.date && <span className="text-[11px] text-muted-foreground">{dayLabel(t.date)}</span>}
          </div>
          <div className="mt-1 text-xs text-muted-foreground">
            {t.legs.length} selecții · probabilitate prudentă <b className="text-foreground">{pct(t.p_ticket, (t.p_ticket ?? 1) < 0.1 ? 2 : 0)}</b>
            {t.ev != null && <> · EV <b className={cn(t.ev > 0 ? 'text-win' : 'text-loss')}>{signed(t.ev * 100, 1, '%')}</b></>}
            {t.settled_legs != null && t.legs_count ? <> · decontate {t.settled_legs}/{t.legs_count}</> : null}
          </div>
        </div>
        <div className="text-right">
          <div className="text-2xl font-extrabold leading-none text-primary">{fo(t.total_odds)}</div>
          {t.created_by === 'user' || t.followed ? (t.stake ? <div className="text-[11px] text-muted-foreground">{t.stake} lei → {(t.stake * t.total_odds).toFixed(0)} lei</div> : null)
            : t.stake_units ? <div className="mt-1 text-[11px] text-muted-foreground" title="Miză sugerată: ¼ Kelly, plafonată. 1u = 1% din banca ta.">miză <b className="text-foreground">{t.stake_units}u</b> · {t.stake_units}% bancă</div> : null}
        </div>
      </div>
      {open && (
        <ul className="divide-y border-t">
          {t.legs.map((l, i) => (
            <li key={`${l.match_id}-${i}`} className="px-3 py-2 text-sm">
              <div className="flex items-center gap-2">
                <LegIcon r={l.result} />
                <div className="min-w-0 flex-1">
                  <Link to={`/meci/${l.match_id}?zi=${l.kickoff_utc ? roDay(l.kickoff_utc) : ''}`} className="block truncate font-medium hover:underline">{l.home} – {l.away}</Link>
                  <div className="truncate text-xs text-muted-foreground">{roTime(l.kickoff_utc)} · {l.league}{l.score ? ` · scor ${l.score}` : ''}</div>
                </div>
                <div className="flex items-center gap-1.5">
                  <GradeBadge grade={l.grade} />
                  <div className="text-right"><div className="font-semibold">{l.label}</div><div className="text-xs text-muted-foreground">@ {fo(l.odds)}{l.p != null ? ` · ${pct(l.p)}` : ''}</div></div>
                </div>
              </div>
              {l.reasons?.length ? (
                <button className="ml-6 mt-1 text-[11px] text-primary hover:underline" onClick={() => setWhy(why === i ? null : i)}>{why === i ? 'Ascunde motivele' : 'De ce?'}</button>
              ) : null}
              {why === i && <ul className="ml-6 mt-1 list-disc space-y-0.5 pl-4 text-xs text-muted-foreground">{l.reasons!.map((r) => <li key={r}>{r}</li>)}</ul>}
            </li>
          ))}
        </ul>
      )}
      {open && t.reasons?.length ? <div className="border-t bg-muted/30 px-3 py-2 text-xs text-muted-foreground">{t.reasons.join(' · ')}</div> : null}
      <div className="flex items-center gap-1 border-t px-2 py-1.5">
        <button className="btn btn-ghost px-2 text-xs" onClick={() => setOpen(!open)}>{open ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}{open ? 'Restrânge' : 'Vezi selecțiile'}</button>
        <div className="ml-auto flex gap-1">
          <button className="btn btn-ghost px-2 text-xs" onClick={copy}><Copy className="h-3.5 w-3.5" />Copiază</button>
          {!saved && <button className="btn btn-ghost px-2 text-xs" title="Adaugă biletul la „Biletele mele” (biletele pe care le joci tu, cu miza ta). Statisticile Robotului se salvează automat, oricum."
            onClick={() => { actions.saveTicket({ ...t, id: `${t.id}`, created_by: t.created_by ?? 'robot', followed: true, stake: t.stake ?? getState().settings.defaultStake }); toast.success('Adăugat la „Biletele mele” — îl urmărim și îl decontăm automat'); }}><Save className="h-3.5 w-3.5" />Îl joc</button>}
          {onRemove && <button className="btn btn-ghost px-2 text-xs" onClick={onRemove}><Trash2 className="h-3.5 w-3.5" />Șterge</button>}
        </div>
      </div>
    </div>
  );
}
