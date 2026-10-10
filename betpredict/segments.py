"""Focus agresiv pe segmente ligă × piață (învățare săptămânală).

Indicatorul principal e CLV-ul (se stabilizează în zeci de selecții), ROI-ul e confirmarea (sute).
Ambele sunt micșorate bayesian spre un prior neutru, ca zgomotul unei săptămâni să nu mute nimic:

* CLV posterior = Σ clv / (n + 50)            (prior: 50 de selecții cu CLV 0)
* ROI posterior = (Σ profit − 0,04·150) / (n + 150)   (prior: 150 de selecții la marja pieței, −4%)

Reguli (cu histerezis, ca segmentele să nu „pâlpâie” de la o săptămână la alta):
* OPRIT  dacă (n_clv ≥ 30, CLV post ≤ −1% și P(CLV < 0) ≥ 90%) sau (n ≥ 150, ROI post ≤ −8% și CLV post ≤ 0);
* ÎNTĂRIT dacă n_clv ≥ 30, CLV post ≥ +1%, P(CLV > 0) ≥ 90% și ROI post ≥ −3%;
* un segment oprit revine doar când CLV post ≥ 0 și ROI post > −5%; unul întărit rămâne până CLV post < +0,3%.

Efect: oprit → selecțiile segmentului nu mai sunt „sănătoase” (fără recomandări/bilete/piramidă);
întărit → pragul de EV al segmentului scade cu 1 pp și primește prioritate în bilete.
"""

from __future__ import annotations

import math
import sqlite3
from collections import defaultdict
from typing import Any, Dict, List, Optional, Tuple

PRIOR_CLV_N = 50
PRIOR_ROI_N = 150
PRIOR_ROI = -0.04
MIN_CLV_N = 30
MIN_ROI_N = 150  # v4: CLV-first — ROI singur decide doar pe eșantioane mari
BOOST_EV = 0.01


def seg_key(league_id: Any, mkey: str) -> str:
    return f"{league_id}|{mkey}"


def group_key(league_id: Any, mkey: str) -> str:
    """v4: segment pe grup de ligi (top/second/other) × piață — CLV-ul converge mai repede decât pe ligă."""
    from betpredict.model.calib import league_group
    return f"g:{league_group(league_id)}|{mkey}"


def _norm_cdf(x: float) -> float:
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def segment_stats(conn: sqlite3.Connection, since: str) -> Dict[str, Dict[str, Any]]:
    """Selecțiile „acționabile” ale Robotului (pick, A/B sau EV > 0), cu cotă publicată."""
    from betpredict.robot import MODEL_VERSION
    from betpredict.robot.markets import market_key

    acc: Dict[str, Dict[str, Any]] = defaultdict(lambda: {"n": 0, "profit": 0.0, "won": 0, "n_clv": 0, "clv": 0.0, "clv2": 0.0})
    for r in conn.execute(
        """SELECT p.market, p.line, p.result, p.profit_1u, p.clv, m.league_id, l.name AS league
           FROM prediction p JOIN match m ON m.id = p.match_id LEFT JOIN league l ON l.id = m.league_id
           WHERE p.model_version = ? AND p.shown_on_page = 'predictii' AND p.day >= ? AND p.odds_shown IS NOT NULL
             AND (p.is_pick = 1 OR p.grade IN ('A','B') OR COALESCE(p.ev, -1) > 0) AND m.league_id IS NOT NULL""",
        (MODEL_VERSION, since)):
        mk = market_key(r["market"], r["line"] or 0.0)
        for k, name in ((seg_key(r["league_id"], mk), r["league"]), (group_key(r["league_id"], mk), None)):
            a = acc[k]
            a["league"] = name or ("Grup " + k.split("|")[0][2:])
            if r["result"] in ("won", "lost"):
                a["n"] += 1
                a["won"] += r["result"] == "won"
                a["profit"] += r["profit_1u"] or 0.0
            if r["clv"] is not None:
                a["n_clv"] += 1
                a["clv"] += r["clv"]
                a["clv2"] += r["clv"] ** 2
    return acc


