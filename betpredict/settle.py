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
# Regula caselor de pariuri (Superbet, 28.11): un meci amânat/suspendat rămâne valabil dacă se joacă în 48 de ore de la ora
# inițială (contează rezultatul); altfel selecția primește cota 1.00 (pe bilet multiplu). Anulat = cota 1.00 imediat.
WAIT_STATUSES = {"postponed", "suspended", "interrupted", "delayed"}
WAIT_HOURS = 48


def wait_or_void(status: str, kickoff_utc: Optional[str], now: Optional[datetime] = None) -> Optional[str]:
    """Pentru un meci amânat/suspendat: None cât încă se poate juca (sub 48 h de la ora inițială), apoi „void”."""
    if status not in WAIT_STATUSES:
        return "void"
    try:
        ko = datetime.fromisoformat((kickoff_utc or "").replace("Z", "+00:00"))
    except ValueError:
        return "void"
    ko = ko if ko.tzinfo else ko.replace(tzinfo=timezone.utc)
    return "void" if (now or datetime.now(timezone.utc)) >= ko + timedelta(hours=WAIT_HOURS) else None
_AET = {"aet", "pen", "afterextra", "after_extra", "afterpen", "after_penalties", "ap"}
FINAL_STATUSES = {"finished", "ft", "ended", *_AET}
# Fără status „terminat”, scorul se acceptă abia la 6 ore după start: la 2 ore, meciurile cu prelungiri/penalty-uri sau cu
# scorul live întârziat s-au decontat greșit (14.11: 94 de predicții pe 33 de meciuri, corectate abia de rechecks).
FALLBACK_FINISH_H = 6.0
RECHECK_DAYS = 10     # rezultatele decontate se reverifică atâtea zile: scorurile corectate ulterior schimbă selecția
TWIN_WINDOW_H = 36.0  # același meci dublat în fixture-uri (alt id, uneori altă oră): căutăm geamănul terminat în ±36 h
_PENDING_STATUSES = {"", "notstarted", "upcoming", "scheduled", "not_started", "tbd"}


def looks_final(status: Optional[str], ft_home, ft_away, kickoff_utc: Optional[str], now: Optional[datetime] = None) -> bool:
    """Meci terminat: status final, sau scor prezent și start de peste ``FALLBACK_FINISH_H`` ore (feed fără status final)."""
    st = (status or "").lower()
    if st in FINAL_STATUSES:
        return True
    if st in VOID_STATUSES or ft_home is None or ft_away is None or not kickoff_utc:
        return False
    now = now or datetime.now(timezone.utc)
    return kickoff_utc < canon_utc((now - timedelta(hours=FALLBACK_FINISH_H)).isoformat())


def _row_get(r, key):
    try:
        return r[key]
    except (IndexError, KeyError):
        return None


