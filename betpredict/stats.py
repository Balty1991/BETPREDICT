"""Agregate pentru pagina Statistici (din jurnalul Robotului + bilete + piramidă)."""

from __future__ import annotations

import json
import math
import sqlite3
from collections import defaultdict
from typing import Any, Callable, Dict, Iterable, List, Optional

from betpredict.robot import MODEL_VERSION
from betpredict.robot.markets import market_key, market_name_ro

ECE_LIMIT = 0.08


def _agg(rows: Iterable[sqlite3.Row]) -> Dict[str, Any]:
    n = won = lost = void = pending = 0
    profit = 0.0
    odds_sum = p_sum = brier = ll = 0.0
    n_bin = 0
    for r in rows:
        n += 1
        res = r["result"]
        if res is None:
            pending += 1
            continue
        if res == "void":
            void += 1
            continue
        y = 1.0 if res in ("won", "half_won") else 0.0
        won += res in ("won", "half_won")
        lost += res in ("lost", "half_lost")
        profit += r["profit_1u"] or 0.0
        odds_sum += r["odds_shown"] or 0.0
        p = min(1 - 1e-6, max(1e-6, r["p_calibrated"] or 0.5))
        p_sum += p
        brier += (p - y) ** 2
        ll += -(y * math.log(p) + (1 - y) * math.log(1 - p))
        n_bin += 1
    decided = won + lost
    return {
        "n": n, "won": won, "lost": lost, "void": void, "pending": pending,
        "win_rate": round(won / decided, 4) if decided else None,
        "roi_pct": round(100 * profit / decided, 2) if decided else None,
        "profit": round(profit, 2),
        "avg_odds": round(odds_sum / n_bin, 3) if n_bin else None,
        "avg_p": round(p_sum / n_bin, 4) if n_bin else None,
        "brier": round(brier / n_bin, 4) if n_bin else None,
        "logloss": round(ll / n_bin, 4) if n_bin else None,
    }


def _group(rows: List[sqlite3.Row], keyfn: Callable[[sqlite3.Row], Optional[str]], extra: Callable = None, limit: int = 0):
    groups: Dict[str, List[sqlite3.Row]] = defaultdict(list)
    for r in rows:
        k = keyfn(r)
        if k is not None:
            groups[k].append(r)
    out = []
    for k, rs in groups.items():
        item = {"key": k, **_agg(rs)}
        if extra:
            item.update(extra(k, rs))
        out.append(item)
    out.sort(key=lambda x: -x["n"])
    return out[:limit] if limit else out


def odds_band(o: Optional[float]) -> Optional[str]:
    if not o:
        return None
    for lo, hi in ((1.15, 1.3), (1.3, 1.5), (1.5, 1.75), (1.75, 2.0), (2.0, 2.5), (2.5, 3.5), (3.5, 99)):
        if lo <= o < hi:
            return f"{lo:.2f}-{hi:.2f}" if hi < 99 else f"{lo:.2f}+"
    return None


def p_band(p: Optional[float]) -> Optional[str]:
    if p is None:
        return None
    lo = min(0.9, math.floor(p * 10) / 10)
    return f"{lo:.2f}-{lo + 0.1:.2f}"


def calibration(rows: List[sqlite3.Row], bins: int = 10) -> Dict[str, Any]:
    settled = [r for r in rows if r["result"] in ("won", "lost")]
    b: Dict[int, List[float]] = defaultdict(list)
    for r in settled:
        p = r["p_calibrated"] or 0.0
        b[min(bins - 1, int(p * bins))].append((p, 1.0 if r["result"] == "won" else 0.0))
    out, ece, n = [], 0.0, len(settled)
    for i in range(bins):
        items = b.get(i) or []
        if not items:
            continue
        pa = sum(x for x, _ in items) / len(items)
        hr = sum(y for _, y in items) / len(items)
        ece += len(items) / max(1, n) * abs(pa - hr)
        out.append({"lo": i / bins, "hi": (i + 1) / bins, "n": len(items), "p_avg": round(pa, 4), "hit_rate": round(hr, 4)})
    return {"n": n, "ece": round(ece, 4) if n else None, "bins": out}


