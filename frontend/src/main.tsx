import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.tsx'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)

// ── Service worker: înregistrare + auto-update agresiv ───────────────────────
// Fără asta, un SW vechi (cache-first) rămânea „blocat" și servea la nesfârșit
// versiunea veche a aplicației, oricâte deploy-uri se făceau. Acum:
//  - verificăm sw.js mereu proaspăt (updateViaCache: 'none')
//  - forțăm update la fiecare încărcare + la interval
//  - când se activează o versiune nouă, reîncărcăm pagina o singură dată
if ('serviceWorker' in navigator) {
  window.addEventListener('load', () => {
    navigator.serviceWorker
      .register(`${import.meta.env.BASE_URL}sw.js`, { updateViaCache: 'none' })
      .then((reg) => {
        reg.update();
        setInterval(() => reg.update().catch(() => {}), 60 * 1000);
        reg.addEventListener('updatefound', () => {
          const sw = reg.installing;
          if (!sw) return;
          sw.addEventListener('statechange', () => {
            if (sw.state === 'installed' && navigator.serviceWorker.controller) {
              sw.postMessage({ type: 'SKIP_WAITING' });
            }
          });
        });
      })
      .catch(() => {});

    let reloaded = false;
    navigator.serviceWorker.addEventListener('controllerchange', () => {
      if (reloaded) return;
      reloaded = true;
      window.location.reload();
    });
  });
}
