import { PlayOnSuperbet, legWebUrl } from './PlayOnSuperbet';
import { SuperbetLink } from './SuperbetLink';
import { useState } from 'react';
import { Link } from 'react-router';
import { Trash2, Copy, CheckCircle2, XCircle, Clock, MinusCircle, Ticket as TicketIcon, Triangle, ChevronDown, ChevronUp, User, ShieldCheck, AlertTriangle, Share2, HelpCircle, Plus } from 'lucide-react';
import type { Ticket } from '@/lib/types';
import { odds as fo, pct, roDay, roKickoff, dayLabel } from '@/lib/format';
import { plainPick } from '@/lib/markets';
import { BookmakerTag, ClvChip, InfoTip } from './kit';
import { cn } from '@/lib/utils';
import { actions, getState, useStore } from '@/lib/store';
import { HELP, valueInfo } from '@/lib/ui';
import { toast } from 'sonner';
import { isSafeTicket } from '@/lib/robot';
import { stakePct, suggestedLei } from '@/lib/stake';

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
  return ds.length > 1 ? `${dayLabel(ds[0])} – ${dayLabel(ds[ds.length - 1])}` : null;
}

/** Id-urile Superbet ale selecției (simple sau picioarele Bet Builder), pentru „pune pe bilet” în aplicație. */
function legRefs(l: Ticket['legs'][number]) {
  if (!l.sb_event_id) return undefined;
  const picks = l.bb_picks?.length ? l.bb_picks : l.sb_pick ? [l.sb_pick] : [];
  const out = picks.map((p) => p.ref?.split(',')).filter((r): r is string[] => !!r && r.length >= 3 && /^\d+$/.test(r[0]))
    .map((r) => ({ eventId: l.sb_event_id!, outcomeId: Number(r[0]), sbv: r.slice(1, -1).join(','), uuid: r[r.length - 1] }));
  return out.length === picks.length && out.length ? out : undefined;
}

function ticketTitle(t: Ticket) {
  if (t.kind === 'pyramid') return t.variant === 'principal' || !t.variant ? 'Piramida zilei' : (t.variant_label ?? 'Alternativă');
  if (t.created_by === 'user') return 'Biletul meu';
  if (t.kind === 'acca_value') return `Bilet de valoare · ${t.legs.length} selecții`;
  if (t.kind === 'acca_double') return 'Dublu de valoare';
  if (t.kind === 'acca_pont') return t.legs?.length === 2 ? 'Pontul zilei · dublu' : 'Pontul zilei';
  if (t.kind === 'acca_80') return t.variant_label ?? 'Tiparul 80%+';
  if (t.kind === 'acca_stil' || t.variant === 'stil_supersocial') {
    const name = (t.variant_label ?? '').replace(/^Stil Supersocial\s*·\s*/, '').replace(/^Pe val\s*·\s*/, '').trim();
    if (!name || name === 'Supersocial' || /scurt/i.test(name)) return 'Stil Supersocial';
    if (name.startsWith('Alegerea robotului')) return `⭐ ${name}`;
    return `Pe val · ${name}`;
  }
  if (t.lottery || t.variant === 'loterie') return `Loterie ~${t.target_odds ?? Math.round(t.total_odds)}`;
  if (isSafeTicket(t)) return `Bilet sigur ~${t.target_odds ?? Math.round(t.total_odds)}`;
  if (t.target_odds) return `Bilet cotă ~${t.target_odds}`;
  return t.variant_label ?? 'Bilet';
}

/** Bilet ca la casa de pariuri: selecțiile sus, perforație, apoi cota totală, șansa și miza. */
/** Bilet pierdut: status „lost” sau (acumulator, nu sistem) cel puțin o selecție pierdută. Ascuns peste tot în afară de Statistici. */
export { isLostTicket } from '@/lib/board';

