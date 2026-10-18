import type { ReactNode } from 'react';

/** Antetul de pagină: titlu mare, inelul din siglă ca decor, opțional 2–3 cifre cheie. */
export function PageHero({ eyebrow, title, right, stats }: { eyebrow?: string; title: string; right?: ReactNode; stats?: Array<{ label: string; value: ReactNode; tone?: 'win' | 'loss' | 'primary' }> }) {
  return (
    <section className="page-hero" aria-label={title}>
      <svg className="page-hero-ring" viewBox="0 0 100 100" aria-hidden>
        <defs><linearGradient id="ph-g" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stopColor="#22d3ee" /><stop offset="1" stopColor="#a78bfa" /></linearGradient></defs>
        <circle cx="50" cy="50" r="40" fill="none" stroke="url(#ph-g)" strokeWidth="5" strokeLinecap="round" strokeDasharray="190 400" transform="rotate(-210 50 50)" />
        <circle cx="70" cy="15.4" r="5" fill="#22d3ee" />
      </svg>
      <div className="relative flex items-end justify-between gap-3">
        <div className="min-w-0">
          {eyebrow && <div className="eyebrow">{eyebrow}</div>}
          <h1>{title}</h1>
        </div>
        {right && <div className="shrink-0">{right}</div>}
      </div>
      {stats && stats.length > 0 && (
        <div className="relative mt-3 grid gap-2" style={{ gridTemplateColumns: `repeat(${stats.length}, minmax(0, 1fr))` }}>
          {stats.map((s) => (
            <div key={s.label} className="page-hero-stat">
              <div className={`big-num text-[22px] leading-none ${s.tone === 'win' ? 'text-win' : s.tone === 'loss' ? 'text-loss' : s.tone === 'primary' ? 'neon-text' : ''}`}>{s.value}</div>
              <div className="label mt-1">{s.label}</div>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}
