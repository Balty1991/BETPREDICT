import { ManualGenerator } from '@/components/ManualGenerator';
import { todayRo } from '@/lib/format';

/** Generatorul stă pe ruta lui, nu la coada paginii de cornere. */
export default function GeneratorPage() {
  return <ManualGenerator date={todayRo()} />;
}