def posterior(a: Dict[str, Any]) -> Dict[str, Any]:
    n_c = a["n_clv"]
    clv_post = a["clv"] / (n_c + PRIOR_CLV_N)
    mean = a["clv"] / n_c if n_c else 0.0
    var = max(1e-4, a["clv2"] / n_c - mean ** 2) if n_c > 1 else 0.0025
    se = math.sqrt(var / (n_c + PRIOR_CLV_N))
    p_pos = _norm_cdf(clv_post / se) if se > 0 else 0.5
    roi_post = (a["profit"] + PRIOR_ROI * PRIOR_ROI_N) / (a["n"] + PRIOR_ROI_N)
    return {"n": a["n"], "n_clv": n_c, "clv_post": round(clv_post, 4), "p_clv_pos": round(p_pos, 3),
            "roi_post": round(roi_post, 4), "roi_raw": round(a["profit"] / a["n"], 4) if a["n"] else None,
            "clv_raw": round(mean, 4) if n_c else None}


def decide(post: Dict[str, Any], current: Optional[str]) -> Tuple[Optional[str], str]:
    c, r, pp = post["clv_post"], post["roi_post"], post["p_clv_pos"]
    off_clv = post["n_clv"] >= MIN_CLV_N and c <= -0.01 and pp <= 0.10
    off_roi = post["n"] >= MIN_ROI_N and r <= -0.08 and c <= 0.0
    boost = post["n_clv"] >= MIN_CLV_N and c >= 0.01 and pp >= 0.90 and r >= -0.03
    if current == "off":
        if c >= 0 and r > -0.05 and not (off_clv or off_roi):
            return None, f"revine: CLV {c:+.1%}, ROI {r:+.1%} (micșorate)"
        return "off", "rămâne oprit"
    if off_clv or off_roi:
        why = (f"CLV mediu {post['clv_raw']:+.1%} pe {post['n_clv']} selecții (micșorat {c:+.1%}, P(CLV<0)={1 - pp:.0%})" if off_clv
               else f"ROI {post['roi_raw']:+.1%} pe {post['n']} selecții decontate (micșorat {r:+.1%}) și CLV ≤ 0")
        return "off", why
    if current == "boost" and c >= 0.003 and r >= -0.05:
        return "boost", "rămâne întărit"
    if boost:
        return "boost", f"CLV mediu {post['clv_raw']:+.1%} pe {post['n_clv']} selecții (micșorat {c:+.1%}, P(CLV>0)={pp:.0%}), ROI {r:+.1%}"
    return None, ""


def learn_segments(conn: sqlite3.Connection, params: Dict[str, Any], since: str, log_fn) -> List[Dict[str, Any]]:
    cur: Dict[str, Dict[str, Any]] = dict(params.get("segments") or {})
    new: Dict[str, Dict[str, Any]] = {}
    changes = []
    stats = segment_stats(conn, since)
    for k, a in stats.items():
        post = posterior(a)
        before = (cur.get(k) or {}).get("action")
        action, why = decide(post, before)
        if action:
            new[k] = {"action": action, "league": a.get("league"), **post}
        if action != before:
            lid, mk = k.split("|", 1)
            label = {"off": "oprit", "boost": "întărit", None: "normal"}
            text = f"{a.get('league') or 'Liga ' + lid} · {mk}: {label[before]} → {label[action]} — {why}"
            log_fn("segment", mk, label[before], label[action], {"n": post["n"], "n_clv": post["n_clv"], "clv_post": post["clv_post"],
                                                                  "roi_post": post["roi_post"], "why": text}, (None if lid.startswith("g:") else int(lid)))
            changes.append({"segment": k, "type": "segment", "before": before, "after": action})
    # segmentele oprite fără date noi rămân oprite (histerezis)
    for k, v in cur.items():
        if k not in stats and v.get("action") == "off":
            new[k] = v
    params["segments"] = new
    return changes


def segment_action(params: Dict[str, Any], league_id: Any, mkey: str) -> Optional[str]:
    """Acțiunea pe ligă × piață; dacă liga n-are decizie, cea a grupului de ligi × piață."""
    if league_id is None:
        return None
    segs = params.get("segments") or {}
    a = (segs.get(seg_key(league_id, mkey)) or {}).get("action")
    if a:
        return a
    return (segs.get(group_key(league_id, mkey)) or {}).get("action")