def robot_rows(conn: sqlite3.Connection) -> List[sqlite3.Row]:
    return conn.execute(
        """SELECT p.*, m.league_id, l.name AS league_name FROM prediction p
           JOIN match m ON m.id = p.match_id LEFT JOIN league l ON l.id = m.league_id
           WHERE p.model_version = ? AND p.shown_on_page = 'predictii'""",
        (MODEL_VERSION,),
    ).fetchall()


def ticket_stats(conn: sqlite3.Connection) -> List[Dict[str, Any]]:
    out = []
    for r in conn.execute(
        """SELECT kind, variant, COUNT(*) n, SUM(status='won') won, SUM(status='lost') lost, SUM(status='void') void,
                  SUM(status='pending') pending, SUM(CASE WHEN status IN ('won','lost') THEN COALESCE(payout,0) - stake ELSE 0 END) profit,
                  SUM(CASE WHEN status IN ('won','lost') THEN stake ELSE 0 END) staked
           FROM ticket WHERE status != 'replaced' GROUP BY kind, variant ORDER BY kind, variant"""
    ):
        out.append({"kind": r["kind"], "variant": r["variant"], "n": r["n"], "won": r["won"] or 0, "lost": r["lost"] or 0,
                    "void": r["void"] or 0, "pending": r["pending"] or 0, "profit": round(r["profit"] or 0, 2),
                    "roi_pct": round(100 * (r["profit"] or 0) / r["staked"], 2) if r["staked"] else None})
    return out


def pyramid_stats(conn: sqlite3.Connection) -> Dict[str, Any]:
    picks = conn.execute("SELECT status FROM ticket WHERE kind='pyramid' AND variant='principal' AND status!='replaced'").fetchall()
    days = conn.execute("SELECT COUNT(*) FROM ingest_state WHERE key LIKE 'pyramid.day.%'").fetchone()[0]
    won = sum(1 for p in picks if p["status"] == "won")
    lost = sum(1 for p in picks if p["status"] == "lost")
    best = conn.execute("SELECT MAX(current_step) FROM pyramid_run").fetchone()[0]
    runs = conn.execute("SELECT COUNT(*) FROM pyramid_run").fetchone()[0]
    return {"days": days, "picks": len(picks), "no_bet": max(0, days - len(picks)), "won": won, "lost": lost,
            "win_rate": round(won / (won + lost), 4) if won + lost else None, "runs": runs, "best_step": best or 0}


def recommendations(by_market: List[Dict[str, Any]], calib: List[Dict[str, Any]], by_odds: List[Dict[str, Any]],
                    tickets: List[Dict[str, Any]], overall: Dict[str, Any]) -> List[Dict[str, Any]]:
    rec: List[Dict[str, Any]] = []
    for c in calib:
        if c["n"] >= 50 and c["ece"] is not None and c["ece"] > ECE_LIMIT:
            rec.append({"severity": "warn", "text": f"{market_name_ro(c['key'])}: ECE {c['ece']:.2f} pe n={c['n']} → exclus din bilete până la recalibrare.",
                        "evidence": {"n": c["n"], "ece": c["ece"]}})
    for m in by_market:
        if m["won"] + m["lost"] >= 60 and m["roi_pct"] is not None and m["roi_pct"] < -8:
            rec.append({"severity": "warn", "text": f"{market_name_ro(m['key'])}: ROI {m['roi_pct']:.1f}% pe {m['won'] + m['lost']} selecții → pragul de EV crește pentru această piață.",
                        "evidence": {"n": m["won"] + m["lost"], "roi_pct": m["roi_pct"]}})
        elif m["won"] + m["lost"] >= 60 and m["roi_pct"] is not None and m["roi_pct"] > 4:
            rec.append({"severity": "info", "text": f"{market_name_ro(m['key'])}: ROI +{m['roi_pct']:.1f}% pe {m['won'] + m['lost']} selecții → pondere mai mare în bilete.",
                        "evidence": {"n": m["won"] + m["lost"], "roi_pct": m["roi_pct"]}})
    low = next((b for b in by_odds if b["key"] == "1.15-1.30"), None)
    if low and low["won"] + low["lost"] >= 50 and (low["roi_pct"] or 0) < 0:
        rec.append({"severity": "info", "text": f"Cote 1.15–1.30: rată de câștig {low['win_rate']:.0%} dar ROI {low['roi_pct']:.1f}% → ancorele cer EV mai mare.",
                    "evidence": {"n": low["won"] + low["lost"]}})
    for t in tickets:
        if t["kind"].startswith("acca_") and t["won"] + t["lost"] >= 20 and t["won"] == 0:
            rec.append({"severity": "info", "text": f"Bilete {t['kind'].replace('acca_', '~')} «{t['variant']}»: 0 câștigate din {t['won'] + t['lost']} — normal pentru cote mari, mizează mic și fix.",
                        "evidence": {"n": t["won"] + t["lost"]}})
    if not rec:
        n = (overall.get("won") or 0) + (overall.get("lost") or 0)
        rec.append({"severity": "info", "text": f"Eșantion încă mic ({n} selecții decontate). Recomandările apar după ~50 de selecții pe piață.",
                    "evidence": {"n": n}})
    return rec


