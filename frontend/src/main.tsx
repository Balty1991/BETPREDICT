import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './fonts.css'
import './index.css'
import App from './App.tsx'
import { startCloudSync } from './lib/cloudSync'

// tema se aplică înainte de primul render (fără „flash” alb)
try {
  const st = JSON.parse(localStorage.getItem('betpredict.v3') || '{}');
  document.documentElement.classList.toggle('dark', (st.settings?.theme ?? 'dark') === 'dark');
} catch { document.documentElement.classList.add('dark'); }

// sincronizarea biletelor prin Gist (doar dacă utilizatorul a pus un token pe acest dispozitiv)
startCloudSync()

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
    // curățenie: dezactivează orice service worker vechi (v2) care nu e sw.js-ul curent
    navigator.serviceWorker.getRegistrations().then((regs) => regs.forEach((r) => {
      const url = r.active?.scriptURL ?? r.waiting?.scriptURL ?? r.installing?.scriptURL ?? '';
      if (url && !url.endsWith(`${import.meta.env.BASE_URL}sw.js`.replace(/^\.\//, '/')) && !url.endsWith('/sw.js')) r.unregister();
    })).catch(() => {});
    setTimeout(() => sessionStorage.removeItem('bp-chunk-reload'), 10000);
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
