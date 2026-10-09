"""Autoînvățare săptămânală: ponderi de blend și calibrare pe piață, piețe excluse (ECE),
penalizare pe ligă, raport walk-forward al modelului de goluri. Totul logat în learning_log."""

from __future__ import annotations

import itertools
import json
import math
import sqlite3
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from betpredict.ingest.history import finished_matches
from betpredict.robot import MODEL_VERSION
from betpredict.robot.markets import market_key, probs_from_matrix
from betpredict.robot.model import RHO, fit_goal_model
from betpredict.robot.params import DEFAULT_BLEND, blend_weights, load_params, logit, save_params, sigmoid
from betpredict.stats import ECE_LIMIT, calibration
from betpredict.store import repo

MIN_N_BLEND = 150
MIN_N_CALIB = 150
MIN_N_ECE = 60


def _ll(p: float, y: float) -> float:
    p = min(1 - 1e-6, max(1e-6, p))
    return -(y * math.log(p) + (1 - y) * math.log(1 - p))


def blend_p(w: Dict[str, float], pm, pb, pk) -> Optional[float]:
    parts = [(w["model"], pm), (w["bsd"], pb), (w["market"], pk)]
    parts = [(a, b) for a, b in parts if b is not None and a > 0]
    den = sum(a for a, _ in parts)
    return sum(a * b for a, b in parts) / den if den > 0 else None


def fit_blend(samples: List[Tuple]) -> Tuple[Dict[str, float], float]:
    best, best_ll = dict(DEFAULT_BLEND), float("inf")
    grid = [i / 10 for i in range(11)]
    for wm, wb in itertools.product(grid, grid):
        wk = round(1 - wm - wb, 2)
        if wk < -1e-9:
            continue
        w = {"model": wm, "bsd": wb, "market": max(0.0, wk)}
        tot, n = 0.0, 0
        for pm, pb, pk, y in samples:
            p = blend_p(w, pm, pb, pk)
            if p is None:
                continue
            tot += _ll(p, y)
            n += 1
        if n and tot / n < best_ll:
            best, best_ll = w, tot / n
    return best, best_ll


def fit_platt(ps: List[float], ys: List[float], iters: int = 50) -> Tuple[float, float]:
    a, b = 1.0, 0.0
    xs = [logit(p) for p in ps]
    for _ in range(iters):
        ga = gb = haa = hab = hbb = 0.0
        for x, y in zip(xs, ys):
            q = sigmoid(a * x + b)
            r = q - y
            wq = q * (1 - q)
            ga += r * x
            gb += r
            haa += wq * x * x + 1e-6
            hab += wq * x
            hbb += wq + 1e-6
        det = haa * hbb - hab * hab
        if abs(det) < 1e-12:
            break
        da = (hbb * ga - hab * gb) / det
        db = (haa * gb - hab * ga) / det
        a, b = a - da, b - db
        if abs(da) + abs(db) < 1e-6:
            break
    return max(0.3, min(2.0, a)), max(-1.5, min(1.5, b))


