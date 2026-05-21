/**
 * BetPredict — Modal Scroll Fix v3
 * Corectează v2: nu mai micșorează modalul și nu mai lasă zona neagră jos.
 * Strategia corectă: sheet mare + padding intern jos, ca ultimul card să poată urca peste bara Android/Brave.
 */
(function(){
  'use strict';

  function removeOldFixes(){
    ['bp-modal-fit-css', 'bp-modal-scroll-fix-v2', 'bp-modal-scroll-fix-v3'].forEach(id => {
      const el = document.getElementById(id);
      if(el) el.remove();
    });
  }

  function addCss(){
    removeOldFixes();

    const st = document.createElement('style');
    st.id = 'bp-modal-scroll-fix-v3';
    st.textContent = `
      /* v3: sheet-ul rămâne jos și mare; doar corpul primește spațiu de scroll suplimentar */
      .md-backdrop.show{
        display:flex!important;
        align-items:flex-end!important;
        justify-content:center!important;
        overflow:hidden!important;
        padding:0!important;
      }

      .md-sheet{
        width:min(500px,100%)!important;
        height:min(88dvh,760px)!important;
        max-height:calc(100dvh - env(safe-area-inset-top,0px) - 8px)!important;
        min-height:0!important;
        margin:0!important;
        border-radius:18px 18px 0 0!important;
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

        /* cheia: spațiu real în interior, nu scurtăm modalul */
        padding-bottom:calc(190px + env(safe-area-inset-bottom,0px))!important;
        scroll-padding-bottom:190px!important;
      }

      .md-body::after{
        content:''!important;
        display:block!important;
        height:150px!important;
      }

      .md-panel.active{
        padding-bottom:24px!important;
      }

      .md-panel.active::after{
        content:''!important;
        display:block!important;
        height:110px!important;
      }

      .md-section:last-child{
        margin-bottom:75px!important;
      }

      @media(max-height:760px){
        .md-sheet{
          height:min(91dvh,760px)!important;
          max-height:calc(100dvh - env(safe-area-inset-top,0px) - 4px)!important;
        }
        .md-head{
          padding:9px 12px 7px!important;
        }
        .md-title{
          font-size:clamp(13px,4vw,17px)!important;
          line-height:1.12!important;
        }
        .md-sub{
          font-size:9px!important;
          margin-top:2px!important;
        }
        .md-close{
          width:30px!important;
          height:30px!important;
          font-size:17px!important;
        }
        .md-tabs{
          padding:7px 10px!important;
          gap:5px!important;
        }
        .md-tab{
          padding:5px 8px!important;
          font-size:8.5px!important;
        }
        .md-body{
          padding-top:8px!important;
          padding-bottom:calc(205px + env(safe-area-inset-bottom,0px))!important;
          scroll-padding-bottom:205px!important;
        }
      }

      @media(max-width:420px){
        .md-sheet{
          width:100%!important;
          border-radius:16px 16px 0 0!important;
        }
        .md-body{
          padding-left:8px!important;
          padding-right:8px!important;
        }
      }

      @supports not (height:100dvh){
        .md-sheet{
          height:min(88vh,760px)!important;
          max-height:calc(100vh - env(safe-area-inset-top,0px) - 8px)!important;
        }
      }
    `;
    document.head.appendChild(st);
  }

  function patchScrollReset(){
    if(window.__bpModalScrollFixV3Patched) return;
    window.__bpModalScrollFixV3Patched = true;

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
    patchScrollReset();
  }

  if(document.readyState === 'loading'){
    document.addEventListener('DOMContentLoaded', init, {once:true});
  } else {
    init();
  }
})();
