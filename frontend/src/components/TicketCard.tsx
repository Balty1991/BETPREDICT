import { useState } from 'react';
import { Link } from 'react-router';
import { PlayCircle, Trash2, Copy, CheckCircle2, XCircle, Clock, MinusCircle, Ticket as TicketIcon, Triangle, ChevronDown, ChevronUp, User, ShieldCheck, AlertTriangle, Share2 } from 'lucide-react';
import type { Ticket } from '@/lib/types';
import { odds as fo, pct, roDay, roKickoff, dayLabel } from '@/lib/format';
import { plainPick } from '@/lib/markets';
import { BookmakerTag, ClvChip, InfoTip } from './kit';
import { cn } from '@/lib/utils';
import { actions, getState } from '@/lib/store';
import { HELP, valueInfo } from '@/lib/ui';
import { toast } from 'sonner';
import { isSafeTicket } from '@/lib/robot';

function LegIcon({ r }: { r?: string | null }) {
  if (r === 'won' || r === 'half_won') return <CheckCircle2 className="h-4 w-4 shrink-0 text-win" aria-label="câștigat" />;
  if (r === 'lost' || r === 'half_lost') return <XCircle className="h-4 w-4 shrink-0 text-loss" aria-label="pierdut" />;
  if (r === 'void') return <MinusCircle className="h-4 w-4 shrink-0 text-warn" aria-label="anulat" />;
  return <Clock className="h-4 w-4 shrink-0 text-muted-foreground" aria-label="în așteptare" />;
}

const PILL: Record<string, string> = { win: 'bg-win text-win', loss: 'bg-loss text-loss', warn: 'bg-warn text-warn', pending: 'bg-pending text-pending' };

export function statusTone(s?: string) { return s === 'won' ? 'win' : s === 'lost' ? 'loss' : s === 'void' ? 'warn' : 'pending'; }
export function statusText(s?: string) { return s === 'won' ? 'Câștigat' : s === 'lost' ? 'Pierdut' : s === 'void' ? 'Anulat' : 'În curs'; }

/** Pentru biletele cu meciuri din mai multe zile: „Azi–Dum”. */
function legSpan(t: Ticket): string | null {
  const ds = [...new Set(t.legs.map((l) => (l.kickoff_utc ? roDay(l.kickoff_utc) : '')).filter(Boolean))].sort();
  return ds.length > 1 ? `${dayLabel(ds[0])}–${dayLabel(ds[ds.length - 1])}` : null;
}

function ticketTitle(t: Ticket) {
  if (t.kind === 'pyramid') return t.variant === 'principal' || !t.variant ? 'Piramida zilei' : (t.variant_label ?? 'Alternativă');
  if (t.created_by === 'user') return 'Biletul meu';
  if (t.kind === 'acca_value') return `Bilet de valoare · ${t.legs.length} selecții`;
  if (t.kind === 'acca_double') return 'Dublu de valoare';
  if (t.lottery || t.variant === 'loterie') return `Loterie ~${t.target_odds ?? Math.round(t.total_odds)}`;
  if (isSafeTicket(t)) return `Bilet sigur ~${t.target_odds ?? Math.round(t.total_odds)}`;
  if (t.target_odds) return `Bilet cotă ~${t.target_odds}`;
  return t.variant_label ?? 'Bilet';
}