def walk_forward(conn: sqlite3.Connection, months: int = 3, now: Optional[datetime] = None) -> List[Dict[str, Any]]:
    now = now or datetime.now(timezone.utc)
    rows = [tuple(r) for r in finished_matches(conn)]
    if not rows:
        return []
    last = datetime.fromisoformat(rows[-1][2].replace("Z", "+00:00"))
    folds = []
    for k in range(months, 0, -1):
        end = last - timedelta(days=30 * (k - 1))
        start = end - timedelta(days=30)
        s_s, e_s = start.strftime("%Y-%m-%dT%H:%M:%SZ"), end.strftime("%Y-%m-%dT%H:%M:%SZ")
        test = [r for r in rows if s_s <= r[2] < e_s]
        if len(test) < 100:
            continue
        model = fit_goal_model(rows, start)
        train_prior = [r for r in rows if r[2] < s_s][-20000:]
        nh = sum(1 for r in train_prior if r[5] > r[6]) / max(1, len(train_prior))
        nd = sum(1 for r in train_prior if r[5] == r[6]) / max(1, len(train_prior))
        no25 = sum(1 for r in train_prior if r[5] + r[6] > 2.5) / max(1, len(train_prior))
        ll1 = b1 = llo = bo = 0.0
        from analytics_core import football_score_matrix

        for r in test:
            lh, la = model.lambdas(r[3], r[4], r[1])
            pr = probs_from_matrix(football_score_matrix(lh, la, max_goals=10, rho=RHO))
            out = "HOME" if r[5] > r[6] else ("AWAY" if r[5] < r[6] else "DRAW")
            p_out = pr[("1x2", 0.0, out)]
            base = {"HOME": nh, "DRAW": nd, "AWAY": 1 - nh - nd}[out]
            ll1 += -math.log(max(1e-6, p_out))
            b1 += -math.log(max(1e-6, base))
            y = 1.0 if r[5] + r[6] > 2.5 else 0.0
            llo += _ll(pr[("over_under", 2.5, "OVER")], y)
            bo += _ll(no25, y)
        n = len(test)
        folds.append({"fold": start.strftime("%Y-%m"), "n": n, "logloss_1x2": round(ll1 / n, 4), "baseline_1x2": round(b1 / n, 4),
                      "logloss_ou25": round(llo / n, 4), "baseline_ou25": round(bo / n, 4)})
    return folds


def _log(conn, change_type: str, market: Optional[str], before: Any, after: Any, evidence: Dict[str, Any], league_id=None):
    conn.execute(
        "INSERT INTO learning_log(run_at, market, league_id, change_type, before, after, evidence_json) VALUES (?,?,?,?,?,?,?)",
        (repo.now_iso(), market, league_id, change_type, json.dumps(before, ensure_ascii=False),
         json.dumps(after, ensure_ascii=False), json.dumps(evidence, ensure_ascii=False)),
    )