def twin_match(conn: sqlite3.Connection, m, now: Optional[datetime] = None) -> Optional[sqlite3.Row]:
    """Meciul dublat: același meci sub alt id (aceleași echipe, start la cel mult 36 h), unul rămas „notstarted” pentru
    totdeauna. Întoarce geamănul terminat cu scor, cel mai apropiat ca oră; None dacă nu există sau e ambiguu."""
    from betpredict.ingest.superbet import norm_name

    status = (_row_get(m, "status") or "").lower()
    ko = _row_get(m, "kickoff_utc")
    if status not in _PENDING_STATUSES or not ko or _row_get(m, "ft_home") is not None:
        return None
    now = now or datetime.now(timezone.utc)
    if ko >= canon_utc((now - timedelta(hours=FALLBACK_FINISH_H)).isoformat()):
        return None
    try:
        t = datetime.fromisoformat(ko.replace("Z", "+00:00"))
    except ValueError:
        return None
    lo = canon_utc((t - timedelta(hours=TWIN_WINDOW_H)).isoformat())
    hi = canon_utc((t + timedelta(hours=TWIN_WINDOW_H)).isoformat())
    hid, aid = _row_get(m, "home_id"), _row_get(m, "away_id")
    hn, an = norm_name(_row_get(m, "home_name") or ""), norm_name(_row_get(m, "away_name") or "")
    best, best_dt = None, None
    q = ",".join("?" for _ in FINAL_STATUSES)
    try:
        cands = conn.execute(
            f"SELECT * FROM match WHERE id != ? AND kickoff_utc BETWEEN ? AND ? AND ft_home IS NOT NULL AND ft_away IS NOT NULL "
            f"AND lower(status) IN ({q})", (_row_get(m, "id"), lo, hi, *FINAL_STATUSES)).fetchall()
    except sqlite3.Error:
        return None
    for c in cands:
        same_ids = hid is not None and aid is not None and _row_get(c, "home_id") == hid and _row_get(c, "away_id") == aid
        same_names = bool(hn and an) and norm_name(_row_get(c, "home_name") or "") == hn \
            and norm_name(_row_get(c, "away_name") or "") == an
        if not (same_ids or same_names):
            continue
        dt = abs((datetime.fromisoformat(c["kickoff_utc"].replace("Z", "+00:00")) - t).total_seconds())
        if best_dt is not None and abs(dt - best_dt) < 1:
            if (best["ft_home"], best["ft_away"]) != (c["ft_home"], c["ft_away"]):
                return None  # doi gemeni cu scoruri diferite: nu ghicim
        if best_dt is None or dt < best_dt:
            best, best_dt = c, dt
    return best


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
        """SELECT p.id, p.market, p.line, p.selection, p.odds_shown, m.id AS mid, m.status, m.ft_home, m.ft_away, m.kickoff_utc,
                  m.raw_json, m.home_id, m.away_id, m.home_name, m.away_name
           FROM prediction p JOIN match m ON m.id = p.match_id
           WHERE p.result IS NULL AND p.shown_on_page != 'legacy'"""
    ).fetchall()
    stats = {"checked": len(rows), "settled": 0, "void": 0, "twin": 0}
    twins: Dict[int, Optional[sqlite3.Row]] = {}
    stamp = repo.now_iso()
    with conn:
        for r in rows:
            status = (r["status"] or "").lower()
            result = None
            finished = looks_final(status, r["ft_home"], r["ft_away"], r["kickoff_utc"], now)
            if status in VOID_STATUSES and status not in WAIT_STATUSES:
                result = "void"
            elif finished:
                hs, aw = regulation_score(r["ft_home"], r["ft_away"], status, r["raw_json"])
                result = settle_selection(r["market"], r["line"] or 0.0, r["selection"], hs, aw)
            else:
                if r["mid"] not in twins:
                    twins[r["mid"]] = twin_match(conn, {**dict(r), "id": r["mid"]}, now)
                tw = twins[r["mid"]]
                if tw is not None:
                    hs, aw = regulation_score(tw["ft_home"], tw["ft_away"], (tw["status"] or "").lower(), tw["raw_json"])
                    result = settle_selection(r["market"], r["line"] or 0.0, r["selection"], hs, aw)
                    stats["twin"] += 1 if result else 0
            if result is None and status in WAIT_STATUSES:
                result = wait_or_void(status, r["kickoff_utc"], now)  # rejucat în 48 h → rezultatul (geamănul de mai sus)
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
    if payout <= tol and not all_void:
        return "lost"  # nimic înapoi nu e niciodată câștig, oricare ar fi miza salvată
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
        # fără miză salvată (biletele Robotului pe hârtie): miza 1, ca la decontare — altfel plata 0 vs miza 0 ieșea „câștigat”
        new = classify_payout(t["stake"] or 1.0, t["payout"], all_void=all_void)
        if new != t["status"]:
            conn.execute("UPDATE ticket SET status=? WHERE id=?", (new, t["id"]))
            n += 1
    return n


def leg_result_from_match(market: str, selection: str, match: sqlite3.Row, now: Optional[datetime] = None) -> Optional[str]:
    """Settle a ticket leg from the match score when it has no prediction_id."""
    status = (match["status"] or "").lower()
    if status in VOID_STATUSES:
        return wait_or_void(status, match["kickoff_utc"], now)
    if not looks_final(status, match["ft_home"], match["ft_away"], match["kickoff_utc"], now):
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
    if mk == "interval":
        from betpredict.builder.long26 import interval_hit

        hs, aw = regulation_score(match["ft_home"], match["ft_away"], status, match["raw_json"] if "raw_json" in match.keys() else None)
        if hs is None or aw is None:
            return None
        flag = interval_hit(selection, hs, aw)
        return None if flag is None else ("won" if flag else "lost")
    hs, aw = regulation_score(match["ft_home"], match["ft_away"], status, match["raw_json"] if "raw_json" in match.keys() else None)
    if hs is None or aw is None:
        return None
    try:
        line = float(line_s) if line_s else 0.0
    except ValueError:
        line = 0.0
    return settle_selection(mk, line, selection, hs, aw)