export function TicketCard({ t, saved, onRemove, compact, play: playMode }: { t: Ticket; saved?: boolean; onRemove?: () => void; compact?: boolean; play?: boolean }) {
  // biletul e deja în „Biletele mele” (apăsat „Îl joc”): butonul devine „Plasat”
  const placed = useStore((s) => s.myTickets.some((x) => `${x.id}` === `${t.id}`));
  const bank = useStore((s) => s.settings.bank ?? 0);
  const slip = useStore((s) => s.slip);
  const [now] = useState(() => Date.now());
  const sugg = t.status === 'pending' || !t.status ? suggestedLei(t, bank) : null;
  const [all, setAll] = useState(!compact);
  const [details, setDetails] = useState(false);
  const tone = statusTone(t.status);
  const v = valueInfo(t.ev);
  const maxLegs = all ? t.legs.length : Math.min(t.legs.length, 3);
  const safe = isSafeTicket(t) && t.created_by !== 'user';
  const negEv = !playMode && t.created_by !== 'user' && !t.followed && t.kind !== 'pyramid' && t.kind !== 'acca_stil' && t.variant !== 'stil_supersocial' && (t.informational || (t.ev ?? 0) < 0);
  const Icon = t.kind === 'pyramid' ? Triangle : t.created_by === 'user' ? User : safe ? ShieldCheck : TicketIcon;
  const copy = () => {
    const txt = [`BETPREDICT · ${ticketTitle(t)} · cotă ${fo(t.total_odds)}`, ...t.legs.map((l) => `${roKickoff(l.kickoff_utc)} ${l.home} – ${l.away}: ${plainPick(l.market, l.line, l.selection, l.label)} @ ${fo(l.odds)}`)].join('\n');
    navigator.clipboard?.writeText(txt).then(() => toast.success('Bilet copiat'), () => toast.error('Nu am putut copia'));
  };
  const [play, setPlay] = useState(false);
  const share = async () => {
    const { shareTicket } = await import('@/lib/shareImage');
    const r = await shareTicket(t, ticketTitle(t), `BETPREDICT · ${ticketTitle(t)} · cotă ${fo(t.total_odds)}`);
    if (r === 'downloaded') toast.success('Imaginea biletului a fost descărcată — o poți trimite pe WhatsApp');
    else if (r === 'failed') toast.error('Nu am putut genera imaginea');
  };
  const open = t.legs.filter((l) => !l.result);
  const oneLeft = t.status === 'pending' && t.kind !== 'pyramid' && t.legs.length >= 3 && open.length === 1 && !t.legs.some((l) => l.result === 'lost') ? open[0] : null;
  const hasBoost = t.kind !== 'acca_boost' && t.legs.some((l) => l.market === 'boost');
  const chip = t.lottery ? 'Loterie' : t.kind === 'acca_stil' || t.variant === 'stil_supersocial' ? '' : (t.bucket ?? '').replace(/\(vechi\)/i, '').trim();
  const variantNote = t.kind !== 'pyramid' && t.kind !== 'acca_stil' && t.variant !== 'stil_supersocial' && !safe && t.variant_label && t.target_odds && !t.variant_label.includes('_') ? t.variant_label : null;
  return (
    <article className={cn('card card-hover flex flex-col overflow-hidden', t.status === 'won' && 'border-[hsl(var(--win)/0.5)]', t.status === 'lost' && 'opacity-85')}>
      <header className={cn('flex items-center gap-2.5 px-4 pb-2.5 pt-3.5', t.kind === 'pyramid' ? 'ticket-top-pyr' : safe ? 'ticket-top-safe' : 'ticket-top')}>
        <span className={cn('flex h-10 w-10 shrink-0 items-center justify-center rounded-2xl ring-1 ring-inset ring-[hsl(var(--glass-border))]', t.kind === 'pyramid' ? 'bg-info text-info' : safe ? 'bg-win text-win' : 'bg-primary/15 text-primary')}><Icon className="h-[18px] w-[18px]" /></span>
        <div className="min-w-0 flex-1">
          <div className="truncate text-[16px] font-extrabold leading-tight tracking-[-0.03em]">{ticketTitle(t)}</div>
          {(chip || t.lottery) && <div className="mt-0.5 flex gap-1"><span className={cn('rounded-full px-2 py-px text-[10px] font-bold uppercase tracking-wider', t.lottery ? 'bg-[hsl(var(--glow-3)/0.18)] text-[hsl(var(--glow-3))]' : 'bg-primary/15 text-primary')}>{chip}</span>{negEv && !/informativ/i.test(chip) && <span className="rounded-full bg-warn px-2 py-px text-[10px] font-bold uppercase tracking-wider text-warn">informativ</span>}{!negEv && (t.kind === 'acca_value' || t.kind === 'acca_double') && !t.lottery && (t.ev ?? 0) > 0 && <span className="rounded-full bg-win px-2 py-px text-[10px] font-bold uppercase tracking-wider text-win">joacă</span>}</div>}
          {oneLeft && <div className="mt-0.5"><span className="rounded-full bg-win px-2 py-px text-[10px] font-bold uppercase tracking-wider text-win">mai lipsește o selecție: {oneLeft.home} – {oneLeft.away}</span></div>}
          {t.legs.some((l) => l.unavailable) && <div className="mt-0.5"><span className="rounded-full bg-loss px-2 py-px text-[10px] font-bold uppercase tracking-wider text-loss">o selecție nu se mai poate pune</span></div>}
          {hasBoost && <div className="mt-0.5 flex flex-wrap gap-1">
            {hasBoost && <span className="rounded-full bg-[hsl(var(--glow-3)/0.18)] px-2 py-px text-[10px] font-bold uppercase tracking-wider text-[hsl(var(--glow-3))]">cu cotă mărită</span>}
          </div>}
          <div className="line-clamp-2 text-xs leading-snug text-muted-foreground">{[legSpan(t) ?? (t.date && dayLabel(t.date)), variantNote, `${t.legs.length} ${t.legs.length === 1 ? 'meci' : 'meciuri'}`, t.overlap ? `comun cu ${t.overlap} ${t.overlap === 1 ? 'bilet' : 'bilete'}` : null, t.followed && 'jucat de mine'].filter(Boolean).join(' · ')}</div>
        </div>
        <span className={cn('shrink-0 rounded-full px-2.5 py-1 text-[11px] font-bold', PILL[tone])}>{statusText(t.status)}{t.status === 'pending' && t.settled_legs ? ` · ${t.settled_legs}/${t.legs_count ?? t.legs.length}` : ''}</span>
      </header>
      {playMode && (t.kind === 'acca_stil' || t.variant === 'stil_supersocial') && (
        <p className="mx-4 mb-1 flex items-center gap-1.5 text-[11px] text-muted-foreground"><AlertTriangle className="h-3 w-3 shrink-0 text-warn" aria-hidden />O selecție ratată pierde biletul. Hârtie, miză {String(t.stake ?? 0.05).replace('.', ',')} unități.</p>
      )}
      {playMode && t.kind !== 'acca_stil' && t.variant !== 'stil_supersocial' && (t.ev ?? 0) <= 0 && (
        <p className="mx-4 mb-1 flex items-center gap-1.5 text-[11px] text-muted-foreground"><AlertTriangle className="h-3 w-3 shrink-0 text-warn" aria-hidden />Risc: EV realist {((t.ev ?? 0) * 100).toFixed(1)}% · miză mică</p>
      )}
      {negEv && (
        <p className="mx-4 mb-1 flex items-start gap-1.5 rounded-lg bg-warn px-2.5 py-1.5 text-[11px] font-medium text-warn">
          <AlertTriangle className="mt-px h-3.5 w-3.5 shrink-0" aria-hidden />
          <span><b>INFORMATIV · nu e recomandat la joc.</b> Valoare negativă: cotele nu acoperă marja casei. Pentru joc folosește biletele de valoare.</span>
        </p>
      )}

      <ul className="px-4">
        {t.legs.slice(0, maxLegs).map((l, i) => (
          <li key={`${l.match_id}-${i}`} className="flex items-center gap-3 border-t border-dashed py-2.5 first:border-t-0">
            <LegIcon r={l.result} />
            <div className="min-w-0 flex-1">
              <div className="break-words text-[15px] font-extrabold leading-tight">{plainPick(l.market, l.line, l.selection, l.label)}
                {l.market === 'boost' && t.kind !== 'acca_boost' && <span className="ml-1.5 inline-block rounded-full bg-[hsl(var(--glow-3)/0.18)] px-1.5 py-px align-middle text-[9px] font-bold uppercase tracking-wider text-[hsl(var(--glow-3))]">cotă mărită</span>}</div>
              <Link to={`/meci/${l.match_id}?zi=${l.kickoff_utc ? roDay(l.kickoff_utc) : ''}`} className="mt-0.5 block break-words text-[13px] leading-snug text-foreground/85 hover:text-primary">
                {l.home} – {l.away}{l.score ? <b className="num ml-1">{l.score}</b> : null}
              </Link>
              <div className="num mt-0.5 text-[11px] font-medium text-muted-foreground">{roKickoff(l.kickoff_utc)}{l.absences ? ` · absenți ${l.absences.home}–${l.absences.away}` : ''}</div>
              {l.unavailable && <div className="mt-0.5 text-[11px] font-bold text-loss">Nu se mai poate pune pe Superbet acum</div>}
              {!l.unavailable && l.odds_now ? <div className="mt-0.5 text-[11px] font-bold text-warn">Cota pe Superbet acum: {fo(l.odds_now)}</div> : null}
              <div className="mt-0.5 flex flex-wrap items-center gap-x-3">
                {(l.superbet_url || l.sb_event_id) && <SuperbetLink url={legWebUrl(l)} eventId={l.sb_event_id} bets={legRefs(l)} className="inline-flex min-h-8 items-center gap-1 text-[11px] font-semibold text-primary" />}
                {!l.result && t.status === 'pending' && (!l.kickoff_utc || Date.parse(l.kickoff_utc) > now) && (() => {
                  const on = slip.some((x) => x.match_id === l.match_id && x.market === l.market && x.line === l.line && x.selection === l.selection);
                  return (
                    <button type="button" className={cn('inline-flex min-h-8 items-center gap-1 text-[11px] font-semibold', on ? 'text-win' : 'text-muted-foreground hover:text-primary')}
                      aria-pressed={on} onClick={() => { actions.toggleSlip({ ...l, result: null, score: null, odds: l.odds_now ?? l.odds }); toast(on ? 'Scos de pe biletul meu' : 'Adăugat pe biletul meu'); }}>
                      {on ? <><CheckCircle2 className="h-3 w-3" />Pe biletul meu</> : <><Plus className="h-3 w-3" />Biletul meu</>}
                    </button>
                  );
                })()}
              </div>
            </div>
            <span className="flex shrink-0 flex-col items-end gap-1">
              <span className="odd-chip">{fo(l.odds)}</span>
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

      <div className="slip-sum mx-3 mb-3 grid grid-cols-[1.2fr_1fr_1fr] overflow-hidden rounded-2xl">
        <div className="slip-odds px-3 py-2.5">
          <div className="text-[10px] font-extrabold uppercase tracking-wider text-primary-foreground/75">Cotă</div>
          <div className="num text-[30px] font-extrabold leading-none tracking-tight text-primary-foreground">{fo(t.total_odds)}</div>
          {t.repriced && t.total_odds_published ? <div className="text-[10px] text-primary-foreground/75">publicat {fo(t.total_odds_published)}</div> : null}
          {t.clv != null && <ClvChip clv={t.clv} />}
        </div>
        <div className="flex flex-col items-center justify-center px-1.5 py-2 text-center">
          <div className="flex items-center text-[10px] font-bold uppercase tracking-wide text-muted-foreground">Șansă<InfoTip text={HELP.prudent} label="Ce înseamnă șansa biletului?" /></div>
          <div className="num text-[18px] font-extrabold leading-tight">{pct(t.p_ticket, (t.p_ticket ?? 1) < 0.1 ? 1 : 0)}</div>
          {v && <div className={cn('text-[10px] font-semibold', v.tone === 'win' ? 'text-win' : v.tone === 'loss' ? 'text-loss' : 'text-muted-foreground')}>{v.text}</div>}
        </div>
        <div className="flex flex-col items-center justify-center px-1.5 py-2 text-center">
          <div className="flex items-center text-[10px] font-bold uppercase tracking-wide text-muted-foreground">Miză<InfoTip text={HELP.stake} label="Ce înseamnă miza sugerată?" /></div>
          {t.created_by === 'user' || t.followed
            ? <div className="num text-[18px] font-extrabold leading-tight">{t.stake ? `${t.stake}` : t.stake_units ? `${t.stake_units}u` : '—'}</div>
            : <div className="num text-[18px] font-extrabold leading-tight">{t.stake_units ? `${t.stake_units}u` : '—'}</div>}
          {(t.created_by === 'user' || t.followed) && t.stake ? <div className="text-[10px] text-muted-foreground">{(t.stake * t.total_odds).toFixed(0)} lei</div>
            : negEv ? <div className="text-[10px] text-muted-foreground">informativ</div>
            : sugg ? <div className="text-[10px] font-semibold text-primary" title={`${((stakePct(t) ?? 0) * 100).toLocaleString('ro-RO')}% din bancă`}>sugerat {sugg} lei</div>
            : t.stake_units ? <div className="text-[10px] text-muted-foreground">din bancă</div> : null}
        </div>
      </div>


      {details && (
        <div className="space-y-1 border-t bg-[hsl(var(--elevated))] px-4 py-2.5 text-xs text-muted-foreground">
          {t.reasons?.map((r) => <p key={r}>{r}</p>)}
          {t.legs.filter((l) => l.reasons?.length).map((l, i) => <p key={i}><b className="text-foreground">{plainPick(l.market, l.line, l.selection, l.label)}</b> ({l.home} – {l.away}): {l.reasons!.slice(0, 2).join(' · ')}</p>)}
        </div>
      )}

      <footer className="mt-auto flex items-center gap-1 px-3 pb-3">
        {(t.reasons?.length || t.legs.some((l) => l.reasons?.length)) ? <button className="slip-ico" aria-expanded={details} aria-label={details ? 'Ascunde motivul' : 'De ce acest bilet'} onClick={() => setDetails(!details)}><HelpCircle className="h-4 w-4" /></button> : null}
        <button className="slip-ico" onClick={copy} aria-label="Copiază biletul ca text"><Copy className="h-4 w-4" /></button>
        <button className="slip-ico" onClick={() => void share()} aria-label="Partajează biletul ca imagine"><Share2 className="h-4 w-4" /></button>
        {onRemove && <button className="slip-ico" onClick={onRemove} aria-label="Șterge biletul"><Trash2 className="h-4 w-4" /></button>}
        <div className="ml-auto flex gap-1.5">
          {t.status === 'pending' && t.legs.some((l) => l.sb_event_id) && <button className="btn h-10 rounded-xl px-3" onClick={() => setPlay(true)}>Superbet</button>}
          {!saved && (placed
            ? <button className="btn h-10 gap-1 rounded-xl border-[hsl(var(--win))] px-3 text-win" title="Plasat: e în „Biletele mele”. Atinge ca să-l scoți."
                onClick={() => { actions.removeTicket(`${t.id}`); toast('Scos din „Biletele mele”'); }}><CheckCircle2 className="h-4 w-4" />Plasat</button>
            : <button className="btn btn-primary h-10 rounded-xl px-3" title="Adaugă biletul la „Biletele mele” (cu miza ta)."
                onClick={() => { actions.saveTicket({ ...t, id: `${t.id}`, created_by: t.created_by ?? 'robot', followed: true, stake: t.stake ?? suggestedLei(t, getState().settings.bank ?? 0) ?? getState().settings.defaultStake }); toast.success('Plasat — e în „Biletele mele”, îl urmărim și îl decontăm automat'); }}>Îl joc</button>)}
        </div>
      </footer>
      {play && <PlayOnSuperbet t={t} open={play} onClose={() => setPlay(false)} />}
    </article>
  );
}

