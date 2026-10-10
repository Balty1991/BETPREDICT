/* shared-utils.js — utilitare comune BetPredict, expuse ca window.BPUtils */
(function(){
  'use strict';
  window.BPUtils={
    esc:s=>String(s??'').replace(/[&<>"']/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m])),
    num:v=>{if(v===null||v===undefined||v==='')return null;const n=Number(v);return Number.isFinite(n)?n:null},
    nf:(v,d=1)=>{const n=window.BPUtils.num(v);return n!==null?n.toFixed(d):'—'},
    pct:v=>{const n=window.BPUtils.num(v);return n!==null?`${n>=0?'+':''}${n.toFixed(1)}%`:'—'},
    prob:v=>{const n=Number(v);return Number.isFinite(n)?`${n.toFixed(1)}%`:'—'},
    fmtTime:iso=>{try{if(!iso)return'—';const d=new Date(iso);if(isNaN(d))return'—';return d.toLocaleDateString('ro-RO',{day:'2-digit',month:'2-digit'})+' · '+d.toLocaleTimeString('ro-RO',{hour:'2-digit',minute:'2-digit'});}catch{return'—'}},
  };
})();
