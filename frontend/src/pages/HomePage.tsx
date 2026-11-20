import { Link } from 'react-router';
import { ChevronRight } from 'lucide-react';
import type { ReactNode } from 'react';
import { useTodayBoard, useMeta, useNow } from '@/lib/hooks';
import { useAsync } from '@/lib/fetcher';
import { loadPyramidSafe, loadTicketsHistory } from '@/lib/data';
import { isLostTicket } from '@/lib/board';
import { longDay, odds as fo, pct, roTime, todayRo, lei } from '@/lib/format';
import type { Ticket } from '@/lib/types';
import { cn } from '@/lib/utils';
import { AnalystBrief } from '@/components/AnalystBrief';
import { BankrollPanel } from '@/components/BankrollPanel';
import { useHomeOrder, HomeOrderButton, type HomeSection } from '@/components/HomeOrder';

// același „nou început” ca în Bilete (TicketsPage): biletele Robotului de dinainte nu mai apar
const TICKETS_RESET = '2026-11-19T06:45:00Z';
const LONG_LABEL: Record<string, string> = { s100: 'Cotă 100', s500: 'Cotă 500', s1000: 'Cotă 1.000', s5000: 'Cotă 5.000', s10000: 'Cotă 10.000' };

const finished = (t: Ticket) => t.status === 'won' || t.status === 'lost' || t.status === 'void' || isLostTicket(t);
const firstKick = (t: Ticket) => Math.min(...t.legs.map((l) => (l.kickoff_utc ? Date.parse(l.kickoff_utc) : Infinity)));
const settledLegs = (t: Ticket) => t.settled_legs ?? t.legs.filter((l) => !!l.result).length;

type Tone = 'win' | 'loss' | 'live' | 'wait';
function state(t: Ticket, now: number): { text: string; tone: Tone } {
  if (t.status === 'won') return { text: 'Câștigat', tone: 'win' };
  if (t.status === 'lost' || isLostTicket(t)) return { text: 'Pierdut', tone: 'loss' };
  if (t.status === 'void') return { text: 'Anulat', tone: 'wait' };
  const k = firstKick(t);
  if (Number.isFinite(k) && k <= now) return { text: `În joc · ${settledLegs(t)}/${t.legs.length} decise`, tone: 'live' };
  return { text: Number.isFinite(k) ? `Primul meci ${roTime(new Date(k).toISOString())}` : 'Neînceput', tone: 'wait' };
}

function Section({ title, aside, to, link, children }: { title: string; aside?: ReactNode; to: string; link: string; children: ReactNode }) {
  return (
    <section className="hb-sec">
      <div className="hb-sec-h"><h2>{title}</h2>{aside && <span>{aside}</span>}</div>
      {children}
      <Link to={to} className="hb-more">{link}<ChevronRight className="h-4 w-4" /></Link>
    </section>
  );
}

function TicketRow({ t, label, now }: { t: Ticket; label: string; now: number }) {
  const s = state(t, now);
  return (
    <Link to={`/bilete?bilet=${t.id}`} className="hb-row">
      <span className="min-w-0 flex-1">
        <span className="hb-row-name">{label}</span>
        <span className="hb-row-meta">{t.legs.length} meciuri{t.p_ticket ? ` · șansă estimată ${pct(t.p_ticket)}` : ''}</span>
        <span className={cn('hb-pill', `hb-${s.tone}`)}>{s.text}</span>
      </span>
      <span className="hb-odd">{fo(t.total_odds)}</span>
    </Link>
  );
}