def settle_orphan_legs(conn: sqlite3.Connection, now: Optional[datetime] = None) -> int:
    """Legs left pending after a DB restore: they have a score but no prediction_id, so the copy-from-prediction step skips them.
    A leg on a duplicated fixture (same teams, the copy stays „notstarted” forever) is settled from its finished twin."""
    n = 0
    try:
        rows = conn.execute(
            """SELECT tl.rowid AS rid, tl.market, tl.selection, m.*
               FROM ticket_leg tl JOIN match m ON m.id = tl.match_id
               WHERE tl.result IS NULL"""
        ).fetchall()
    except sqlite3.Error:
        return 0
    twins: Dict[int, Optional[sqlite3.Row]] = {}
    for r in rows:
        res = leg_result_from_match(r["market"], r["selection"], r, now)
        if res is None:
            if r["id"] not in twins:
                twins[r["id"]] = twin_match(conn, r, now)
            if twins[r["id"]] is not None:
                res = leg_result_from_match(r["market"], r["selection"], twins[r["id"]], now)
        if res:
            conn.execute("UPDATE ticket_leg SET result=? WHERE rowid=?", (res, r["rid"]))
            n += 1
    return n


def ticket_outcome(legs: List, stake: float, notes: Optional[str]) -> Optional[tuple]:
    """(status, payout) pentru un bilet din selecțiile lui (``odds``, ``result``); None cât timp nu se poate închide."""
    results = [l["result"] for l in legs]
    if not legs:
        return None
    k = ticket_system(notes)
    if k:  # sistem: plată reală pe combinații
        if sum(1 for r in results if r == "lost") > k:
            return "lost", 0.0
        if all(r is not None for r in results):
            mult = system_multiplier([leg_factor(l["result"], l["odds"]) or 0.0 for l in legs], k)
            payout = round(stake * mult, 2)
            return classify_payout(stake, payout, all_void=all(r == "void" for r in results)), payout
        return None
    if any(r == "lost" for r in results):
        return "lost", 0.0
    if not all(r is not None for r in results):
        return None
    if all(r == "void" for r in results):
        return "void", stake
    mult = 1.0
    for l in legs:
        mult *= leg_factor(l["result"], l["odds"]) or 0.0
    payout = round(stake * mult, 2)
    return classify_payout(stake, payout, all_void=False), payout


