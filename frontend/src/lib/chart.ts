/** Stil comun pentru tooltip-urile graficelor; pe ecrane tactile o atingere „fixează” detaliile punctului. */
const touch = typeof window !== 'undefined' && !!window.matchMedia?.('(hover: none)').matches;
export const tip = {
  contentStyle: { background: 'hsl(var(--popover))', border: '1px solid hsl(var(--primary) / .35)', fontSize: 12, borderRadius: 12, boxShadow: '0 10px 28px rgb(0 0 0 / .35)' },
  cursor: { stroke: 'hsl(var(--primary))', strokeWidth: 1, strokeDasharray: '3 3', fill: 'hsl(var(--accent))', opacity: 0.5 },
  wrapperStyle: { zIndex: 5, outline: 'none' },
  trigger: (touch ? 'click' : 'hover') as 'click' | 'hover',
  isAnimationActive: false,
};
export const activeDot = { r: 6, strokeWidth: 2, stroke: 'hsl(var(--card))' };
