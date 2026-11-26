import { Suspense, lazy, useState } from 'react';
import { Loading } from '@/components/kit';
import { PyrSelector, type PyrId } from '@/components/PyrSelector';

const Pyramid140View = lazy(() => import('@/components/Pyramid140View'));
const ManualPyramid = lazy(() => import('@/components/ManualPyramid'));

/** Piramida cotă 2 (seria principală) sus; celelalte piste vechi stau într-un pliu „Alte piramide”. */
export default function PyramidPage() {
  const [other, setOther] = useState<PyrId | null>(null);
  return (
    <div className="product-pyr space-y-5">
      <Suspense fallback={<Loading />}>
        <Pyramid140View track="1.20" />
      </Suspense>
      <Suspense fallback={<Loading />}>
        <Pyramid140View track="sa" />
      </Suspense>
      <details className="card group px-4 py-3" onToggle={(e) => { if ((e.currentTarget as HTMLDetailsElement).open && !other) setOther('2.00'); }}>
        <summary className="flex cursor-pointer list-none items-center justify-between gap-2">
          <span className="min-w-0"><span className="block text-sm font-semibold">Alte piramide</span><span className="block text-[11px] text-muted-foreground">Value 2.00 și piramida ta manuală. Piste vechi, separate de cotă 2.</span></span>
          <span className="shrink-0 text-xs font-semibold text-primary group-open:hidden">Arată</span><span className="hidden shrink-0 text-xs font-semibold text-primary group-open:inline">Ascunde</span>
        </summary>
        {other && (
          <div className="mt-3 space-y-4 border-t pt-3">
            <PyrSelector value={other} onChange={setOther} exclude={['1.20']} />
            <Suspense fallback={<Loading />}>
              {other === 'manual' ? <ManualPyramid /> : <Pyramid140View key={other} track={other} />}
            </Suspense>
          </div>
        )}
      </details>
    </div>
  );
}
