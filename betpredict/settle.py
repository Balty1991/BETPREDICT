"""Decontare automată: predicții → bilete → piramidă. Void la amânat/anulat/nerezolvat."""

from __future__ import annotations

import math
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

from betpredict.ingest.normalize import VOID_STATUSES
from betpredict.robot.markets import leg_factor, profit_1u, settle_selection
from betpredict.store import repo
from betpredict.timeutil import canon_utc

STALE_VOID_DAYS = 7
_AET = {"aet", "pen", "afterextra", "after_extra", "afterpen", "after_penalties", "ap"}


def regulation_score(ft_home: Optional[int], ft_away: Optional[int], status: Optional[str], raw_json: Optional[str]) -> tuple:
    """90-minute score. Cup matches that go to extra time must not settle 1X2/OU/BTTS on the AET total."""
    import json

    raw: Dict = {}
    try:
        raw = json.loads(raw_json or "{}")
    except (TypeError, ValueError):
        raw = {}
    for hk, ak in (("home_score_90", "away_score_90"), ("home_score_regular", "away_score_regular"),
                   ("home_score_ft", "away_score_ft"), ("ft90_home", "ft90_away")):
        h, a = raw.get(hk), raw.get(ak)
        if h is not None and a is not None:
            try:
                return int(h), int(a)
            except (TypeError, ValueError):
                pass
    score = raw.get("score") if isinstance(raw.get("score"), dict) else {}
    full = score.get("fulltime") or score.get("regular") or {}
    if isinstance(full, dict) and full.get("home") is not None and full.get("away") is not None:
        return int(full["home"]), int(full["away"])
    st = (status or "").lower()
    if st in _AET and ft_home is not None and ft_away is not None:
        et_h, et_a = raw.get("home_score_et"), raw.get("away_score_et")
        if et_h is not None and et_a is not None:
            try:
                return int(ft_home) - int(et_h), int(ft_away) - int(et_a)
            except (TypeError, ValueError):
                pass
    return ft_home, ft_away


def settle_predictions(conn: sqlite3.Connection, now: Optional[datetime] = None) -> Dict[str, int]:
    now = now or datetime.now(timezone.utc)
    stale = canon_utc((now - timedelta(days=STALE_VOID_DAYS)).isoformat())
    rows = conn.execute(
        """SELECT p.id, p.market, p.line, p.selection, p.odds_shown, m.status, m.ft_home, m.ft_away, m.kickoff_utc, m.raw_json
           FROM prediction p JOIN match m ON m.id = p.match_id
           WHERE p.result IS NULL AND p.shown_on_page != 'legacy'"""
    ).fetchall()
    stats = {"checked": len(rows), "settled": 0, "void": 0}
    stamp = repo.now_iso()
    with conn:
        for r in rows:
            status = (r["status"] or "").lower()
            result = None
            finished = status in {"finished", "ft", "ended", *_AET} or (
                r["ft_home"] is not None and r["ft_away"] is not None and r["kickoff_utc"]
                and r["kickoff_utc"] < canon_utc((now - timedelta(hours=2)).isoformat()))
            if status in VOID_STATUSES:
                result = "void"
            elif finished:
                hs, aw = regulation_score(r["ft_home"], r["ft_away"], status, r["raw_json"])
                result = settle_selection(r["market"], r["line"] or 0.0, r["selection"], hs, aw)
            if result is None and r["kickoff_utc"] and r["kickoff_utc"] < stale:
                result = "void"  # fără rezultat după 7 zile
            if result is None:
                continue
            conn.execute("UPDATE prediction SET result=?, settled_at=?, profit_1u=? WHERE id=?",
                         (result, stamp, profit_1u(result, r["odds_shown"]), r["id"]))
            stats["settled"] += 1
            stats["void"] += 1 if result == "void" else 0
    return stats


def ticket_system(notes: Optional[str]) -> int:
    """k pentru biletele sistem (N−k)/N (din notes.backtest.system sau notes.system); 0 = acumulator."""
    import json

    try:
        n = json.loads(notes or "{}")
    except ValueError:
        return 0
    return int((n.get("backtest") or {}).get("system") or n.get("system") or 0)


def system_multiplier(factors: List[float], k: int) -> float:
    """Câștig per 1u pe sistem (N−k)/N: miza împărțită egal pe C(N, N−k) combinații; fiecare combinație plătește produsul
    factorilor (câștig = cota, void = 1, pierdut = 0) — polinomul simetric elementar de grad N−k / C(N, N−k)."""
    n, m = len(factors), len(factors) - k
    if m < 1:
        return 0.0
    e = [1.0] + [0.0] * m
    for f in factors:
        for j in range(m, 0, -1):
            e[j] += e[j - 1] * f
    return e[m] / math.comb(n, m)