def learn(conn: sqlite3.Connection, days: int = 120, with_backtest: bool = True) -> Dict[str, Any]:
    params = load_params(conn)
    since = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")
    rows = conn.execute(
        """SELECT p.*, m.league_id FROM prediction p JOIN match m ON m.id=p.match_id
           WHERE p.model_version=? AND p.shown_on_page='predictii' AND p.result IN ('won','lost') AND p.day >= ?""",
        (MODEL_VERSION, since),
    ).fetchall()
    by_mk: Dict[str, List[sqlite3.Row]] = defaultdict(list)
    for r in rows:
        by_mk[market_key(r["market"], r["line"] or 0.0)].append(r)
    changes: List[Dict[str, Any]] = []
    with conn:
        for mk, rs in by_mk.items():
            ys = [1.0 if r["result"] == "won" else 0.0 for r in rs]
            if len(rs) >= MIN_N_BLEND:
                samples = [(r["p_model"], r["p_bsd"], r["p_market_novig"], y) for r, y in zip(rs, ys)]
                w, ll = fit_blend(samples)
                before = blend_weights(params, mk)
                if any(abs(w[k] - before.get(k, 0)) >= 0.1 for k in w):
                    params.setdefault("blend", {})[mk] = w
                    _log(conn, "blend_weights", mk, before, w, {"n": len(rs), "logloss": round(ll, 4)})
                    changes.append({"market": mk, "type": "blend_weights"})
            if len(rs) >= MIN_N_CALIB:
                w = blend_weights(params, mk)
                pairs = [(blend_p(w, r["p_model"], r["p_bsd"], r["p_market_novig"]), y) for r, y in zip(rs, ys)]
                pairs = [(p, y) for p, y in pairs if p is not None]
                a, b = fit_platt([p for p, _ in pairs], [y for _, y in pairs])
                before = params.get("calibration", {}).get(mk)
                params.setdefault("calibration", {})[mk] = {"a": round(a, 4), "b": round(b, 4), "n": len(pairs)}
                _log(conn, "calibration", mk, before, params["calibration"][mk], {"n": len(pairs)})
                changes.append({"market": mk, "type": "calibration"})
            c = calibration(rs)
            excluded = set(params.get("excluded_markets", []))
            if c["n"] >= MIN_N_ECE and c["ece"] is not None:
                bad = c["ece"] > ECE_LIMIT
                if bad and mk not in excluded:
                    excluded.add(mk)
                    _log(conn, "exclude_market", mk, False, True, {"n": c["n"], "ece": c["ece"]})
                    changes.append({"market": mk, "type": "exclude"})
                elif not bad and mk in excluded:
                    excluded.discard(mk)
                    _log(conn, "include_market", mk, True, False, {"n": c["n"], "ece": c["ece"]})
                    changes.append({"market": mk, "type": "include"})
            params["excluded_markets"] = sorted(excluded)
        # încrederea pe ligă: ROI pe pick-uri
        by_league: Dict[int, List[sqlite3.Row]] = defaultdict(list)
        for r in rows:
            if r["league_id"] is not None:
                by_league[r["league_id"]].append(r)
        pen = dict(params.get("league_penalty", {}))
        for lid, rs in by_league.items():
            if len(rs) < 40:
                continue
            roi = sum(r["profit_1u"] or 0 for r in rs) / len(rs)
            new = 0.85 if roi < -0.12 else (0.93 if roi < -0.06 else 1.0)
            if abs(pen.get(str(lid), 1.0) - new) > 1e-9:
                _log(conn, "league_penalty", None, pen.get(str(lid), 1.0), new, {"n": len(rs), "roi": round(roi, 4)}, league_id=lid)
                changes.append({"league_id": lid, "type": "league_penalty"})
                if new == 1.0:
                    pen.pop(str(lid), None)
                else:
                    pen[str(lid)] = new
        params["league_penalty"] = pen
    save_params(conn, params)
    report: Dict[str, Any] = {"samples": len(rows), "changes": changes, "params": params}
    if with_backtest:
        wf = walk_forward(conn)
        report["walk_forward"] = wf
        with conn:
            conn.execute(
                "INSERT INTO model_registry(version, trained_at, metrics_json, is_active) VALUES (?,?,?,1) "
                "ON CONFLICT(version) DO UPDATE SET trained_at=excluded.trained_at, metrics_json=excluded.metrics_json, is_active=1",
                (MODEL_VERSION, repo.now_iso(), json.dumps({"walk_forward": wf})),
            )
    return report


def learning_doc(conn: sqlite3.Connection) -> Dict[str, Any]:
    params = load_params(conn)
    reg = conn.execute("SELECT * FROM model_registry WHERE version=?", (MODEL_VERSION,)).fetchone()
    wf = json.loads(reg["metrics_json"]).get("walk_forward", []) if reg and reg["metrics_json"] else []
    n_hist = conn.execute("SELECT COUNT(*) FROM match WHERE status='finished'").fetchone()[0]
    log = [{"run_at": r["run_at"], "change_type": r["change_type"], "market": r["market"], "league_id": r["league_id"],
            "before": r["before"], "after": r["after"], "evidence": json.loads(r["evidence_json"] or "{}")}
           for r in conn.execute("SELECT * FROM learning_log WHERE change_type != 'legacy_performance_snapshot' ORDER BY id DESC LIMIT 100")]
    return {"schema": "betpredict.learning.v1",
            "model": {"version": MODEL_VERSION, "trained_at": reg["trained_at"] if reg else None, "matches": n_hist, "half_life_days": 180},
            "walk_forward": wf,
            "params": {k: params.get(k) for k in ("blend", "calibration", "excluded_markets", "league_penalty", "updated_at")},
            "log": log}
