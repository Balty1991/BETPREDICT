import { useAsync, getJSON } from '@/lib/fetcher';
import { Badge, Card } from '@/components/kit';

type Leg = { home: string; away: string; market: string; label: string; odds: number | null; implied: number | null; result: string;
  kickoff_utc?: string | null; model_p: number | null; model_ev: number | null; model_pick: boolean | null };
type SB = { status: number | null; win_count: number | null; lost_count: number | null; active_count: number | null; fetched_at: string | null };
type T = { id: string; posted: string | null; odds: number | null; legs_total: number | null; legs_visible: number; status: string; badge?: string | null; legs: Leg[];
  source?: string; ticket_id?: string | null; link?: string | null; sb?: SB | null };
type M = { market: string; label: string; seen: number; n: number; won: number; hit: number | null; implied: number | null; model_p: number | null; model_pick: number; with_model: number };
type S = { tickets: number; won: number; lost: number; pending: number; legs: number; legs_settled: number; legs_won: number; hit: number | null; implied: number | null; unsettlable: number; model_compared: number; model_would_pick: number };
type Doc = { generated_at: string; tickets: T[]; markets: M[]; summary: S; caveat: string };

const P = (x: number | null | undefined) => (x == null ? '—' : `${Math.round(x * 100)}%`);
const ADD = 'https://github.com/Balty1991/BETPREDICT/issues/new?title=' + encodeURIComponent('Bilet Ștefan') + '&body=' + encodeURIComponent('Lipește aici linkul de share Superbet (superbet.onelink.me/...) sau codul biletului:\n\n');
const ST: Record<string, ['win' | 'loss' | 'muted', string]> = { won: ['win', 'câștigat'], lost: ['loss', 'pierdut'], cashout: ['muted', 'cashout'], pending: ['muted', 'în curs'] };
const RES: Record<string, ['win' | 'loss' | 'muted', string]> = { won: ['win', '✓'], lost: ['loss', '✗'], pending: ['muted', 'în curs'], nesettlabil: ['muted', 'nesettlabil'], negasit: ['muted', 'meci negăsit'] };

/** Statistici: selecțiile reale ale lui Ștefan (din capturi), decontate din datele noastre și puse lângă robot. */
export function StefanCard() {
  const q = useAsync(() => getJSON<Doc>('api/stefan.json'), []);
  const d = q.data;
  if (!d || !d.summary) return null;
  const s = d.summary;
  return (
    <Card className="overflow-hidden">
      <div className="flex items-center justify-between gap-2 p-3 pb-1">
        <h2 className="text-sm font-semibold">Biletele lui Ștefan</h2>
        <Badge tone="muted">doar urmărire</Badge>
      </div>
      <div className="grid grid-cols-3 gap-2 px-3 py-2 text-center">
        <div><div className="num text-lg font-extrabold">{s.legs_won}/{s.legs_settled}</div><div className="text-[11px] text-muted-foreground">selecții lovite</div></div>
        <div><div className="num text-lg font-extrabold">{P(s.hit)}</div><div className="text-[11px] text-muted-foreground">vs cotă {P(s.implied)}</div></div>
        <div><div className="num text-lg font-extrabold">{s.won}✓ {s.lost}✗</div><div className="text-[11px] text-muted-foreground">bilete · {s.pending} în curs</div></div>
      </div>
      <table className="w-full text-xs">
        <thead><tr className="text-muted-foreground"><th className="px-3 py-1 text-left font-medium">Piață</th><th className="text-right font-medium">Lovit</th><th className="text-right font-medium">Cotă</th><th className="px-3 text-right font-medium">Robot</th></tr></thead>
        <tbody>{d.markets.map((m) => (
          <tr key={m.market} className="border-t">
            <td className="px-3 py-1.5">{m.label} <span className="text-muted-foreground">({m.seen})</span></td>
            <td className="text-right num">{m.n ? `${m.won}/${m.n}` : '—'}</td>
            <td className="text-right num">{P(m.implied)}</td>
            <td className="px-3 text-right num">{m.model_p == null ? '—' : P(m.model_p)}</td>
          </tr>))}
        </tbody>
      </table>
      {d.tickets.some((t) => t.source === 'superbet') && (
        <ul className="space-y-1.5 px-3 pt-2 text-xs">{d.tickets.filter((t) => t.source === 'superbet').map((t) => {
          const ours = t.legs.filter((l) => l.result === 'won').length;
          const lost = t.legs.filter((l) => l.result === 'lost').length;
          return (
            <li key={t.id} className="rounded-lg border p-2">
              <div className="flex items-center justify-between gap-2">
                <b className="min-w-0 truncate">Superbet {t.ticket_id} · @{t.odds?.toFixed(2) ?? '—'}</b>
                <Badge tone={ST[t.status]?.[0] ?? 'muted'}>{ST[t.status]?.[1] ?? t.status}</Badge>
              </div>
              <div className="mt-0.5 text-muted-foreground">{t.legs_total} selecții · Superbet: {t.sb?.win_count ?? 0}✓ {t.sb?.lost_count ?? 0}✗ {t.sb?.active_count ?? 0} active · la noi: {ours}✓ {lost}✗{t.link ? <> · <a className="underline" href={t.link} target="_blank" rel="noreferrer">deschide</a></> : null}</div>
            </li>);
        })}</ul>
      )}
      <p className="px-3 pt-2 text-xs">Robotul ar fi ales <b>{s.model_would_pick} din {s.model_compared}</b> selecții comparabile (EV ≥ 0 la cota lui Ștefan). {s.legs - s.legs_settled - s.unsettlable > 0 ? `${s.legs - s.legs_settled - s.unsettlable} în curs, ` : ''}{s.unsettlable} fără date (live sau ligă neacoperită).</p>
      <details className="px-3 pt-1 text-xs">
        <summary className="min-h-11 cursor-pointer py-2 font-semibold">Toate selecțiile ({s.legs})</summary>
        <ul className="space-y-1.5 pb-1">{d.tickets.flatMap((t) => t.legs.map((l, i) => (
          <li key={`${t.id}-${i}`} className="flex items-start justify-between gap-2 border-b border-border/50 pb-1.5 last:border-0">
            <span className="min-w-0 flex-1 break-words"><b>{l.home} – {l.away}</b><span className="block text-muted-foreground">{l.label} · @{l.odds?.toFixed(2) ?? '—'}{l.model_p != null ? ` · robot ${P(l.model_p)}` : ''} · bilet @{t.odds?.toFixed(0) ?? '—'}</span></span>
            <Badge tone={RES[l.result]?.[0] ?? 'muted'}>{RES[l.result]?.[1] ?? l.result}</Badge>
          </li>)))}
        </ul>
      </details>
      <a href={ADD} target="_blank" rel="noreferrer" className="mx-3 mt-2 flex min-h-11 items-center justify-center rounded-lg border text-xs font-semibold">+ Adaugă link de bilet Superbet</a>
      <p className="px-3 pb-3 pt-2 text-[11px] text-muted-foreground">{d.caveat} Linkurile noi se citesc la următoarea rulare (≤ 1 cerere/bilet/rulare).</p>
    </Card>
  );
}
