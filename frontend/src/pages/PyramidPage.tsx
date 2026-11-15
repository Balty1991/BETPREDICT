import { Suspense, lazy } from 'react';
import { Loading } from '@/components/kit';

const Pyramid140View = lazy(() => import('@/components/Pyramid140View'));

export default function PyramidPage() {
  return (
    <div className="product-pyr space-y-4">
      <Suspense fallback={<Loading />}>
        <Pyramid140View track="1.20" />
      </Suspense>
    </div>
  );
}
