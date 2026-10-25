import { useAsync, getJSON } from '@/lib/fetcher';
import { Badge } from '@/components/kit';

type G = { total: number; won: number; lost: number; pending: number; unsettleable: number; hit_rate: number | null; roi: number | null };
type R = { match_id: number; home: string; away: string; kickoff_utc: string; kind: string; label: string; price: number; orig_price?: number | null;
  ev?: number | null; method?: string; result?: string | null; score?: string | null };
type T = { day: string; total_odds: number; stake: number; status: string; ev?: number | null; legs: number };
type Doc = { groups: Record<string, G>; recent: R[]; ticket: { n: number; won: number; pending: number; roi: number | null; list: T[] } };

const NAMES: Record<string, string> = { toate: 'Toate', ev_pozitiv: 'EV > 0', super_cota: 'Super Cota · pe hârtie', model: 'Combinații model', estimat: 'Estimate (?)' };
const pct = (x: number | null | undefined) => (x == null ? '—' : `${x > 0 ? '+' : ''}${(x * 100).toFixed(1)}%`);
const RES: Record<string, ['win' | 'loss' | 'muted', string]> = { won: ['win', 'Câștigat'], lost: ['loss', 'Pierdut'], void: ['muted', 'Anulat'], unsettleable: ['muted', 'Nedecontabil'] };

/** Statistici › Cote mărite: rezultate la cota mărită (miză 1), pe tip, plus biletul „Cote mărite +EV”. */
export function BoostsPanel() {
  const q = useAsync(() => getJSON<Doc>('api/boosts/history.json'), []);
  const d = q.data;
  if (q.loading) return <div className="card p-4 text-sm text-muted-foreground">Se încarcă…</div>;
  if (!d) return <div className="card p-4 text-sm text-muted-foreground">Încă nu există date despre cote mărite.</div>;
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-2">
        {Object.entries(d.groups).map(([k, g]) => (
          <div key={k} className="card p-3">
            <div className="text-[11px] font-bold uppercase tracking-wide text-muted-foreground">{NAMES[k] ?? k}</div>
            <div className="num mt-1 text-lg font-extrabold">{g.hit_rate == null ? '—' : `${(g.hit_rate * 100).toFixed(0)}%`}<span className="ml-1 text-xs font-semibold text-muted-foreground">lovit</span></div>
            <div className={`num text-sm font-bold ${(g.roi ?? 0) > 0 ? 'text-win' : (g.roi ?? 0) < 0 ? 'text-loss' : ''}`}>ROI {pct(g.roi)}</div>
            <div className="mt-1 text-[11px] text-muted-foreground">{g.won}✓ · {g.lost}✗ · {g.pending} în așteptare{g.unsettleable ? ` · ${g.unsettleable} nedecontabile` : ''}</div>
          </div>
        ))}
      </div>
      <p className="text-[11px] text-muted-foreground">ROI la cota mărită, miză egală. „Nedecontabile” = șuturi/cornere/jucători, fără date de rezultat în feed. „Estimate” = EV din cota normală minus ~10% marjă.</p>
      <section className="card p-3">
        <h3 className="mb-2 text-sm font-bold">Biletul „Cote mărite +EV”</h3>
        <div className="mb-2 text-xs text-muted-foreground">{d.ticket.n} decontate · {d.ticket.won} câștigate · {d.ticket.pending} în așteptare · ROI {pct(d.ticket.roi)}</div>
        <ul className="space-y-1">
          {d.ticket.list.map((t) => (
            <li key={t.day} className="flex items-center justify-between gap-2 text-xs">
              <span>{t.day} · {t.legs} sel. · cota <b className="num">{t.total_odds.toFixed(2)}</b>{t.ev != null ? ` · EV ${pct(t.ev)}` : ''}</span>
              <Badge tone={t.status === 'won' ? 'win' : t.status === 'lost' ? 'loss' : 'muted'}>{RES[t.status]?.[1] ?? 'În așteptare'}</Badge>
            </li>
          ))}
          {!d.ticket.list.length && <li className="text-xs text-muted-foreground">Niciun bilet încă.</li>}
        </ul>
      </section>
      <section className="card p-3">
        <h3 className="mb-2 text-sm font-bold">Recente</h3>
        <ul className="space-y-2">
          {d.recent.map((r) => (
            <li key={`${r.match_id}-${r.label}`} className="flex items-start gap-2 border-b border-border/50 pb-2 last:border-0">
              <div className="min-w-0 flex-1">
                <div className="break-words text-xs font-semibold">{r.home} – {r.away}{r.score ? ` · ${r.score}` : ''}</div>
                <div className="break-words text-xs leading-snug">{r.label}{r.kind === 'super_cota' && <span className="ml-1.5 align-middle"><Badge tone="muted">experimental · pe hârtie</Badge></span>}</div>
                <div className="text-[11px] text-muted-foreground">{new Date(r.kickoff_utc).toLocaleString('ro-RO', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit', timeZone: 'Europe/Bucharest' })} · EV {pct(r.ev)}{(r.method || '').startsWith('incert') ? ' ?' : ''}</div>
              </div>
              <div className="flex shrink-0 flex-col items-end gap-1">
                <span className="num text-sm font-extrabold">{r.price.toFixed(2)}</span>
                <Badge tone={RES[r.result ?? '']?.[0] ?? 'muted'}>{RES[r.result ?? '']?.[1] ?? 'În așteptare'}</Badge>
              </div>
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}
