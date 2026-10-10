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
    <svg viewBox="0 0 160 110" className={className} aria-hidden>
      <defs>
        <linearGradient id="bp-ill-g" x1="0" x2="1" y1="0" y2="1"><stop offset="0" stopColor="hsl(var(--primary))" /><stop offset="1" stopColor="hsl(var(--primary-2, var(--primary)))" /></linearGradient>
        <radialGradient id="bp-ill-r"><stop offset="0" stopColor="hsl(var(--primary) / .25)" /><stop offset="1" stopColor="hsl(var(--primary) / 0)" /></radialGradient>
      </defs>
      <circle cx="80" cy="56" r="50" fill="url(#bp-ill-r)" />
      {[44, 31, 18].map((r) => <circle key={r} cx="80" cy="56" r={r} fill="none" stroke="hsl(var(--primary) / .35)" strokeDasharray="3 5" />)}
      <path d="M80 56 L118 34" stroke="url(#bp-ill-g)" strokeWidth="2.5" strokeLinecap="round" className="ill-sweep" />
      <circle cx="104" cy="44" r="4.5" fill="url(#bp-ill-g)" />
      <circle cx="104" cy="44" r="9" fill="none" stroke="hsl(var(--primary) / .5)" />
      <rect x="40" y="94" width="80" height="6" rx="3" fill="hsl(var(--muted-foreground) / .15)" />
    </svg>
  );
}
