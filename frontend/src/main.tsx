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

    // Versiune nouă activă: în primele secunde după deschidere reîncărcăm imediat (utilizatorul
    // n-a apucat să facă nimic); mai târziu arătăm un banner „Versiune nouă · Reîncarcă”, ca să
    // nu reîncărcăm pagina sub degetul lui (un reload în mijlocul unei atingeri pare „buton mort”).
    let reloaded = false;
    const loadedAt = performance.now();
    navigator.serviceWorker.addEventListener('controllerchange', () => {
      if (reloaded) return;
      if (performance.now() - loadedAt < 10000 || document.visibilityState === 'hidden') {
        reloaded = true;
        window.location.reload();
        return;
      }
      showUpdateBanner(() => { reloaded = true; window.location.reload(); });
    });
    document.addEventListener('visibilitychange', () => {
      if (document.visibilityState === 'hidden' && document.getElementById('bp-update-banner') && !reloaded) {
        reloaded = true; window.location.reload();
      }
    });
  });
}

function showUpdateBanner(onReload: () => void) {
  if (document.getElementById('bp-update-banner')) return;
  const bar = document.createElement('div');
  bar.id = 'bp-update-banner';
  bar.setAttribute('role', 'status');
  bar.style.cssText = 'position:fixed;left:50%;top:calc(8px + var(--safe-top, 0px));transform:translateX(-50%);z-index:100;display:flex;gap:10px;align-items:center;padding:8px 8px 8px 14px;border-radius:999px;background:hsl(var(--card));color:hsl(var(--foreground));border:1px solid hsl(var(--glass-border));box-shadow:0 10px 30px -10px rgb(0 0 0/.5);font:600 13px system-ui,sans-serif;max-width:calc(100vw - 24px)';
  const txt = document.createElement('span');
  txt.textContent = 'Versiune nouă disponibilă';
  const btn = document.createElement('button');
  btn.type = 'button';
  btn.textContent = 'Reîncarcă';
  btn.style.cssText = 'border:0;border-radius:999px;padding:8px 14px;background:hsl(var(--primary));color:hsl(var(--primary-foreground));font:700 13px system-ui,sans-serif;min-height:36px';
  btn.addEventListener('click', onReload);
  bar.append(txt, btn);
  document.body.appendChild(bar);
}
