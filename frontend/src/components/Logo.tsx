/** Sigla BetPredict: „B” neon în inelul de șansă (aceeași ca iconița aplicației). */
export function Logo({ size = 32 }: { size?: number }) {
  return (
    <svg viewBox="0 0 100 100" width={size} height={size} aria-hidden className="shrink-0">
      <defs>
        <linearGradient id="lg-b" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stopColor="#22d3ee" /><stop offset="1" stopColor="#a78bfa" /></linearGradient>
        <radialGradient id="lg-bg" cx="0.3" cy="0.2" r="1"><stop offset="0" stopColor="#14204a" /><stop offset="0.55" stopColor="#0a1024" /><stop offset="1" stopColor="#05070f" /></radialGradient>
      </defs>
      <rect x="2" y="2" width="96" height="96" rx="24" fill="url(#lg-bg)" stroke="#22d3ee" strokeOpacity=".3" strokeWidth="2" />
      <g fill="none" stroke="url(#lg-b)" strokeLinecap="round" strokeLinejoin="round">
        <circle cx="50" cy="50" r="37" strokeWidth="5" strokeDasharray="185 400" transform="rotate(-210 50 50)" />
        <path d="M39 31 V69 M39 31 H52.5 a9.5 9.5 0 0 1 0 19 H39 M39 50 H55 a9.5 9.5 0 0 1 0 19 H39" strokeWidth="8.5" />
      </g>
      <circle cx="68.5" cy="17.96" r="5" fill="#e0f7ff" />
    </svg>
  );
}