/** Bilet ca la casa de pariuri: selecțiile sus, perforație, apoi cota totală, șansa și miza. */
export function TicketCard({ t, saved, onRemove, compact }: { t: Ticket; saved?: boolean; onRemove?: () => void; compact?: boolean }) {
  const [all, setAll] = useState(!compact);
  const [details, setDetails] = useState(false);
  const tone = statusTone(t.status);
  const v = valueInfo(t.ev);
  const maxLegs = all ? t.legs.length : Math.min(t.legs.length, 3);
  const safe = isSafeTicket(t) && t.created_by !== 'user';
  const negEv = safe && (t.ev ?? 0) < 0;
  const Icon = t.kind === 'pyramid' ? Triangle : t.created_by === 'user' ? User : safe ? ShieldCheck : TicketIcon;
  const copy = () => {
    const txt = [`BETPREDICT · ${ticketTitle(t)} · cotă ${fo(t.total_odds)}`, ...t.legs.map((l) => `${roKickoff(l.kickoff_utc)} ${l.home} – ${l.away}: ${plainPick(l.market, l.line, l.selection, l.label)} @ ${fo(l.odds)}`)].join('\n');
    navigator.clipboard?.writeText(txt).then(() => toast.success('Bilet copiat'), () => toast.error('Nu am putut copia'));
  };
  const share = async () => {
    const { shareTicket } = await import('@/lib/shareImage');
    const r = await shareTicket(t, ticketTitle(t), `BETPREDICT · ${ticketTitle(t)} · cotă ${fo(t.total_odds)}`);
    if (r === 'downloaded') toast.success('Imaginea biletului a fost descărcată — o poți trimite pe WhatsApp');
    else if (r === 'failed') toast.error('Nu am putut genera imaginea');
  };
  const variantNote = t.kind !== 'pyramid' && !safe && t.variant_label && t.target_odds ? t.variant_label : null;
  return (
    <article className={cn('card card-hover flex flex-col overflow-hidden', t.status === 'won' && 'border-[hsl(var(--win)/0.5)]', t.status === 'lost' && 'opacity-85')}>
      <header className={cn('flex items-center gap-2.5 px-4 pb-2.5 pt-3.5', t.kind === 'pyramid' ? 'ticket-top-pyr' : safe ? 'ticket-top-safe' : 'ticket-top')}>
        <span className={cn('flex h-10 w-10 shrink-0 items-center justify-center rounded-2xl ring-1 ring-inset ring-[hsl(var(--glass-border))]', t.kind === 'pyramid' ? 'bg-info text-info' : safe ? 'bg-win text-win' : 'bg-primary/15 text-primary')}><Icon className="h-[18px] w-[18px]" /></span>
        <div className="min-w-0 flex-1">
          <div className="truncate text-[16px] font-extrabold leading-tight tracking-[-0.03em]">{ticketTitle(t)}</div>
          {(t.bucket || t.lottery) && <div className="mt-0.5 flex gap-1"><span className={cn('rounded-full px-2 py-px text-[10px] font-bold uppercase tracking-wider', t.lottery ? 'bg-[hsl(var(--glow-3)/0.18)] text-[hsl(var(--glow-3))]' : 'bg-primary/15 text-primary')}>{t.lottery ? 'Loterie' : t.bucket}</span></div>}
          <div className="truncate text-xs text-muted-foreground">{[legSpan(t) ?? (t.date && dayLabel(t.date)), variantNote, `${t.legs.length} ${t.legs.length === 1 ? 'meci' : 'meciuri'}`, t.overlap ? `comun cu ${t.overlap} ${t.overlap === 1 ? 'bilet' : 'bilete'}` : null, t.followed && 'jucat de mine'].filter(Boolean).join(' · ')}</div>
        </div>
        <span className={cn('rounded-full px-2.5 py-1 text-[11px] font-bold', PILL[tone])}>{statusText(t.status)}{t.status === 'pending' && t.settled_legs ? ` · ${t.settled_legs}/${t.legs_count ?? t.legs.length}` : ''}</span>
      </header>
      {negEv && (
        <p className="mx-4 mb-1 flex items-start gap-1.5 rounded-lg bg-warn px-2.5 py-1.5 text-[11px] font-medium text-warn">
          <AlertTriangle className="mt-px h-3.5 w-3.5 shrink-0" aria-hidden />
          <span>EV negativ: favoriți clari, dar cotele nu acoperă marja casei. Informativ — miză minimă.</span>
        </p>
      )}

      <ul className="px-4">
        {t.legs.slice(0, maxLegs).map((l, i) => (
          <li key={`${l.match_id}-${i}`} className="flex items-start gap-2.5 border-t border-dashed py-2.5 first:border-t-0">
            <LegIcon r={l.result} />
            <div className="min-w-0 flex-1">
              <div className="text-sm font-semibold leading-snug">{plainPick(l.market, l.line, l.selection, l.label)}</div>
              <Link to={`/meci/${l.match_id}?zi=${l.kickoff_utc ? roDay(l.kickoff_utc) : ''}`} className="mt-0.5 block text-[13px] leading-snug text-foreground/85 [overflow-wrap:anywhere] hover:text-primary">
                {l.home} – {l.away}{l.score ? <b className="num ml-1">{l.score}</b> : null}
              </Link>
              <div className="num mt-0.5 text-xs font-medium text-muted-foreground">{roKickoff(l.kickoff_utc)}</div>
            </div>
            <span className="mt-0.5 flex shrink-0 flex-col items-end gap-1">
              <span className="num rounded-lg bg-[hsl(var(--elevated))] px-2 py-1 text-sm font-extrabold">{fo(l.odds)}</span>
              <BookmakerTag source={l.odds_source} />
            </span>
          </li>
        ))}
      </ul>
      {t.legs.length > 3 && (
        <button className="mx-4 mb-1 flex min-h-[36px] items-center justify-center gap-1 rounded-lg text-xs font-semibold text-primary hover:bg-accent/50" onClick={() => setAll(!all)}>
          {all ? <><ChevronUp className="h-3.5 w-3.5" />Arată mai puține</> : <><ChevronDown className="h-3.5 w-3.5" />Încă {t.legs.length - 3} {t.legs.length - 3 === 1 ? 'meci' : 'meciuri'}</>}
        </button>
      )}

      <div className="perforation my-2" aria-hidden />

      <div className="grid grid-cols-3 gap-2 px-4 pb-3 pt-1">
        <div>
          <div className="text-[11px] font-medium text-muted-foreground">Cotă totală{t.bookmakers?.length === 1 ? ` · ${t.bookmakers[0]}` : ''}</div>
          <div className="num text-gradient-primary text-[28px] font-extrabold leading-tight">{fo(t.total_odds)}</div>
          {t.repriced && t.total_odds_published ? <div className="text-[10.5px] text-muted-foreground" title="Cota de la publicare rămâne cea folosită în statistici">publicat la {fo(t.total_odds_published)}</div> : null}
          {t.clv != null && <ClvChip clv={t.clv} />}
        </div>
        <div className="text-center">
          <div className="flex items-center justify-center text-[11px] font-medium text-muted-foreground">Șansă<InfoTip text={HELP.prudent} label="Ce înseamnă șansa biletului?" /></div>
          <div className="text-[17px] font-bold leading-tight tabular-nums">{pct(t.p_ticket, (t.p_ticket ?? 1) < 0.1 ? 1 : 0)}</div>
          {v && <div className={cn('text-[11px] font-semibold', v.tone === 'win' ? 'text-win' : v.tone === 'loss' ? 'text-loss' : 'text-muted-foreground')}>valoare {v.text}</div>}
        </div>
        <div className="text-right">
          <div className="flex items-center justify-end text-[11px] font-medium text-muted-foreground">Miză<InfoTip text={HELP.stake} label="Ce înseamnă miza sugerată?" /></div>
          {t.created_by === 'user' || t.followed
            ? <div className="text-[17px] font-bold leading-tight tabular-nums">{t.stake ? `${t.stake} lei` : t.stake_units ? `${t.stake_units}u` : '—'}</div>
            : <div className="text-[17px] font-bold leading-tight tabular-nums">{t.stake_units ? `${t.stake_units}u` : '—'}</div>}
          {(t.created_by === 'user' || t.followed) && t.stake ? <div className="text-[11px] text-muted-foreground">câștig {(t.stake * t.total_odds).toFixed(0)} lei</div>
            : negEv ? <div className="text-[11px] text-muted-foreground">doar informativ</div>
            : t.stake_units ? <div className="text-[11px] text-muted-foreground">{t.stake_units}% din bancă</div> : null}
        </div>
      </div>

      {!!t.systems?.length && <SystemTables systems={t.systems} />}

      {details && (
        <div className="space-y-1 border-t bg-[hsl(var(--elevated))] px-4 py-2.5 text-xs text-muted-foreground">
          {t.reasons?.map((r) => <p key={r}>{r}</p>)}
          {t.legs.filter((l) => l.reasons?.length).map((l, i) => <p key={i}><b className="text-foreground">{plainPick(l.market, l.line, l.selection, l.label)}</b> ({l.home} – {l.away}): {l.reasons!.slice(0, 2).join(' · ')}</p>)}
        </div>
      )}

      <footer className="mt-auto flex items-center gap-1 border-t px-2 py-1.5">
        {(t.reasons?.length || t.legs.some((l) => l.reasons?.length)) ? <button className="btn btn-ghost px-2.5 text-xs" aria-expanded={details} onClick={() => setDetails(!details)}>{details ? 'Ascunde' : 'De ce?'}</button> : null}
        <div className="ml-auto flex gap-1">
          <button className="btn btn-ghost px-2.5 text-xs" onClick={copy} aria-label="Copiază biletul ca text"><Copy className="h-4 w-4" /><span className="hidden sm:inline">Copiază</span></button>
          <button className="btn btn-ghost px-2.5 text-xs" onClick={() => void share()} aria-label="Partajează biletul ca imagine"><Share2 className="h-4 w-4" />Imagine</button>
          {!saved && <button className="btn btn-outline px-3 text-xs" title="Adaugă biletul la „Biletele mele” (cu miza ta). Statisticile Robotului se salvează oricum automat."
            onClick={() => { actions.saveTicket({ ...t, id: `${t.id}`, created_by: t.created_by ?? 'robot', followed: true, stake: t.stake ?? getState().settings.defaultStake }); toast.success('Adăugat la „Biletele mele” — îl urmărim și îl decontăm automat'); }}><PlayCircle className="h-4 w-4" />Îl joc</button>}
          {onRemove && <button className="btn btn-ghost px-2.5 text-xs" onClick={onRemove}><Trash2 className="h-4 w-4" />Șterge</button>}
        </div>
      </footer>
    </article>
  );
}