def classify_payout(stake: float, payout: float, all_void: bool = False) -> str:
    """Won only when the ticket returns more than the stake. A partial cash return below stake is not a win."""
    stake = float(stake or 0.0)
    payout = float(0.0 if payout is None else payout)
    if all_void:
        return "void"
    tol = max(0.005, abs(stake) * 0.015)
    if payout + tol < stake:
        return "partial" if payout > tol else "lost"
    if stake > 0 and abs(payout - stake) <= tol:
        return "void"
    return "won"


def reclassify_settled(conn: sqlite3.Connection) -> int:
    """Recompute status from stored stake and payout so historical ROI is not counted on losing 'wins'."""
    n = 0
    rows = conn.execute(
        "SELECT id, stake, payout, status FROM ticket WHERE status IN ('won','lost','partial') AND payout IS NOT NULL"
    ).fetchall()
    for t in rows:
        legs = conn.execute("SELECT result FROM ticket_leg WHERE ticket_id=?", (t["id"],)).fetchall()
        results = [l["result"] for l in legs]
        all_void = bool(results) and all(r == "void" for r in results)
        new = classify_payout(t["stake"] or 0.0, t["payout"], all_void=all_void)
        if new != t["status"]:
            conn.execute("UPDATE ticket SET status=? WHERE id=?", (new, t["id"]))
            n += 1
    return n