def recheck_settled(conn: sqlite3.Connection, now: Optional[datetime] = None, days: int = RECHECK_DAYS) -> Dict[str, int]:
    """Scorurile se corectează după decontare (prelungiri, scor live întârziat, date reparate): refacem rezultatele
    predicțiilor și selecțiilor din ultimele ``days`` zile pe scorul final de acum și închidem din nou biletele atinse.
    Biletele piramidei doar se marchează (``result_mismatch``): pașii piramidei deja jucați nu se rescriu."""
    import json

    now = now or datetime.now(timezone.utc)
    since = canon_utc((now - timedelta(days=days)).isoformat())
    out = {"predictions": 0, "legs": 0, "tickets": 0, "flagged": 0}
    q = ",".join("?" for _ in FINAL_STATUSES)
    try:
        preds = conn.execute(
            f"""SELECT p.id, p.market, p.line, p.selection, p.result, p.odds_shown, m.status, m.ft_home, m.ft_away, m.raw_json
                FROM prediction p JOIN match m ON m.id = p.match_id
                WHERE p.result IN ('won','lost','void') AND m.kickoff_utc >= ? AND lower(m.status) IN ({q})
                  AND m.ft_home IS NOT NULL AND m.ft_away IS NOT NULL""", (since, *FINAL_STATUSES)).fetchall()
    except sqlite3.Error:
        preds = []  # schemă veche/incompletă (teste, restaurări): sărim doar verificarea predicțiilor
    for r in preds:
        hs, aw = regulation_score(r["ft_home"], r["ft_away"], (r["status"] or "").lower(), r["raw_json"])
        new = settle_selection(r["market"], r["line"] or 0.0, r["selection"], hs, aw)
        if new and new != r["result"]:
            conn.execute("UPDATE prediction SET result=?, profit_1u=? WHERE id=?", (new, profit_1u(new, r["odds_shown"]), r["id"]))
            out["predictions"] += 1
    touched = set()
    try:
        legs_rows = conn.execute(
            f"""SELECT tl.rowid AS rid, tl.ticket_id, tl.market, tl.selection, tl.result, m.*
                FROM ticket_leg tl JOIN match m ON m.id = tl.match_id JOIN ticket tk ON tk.id = tl.ticket_id
                WHERE tl.result IN ('won','lost','void') AND m.kickoff_utc >= ? AND lower(m.status) IN ({q})
                  AND NOT (tk.kind = 'pyramid' AND tk.variant = 'psa' AND tl.market LIKE '1x2%')  -- SuperAvantaj: nu e la scorul final
                  AND m.ft_home IS NOT NULL AND m.ft_away IS NOT NULL""", (since, *FINAL_STATUSES)).fetchall()
    except sqlite3.Error:
        legs_rows = []
    for r in legs_rows:
        try:
            new = leg_result_from_match(r["market"], r["selection"], r, now)
        except (IndexError, KeyError):
            continue  # coloane lipsă (cornere la pauză etc.) într-o schemă veche: rămâne cum era
        if new and new != r["result"]:
            conn.execute("UPDATE ticket_leg SET result=? WHERE rowid=?", (new, r["rid"]))
            out["legs"] += 1
            touched.add(r["ticket_id"])
    stamp = repo.now_iso()
    for tid in sorted(touched):
        t = conn.execute("SELECT id, kind, stake, status, payout, notes FROM ticket WHERE id=?", (tid,)).fetchone()
        if t is None or t["status"] not in ("won", "lost", "partial", "void"):
            continue  # în joc: se închide normal; înlocuit: nu intră în statistică
        legs = conn.execute("SELECT odds, result FROM ticket_leg WHERE ticket_id=?", (tid,)).fetchall()
        res = ticket_outcome(legs, t["stake"] or 1.0, t["notes"])
        if res is None or (res[0] == t["status"] and abs((res[1] or 0) - (t["payout"] or 0)) < 0.005):
            continue
        try:
            notes = json.loads(t["notes"] or "{}")
        except ValueError:
            notes = {}
        if (t["kind"] or "").startswith("pyramid"):
            notes["result_mismatch"] = {"was": t["status"], "now": res[0], "at": stamp}
            conn.execute("UPDATE ticket SET notes=? WHERE id=?", (json.dumps(notes, ensure_ascii=False), tid))
            out["flagged"] += 1
            continue
        notes["corrected"] = {"was": t["status"], "was_payout": t["payout"], "at": stamp}
        conn.execute("UPDATE ticket SET status=?, payout=?, notes=? WHERE id=?",
                     (res[0], res[1], json.dumps(notes, ensure_ascii=False), tid))
        out["tickets"] += 1
    return out


def settle_tickets(conn: sqlite3.Connection, now: Optional[datetime] = None) -> Dict[str, int]:
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
        try:  # selecțiile din piețele generale găsite de Robot (market 'sb|0')
            from betpredict.builder.market_settle import settle_sb_legs

            settle_sb_legs(conn)
        except Exception:  # noqa: BLE001
            pass
        settle_track(conn)  # toate selecțiile Supersocial urmărite (din ele învață robotul)
        settle_soft(conn)
        settle_soft_track(conn)  # doar egalurile A urmărite (Proiectul Egaluri)
        try:
            from betpredict.builder.betbuilder import settle_suggestions
            from betpredict.builder.corner_tickets import settle_legs as settle_corners

            settle_suggestions(conn)
            settle_corners(conn)
        except Exception:  # noqa: BLE001 — decontarea cornere nu oprește restul biletelor
            pass
        stats["reclassified"] = reclassify_settled(conn)
        stats["orphan_legs"] = settle_orphan_legs(conn, now)
        for k, v in recheck_settled(conn, now).items():
            stats[f"recheck_{k}"] = v
        for t in conn.execute("SELECT id, total_odds, stake, notes FROM ticket WHERE status='pending'").fetchall():
            legs = conn.execute("SELECT odds, result FROM ticket_leg WHERE ticket_id=?", (t["id"],)).fetchall()
            res = ticket_outcome(legs, t["stake"] or 1.0, t["notes"])
            if res is None:
                continue
            status, payout = res
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

    out = {"predictions": settle_predictions(conn, now), "tickets": settle_tickets(conn, now)}
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
