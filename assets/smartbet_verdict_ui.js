/**
 * BetPredict — SmartBet Verdict UI (Pasul 3.7 + 3.8)
 * Patch non-invaziv: adaugă verdict final explicabil în Analiză completă → Engine.
 * Nu modifică datele, scorurile sau motorul Python.
 */
(function(){
  'use strict';
  const VERSION='pas38';

  function addCss(){
    if(document.getElementById('bp-sbv-ui-css')) return;
    const st=document.createElement('style');
    st.id='bp-sbv-ui-css';
    st.textContent=`
      .sbv-head{display:flex;align-items:center;justify-content:space-between;gap:8px;margin-bottom:8px}
      .sbv-title{font-size:8px;font-weight:800;letter-spacing:.45px;text-transform:uppercase;color:var(--t3)}
      .sbv-pill{display:inline-flex;align-items:center;gap:5px;padding:4px 9px;border-radius:999px;border:1px solid var(--br);font-size:8px;font-weight:800;letter-spacing:.35px;text-transform:uppercase;white-space:nowrap}
      .sbv-pill.bet{background:var(--gd);border-color:rgba(0,232,122,.25);color:var(--green)}
      .sbv-pill.watch{background:var(--od);border-color:rgba(255,184,48,.25);color:var(--gold)}
      .sbv-pill.avoid{background:var(--rd);border-color:rgba(255,61,90,.25);color:var(--red)}
      .sbv-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:6px;margin-bottom:7px}
      .sbv-box{background:rgba(255,255,255,.035);border:1px solid var(--br);border-radius:10px;padding:7px 5px;min-width:0;text-align:center}
      .sbv-l{font-size:7px;color:var(--t3);font-weight:800;text-transform:uppercase;letter-spacing:.3px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
      .sbv-v{font-family:var(--ff-mono);font-size:12px;font-weight:800;color:var(--text);margin-top:2px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
      .sbv-v.g{color:var(--green)}.sbv-v.o{color:var(--gold)}.sbv-v.b{color:var(--blue)}.sbv-v.r{color:var(--red)}.sbv-v.dim{color:var(--t2)}
      .sbv-main{display:flex;align-items:center;gap:8px;border:1px solid var(--br);border-radius:10px;background:rgba(255,255,255,.025);padding:8px;margin-bottom:7px}
      .sbv-icon{display:flex;align-items:center;justify-content:center;width:34px;height:34px;border-radius:10px;border:1px solid var(--br);font-size:17px;flex-shrink:0}
      .sbv-main.bet .sbv-icon{background:var(--gd);border-color:rgba(0,232,122,.24);color:var(--green)}
      .sbv-main.watch .sbv-icon{background:var(--od);border-color:rgba(255,184,48,.24);color:var(--gold)}
      .sbv-main.avoid .sbv-icon{background:var(--rd);border-color:rgba(255,61,90,.24);color:var(--red)}
      .sbv-copy{min-width:0;flex:1}
      .sbv-verdict{font-family:var(--ff-display);font-size:14px;font-weight:800;letter-spacing:.2px;text-transform:uppercase;color:var(--text);line-height:1.15}
      .sbv-sub{font-size:9px;color:var(--t2);line-height:1.35;margin-top:3px}
      .sbv-drivers{display:flex;gap:4px;flex-wrap:wrap;margin-top:7px}
      .sbv-chip{display:inline-flex;align-items:center;gap:4px;border:1px solid var(--br);border-radius:999px;padding:3px 7px;font-size:8px;font-weight:800;letter-spacing:.25px;text-transform:uppercase;background:rgba(255,255,255,.025);color:var(--t2)}
      .sbv-chip.bad{border-color:rgba(255,61,90,.22);background:rgba(255,61,90,.055);color:var(--red)}
      .sbv-chip.warn{border-color:rgba(255,184,48,.22);background:rgba(255,184,48,.055);color:var(--gold)}
      .sbv-chip.good{border-color:rgba(0,232,122,.22);background:rgba(0,232,122,.055);color:var(--green)}
      .sbv-chip.info{border-color:rgba(74,158,255,.22);background:rgba(74,158,255,.055);color:var(--blue)}
      .sbv-note{font-size:9px;color:var(--t2);line-height:1.35;margin-top:7px;padding:7px;border-radius:9px;background:rgba(255,255,255,.03);border:1px solid var(--br)}
      .sbv-note b{color:var(--text)}
      .sbv-card-strip{display:flex;align-items:center;justify-content:space-between;gap:6px;margin:0 12px 8px;padding:6px 7px;border:1px solid var(--br);border-radius:9px;background:rgba(255,255,255,.025)}
      .sbv-card-strip.bet{border-color:rgba(0,232,122,.18);background:rgba(0,232,122,.045)}
      .sbv-card-strip.watch{border-color:rgba(255,184,48,.18);background:rgba(255,184,48,.045)}
      .sbv-card-strip.avoid{border-color:rgba(255,61,90,.18);background:rgba(255,61,90,.045)}
      .sbv-card-pill{display:inline-flex;align-items:center;gap:4px;padding:3px 7px;border-radius:999px;font-size:8px;font-weight:800;letter-spacing:.35px;text-transform:uppercase;white-space:nowrap;border:1px solid var(--br)}
      .sbv-card-pill.bet{background:var(--gd);border-color:rgba(0,232,122,.25);color:var(--green)}
      .sbv-card-pill.watch{background:var(--od);border-color:rgba(255,184,48,.25);color:var(--gold)}
      .sbv-card-pill.avoid{background:var(--rd);border-color:rgba(255,61,90,.25);color:var(--red)}
      .sbv-card-reason{font-size:8px;font-weight:800;letter-spacing:.25px;text-transform:uppercase;color:var(--t2);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;text-align:right}
      .sbv-card-reason.bet{color:var(--green)}.sbv-card-reason.watch{color:var(--gold)}.sbv-card-reason.avoid{color:var(--red)}
      @media(max-width:380px){.sbv-grid{grid-template-columns:repeat(2,minmax(0,1fr));gap:5px}.sbv-verdict{font-size:13px}.sbv-main{padding:7px}.sbv-icon{width:31px;height:31px}.sbv-card-strip{margin:0 10px 8px;padding:5px 6px}.sbv-card-reason{font-size:7px}}
    `;
    document.head.appendChild(st);
  }

  function e(v){
    if(typeof window.esc==='function') return window.esc(v);
    return String(v ?? '—').replace(/[&<>"']/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m]));
  }
  function n(v,def=null){
    if(v===null||v===undefined||v==='') return def;
    const x=Number(v);
    return Number.isFinite(x)?x:def;
  }
  function f1(v){
    const x=n(v,null);
    if(x===null) return '—';
    return Number.isInteger(x)?String(x):x.toFixed(1);
  }
  function pp(v){
    const x=n(v,null);
    if(x===null) return '—';
    return `${x>0?'+':''}${x.toFixed(2)}`;
  }
  function pct(v){
    const x=n(v,null);
    if(x===null) return '—';
    return x<=1?`${Math.round(x*100)}%`:`${Math.round(x)}%`;
  }
  function gradeRank(g){
    const ch=String(g||'').trim().toUpperCase()[0]||'E';
    return {A:5,B:4,C:3,D:2,E:1}[ch]||1;
  }
  function safetyInfo(p){
    const ls=p?.league_strength||{};
    const cal=ls.calibration||{};
    const safe=p?.league_strength_safety||{};
    const scale=n(cal.scale,n(safe.scale,null));
    const reason=cal.reason||safe.reason||'';
    return {scale,reason};
  }
  function safetyLabel(scale,reason){
    if(scale===0) return reason==='competition_unreliable_type'?'Ligă/cupă instabilă':'LS oprit';
    if(scale!==null && scale<1) return 'LS redus';
    return 'LS complet';
  }

  function computeVerdict(p){
    const score=n(p?.smartbet_score,0)||0;
    const edge=n(p?.edge_pp,null);
    const conf=n(p?.confidence,null);
    const bonus=n(p?.league_strength_bonus,0)||0;
    const grade=String(p?.quality_grade||'E').toUpperCase();
    const gr=gradeRank(grade);
    const rec=String(p?.recommended_bet||'').trim();
    const sf=safetyInfo(p);
    let verdict='EVITĂ';
    let cls='avoid';
    let icon='⛔';
    let note='Scor slab sau risc mare. Nu este blocat de UI, dar nu intră în selecție principală.';
    const hardRisk=(score<45)||(edge!==null&&edge<0)||(gr<=2);
    const unstable=(sf.scale===0 && sf.reason==='competition_unreliable_type');

    if(score>=75 && gr>=4 && (edge===null || edge>=0) && !unstable){
      verdict='PARIAZĂ'; cls='bet'; icon='✅';
      note='Candidat principal: scor puternic, grade bun și fără avertizare critică de ligă.';
    }else if(score>=60 && gr>=3 && (edge===null || edge>=-2)){
      verdict='WATCH'; cls='watch'; icon='👁️';
      note=unstable?'Scor bun, dar competiția este instabilă/cupă — păstrează ca WATCH.':'Shortlist: merită urmărit, dar cere confirmare pe cotă/context.';
    }else if(score>=45 && !hardRisk){
      verdict='WATCH'; cls='watch'; icon='👁️';
      note='Semnal mediu. Nu este suficient de puternic pentru pariu principal.';
    }

    const chips=[];
    chips.push({cls:score>=75?'good':score>=60?'info':score>=45?'warn':'bad',txt:`SB ${f1(score)}`});
    if(edge!==null) chips.push({cls:edge>=8?'good':edge>=3?'info':edge>=0?'warn':'bad',txt:`edge ${pp(edge)}`});
    if(conf!==null) chips.push({cls:conf>=.60?'good':conf>=.50?'warn':'bad',txt:`conf ${pct(conf)}`});
    chips.push({cls:gr>=4?'good':gr===3?'warn':'bad',txt:`grade ${grade}`});
    chips.push({cls:bonus>=3?'good':bonus>0?'info':'warn',txt:`LS +${f1(bonus)}`});
    chips.push({cls:sf.scale===0?'warn':sf.scale<1?'warn':'good',txt:safetyLabel(sf.scale,sf.reason)});
    if(!rec || rec==='—') chips.push({cls:'warn',txt:'fără recomandare'});
    return {verdict,cls,icon,note,chips,score,edge,conf,bonus,grade,scale:sf.scale};
  }

  function renderSmartBetVerdictBlock(p){
    if(!p || n(p.smartbet_score,null)===null) return '';
    const v=computeVerdict(p);
    const rec=p.recommended_bet||'—';
    return `<div class="md-section" id="md-smartbet-verdict">
      <div class="sbv-head"><div class="sbv-title">Verdict final explicabil</div><span class="sbv-pill ${v.cls}">${e(v.verdict)}</span></div>
      <div class="sbv-main ${v.cls}"><div class="sbv-icon">${v.icon}</div><div class="sbv-copy"><div class="sbv-verdict">${e(v.verdict)} · ${e(rec)}</div><div class="sbv-sub">${e(v.note)}</div></div></div>
      <div class="sbv-grid">
        <div class="sbv-box"><div class="sbv-l">SmartBet</div><div class="sbv-v ${v.score>=75?'g':v.score>=60?'b':v.score>=45?'o':'r'}">${e(f1(v.score))}</div></div>
        <div class="sbv-box"><div class="sbv-l">Edge</div><div class="sbv-v ${n(v.edge,0)>0?'g':'r'}">${e(pp(v.edge))}</div></div>
        <div class="sbv-box"><div class="sbv-l">Confidence</div><div class="sbv-v ${n(v.conf,0)>=.6?'g':n(v.conf,0)>=.5?'o':'r'}">${e(pct(v.conf))}</div></div>
      </div>
      <div class="sbv-drivers">${v.chips.slice(0,8).map(c=>`<span class="sbv-chip ${c.cls}">${e(c.txt)}</span>`).join('')}</div>
      <div class="sbv-note"><b>Regulă:</b> verdictul nu schimbă predicția; doar traduce scorul în decizie rapidă. Cupe/friendly/LS oprit pot coborî un scor bun la WATCH.</div>
    </div>`;
  }

  function cardReason(p,v){
    const sf=safetyInfo(p);
    const grade=String(p?.quality_grade||'—').toUpperCase();
    const score=f1(v.score);
    if(v.cls==='bet') return `SB ${score} · grade ${grade} · ${safetyLabel(sf.scale,sf.reason)}`;
    if(v.cls==='watch'){
      if(sf.scale===0) return `SB ${score} · ${safetyLabel(sf.scale,sf.reason)} · verifică`;
      if(n(v.edge,0)<0) return `SB ${score} · edge ${pp(v.edge)} · watch`;
      return `SB ${score} · grade ${grade} · watch`;
    }
    if(n(v.edge,null)!==null && n(v.edge,0)<0) return `SB ${score} · edge negativ · grade ${grade}`;
    return `SB ${score} · risc mare · grade ${grade}`;
  }

  function renderCardVerdict(p){
    if(!p || n(p.smartbet_score,null)===null) return '';
    const v=computeVerdict(p);
    return `<div class="sbv-card-strip ${v.cls}"><span class="sbv-card-pill ${v.cls}">${e(v.verdict)}</span><span class="sbv-card-reason ${v.cls}">${e(cardReason(p,v))}</span></div>`;
  }

  function patchPredCard(){
    const prevCard=window.predCard;
    if(typeof prevCard!=='function' || window.__bpSmartBetCardVerdictPas38) return;
    window.__bpSmartBetCardVerdictPas38=true;
    window.predCard=function(p,sigIdx){
      const html=prevCard(p,sigIdx);
      const badge=renderCardVerdict(p);
      if(!badge || typeof html!=='string') return html;
      const marker='<div class="card-teams">';
      if(html.includes(marker)) return html.replace(marker, badge+marker);
      return html.replace('<div class="card">','<div class="card">'+badge);
    };
  }

  function install(){
    addCss();
    if(!window.__bpSmartBetVerdictPas38){
      const prev=window.renderLeagueStrengthBlock;
      if(typeof prev==='function'){
        window.__bpSmartBetVerdictPas38=true;
        window.renderLeagueStrengthBlock=function(p){
          return renderSmartBetVerdictBlock(p)+prev(p);
        };
      }
    }
    patchPredCard();
  }

  if(document.readyState==='loading') document.addEventListener('DOMContentLoaded',install,{once:true});
  else install();
})();
