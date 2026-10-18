import type { ReactNode } from 'react';

/** Antetul de pagină: titlu mare, inelul din siglă ca decor, opțional 2–3 cifre cheie. */
export function PageHero({ eyebrow, title, right, stats }: { eyebrow?: string; title: string; right?: ReactNode; stats?: Array<{ label: string; value: ReactNode; tone?: 'win' | 'loss' | 'primary' }> }) {
  return (
    <section className="page-hero" aria-label={title}>
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
