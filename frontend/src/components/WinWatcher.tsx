import { useEffect, useState } from 'react';
import { createPortal } from 'react-dom';
import { Trophy } from 'lucide-react';
import { getJSON } from '@/lib/fetcher';
import { useStore } from '@/lib/store';
import { reducedMotion, haptic } from '@/lib/gestures';
import type { Ticket, TicketsFile } from '@/lib/types';

const KEY = 'bp.won.seen';
const seen = (): Set<string> => { try { return new Set(JSON.parse(localStorage.getItem(KEY) || '[]')); } catch { return new Set(); } };
const save = (s: Set<string>) => { try { localStorage.setItem(KEY, JSON.stringify([...s].slice(-300))); } catch { /* */ } };

/** Animație de câștig când un bilet (al Robotului sau al meu) se decontează „câștigat”. Prima rulare doar memorează. */
export function WinWatcher() {
  const mine = useStore((s) => s.myTickets);
  const [win, setWin] = useState<Ticket | null>(null);
  useEffect(() => {
    let alive = true;
    const check = async () => {
      const f = await getJSON<TicketsFile>('api/tickets/today.json', { fresh: true });
      const all: Ticket[] = [...(f?.tickets ?? []), ...mine];
      const s = seen(); const first = !localStorage.getItem(KEY);
      const fresh = all.filter((t) => t.status === 'won' && !s.has(String(t.id)));
      fresh.forEach((t) => s.add(String(t.id))); save(s);
      if (!first && fresh.length && alive) { haptic(40); setWin(fresh[0]); }
    };
    void check();
    const id = setInterval(check, 5 * 60 * 1000);
    return () => { alive = false; clearInterval(id); };
  }, [mine]);
  useEffect(() => { if (!win) return; const id = setTimeout(() => setWin(null), 4200); return () => clearTimeout(id); }, [win]);
  if (!win) return null;
  const rm = reducedMotion();
  return createPortal(
    <div role="status" aria-live="polite" className="fixed inset-0 z-[90] grid place-items-center bg-black/40 p-6" onClick={() => setWin(null)}>
      {!rm && <div aria-hidden className="confetti">{Array.from({ length: 36 }, (_, i) => <i key={i} style={{ left: `${(i * 37) % 100}%`, animationDelay: `${(i % 9) * 0.08}s`, background: `hsl(${(i * 47) % 360} 90% 60%)` }} />)}</div>}
      <div className={rm ? 'card p-6 text-center' : 'card win-pop p-6 text-center'}>
        <Trophy className="mx-auto h-12 w-12 text-warn" aria-hidden />
        <div className="mt-2 text-xl font-extrabold">Bilet câștigat!</div>
        <div className="num text-gradient-primary text-3xl font-extrabold">cotă {Number(win.effective_odds ?? win.total_odds).toFixed(2)}</div>
        <div className="mt-1 text-sm text-muted-foreground">{win.variant_label ?? win.kind} · {win.legs.length} selecții</div>
      </div>
    </div>, document.body);
}
