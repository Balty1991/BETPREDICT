/** Sigla: inelul verde e masa de cornere, punctul auriu e jumătatea de bancă. */
export function Logo({ size = 32 }: { size?: number }) {
  return (
    <svg viewBox="0 0 100 100" width={size} height={size} aria-hidden className="shrink-0">
      <defs>
        <linearGradient id="lg-b" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stopColor="#c6f54a" /><stop offset="1" stopColor="#f0b429" /></linearGradient>
        <radialGradient id="lg-bg" cx="0.3" cy="0.2" r="1"><stop offset="0" stopColor="#1a2414" /><stop offset="0.6" stopColor="#10160e" /><stop offset="1" stopColor="#070a06" /></radialGradient>
      </defs>
      <rect x="2" y="2" width="96" height="96" rx="24" fill="url(#lg-bg)" stroke="#c6f54a" strokeOpacity=".35" strokeWidth="2" />
      <g fill="none" stroke="url(#lg-b)" strokeLinecap="round" strokeLinejoin="round">
        <circle cx="50" cy="50" r="37" strokeWidth="5" strokeDasharray="116 400" transform="rotate(-200 50 50)" />
        <circle cx="50" cy="50" r="37" stroke="#f0b429" strokeWidth="5" strokeDasharray="116 400" transform="rotate(20 50 50)" />
        <path d="M39 31 V69 M39 31 H52.5 a9.5 9.5 0 0 1 0 19 H39 M39 50 H55 a9.5 9.5 0 0 1 0 19 H39" strokeWidth="8.5" />
      </g>
      <circle cx="74" cy="22" r="5" fill="#f0b429" />
    </svg>
  );
}