/** Acasă: brief-ul zilei — biletul de ~10, pasul piramidei, biletele lungi, rezumatul analistului și banca. */
export default function HomePage() {
  const now = useNow();
  const today = todayRo();
  const meta = useMeta();
  const { full, loading } = useTodayBoard(today, false);
  const history = useAsync(loadTicketsHistory, []);
  const pyr = useAsync(() => loadPyramidSafe('1.20'), []);
  const [order, setOrder] = useHomeOrder();

  const s10 = full.filter((t) => t.kind === 'acca_super' && t.variant === 's10');
  const seen = new Set<string>();
  const long = [...full, ...(history.data ?? [])]
    .filter((t) => t.kind === 'acca_super' && t.variant !== 's10' && (t.created_at ?? '') >= TICKETS_RESET && !finished(t))
    .filter((t) => { const id = String(t.id); if (seen.has(id)) return false; seen.add(id); return true; })
    .sort((a, b) => (b.total_odds ?? 0) - (a.total_odds ?? 0));

  const p = pyr.data;
  const start = p?.run?.start_date || null;
  const stepRow = (p?.history ?? []).find((r) => r.date === today && (!start || r.date >= start));
  const stepNo = p?.action?.step ?? (p?.run?.step != null ? p.run.step + 1 : null);
  const pyrState = pyr.loading ? '…' : !p ? 'fără date'
    : stepRow?.result === 'won' ? 'câștigat' : stepRow?.result === 'lost' ? 'pierdut'
      : p.today?.status !== 'pick' || stepRow?.status === 'no_bet' ? 'pauză azi' : 'în joc';
  const pyrOdd = p?.today?.main?.total_odds ?? stepRow?.odds ?? null;
  const s10Best = s10[0];

  const blocks: Record<HomeSection, ReactNode> = {
    brief: <AnalystBrief key="brief" />,
    s10: (
      <Section key="s10" title="Cotă ~10 azi" aside="meciuri de azi, 10–24" to="/bilete" link="Toate biletele">
        {loading ? <p className="hb-empty">Se încarcă biletele…</p> : s10.length === 0
          ? <p className="hb-empty">Niciun bilet de cotă ~10 azi. Când nu sunt meciuri potrivite, nu se forțează.</p>
          : s10.map((t, i) => <TicketRow key={t.id} t={t} label={s10.length > 1 ? `Biletul ${i + 1}` : 'Biletul zilei'} now={now} />)}
      </Section>
    ),
    pyramid: (
      <Section key="pyramid" title="Piramida cotă 2" aside={stepNo ? `pasul ${stepNo}` : undefined} to="/piramida" link="Deschide piramida">
        <div className="hb-card">
          <dl className="hb-pyr-grid">
            <div><dt>Azi</dt><dd>{pyrState}</dd></div>
            <div><dt>Cotă</dt><dd className="num">{pyrOdd ? fo(pyrOdd) : '—'}</dd></div>
            <div><dt>Bancă</dt><dd className="num">{p?.run?.bank != null ? lei(p.run.bank) : '—'}</dd></div>
          </dl>
          {(p?.action?.today || p?.today?.reason) && <p className="hb-note">{p?.action?.today ?? p?.today?.reason}</p>}
        </div>
      </Section>
    ),
    long: (
      <Section key="long" title="Bilete lungi" aside={history.loading ? '…' : `${long.length} active`} to="/bilete" link="Toate biletele lungi">
        {history.loading && loading ? <p className="hb-empty">Se încarcă…</p> : long.length === 0
          ? <p className="hb-empty">Niciun bilet lung activ acum. Un bilet pierdut se înlocuiește la următoarea rulare.</p>
          : (
            <div className="hb-card hb-long">
              {long.slice(0, 5).map((t) => (
                <Link key={t.id} to={`/bilete?bilet=${t.id}`} className="hb-long-row">
                  <span className="min-w-0 flex-1">
                    <span className="hb-row-name">{LONG_LABEL[t.variant ?? ''] ?? 'Bilet lung'}</span>
                    <span className="hb-track" aria-hidden><i style={{ width: `${(settledLegs(t) / Math.max(1, t.legs.length)) * 100}%` }} /></span>
                    <span className="hb-row-meta">{settledLegs(t)}/{t.legs.length} meciuri decise{t.superbonus ? ` · SuperBonus ${t.superbonus}%` : ''}</span>
                  </span>
                  <span className="hb-odd hb-odd-sm">{fo(t.total_odds)}</span>
                </Link>
              ))}
            </div>
          )}
      </Section>
    ),
    bank: <BankrollPanel key="bank" />,
  };

  return (
    <div className="home-brief space-y-6">
      <header className="hb-hero">
        <p className="dash-kicker"><span className="hb-live-dot" aria-hidden />{longDay(today)}{meta.data?.generated_at ? ` · actualizat ${roTime(meta.data.generated_at)}` : ''}</p>
        <h1 className="mt-2">Brief-ul zilei</h1>
        <p className="hb-lede">Cotă ~10, bilete lungi și piramida de cotă 2. Probabilități estimate, nu promisiuni.</p>
        <div className="hb-kpis">
        <Link to="/bilete" className="hb-kpi"><span className="hb-kpi-k">Cotă ~10</span><strong className="num">{loading ? '…' : s10Best ? fo(s10Best.total_odds) : '—'}</strong><span className="hb-kpi-s">{loading ? '' : s10.length ? `${s10.length} bilet${s10.length > 1 ? 'e' : ''} azi` : 'fără bilet azi'}</span></Link>
        <Link to="/piramida" className="hb-kpi"><span className="hb-kpi-k">Piramidă</span><strong className="num">{stepNo ? `Pas ${stepNo}` : '—'}</strong><span className="hb-kpi-s">{pyrState}</span></Link>
        <Link to="/bilete" className="hb-kpi"><span className="hb-kpi-k">Lungi</span><strong className="num">{history.loading ? '…' : long.length}</strong><span className="hb-kpi-s">active</span></Link>
        </div>
      </header>

      {order.map((k) => blocks[k])}

      <div className="flex justify-center"><HomeOrderButton order={order} onChange={setOrder} /></div>
    </div>
  );
}
