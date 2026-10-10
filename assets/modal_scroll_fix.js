/**
 * BetPredict — Modal Scroll Fix v5
 * Fix după test video:
 * - modalul acoperă complet tabbar-ul aplicației;
 * - sheet-ul ajunge până jos în viewport, nu se oprește deasupra barei;
 * - scroll-ul se face doar în .md-body;
 * - spațiu intern jos ca ultimul card să urce peste bara Android/Brave.
 */
(function(){
  'use strict';

  function removeOldFixes(){
    [
      'bp-modal-fit-css',
      'bp-modal-scroll-fix-v2',
      'bp-modal-scroll-fix-v3',
      'bp-modal-scroll-fix-v4',
      'bp-modal-scroll-fix-v5'
    ].forEach(id => {
      const el = document.getElementById(id);
      if(el) el.remove();
    });
  }

  function addCss(){
    removeOldFixes();

    const st = document.createElement('style');
    st.id = 'bp-modal-scroll-fix-v5';
    st.textContent = `
      :root{
        --bp-modal-top: 6px;
      }

      .md-backdrop{
        position:fixed!important;
        inset:0!important;
        z-index:9999!important;
        padding:0!important;
        margin:0!important;
        overflow:hidden!important;
        background:rgba(0,0,0,.66)!important;
        backdrop-filter:blur(10px)!important;
      }

      .md-backdrop.show{
        display:block!important;
      }

      .md-sheet{
        position:fixed!important;
        left:0!important;
        right:0!important;
        top:calc(var(--bp-modal-top) + env(safe-area-inset-top,0px))!important;
        bottom:0!important;
        width:min(500px,100%)!important;
        height:auto!important;
        max-height:none!important;
        min-height:0!important;
        margin:0 auto!important;
        transform:none!important;
        animation:none!important;
        display:flex!important;
        flex-direction:column!important;
        overflow:hidden!important;
        border-radius:18px 18px 0 0!important;
        border-bottom:0!important;
      }

      .md-head,
      .md-tabs{
        flex:0 0 auto!important;
      }

      .md-body{
        flex:1 1 auto!important;
        min-height:0!important;
        height:auto!important;
        max-height:none!important;
        overflow-y:auto!important;
        overflow-x:hidden!important;
        -webkit-overflow-scrolling:touch!important;
        overscroll-behavior-y:contain!important;
        touch-action:pan-y!important;
        padding-bottom:calc(260px + env(safe-area-inset-bottom,0px))!important;
        scroll-padding-bottom:260px!important;
      }

      .md-body::after{
        content:''!important;
        display:block!important;
        height:220px!important;
      }

      .md-panel.active{
        display:block!important;
        padding-bottom:40px!important;
      }

      .md-panel.active::after{
        content:''!important;
        display:block!important;
        height:180px!important;
      }

      .md-section:last-child{
        margin-bottom:110px!important;
      }

      body.bp-modal-open{
        overflow:hidden!important;
      }

      /* Ascunde tabbar-ul aplicației cât modalul este deschis, ca să nu mai mănânce spațiul de jos. */
      body.bp-modal-open .tabbar{
        display:none!important;
      }

      @media(max-height:760px){
        :root{
          --bp-modal-top: 2px;
        }
        .md-head{
          padding:8px 12px 6px!important;
        }
        .md-title{
          font-size:clamp(13px,3.9vw,17px)!important;
          line-height:1.1!important;
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
          padding:6px 10px!important;
          gap:5px!important;
        }
        .md-tab{
          padding:5px 8px!important;
          font-size:8.5px!important;
        }
        .md-body{
          padding-top:8px!important;
          padding-bottom:calc(280px + env(safe-area-inset-bottom,0px))!important;
          scroll-padding-bottom:280px!important;
        }
        .md-body::after{
          height:235px!important;
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
          top:calc(var(--bp-modal-top) + env(safe-area-inset-top,0px))!important;
          bottom:0!important;
        }
      }
    `;
    document.head.appendChild(st);
  }

  function setOpenClass(){
    const modal = document.getElementById('match-modal');
    document.body.classList.toggle('bp-modal-open', !!(modal && modal.classList.contains('show')));
  }

  function patchFunctions(){
    if(window.__bpModalScrollFixV5Patched) return;
    window.__bpModalScrollFixV5Patched = true;

    const oldOpen = window.openMatchDetail;
    if(typeof oldOpen === 'function'){
      window.openMatchDetail = async function(){
        const out = await oldOpen.apply(this, arguments);
        requestAnimationFrame(() => {
          setOpenClass();
          const body = document.querySelector('#match-modal .md-body');
          if(body) body.scrollTop = 0;
        });
        return out;
      };
    }

    const oldClose = window.closeMatchDetail;
    if(typeof oldClose === 'function'){
      window.closeMatchDetail = function(){
        const out = oldClose.apply(this, arguments);
        requestAnimationFrame(setOpenClass);
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

    const mo = new MutationObserver(setOpenClass);
    mo.observe(document.body, {subtree:true, attributes:true, attributeFilter:['class']});
  }

  function init(){
    addCss();
    patchFunctions();
    setOpenClass();
  }

  if(document.readyState === 'loading'){
    document.addEventListener('DOMContentLoaded', init, {once:true});
  } else {
    init();
  }
})();
