import type { SVGProps } from 'react';

/** Set de iconițe BetPredict (stil „HUD”: linie 2px, colțuri teșite, punct de accent). */
type P = SVGProps<SVGSVGElement> & { strokeWidth?: number };
const base = (p: P) => ({ width: 24, height: 24, viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', strokeWidth: p.strokeWidth ?? 2, strokeLinecap: 'round' as const, strokeLinejoin: 'round' as const, 'aria-hidden': true, ...p });

export const IconHome = (p: P) => (<svg {...base(p)}><path d="M3.5 10.5 12 3.5l8.5 7" /><path d="M5.5 9v10.5h13V9" /><path d="M10 19.5v-5h4v5" /><circle cx="12" cy="9.6" r="1" fill="currentColor" stroke="none" /></svg>);
export const IconPredict = (p: P) => (<svg {...base(p)}><path d="M4 18 9 12l3.5 3L20 6" /><path d="M15.5 6H20v4.5" /><path d="M4 21h16" opacity=".45" /><circle cx="9" cy="12" r="1.3" fill="currentColor" stroke="none" /></svg>);
export const IconPyramid = (p: P) => (<svg {...base(p)}><path d="M12 3.5 21 19.5H3z" /><path d="M7.4 12h9.2" opacity=".55" /><path d="M5.2 15.8h13.6" opacity=".55" /><circle cx="12" cy="8.4" r="1.2" fill="currentColor" stroke="none" /></svg>);
export const IconStats = (p: P) => (<svg {...base(p)}><path d="M4 20V4" opacity=".45" /><path d="M4 20h16" opacity=".45" /><rect x="7" y="12" width="3" height="5" rx="1" /><rect x="12" y="8" width="3" height="9" rx="1" /><rect x="17" y="5" width="3" height="12" rx="1" /></svg>);

/** Ilustrație pentru stări goale: radar futurist cu „ținta” găsită. */
export function EmptyIllustration({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 160 120" className={className} aria-hidden>
      <defs>
        <linearGradient id="bp-ill-g" x1="0" x2="1" y1="0" y2="1"><stop offset="0" stopColor="#22d3ee" /><stop offset="1" stopColor="#a78bfa" /></linearGradient>
        <radialGradient id="bp-ill-r"><stop offset="0" stopColor="#22d3ee" stopOpacity=".22" /><stop offset="1" stopColor="#22d3ee" stopOpacity="0" /></radialGradient>
      </defs>
      <circle cx="80" cy="58" r="56" fill="url(#bp-ill-r)" />
      <rect x="44" y="22" width="72" height="72" rx="20" fill="#0b1630" stroke="url(#bp-ill-g)" strokeOpacity=".45" />
      <circle cx="80" cy="58" r="24" fill="none" stroke="hsl(210 40% 60% / .18)" strokeWidth="5" />
      <circle cx="80" cy="58" r="24" fill="none" stroke="url(#bp-ill-g)" strokeWidth="5" strokeLinecap="round" strokeDasharray="105 200" transform="rotate(-90 80 58)" className="ill-sweep" />
      <rect x="70" y="50" width="20" height="16" rx="3" fill="none" stroke="url(#bp-ill-g)" strokeWidth="2" />
      <path d="M74 56h12M74 61h8" stroke="#a78bfa" strokeWidth="2" strokeLinecap="round" />
      <circle cx="124" cy="26" r="3" fill="#22d3ee" /><circle cx="36" cy="92" r="2.5" fill="#a78bfa" /><circle cx="132" cy="84" r="1.8" fill="#a78bfa" />
      <rect x="52" y="106" width="56" height="5" rx="2.5" fill="hsl(var(--muted-foreground) / .15)" />
    </svg>
  );
}