def leg_result_from_match(market: str, selection: str, match: sqlite3.Row) -> Optional[str]:
    """Settle a ticket leg from the match score when it has no prediction_id."""
    from betpredict.ingest.normalize import VOID_STATUSES

    status = (match["status"] or "").lower()
    if status in VOID_STATUSES:
        return "void"
    scored = match["ft_home"] is not None and match["ft_away"] is not None
    old = bool(match["kickoff_utc"] and match["kickoff_utc"] < canon_utc((datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()))
    if status not in {"finished", "ft", "ended", *_AET} and not (scored and old):
        return None
    mk, _, line_s = (market or "").partition("|")
    if mk == "boost":
        return None
    if mk == "ss":
        from betpredict.experimental.supersocial import _settle_result

        return _settle_result(selection, match, "1970-01-01")
    if mk == "bb":
        from betpredict.builder.bb_legs import hits

        market_name, _, outcome = (selection or "").partition("|")
        hs, aw = regulation_score(match["ft_home"], match["ft_away"], status, match["raw_json"] if "raw_json" in match.keys() else None)
        if hs is None or aw is None:
            return None
        flag = hits(market_name, outcome, hs, aw)
        return None if flag is None else ("won" if flag else "lost")
    hs, aw = regulation_score(match["ft_home"], match["ft_away"], status, match["raw_json"] if "raw_json" in match.keys() else None)
    if hs is None or aw is None:
        return None
    try:
        line = float(line_s) if line_s else 0.0
    except ValueError:
        line = 0.0
    return settle_selection(mk, line, selection, hs, aw)


def settle_orphan_legs(conn: sqlite3.Connection) -> int:
    """Legs left pending after a DB restore: they have a score but no prediction_id, so the copy-from-prediction step skips them."""
    n = 0
    try:
        rows = conn.execute(
            """SELECT tl.rowid AS rid, tl.market, tl.selection, m.status, m.ft_home, m.ft_away, m.ht_home, m.ht_away,
                      m.corners_home, m.corners_away, m.corners_ht_home, m.corners_ht_away, m.cards_home, m.cards_away,
                      m.raw_json, m.kickoff_utc
               FROM ticket_leg tl JOIN match m ON m.id = tl.match_id
               WHERE tl.result IS NULL"""
        ).fetchall()
    except sqlite3.Error:
        return 0
    for r in rows:
        res = leg_result_from_match(r["market"], r["selection"], r)
        if res:
            conn.execute("UPDATE ticket_leg SET result=? WHERE rowid=?", (res, r["rid"]))
            n += 1
    return n


def settle_tickets(conn: sqlite3.Connection) -> Dict[str, int]:
    stats = {"tickets": 0, "won": 0, "lost": 0, "void": 0, "partial": 0, "reclassified": 0}
    stamp = repo.now_iso()
    with conn:
        conn.execute(
            """UPDATE ticket_leg SET result = (SELECT p.result FROM prediction p WHERE p.id = ticket_leg.prediction_id)
               WHERE result IS NULL AND prediction_id IS NOT NULL"""
        )
        from betpredict.experimental.supersocial import settle_legs, settle_track

        from betpredict.builder.soft_draw import settle_legs as settle_soft, settle_track as settle_soft_track

        from betpredict.ingest.boosts import settle as settle_boosts, settle_legs as settle_boost_legs

        settle_boosts(conn)
        settle_boost_legs(conn)
        settle_legs(conn)  # selecțiile „Stil Supersocial” (fără predicție): scor final + pauză
        settle_track(conn)  # toate selecțiile Supersocial urmărite (din ele învață robotul)
        settle_soft(conn)
        settle_soft_track(conn)  # toate egalurile A/B urmărite (Proiectul Egaluri)
        stats["reclassified"] = reclassify_settled(conn)
        stats["orphan_legs"] = settle_orphan_legs(conn)
        for t in conn.execute("SELECT id, total_odds, stake, notes FROM ticket WHERE status='pending'").fetchall():
            legs = conn.execute("SELECT odds, result FROM ticket_leg WHERE ticket_id=?", (t["id"],)).fetchall()
            if not legs:
                continue
            results = [l["result"] for l in legs]
            stake = t["stake"] or 1.0
            k = ticket_system(t["notes"])
            if k:  # sistem: plată reală pe combinații
                if sum(1 for r in results if r == "lost") > k:
                    status, payout = "lost", 0.0
                elif all(r is not None for r in results):
                    mult = system_multiplier([leg_factor(l["result"], l["odds"]) or 0.0 for l in legs], k)
                    payout = round(stake * mult, 2)
                    status = classify_payout(stake, payout, all_void=all(r == "void" for r in results))
                else:
                    continue
            elif any(r == "lost" for r in results):
                status, payout = "lost", 0.0
            elif all(r is not None for r in results):
                if all(r == "void" for r in results):
                    status, payout = "void", stake
                else:
                    mult = 1.0
                    for l in legs:
                        mult *= leg_factor(l["result"], l["odds"]) or 0.0
                    payout = round(stake * mult, 2)
                    status = classify_payout(stake, payout, all_void=False)
            else:
                continue
            conn.execute("UPDATE ticket SET status=?, payout=?, settled_at=? WHERE id=?", (status, payout, stamp, t["id"]))
            stats["tickets"] += 1
            stats[status] = stats.get(status, 0) + 1
        stats["stuck"] = flag_stale_tickets(conn)
    return stats


def flag_stale_tickets(conn: sqlite3.Connection, hours: float = 4.0) -> int:
    """După o nouă încercare de decontare, biletele al căror ultim meci a început de peste 4 ore rămân marcate cu motivul."""
    import json

    cutoff = canon_utc((datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat())
    n = 0
    rows = conn.execute(
        """SELECT t.id, t.notes, MAX(m.kickoff_utc) AS last_ko
           FROM ticket t JOIN ticket_leg tl ON tl.ticket_id = t.id JOIN match m ON m.id = tl.match_id
           WHERE t.status = 'pending' GROUP BY t.id"""
    ).fetchall()
    for t in rows:
        if not t["last_ko"] or t["last_ko"] >= cutoff:
            continue
        reasons = []
        for l in conn.execute(
                """SELECT tl.market, tl.selection, tl.result, tl.prediction_id, m.status, m.ft_home, m.kickoff_utc
                   FROM ticket_leg tl JOIN match m ON m.id = tl.match_id WHERE tl.ticket_id=? AND tl.result IS NULL""",
                (t["id"],)):
            if (l["status"] or "").lower() in VOID_STATUSES:
                reasons.append(f"{l['market']} {l['selection']}: meci anulat/amânat, încă nedecontat")
            elif l["ft_home"] is None:
                reasons.append(f"{l['market']} {l['selection']}: lipsă scor (status {l['status'] or 'necunoscut'})")
            else:
                reasons.append(f"{l['market']} {l['selection']}: scor prezent, piața nu se poate deconta")
        if not reasons:
            reasons.append("selecțiile au rezultat, biletul nu s-a închis")
        try:
            notes = json.loads(t["notes"] or "{}")
        except ValueError:
            notes = {}
        notes["stuck_reason"] = "; ".join(reasons[:8])
        conn.execute("UPDATE ticket SET notes=? WHERE id=?", (json.dumps(notes, ensure_ascii=False), t["id"]))
        n += 1
    return n


def settle_all(conn: sqlite3.Connection, now: Optional[datetime] = None) -> Dict[str, Dict[str, int]]:
    from betpredict.builder.pyramid import advance_pyramid

    out = {"predictions": settle_predictions(conn, now), "tickets": settle_tickets(conn)}
    try:
        from betpredict.builder.betbuilder import settle_suggestions

        out["bet_builder"] = settle_suggestions(conn)
    except Exception as exc:  # noqa: BLE001
        out["bet_builder"] = {"error": str(exc)}
    try:
        from betpredict.clv import compute_clv

        out["clv"] = compute_clv(conn, now)
    except Exception as exc:  # noqa: BLE001 — CLV e informativ; nu oprește decontarea
        out["clv_error"] = str(exc)
    from betpredict.builder.pyramid_auto import advance_all

    out["pyramid"] = advance_all(conn)  # cele 3 piramide, cu regula de retragere curentă (campion)
    return out