def compute_stats(conn: sqlite3.Connection) -> Dict[str, Dict[str, Any]]:
    rows = robot_rows(conn)
    mk = lambda r: market_key(r["market"], r["line"] or 0.0)  # noqa: E731
    overall = _agg(rows)
    by_market = _group(rows, mk)
    calib = []
    by_mk: Dict[str, List] = defaultdict(list)
    for r in rows:
        by_mk[mk(r)].append(r)
    for k, rs in by_mk.items():
        c = calibration(rs)
        calib.append({"key": k, "n": c["n"], "ece": c["ece"], "healthy": not (c["n"] >= 50 and (c["ece"] or 0) > ECE_LIMIT), "bins": c["bins"]})
    calib.sort(key=lambda x: -x["n"])
    by_odds = _group(rows, lambda r: odds_band(r["odds_shown"]))
    tickets = ticket_stats(conn)
    legacy = conn.execute("""SELECT COUNT(*) n, SUM(result='won') w, SUM(profit_1u) pr FROM prediction
                             WHERE shown_on_page='legacy' AND result IN ('won','lost')""").fetchone()
    summary = {
        "schema": "betpredict.stats.v1", "scope": "robot",
        "overall": overall,
        "picks": _agg([r for r in rows if r["is_pick"]]),
        "value": _agg([r for r in rows if (r["ev"] or 0) > 0]),
        "by_market": by_market,
        "by_league": _group(rows, lambda r: str(r["league_id"]) if r["league_id"] is not None else None,
                            extra=lambda k, rs: {"name": rs[0]["league_name"]}, limit=40),
        "by_odds_band": by_odds,
        "by_grade": _group(rows, lambda r: r["grade"]),
        "by_p_band": _group(rows, lambda r: p_band(r["p_calibrated"])),
        "tickets": tickets,
        "pyramid": pyramid_stats(conn),
        "legacy": {"n": legacy["n"], "win_rate": round(legacy["w"] / legacy["n"], 4) if legacy["n"] else None,
                   "roi_pct": round(100 * (legacy["pr"] or 0) / legacy["n"], 2) if legacy["n"] else None},
    }
    summary["recommendations"] = recommendations(by_market, calib, by_odds, tickets, overall)

    def series(keyfn):
        out = []
        tick_rows = conn.execute("SELECT day, status, payout, stake FROM ticket WHERE status IN ('won','lost') AND kind LIKE 'acca_%'").fetchall()
        for g in _group(rows, keyfn):
            picks = _agg([r for r in rows if keyfn(r) == g["key"] and r["is_pick"]])
            tr = [t for t in tick_rows if t["day"] and keyfn({"day": t["day"]}) == g["key"]]
            g["picks"] = {"n": picks["n"], "won": picks["won"], "roi_pct": picks["roi_pct"]}
            g["tickets"] = {"n": len(tr), "won": sum(1 for t in tr if t["status"] == "won"),
                            "profit": round(sum((t["payout"] or 0) - t["stake"] for t in tr), 2)}
            out.append(g)
        out.sort(key=lambda x: x["key"])
        return out

    daily = {"schema": "betpredict.stats_series.v1", "rows": series(lambda r: r["day"])}
    monthly = {"schema": "betpredict.stats_series.v1", "rows": series(lambda r: (r["day"] or "")[:7] or None)}
    calibration_doc = {"schema": "betpredict.calibration.v1", "markets": calib}
    return {"summary": summary, "daily": daily, "monthly": monthly, "calibration": calibration_doc}