/** Variante sistem Superbet: tabel câștig după numărul de selecții ratate (în unități, pentru miza totală). */
function SystemTables({ systems }: { systems: NonNullable<Ticket['systems']> }) {
  return (
    <details className="border-t px-4 py-2 text-xs">
      <summary className="cursor-pointer font-semibold text-primary">Variante sistem ({systems.map((s) => s.system).join(', ')})</summary>
      <div className="mt-2 space-y-3">{systems.map((s) => (
        <div key={s.system}>
          <div className="mb-1 flex flex-wrap gap-x-3 text-muted-foreground"><b className="text-foreground">Sistem {s.system}</b><span>{s.combos} combinații × {s.stake_per_combo}u = {s.stake_total}u</span>{s.p_any_return != null && <span>șansă de a primi ceva: {pct(s.p_any_return, 1)}</span>}{s.ev != null && <span className={s.ev >= 0 ? 'text-win' : 'text-loss'}>EV {(s.ev * 100).toFixed(1)}%</span>}</div>
          <table className="pro-table w-full"><thead><tr><th className="text-left">Ratate</th><th>Șansă</th><th>Min</th><th>Mediu</th><th>Max</th></tr></thead>
            <tbody>{s.table.map((r) => <tr key={r.misses}><td className="text-left">{r.misses === 0 ? 'toate intră' : `${r.misses} ratat${r.misses > 1 ? 'e' : 'ă'}`}</td><td>{pct(r.prob, 1)}</td><td>{r.payout_min.toFixed(2)}u</td><td>{r.payout_avg.toFixed(2)}u</td><td>{r.payout_max.toFixed(2)}u</td></tr>)}</tbody></table>
        </div>
      ))}</div>
    </details>
  );
}
