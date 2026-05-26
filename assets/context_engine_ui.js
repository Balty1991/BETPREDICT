/**
 * BetPredict — Context Engine UI v4 Premium
 * Design îmbunătățit: progress bars, score track, factor cards cu gradient confidence.
 */
(function () {
  'use strict';

  const FACTOR_LABELS = {
    form: 'Formă', h2h: 'H2H', xgd: 'Standings/xGd',
    referee: 'Arbitru', manager: 'Manageri',
    weather: 'Vreme', odds_movement: 'Odds Movement'
  };
  const FACTOR_ICONS = {
    form: '📈', h2h: '⚔️', xgd: '📊', referee: '🟨',
    manager: '🎯', weather: '🌤', odds_movement: '💹'
  };
  const MARKET_LABELS = {
    homeWin: '1', draw: 'X', awayWin: '2',
    over25: 'O2.5', over15: 'O1.5', btts: 'BTTS',
    under25: 'U2.5', under35: 'U3.5'
  };
  const MARKET_COLORS = {
    homeWin: '#4a9eff', draw: '#ffb830', awayWin: '#b06aff',
    over25: '#00e87a', over15: '#00c96a', btts: '#ff7c3a',
    under25: '#ff3d5a', under35: '#e05555'
  };

  function addCss() {
    if (document.getElementById('bp-ctx4-css')) return;
    const st = document.createElement('style');
    st.id = 'bp-ctx4-css';
    st.textContent = `
#md-context-engine.ctx4{padding:14px 12px 12px!important;margin-top:10px!important;background:rgba(255,255,255,.018);border:1px solid rgba(255,255,255,.07);border-radius:16px;}
.ctx4-head{display:flex;align-items:center;justify-content:space-between;margin-bottom:12px;gap:8px;}
.ctx4-title{font-size:8px;font-weight:800;letter-spacing:.55px;text-transform:uppercase;color:var(--t3);}
.ctx4-pill{display:inline-flex;align-items:center;gap:4px;padding:3px 9px;border-radius:999px;font-size:8px;font-weight:800;letter-spacing:.4px;text-transform:uppercase;}
.ctx4-pill.on{background:rgba(0,232,122,.1);border:1px solid rgba(0,232,122,.3);color:#00e87a;}
.ctx4-pill.mid{background:rgba(255,184,48,.1);border:1px solid rgba(255,184,48,.3);color:#ffb830;}
.ctx4-pill.off{background:rgba(255,255,255,.05);border:1px solid rgba(255,255,255,.1);color:var(--t2);}
.ctx4-pill.on::before{content:'●';font-size:5px;}
.ctx4-pill.mid::before{content:'●';font-size:5px;}
.ctx4-pill.off::before{content:'○';font-size:5px;}
.ctx4-track{display:grid;grid-template-columns:1fr auto 1fr auto;align-items:center;gap:6px;background:rgba(255,255,255,.025);border:1px solid rgba(255,255,255,.07);border-radius:12px;padding:10px 12px;margin-bottom:10px;}
.ctx4-score-block{text-align:center;}
.ctx4-score-label{font-size:7px;font-weight:800;letter-spacing:.4px;text-transform:uppercase;color:var(--t3);margin-bottom:3px;}
.ctx4-score-value{font-family:var(--ff-mono);font-size:22px;font-weight:800;line-height:1;}
.ctx4-score-value.dim{color:var(--t2);}
.ctx4-score-value.blue{color:#4a9eff;}
.ctx4-score-value.green{color:#00e87a;}
.ctx4-score-value.gold{color:#ffb830;}
.ctx4-score-value.red{color:#ff3d5a;}
.ctx4-arrow{font-size:16px;color:var(--t3);line-height:1;}
.ctx4-boost-badge{display:flex;flex-direction:column;align-items:center;background:rgba(0,232,122,.08);border:1px solid rgba(0,232,122,.2);border-radius:10px;padding:6px 10px;min-width:54px;text-align:center;}
.ctx4-boost-label{font-size:7px;font-weight:800;letter-spacing:.4px;text-transform:uppercase;color:var(--t3);margin-bottom:2px;}
.ctx4-boost-value{font-family:var(--ff-mono);font-size:14px;font-weight:800;color:#00e87a;line-height:1;}
.ctx4-boost-value.neg{color:#ff3d5a;}
.ctx4-conf-row{display:flex;align-items:center;gap:8px;margin-bottom:10px;}
.ctx4-conf-label{font-size:7px;font-weight:800;letter-spacing:.4px;text-transform:uppercase;color:var(--t3);white-space:nowrap;}
.ctx4-conf-track{flex:1;height:4px;border-radius:999px;background:rgba(255,255,255,.07);overflow:hidden;}
.ctx4-conf-fill{height:100%;border-radius:999px;}
.ctx4-conf-pct{font-family:var(--ff-mono);font-size:9px;font-weight:800;white-space:nowrap;}
.ctx4-section-label{font-size:7px;font-weight:800;letter-spacing:.45px;text-transform:uppercase;color:var(--t3);margin-bottom:5px;margin-top:8px;}
.ctx4-verdicts{display:flex;flex-wrap:wrap;gap:5px;margin-bottom:8px;}
.ctx4-verdict{display:inline-flex;align-items:center;gap:4px;padding:5px 10px;border-radius:8px;font-size:9px;font-weight:800;letter-spacing:.3px;text-transform:uppercase;}
.ctx4-verdict.pariaza{background:rgba(0,232,122,.12);border:1px solid rgba(0,232,122,.35);color:#00e87a;}
.ctx4-verdict.risc{background:rgba(255,184,48,.10);border:1px solid rgba(255,184,48,.3);color:#ffb830;}
.ctx4-verdict.evita{background:rgba(255,61,90,.08);border:1px solid rgba(255,61,90,.2);color:#ff3d5a;}
.ctx4-prob-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:5px;margin-bottom:8px;}
.ctx4-prob-card{border-radius:10px;padding:7px 4px;text-align:center;position:relative;overflow:hidden;}
.ctx4-prob-market{font-size:7px;font-weight:800;letter-spacing:.35px;text-transform:uppercase;color:rgba(255,255,255,.5);margin-bottom:2px;}
.ctx4-prob-val{font-family:var(--ff-mono);font-size:13px;font-weight:800;color:#fff;line-height:1;}
.ctx4-prob-bar{position:absolute;bottom:0;left:0;height:3px;border-radius:0 0 10px 10px;}
.ctx4-factors{display:grid;grid-template-columns:repeat(2,1fr);gap:6px;}
.ctx4-factor{border-radius:11px;background:rgba(255,255,255,.025);border:1px solid rgba(255,255,255,.07);padding:8px;overflow:hidden;position:relative;}
.ctx4-factor::before{content:'';position:absolute;top:0;left:0;right:0;height:2px;border-radius:11px 11px 0 0;}
.ctx4-factor.conf-high::before{background:linear-gradient(90deg,#00e87a,#00c96a);}
.ctx4-factor.conf-mid::before{background:linear-gradient(90deg,#ffb830,#ff9020);}
.ctx4-factor.conf-zero::before{background:rgba(255,255,255,.07);}
.ctx4-factor-top{display:flex;align-items:flex-start;justify-content:space-between;gap:4px;margin-bottom:5px;}
.ctx4-factor-name{font-size:8px;font-weight:800;letter-spacing:.3px;text-transform:uppercase;color:var(--t2);display:flex;align-items:center;gap:3px;line-height:1.2;}
.ctx4-factor-icon{font-size:9px;line-height:1;}
.ctx4-factor-conf-pct{font-family:var(--ff-mono);font-size:10px;font-weight:800;white-space:nowrap;}
.ctx4-factor-conf-pct.high{color:#00e87a;}
.ctx4-factor-conf-pct.mid{color:#ffb830;}
.ctx4-factor-conf-pct.zero{color:rgba(255,255,255,.2);}
.ctx4-factor-bar-track{height:3px;border-radius:999px;background:rgba(255,255,255,.06);overflow:hidden;margin-bottom:4px;}
.ctx4-factor-bar-fill{height:100%;border-radius:999px;}
.ctx4-factor-bar-fill.high{background:linear-gradient(90deg,#00c96a80,#00e87a);}
.ctx4-factor-bar-fill.mid{background:linear-gradient(90deg,#ff902080,#ffb830);}
.ctx4-factor-bar-fill.zero{background:rgba(255,255,255,.08);}
.ctx4-factor-mult{font-size:7.5px;color:var(--t3);font-weight:800;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}
.ctx4-details{border:1px solid rgba(255,255,255,.07);border-radius:12px;background:rgba(255,255,255,.018);overflow:hidden;margin-top:2px;}
.ctx4-details summary{list-style:none;cursor:pointer;padding:8px 11px;font-size:8px;font-weight:800;letter-spacing:.4px;text-transform:uppercase;color:#4a9eff;display:flex;align-items:center;justify-content:space-between;user-select:none;}
.ctx4-details summary::-webkit-details-marker{display:none;}
.ctx4-details summary::after{content:'+';font-family:var(--ff-mono);font-size:13px;color:rgba(255,255,255,.25);}
.ctx4-details[open] summary::after{content:'−';}
.ctx4-details-body{padding:2px 10px 11px;}
.ctx4-note{font-size:8px;color:var(--t3);line-height:1.45;margin-top:9px;padding:7px 9px;border-radius:9px;background:rgba(255,255,255,.025);border:1px solid rgba(255,255,255,.06);}
.ctx4-note strong{color:var(--t2);}
@media(max-width:390px){
  .ctx4-prob-val{font-size:12px;}
  .ctx4-score-value{font-size:19px;}
}
    `;
    document.head.appendChild(st);
  }

  function esc(v) {
    if (typeof window.esc === 'function') return window.esc(v);
    return String(v ?? '—').replace(/[&<>"']/g, m => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m]));
  }
  function n(v, def) {
    if (def === undefined) def = null;
    if (v === null || v === undefined || v === '') return def;
    const x = Number(v);
    return Number.isFinite(x) ? x : def;
  }
  function f1(v) { const x = n(v); return x === null ? '—' : (Number.isInteger(x) ? String(x) : x.toFixed(1)); }
  function pp(v) { const x = n(v); return x === null ? '—' : `${x > 0 ? '+' : ''}${x.toFixed(2)}`; }
  function prob(v) { const x = n(v); return x === null ? '—' : `${Math.round(x * 100)}%`; }

  function scoreColorClass(s) {
    s = n(s, 0);
    if (s >= 75) return 'green';
    if (s >= 60) return 'blue';
    if (s >= 45) return 'gold';
    return 'red';
  }
  function confTier(cc) {
    cc = n(cc, 0);
    if (cc >= 0.55) return 'high';
    if (cc > 0) return 'mid';
    return 'zero';
  }
  function pillClass(cc) { return confTier(n(cc,0)) === 'high' ? 'on' : confTier(n(cc,0)) === 'mid' ? 'mid' : 'off'; }
  function pillLabel(cc) {
    const t = confTier(n(cc,0));
    return t === 'high' ? 'Context Puternic' : t === 'mid' ? 'Context Parțial' : 'Fără Context';
  }
  function confBarColor(tier) {
    if (tier === 'high') return 'linear-gradient(90deg,#00c96a,#00e87a)';
    if (tier === 'mid')  return 'linear-gradient(90deg,#ff9020,#ffb830)';
    return 'rgba(255,255,255,.12)';
  }
  function verdictCls(v) {
    v = String(v||'').toUpperCase();
    return v === 'PARIAZA' ? 'pariaza' : v === 'RISC' ? 'risc' : 'evita';
  }
  function verdictIcon(v) {
    v = String(v||'').toUpperCase();
    return v === 'PARIAZA' ? '✓' : v === 'RISC' ? '⚡' : '✗';
  }
  function factorLine(f) {
    const p = [];
    if (n(f?.m_H) !== null) p.push(`1×${(+f.m_H).toFixed(2)}`);
    if (n(f?.m_A) !== null) p.push(`2×${(+f.m_A).toFixed(2)}`);
    return p.length ? p.join(' · ') : 'fără 1X2 direct';
  }
  function hexToRgb(hex) {
    return [parseInt(hex.slice(1,3),16), parseInt(hex.slice(3,5),16), parseInt(hex.slice(5,7),16)].join(',');
  }
  function hasContext(p) {
    return !!(p && (p._context_engine || p.context_confidence !== undefined || p.ctx_verdicts || p.ctx_factors));
  }

  function renderVerdicts(verdicts) {
    if (!verdicts || typeof verdicts !== 'object')
      return '<span class="ctx4-verdict evita">Fără verdicte</span>';
    const par = Object.entries(verdicts).filter(([,v]) => String(v).toUpperCase() === 'PARIAZA');
    const ris = Object.entries(verdicts).filter(([,v]) => String(v).toUpperCase() === 'RISC');
    const chosen = par.length ? par : ris.slice(0, 4);
    if (!chosen.length) return '<span class="ctx4-verdict evita">Toate piețele — Evită</span>';
    return chosen.slice(0, 6).map(([k, v]) =>
      `<span class="ctx4-verdict ${verdictCls(v)}">${verdictIcon(v)} ${esc(MARKET_LABELS[k]||k)} · ${esc(v)}</span>`
    ).join('');
  }

  function renderProbGrid(p) {
    const items = [
      ['homeWin', p.ctx_home_win], ['draw', p.ctx_draw], ['awayWin', p.ctx_away_win],
      ['over15', p.ctx_over15], ['over25', p.ctx_over25], ['btts', p.ctx_btts],
      ['under25', p.ctx_under25], ['under35', p.ctx_under35]
    ].filter(([,v]) => n(v) !== null);
    if (!items.length) return '<div style="color:var(--t3);font-size:8px;padding:4px 0">Probabilități lipsă</div>';
    return `<div class="ctx4-prob-grid">${items.map(([k, v]) => {
      const val = Math.max(0, Math.min(1, n(v, 0)));
      const pv  = Math.round(val * 100);
      const col = MARKET_COLORS[k] || '#4a9eff';
      const rgb = hexToRgb(col);
      const alpha = (0.08 + val * 0.12).toFixed(2);
      return `<div class="ctx4-prob-card" style="background:rgba(${rgb},${alpha});border:1px solid rgba(${rgb},.2)">
        <div class="ctx4-prob-market">${esc(MARKET_LABELS[k]||k)}</div>
        <div class="ctx4-prob-val">${pv}%</div>
        <div class="ctx4-prob-bar" style="width:${Math.min(100,pv)}%;background:${col}"></div>
      </div>`;
    }).join('')}</div>`;
  }

  function renderFactors(factors) {
    if (!factors || typeof factors !== 'object')
      return '<div class="ctx4-note">Nu există breakdown pe factori.</div>';
    const rows = Object.entries(factors).filter(([,v]) => v && typeof v === 'object');
    if (!rows.length) return '<div class="ctx4-note">Nu există breakdown pe factori.</div>';
    return `<div class="ctx4-factors">${rows.map(([k, v]) => {
      const cc   = n(v.conf, 0);
      const tier = confTier(cc);
      const pv   = Math.round(cc * 100);
      return `<div class="ctx4-factor conf-${tier}">
        <div class="ctx4-factor-top">
          <div class="ctx4-factor-name">
            <span class="ctx4-factor-icon">${FACTOR_ICONS[k]||'•'}</span>
            ${esc(FACTOR_LABELS[k]||k)}
          </div>
          <span class="ctx4-factor-conf-pct ${tier}">${pv}%</span>
        </div>
        <div class="ctx4-factor-bar-track">
          <div class="ctx4-factor-bar-fill ${tier}" style="width:${pv}%"></div>
        </div>
        <div class="ctx4-factor-mult">${esc(factorLine(v))}</div>
      </div>`;
    }).join('')}</div>`;
  }

  function renderContextEngineBlock(p) {
    if (!hasContext(p)) return '';
    const cc      = n(p.context_confidence, 0);
    const base    = n(p.smartbet_score_base);
    const score   = n(p.smartbet_score);
    const boost   = n(p.smartbet_context_boost);
    const tier    = confTier(cc);
    const confPct = Math.round(cc * 100);
    const boostNeg = (boost || 0) < 0;

    return `<div class="md-section ctx4" id="md-context-engine">

      <div class="ctx4-head">
        <div class="ctx4-title">Context Engine Matematic</div>
        <span class="ctx4-pill ${pillClass(cc)}">${esc(pillLabel(cc))}</span>
      </div>

      <div class="ctx4-track">
        <div class="ctx4-score-block">
          <div class="ctx4-score-label">Base</div>
          <div class="ctx4-score-value dim">${esc(f1(base))}</div>
        </div>
        <div class="ctx4-arrow">→</div>
        <div class="ctx4-score-block">
          <div class="ctx4-score-label">Nou</div>
          <div class="ctx4-score-value ${scoreColorClass(score)}">${esc(f1(score))}</div>
        </div>
        <div class="ctx4-boost-badge" style="${boostNeg ? 'background:rgba(255,61,90,.08);border-color:rgba(255,61,90,.2)' : ''}">
          <div class="ctx4-boost-label">Boost</div>
          <div class="ctx4-boost-value${boostNeg ? ' neg' : ''}">${esc(pp(boost))}</div>
        </div>
      </div>

      <div class="ctx4-conf-row">
        <span class="ctx4-conf-label">Confidență</span>
        <div class="ctx4-conf-track">
          <div class="ctx4-conf-fill" style="width:${confPct}%;background:${confBarColor(tier)}"></div>
        </div>
        <span class="ctx4-conf-pct" style="color:${tier==='high'?'#00e87a':tier==='mid'?'#ffb830':'var(--t3)'}">${confPct}%</span>
      </div>

      <details class="ctx4-details">
        <summary>Detalii Context + Factori</summary>
        <div class="ctx4-details-body">
          <div class="ctx4-section-label">Verdicte Context</div>
          <div class="ctx4-verdicts">${renderVerdicts(p.ctx_verdicts)}</div>
          <div class="ctx4-section-label">Probabilități Ajustate</div>
          ${renderProbGrid(p)}
          <div class="ctx4-section-label">Factori Utilizați</div>
          ${renderFactors(p.ctx_factors)}
          <div class="ctx4-note">
            <strong>Regulă sigură:</strong> La confidență 0%, scorul rămâne pe formula de bază — contextul adaugă boost controlat, fără să ascundă meciuri.
          </div>
        </div>
      </details>

    </div>`;
  }

  function install() {
    addCss();
    window.renderContextEngineBlock = renderContextEngineBlock;
    window.__bpContextEngineUiV4 = true;
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', install, { once: true });
  else install();
})();
