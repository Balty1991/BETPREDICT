/**
 * BetPredict — Modal Scroll Fix v2
 * Fix dedicat pentru Android Chrome/Brave: modalul de analiză completă
 * nu mai intră sub bara de navigație și conținutul poate fi derulat până la capăt.
 */
(function(){
  'use strict';

  function addCss(){
    if(document.getElementById('bp-modal-scroll-fix-v2')) return;

    const st = document.createElement('style');
    st.id = 'bp-modal-scroll-fix-v2';
    st.textContent = `
      :root{
        --bp-modal-bottom-gap: 92px;
        --bp-modal-top-gap: 52px;
      }

      .md-backdrop.show{
        display:flex!important;
        align-items:flex-end!important;
        justify-content:center!important;
        overflow:hidden!important;
        padding-top:var(--bp-modal-top-gap)!important;
        padding-bottom:calc(var(--bp-modal-bottom-gap) + env(safe-area-inset-bottom,0px))!important;
      }

      .md-sheet{
        height:calc(100dvh - var(--bp-modal-top-gap) - var(--bp-modal-bottom-gap) - env(safe-area-inset-bottom,0px))!important;
        max-height:calc(100dvh - var(--bp-modal-top-gap) - var(--bp-modal-bottom-gap) - env(safe-area-inset-bottom,0px))!important;
        min-height:0!important;
        margin-bottom:0!important;
        overflow:hidden!important;
        display:flex!important;
        flex-direction:column!important;
      }

      .md-head,
      .md-tabs{
        flex:0 0 auto!important;
      }

      .md-body{
        flex:1 1 auto!important;
        min-height:0!important;
        overflow-y:auto!important;
        overflow-x:hidden!important;
        -webkit-overflow-scrolling:touch!important;
        overscroll-behavior-y:contain!important;
        touch-action:pan-y!important;
        padding-bottom:calc(210px + env(safe-area-inset-bottom,0px))!important;
        scroll-padding-bottom:210px!important;
      }

      .md-body::after{
        content:''!important;
        display:block!important;
        height:170px!important;
      }

      .md-panel.active{
        padding-bottom:28px!important;
      }

      .md-panel.active::after{
        content:''!important;
        display:block!important;
        height:120px!important;
      }

      .md-section:last-child{
        margin-bottom:80px!important;
      }

      /* Pe ecrane joase, compactăm headerul și taburile ca să rămână mai mult spațiu util. */
      @media(max-height:760px){
        :root{
          --bp-modal-bottom-gap: 96px;
          --bp-modal-top-gap: 38px;
        }
        .md-head{padding:9px 12px 7px!important}
        .md-title{font-size:clamp(13px,4vw,17px)!important;line-height:1.12!important}
        .md-sub{font-size:9px!important;margin-top:2px!important}
        .md-close{width:30px!important;height:30px!important;font-size:17px!important}
        .md-tabs{padding:7px 10px!important;gap:5px!important}
        .md-tab{padding:5px 8px!important;font-size:8.5px!important}
        .md-body{padding-top:8px!important}
      }

      @media(max-width:420px){
        :root{
          --bp-modal-bottom-gap: 98px;
        }
        .md-body{
          padding-left:8px!important;
          padding-right:8px!important;
        }
        .md-sheet{
          width:100%!important;
          border-radius:16px 16px 0 0!important;
        }
      }

      /* Fallback pentru browsere care nu tratează corect dvh. */
      @supports not (height:100dvh){
        .md-sheet{
          height:calc(100vh - var(--bp-modal-top-gap) - var(--bp-modal-bottom-gap) - env(safe-area-inset-bottom,0px))!important;
          max-height:calc(100vh - var(--bp-modal-top-gap) - var(--bp-modal-bottom-gap) - env(safe-area-inset-bottom,0px))!important;
        }
      }
    `;
    document.head.appendChild(st);
  }

  function patchOpenClose(){
    if(window.__bpModalScrollFixV2Patched) return;
    window.__bpModalScrollFixV2Patched = true;

    const oldOpen = window.openMatchDetail;
    if(typeof oldOpen === 'function'){
      window.openMatchDetail = async function(){
        const out = await oldOpen.apply(this, arguments);
        requestAnimationFrame(() => {
          const body = document.querySelector('#match-modal .md-body');
          if(body) body.scrollTop = 0;
        });
        return out;
      };
    }

    const oldSwitch = window.switchMatchTab;
    if(typeof oldSwitch === 'function'){
      window.switchMatchTab = function(){
        const out = oldSwitch.apply(this, arguments);
        requestAnimationFrame(() => {
          const body = document.querySelector('#match-modal .md-body');
          if(body) body.scrollTop = 0;
        });
        return out;
      };
    }
  }

  function init(){
    addCss();
    patchOpenClose();
  }

  if(document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init, {once:true});
  else init();
})();
