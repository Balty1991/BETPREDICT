import type { Ticket } from './types';
import { plainPick } from './markets';
import { roKickoff } from './format';

/** Desenează biletul pe un canvas (fără dependențe) și îl întoarce ca PNG. */
export async function ticketImage(t: Ticket, title: string): Promise<Blob | null> {
  const W = 720, pad = 36, rowH = 86, n = t.legs.length;
  const H = 210 + n * rowH + 150;
  const c = document.createElement('canvas'); c.width = W * 2; c.height = H * 2;
  const g = c.getContext('2d'); if (!g) return null;
  g.scale(2, 2);
  const bg = g.createLinearGradient(0, 0, W, H); bg.addColorStop(0, '#05070f'); bg.addColorStop(1, '#0b1424');
  g.fillStyle = bg; g.fillRect(0, 0, W, H);
  const glow = g.createRadialGradient(W * 0.85, 0, 10, W * 0.85, 0, 420); glow.addColorStop(0, 'rgba(8,240,200,.25)'); glow.addColorStop(1, 'rgba(8,240,200,0)');
  g.fillStyle = glow; g.fillRect(0, 0, W, H);
  const font = (w: number, s: number) => `${w} ${s}px Inter, system-ui, sans-serif`;
  const clip = (s: string, max: number) => { let x = s; while (g.measureText(x).width > max && x.length > 3) x = x.slice(0, -2); return x === s ? s : x + '…'; };
  g.fillStyle = '#08f0c8'; g.font = font(800, 18); g.fillText('BETPREDICT', pad, 52);
  g.fillStyle = '#fff'; g.font = font(800, 34); g.fillText(clip(title, W - pad * 2), pad, 100);
  g.fillStyle = '#93a3b8'; g.font = font(500, 18); g.fillText(`${n} ${n === 1 ? 'selecție' : 'selecții'}${t.date ? ' · ' + t.date : ''}`, pad, 132);
  let y = 175;
  for (const l of t.legs) {
    g.fillStyle = 'rgba(255,255,255,.05)'; g.beginPath(); g.roundRect(pad - 12, y - 30, W - pad * 2 + 24, rowH - 10, 16); g.fill();
    const res = l.result === 'won' ? '#22c55e' : l.result === 'lost' ? '#ef4444' : null;
    if (res) { g.fillStyle = res; g.fillRect(pad - 12, y - 30, 5, rowH - 10); }
    g.fillStyle = '#fff'; g.font = font(700, 21); g.fillText(clip(plainPick(l.market, l.line, l.selection, l.label), W - pad * 2 - 110), pad, y);
    g.fillStyle = '#c3cede'; g.font = font(500, 17); g.fillText(clip(`${l.home} – ${l.away}`, W - pad * 2 - 110), pad, y + 25);
    g.fillStyle = '#7d8ba0'; g.font = font(500, 14); g.fillText(roKickoff(l.kickoff_utc), pad, y + 45);
    g.fillStyle = '#08f0c8'; g.font = font(800, 24); g.textAlign = 'right'; g.fillText(Number(l.odds).toFixed(2), W - pad, y + 10); g.textAlign = 'left';
    y += rowH;
  }
  g.strokeStyle = 'rgba(255,255,255,.15)'; g.setLineDash([6, 6]); g.beginPath(); g.moveTo(pad, y - 10); g.lineTo(W - pad, y - 10); g.stroke(); g.setLineDash([]);
  g.fillStyle = '#93a3b8'; g.font = font(600, 16); g.fillText('COTĂ TOTALĂ', pad, y + 24);
  g.fillStyle = '#08f0c8'; g.font = font(900, 52); g.fillText(Number(t.total_odds).toFixed(2), pad, y + 78);
  if (t.p_ticket != null) { g.textAlign = 'right'; g.fillStyle = '#93a3b8'; g.font = font(600, 16); g.fillText('ȘANSĂ ESTIMATĂ', W - pad, y + 24); g.fillStyle = '#fff'; g.font = font(800, 34); g.fillText(`${Math.round(t.p_ticket * 100)}%`, W - pad, y + 70); g.textAlign = 'left'; }
  g.fillStyle = '#5b6b80'; g.font = font(500, 12); g.fillText('Estimări statistice, nu garanții. 18+ · Pariază responsabil.', pad, H - 18);
  return new Promise((r) => c.toBlob((b) => r(b), 'image/png'));
}

/** Partajează imaginea (WhatsApp etc. prin meniul nativ); altfel o descarcă. */
export async function shareTicket(t: Ticket, title: string, text: string): Promise<'shared' | 'downloaded' | 'failed'> {
  const blob = await ticketImage(t, title);
  if (!blob) return 'failed';
  const file = new File([blob], `bilet-${t.id}.png`, { type: 'image/png' });
  try {
    if (navigator.canShare?.({ files: [file] })) { await navigator.share({ files: [file], text, title }); return 'shared'; }
  } catch (e) { if ((e as Error)?.name === 'AbortError') return 'shared'; }
  const a = document.createElement('a'); a.href = URL.createObjectURL(blob); a.download = file.name; a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 4000);
  return 'downloaded';
}
