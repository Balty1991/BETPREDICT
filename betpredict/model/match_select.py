"""Per-match market choice.

For each fixture, score every offered market with a corrected probability and keep
at most one: the positive-EV market, or an explicit no-bet. The correction is:

* isotonic (or Platt, on small samples) on the model's own settled probabilities,
  which pulls in the overconfident 0.70–0.75 and 0.85–0.90 buckets;
* an empirical-Bayes hit/implied ratio by market and by market×league, shrunk
  toward the market and then the global ratio when the sample is small.

Nothing here is a global blacklist. A market that usually finishes below its
price is only skipped when, after that penalty, its EV for *this* match is not
positive.
"""

from __future__ import annotations

import math
import sqlite3
from collections import defaultdict
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

EV_MARGIN = 0.02
SHRINK_K = 40.0
MIN_ISO = 80
MIN_PLATT = 25

_ACTIVE: Optional["Calibrator"] = None


def _clip(p: float, lo: float = 0.01, hi: float = 0.99) -> float:
    return min(hi, max(lo, float(p)))


def _logit(p: float) -> float:
    p = _clip(p, 1e-4, 1 - 1e-4)
    return math.log(p / (1 - p))


def _sig(z: float) -> float:
    if z > 30:
        return 1.0
    if z < -30:
        return 0.0
    return 1 / (1 + math.exp(-z))


def use_calibrator(cal: Optional["Calibrator"]) -> None:
    global _ACTIVE
    _ACTIVE = cal


def active() -> Optional["Calibrator"]:
    return _ACTIVE


def market_id(market: str, selection: str = "", line: float = 0.0) -> str:
    sel = selection or market
    if market == "ss" or (market == sel and not line):
        return sel
    if line:
        return f"{market}_{line:g}:{sel}"
    return f"{market}:{sel}"


class Calibrator:
    """Fitted on settled rows. Empty calibrator leaves probabilities unchanged aside from clipping."""

    def __init__(self) -> None:
        self.n = 0
        self.iso_x: List[float] = []
        self.iso_y: List[float] = []
        self.platt: Optional[Tuple[float, float]] = None
        self.global_hit = 0.5
        self.global_imp = 0.5
        self.market: Dict[str, Tuple[float, float, float]] = {}
        self.ctx: Dict[str, Tuple[float, float, float]] = {}

    def _recal(self, p: float) -> float:
        p = _clip(p)
        if len(self.iso_x) >= 2:
            return _clip(_interp(self.iso_x, self.iso_y, p))
        if self.platt:
            a, b = self.platt
            return _clip(_sig(a * _logit(p) + b))
        return p

    def ratio(self, market: str, league: str) -> float:
        if self.n <= 0:
            return 1.0
        k = SHRINK_K
        g_hit, g_imp = self.global_hit, max(1e-6, self.global_imp)
        mh, mn, mi = self.market.get(market, (0.0, 0.0, 0.0))
        hit = (mh + k * g_hit) / (mn + k)
        imp = (mi + k * g_imp) / (mn + k)
        lh, ln, li = self.ctx.get(f"{market}|{league}", (0.0, 0.0, 0.0))
        hit_l = (lh + k * hit) / (ln + k)
        imp_l = (li + k * imp) / (ln + k)
        return hit_l / max(1e-6, imp_l)

    def adjust(self, p: float, market: str, league: str = "", odds: float = 0.0,
               corner_conf: float = 1.0) -> float:
        out = _clip(self._recal(p) * self.ratio(market, league or ""))
        conf = min(1.0, max(0.0, corner_conf))
        if conf < 0.999:
            out = 0.5 + (out - 0.5) * (0.45 + 0.55 * conf)
        return _clip(out)


def _interp(xs: Sequence[float], ys: Sequence[float], x: float) -> float:
    if x <= xs[0]:
        return ys[0]
    if x >= xs[-1]:
        return ys[-1]
    for i in range(1, len(xs)):
        if x <= xs[i]:
            w = (x - xs[i - 1]) / max(1e-9, xs[i] - xs[i - 1])
            return ys[i - 1] * (1 - w) + ys[i] * w
    return ys[-1]


def _isotonic(ps: Sequence[float], ys: Sequence[float]) -> Tuple[List[float], List[float]]:
    order = sorted(range(len(ps)), key=lambda i: ps[i])
    blocks: List[List[float]] = []
    for i in order:
        blocks.append([ys[i], 1.0, ps[i], ps[i]])
        while len(blocks) > 1 and blocks[-2][0] > blocks[-1][0]:
            v2, w2, a2, _ = blocks.pop(-2)
            v1, w1, _, b1 = blocks.pop(-1)
            blocks.append([(v1 * w1 + v2 * w2) / (w1 + w2), w1 + w2, a2, b1])
    return [(b[2] + b[3]) / 2 for b in blocks], [b[0] for b in blocks]


def _platt(ps: Sequence[float], ys: Sequence[float]) -> Tuple[float, float]:
    best, ba, bb = 1e9, 1.0, 0.0
    zs = [_logit(p) for p in ps]
    for a_i in range(8, 29):  # 0.4 .. 1.4
        a = a_i / 20
        for b_i in range(-12, 7):  # -0.6 .. 0.3
            b = b_i / 20
            ll = 0.0
            for z, y in zip(zs, ys):
                ph = _clip(_sig(a * z + b), 1e-4, 1 - 1e-4)
                ll += -(y * math.log(ph) + (1 - y) * math.log(1 - ph))
            if ll < best:
                best, ba, bb = ll, a, b
    return ba, bb


def fit_rows(rows: Iterable[Dict[str, Any]]) -> Calibrator:
    """rows: p, y (0/1), odds, market, league (optional)."""
    cal = Calibrator()
    ps: List[float] = []
    ys: List[float] = []
    mkt: Dict[str, List[float]] = defaultdict(lambda: [0.0, 0.0, 0.0])  # hits, n, imp
    ctx: Dict[str, List[float]] = defaultdict(lambda: [0.0, 0.0, 0.0])
    g_hit = g_imp = g_n = 0.0
    for r in rows:
        try:
            p = float(r["p"])
            odds = float(r["odds"])
            y = 1.0 if r.get("y") in (1, True, "won", "WIN") or r.get("y") == 1 else 0.0
        except (TypeError, ValueError, KeyError):
            continue
        if not (0 < p < 1) or odds <= 1:
            continue
        market = str(r.get("market") or "")
        league = str(r.get("league") or "")
        imp = 1.0 / odds
        ps.append(p)
        ys.append(y)
        g_hit += y
        g_imp += imp
        g_n += 1
        for bucket, key in ((mkt, market), (ctx, f"{market}|{league}")):
            bucket[key][0] += y
            bucket[key][1] += 1
            bucket[key][2] += imp
    cal.n = int(g_n)
    if g_n:
        cal.global_hit = g_hit / g_n
        cal.global_imp = g_imp / g_n
    cal.market = {k: (v[0], v[1], v[2]) for k, v in mkt.items()}
    cal.ctx = {k: (v[0], v[1], v[2]) for k, v in ctx.items()}
    if len(ps) >= MIN_ISO:
        cal.iso_x, cal.iso_y = _isotonic(ps, ys)
    elif len(ps) >= MIN_PLATT:
        cal.platt = _platt(ps, ys)
    return cal


def fit_from_connection(conn: sqlite3.Connection) -> Calibrator:
    """Settled robot predictions plus Supersocial selections, when those tables exist."""
    rows: List[Dict[str, Any]] = []
    try:
        q = conn.execute(
            """SELECT p.p_calibrated AS p, p.result AS y, p.odds_shown AS odds, p.market, p.selection, p.line,
                      COALESCE(l.name, '') AS league
               FROM prediction p JOIN match m ON m.id = p.match_id
               LEFT JOIN league l ON l.id = m.league_id
               WHERE p.result IN ('won','lost') AND p.p_calibrated IS NOT NULL AND p.odds_shown > 1"""
        )
        for r in q:
            rows.append({"p": r[0], "y": 1 if r[1] == "won" else 0, "odds": r[2],
                         "market": market_id(r[3], r[4], r[5] or 0.0), "league": r[6] or ""})
    except sqlite3.Error:
        pass
    try:
        q = conn.execute(
            """SELECT t.p, t.result, t.odds, t.mkey, COALESCE(l.name, '')
               FROM ss_track t LEFT JOIN match m ON m.id = t.match_id
               LEFT JOIN league l ON l.id = m.league_id
               WHERE t.result IN ('won','lost') AND t.p IS NOT NULL AND t.odds > 1"""
        )
        for r in q:
            rows.append({"p": r[0], "y": 1 if r[1] == "won" else 0, "odds": r[2], "market": r[3], "league": r[4] or ""})
    except sqlite3.Error:
        pass
    cal = fit_rows(rows)
    use_calibrator(cal)
    return cal


def probability_for_leg(c: Any) -> float:
    """Ticket-leg probability. Uses the stored per-match p_adj, else the fitted calibrator, else the existing blend."""
    extra = getattr(c, "extra", None) or {}
    if isinstance(c, dict) and c.get("p_adj") is not None:
        return _clip(float(c["p_adj"]))
    if extra.get("p_adj") is not None:
        return _clip(float(extra["p_adj"]))
    cal = active()
    if cal is not None and cal.n:
        if isinstance(c, dict):
            return cal.adjust(float(c.get("p") or 0.5), str(c.get("key") or c.get("market") or ""),
                              str(c.get("league") or c.get("league_id") or ""), float(c.get("odds") or 0),
                              corner_conf=float(c.get("corner_conf") or 1))
        return cal.adjust(float(c.p), market_id(c.market, c.selection, c.line or 0.0),
                          str(getattr(c, "league", None) or getattr(c, "league_id", "") or ""), float(c.odds),
                          corner_conf=float(extra.get("corner_conf") or 1))
    if isinstance(c, dict):
        return _clip(float(c.get("p") or 0.5))
    return _clip(float(c.p_adj))


def _pub(row: Dict[str, Any]) -> Dict[str, Any]:
    return {k: row[k] for k in ("market", "selection", "line", "label", "odds", "p", "p_adj", "p_implied", "ev", "reason")}


def select_fixture(offers: Sequence[Dict[str, Any]], cal: Optional[Calibrator] = None) -> Dict[str, Any]:
    """Best positive-EV market, the safest market, or an explicit no-bet."""
    cal = cal or Calibrator()
    scored: List[Dict[str, Any]] = []
    for o in offers:
        odds = o.get("odds")
        p = o.get("p")
        if odds is None or p is None or not (odds > 1) or not (0 < p < 1):
            continue
        market = str(o.get("market") or "")
        league = str(o.get("league") or "")
        conf = float(o.get("corner_conf") or 1)
        p_adj = cal.adjust(float(p), market, league, float(odds), corner_conf=conf)
        implied = float(o["p_market"]) if o.get("p_market") else 1.0 / float(odds)
        ev = p_adj * float(odds) - 1
        ratio = cal.ratio(market, league)
        bits = []
        if cal.n and ratio < 0.97:
            bits.append(f"istoric sub cotă ({ratio - 1:+.0%})")
        elif cal.n and ratio > 1.03:
            bits.append(f"istoric peste cotă ({ratio - 1:+.0%})")
        if conf < 0.85:
            bits.append("ligă cu puține cornere, încredere redusă")
        why = "; ".join(bits)
        scored.append({
            "market": market, "selection": str(o.get("selection") or market), "line": o.get("line"),
            "label": str(o.get("label") or market), "odds": round(float(odds), 3),
            "p": round(float(p), 4), "p_adj": round(p_adj, 4), "p_implied": round(implied, 4),
            "ev": ev, "reason": why, "_id": id(o),
        })
    if not scored:
        return {"decision": "no_bet", "best_value": None, "safest": None,
                "reason": "Niciun pariu: nicio piață nu are și cotă, și probabilitate."}
    safest = max(scored, key=lambda r: (r["p_adj"], r["ev"]))
    best = max(scored, key=lambda r: (r["ev"], r["p_adj"]))
    safe_txt = (f"Cea mai sigură: {safest['label']} · p ajustat {safest['p_adj']:.0%} "
                f"(cota implică {safest['p_implied']:.0%}) · EV {safest['ev']:+.1%}.")
    if best["ev"] <= EV_MARGIN:
        return {"decision": "no_bet", "best_value": None, "safest": _pub(safest),
                "reason": (f"Niciun pariu. {best['label']} are cel mai bun EV ({best['ev']:+.1%}) după calibrare, "
                           f"sub pragul de {EV_MARGIN:.0%}. {safe_txt}")}
    why = f" {best['reason']}." if best["reason"] else ""
    return {"decision": "value", "best_value": _pub(best), "safest": _pub(safest),
            "reason": (f"Valoare: {best['label']} · p ajustat {best['p_adj']:.0%} vs cotă {best['p_implied']:.0%} "
                       f"· EV {best['ev']:+.1%}.{why} {safe_txt}")}


def _offer_from_cand(c: Any) -> Dict[str, Any]:
    extra = getattr(c, "extra", None) or {}
    return {
        "market": market_id(c.market, c.selection, c.line or 0.0),
        "selection": c.selection, "line": c.line, "label": getattr(c, "label", None) or c.selection,
        "p": c.p, "odds": c.odds, "p_market": c.p_market,
        "league": str(getattr(c, "league", None) or getattr(c, "league_id", "") or ""),
        "corner_conf": float(extra.get("corner_conf") or 1),
    }


def choose_pool(pool: Sequence[Any], cal: Optional[Calibrator] = None) -> List[Any]:
    """One leg per match: the best positive-EV market. Matches with no such market are left out."""
    cal = cal or active() or Calibrator()
    by: Dict[Any, List[Any]] = defaultdict(list)
    for c in pool:
        by[c.match_id].append(c)
    out: List[Any] = []
    for xs in by.values():
        offers = [_offer_from_cand(c) for c in xs]
        pick = select_fixture(offers, cal)
        if pick["decision"] != "value" or not pick["best_value"]:
            continue
        bv = pick["best_value"]
        chosen = next((c for c, o in zip(xs, offers) if o["market"] == bv["market"] and o["selection"] == bv["selection"]), None)
        if chosen is None:
            continue
        extra = dict(getattr(chosen, "extra", None) or {})
        extra["p_adj"] = bv["p_adj"]
        extra["ev_adj"] = bv["ev"]
        extra["match_pick"] = pick["reason"]
        chosen.extra = extra
        out.append(chosen)
    return out


def annotate_ss(cands: Sequence[Dict[str, Any]], cal: Optional[Calibrator] = None) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Stamp p_adj and mark the positive-EV market on each match. Other markets stay available to single-market recipes."""
    cal = cal or active() or Calibrator()
    by: Dict[Any, List[Dict[str, Any]]] = defaultdict(list)
    for c in cands:
        by[c.get("match_id")].append(c)
    kept: List[Dict[str, Any]] = []
    summary: List[Dict[str, Any]] = []
    for mid, xs in by.items():
        offers = []
        for c in xs:
            if not c.get("odds") or not c.get("p"):
                continue
            offers.append({
                "market": c["key"], "selection": c["key"], "label": c.get("label") or c["key"],
                "p": c["p"], "odds": c["odds"], "league": str(c.get("league") or c.get("league_id") or ""),
                "corner_conf": c.get("corner_conf") or 1, "p_market": None,
            })
        pick = select_fixture(offers, cal)
        summary.append({"match_id": mid, "decision": pick["decision"], "reason": pick["reason"]})
        bv = pick.get("best_value")
        calibrated = bool(cal.n)
        for c in xs:
            if not c.get("odds") or not c.get("p"):
                kept.append(c)
                continue
            # stamp the adjusted probability; only the winning market is eligible for mixed tickets
            same = bv and c["key"] == bv["market"]
            if same:
                c["p_adj"] = bv["p_adj"]
                c["ev_adj"] = bv["ev"]
                c["chosen"] = True
                c["calibrated"] = calibrated
            elif calibrated:
                c["p_adj"] = cal.adjust(float(c["p"]), c["key"], str(c.get("league") or c.get("league_id") or ""), float(c["odds"]),
                                        corner_conf=float(c.get("corner_conf") or 1))
                c["calibrated"] = True
            kept.append(c)
    return kept, summary


def p_goals_exact_band(lh: float, la: float, lo: int, hi: int) -> float:
    """P(lo ≤ home+away ≤ hi) from two independent Poisson means."""
    t = max(0.05, lh + la)
    s = 0.0
    term = math.exp(-t)
    for k in range(0, hi + 1):
        if k >= lo:
            s += term
        term *= t / (k + 1)
    return max(0.0, min(0.995, s))


# ---------------------------------------------------------------- backtest
def _band(odds: float) -> str:
    if odds < 1.5:
        return "<1.5"
    if odds < 2:
        return "1.5–2"
    if odds < 3:
        return "2–3"
    if odds < 5:
        return "3–5"
    return "5+"


def _ece(ps: Sequence[float], ys: Sequence[float], bins: int = 8) -> Optional[float]:
    if not ps:
        return None
    tot = 0.0
    for i in range(bins):
        lo, hi = i / bins, (i + 1) / bins
        chunk = [(p, y) for p, y in zip(ps, ys) if (lo <= p < hi) or (hi == 1 and p == 1)]
        if chunk:
            tot += len(chunk) / len(ps) * abs(sum(p for p, _ in chunk) / len(chunk) - sum(y for _, y in chunk) / len(chunk))
    return tot


def _flat(rows: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    if not rows:
        return {"n": 0, "hit": None, "implied": None, "roi": None, "ece": None}
    y = [1.0 if r["y"] else 0.0 for r in rows]
    imp = [1 / r["odds"] for r in rows]
    profit = [(r["odds"] - 1) if r["y"] else -1.0 for r in rows]
    return {"n": len(rows), "hit": round(sum(y) / len(y), 4), "implied": round(sum(imp) / len(imp), 4),
            "roi": round(sum(profit) / len(profit), 4), "ece": None if _ece([r["p_used"] for r in rows], y) is None else round(_ece([r["p_used"] for r in rows], y) or 0, 4)}


def _by_band(rows: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    groups: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for r in rows:
        groups[_band(r["odds"])].append(r)
    return [{"band": b, **_flat(groups[b])} for b in ("<1.5", "1.5–2", "2–3", "3–5", "5+") if groups.get(b)]


def _tickets(rows: Sequence[Dict[str, Any]], legs: int = 2) -> List[Dict[str, Any]]:
    """Non-overlapping accas in time order, flat 1u, grouped by combined odds."""
    ordered = sorted(rows, key=lambda r: r.get("ts") or "")
    made = []
    for i in range(0, len(ordered) - legs + 1, legs):
        chunk = ordered[i:i + legs]
        if len({r["event"] for r in chunk}) < legs:
            continue
        odds = 1.0
        won = True
        for r in chunk:
            odds *= r["odds"]
            won = won and bool(r["y"])
        made.append({"odds": odds, "y": won, "p_used": 0.5, "ts": chunk[0].get("ts")})
    return _by_band(made)


def backtest_rows(rows: Sequence[Dict[str, Any]], split: float = 0.7) -> Dict[str, Any]:
    """Time-ordered split: fit on the earlier part, score the later part.

    Old: stake the historically published pick at its raw model probability.
    New: recalibrate, then stake that pick only when adjusted EV clears the margin.
    Where an event has more than one settled market, the new rule may switch market.
    """
    ordered = sorted(rows, key=lambda r: str(r.get("ts") or ""))
    if len(ordered) < 40:
        return {"n": len(ordered), "note": "Prea puține rânduri decontate pentru un split.", "old": {}, "new": {}}
    cut = max(20, min(len(ordered) - 15, int(len(ordered) * split)))
    train, test = ordered[:cut], ordered[cut:]
    cal = fit_rows(train)
    by_event: Dict[Any, List[Dict[str, Any]]] = defaultdict(list)
    for r in test:
        by_event[r.get("event")].append(r)
    old_bets: List[Dict[str, Any]] = []
    new_bets: List[Dict[str, Any]] = []
    switched = 0
    for ev, xs in by_event.items():
        for r in xs:
            old_bets.append({**r, "p_used": float(r["p"]), "event": ev})
        offers = [{"market": r["market"], "selection": r["market"], "label": r["market"], "p": r["p"],
                   "odds": r["odds"], "league": r.get("league") or ""} for r in xs]
        pick = select_fixture(offers, cal)
        if pick["decision"] != "value" or not pick["best_value"]:
            continue
        chosen = next(r for r in xs if r["market"] == pick["best_value"]["market"])
        if chosen is not xs[0] and len(xs) > 1:
            switched += 1
        new_bets.append({**chosen, "p_used": pick["best_value"]["p_adj"], "event": ev})
    return {
        "n_train": len(train), "n_test_rows": len(test), "n_test_events": len(by_event),
        "switched_market": switched, "margin": EV_MARGIN,
        "old": {"singles": _flat([{**r, "p_used": r["p_used"]} for r in old_bets]), "by_odds": _by_band(old_bets),
                "tickets": _tickets(old_bets)},
        "new": {"singles": _flat(new_bets), "by_odds": _by_band(new_bets), "tickets": _tickets(new_bets)},
        "note": ("Majoritatea meciurilor din jurnal au o singură piață decontată, deci regula nouă mai ales "
                 "refuză selecțiile cu EV ajustat ≤ 0. Schimbarea de piață e posibilă doar unde există alternative."),
    }


def load_selection_journal(path: str) -> List[Dict[str, Any]]:
    import json
    from pathlib import Path

    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    names = {
        "homeWin": "1x2:HOME", "awayWin": "1x2:AWAY", "draw": "1x2:DRAW",
        "over15": "over_under_1.5:OVER", "over25": "over_under_2.5:OVER", "over35": "over_under_3.5:OVER",
        "under15": "over_under_1.5:UNDER", "under25": "over_under_2.5:UNDER", "under35": "over_under_3.5:UNDER",
        "btts": "btts:YES", "bttsNo": "btts:NO",
    }
    out = []
    for r in raw.get("results") or []:
        if r.get("status") != "settled" or r.get("result") not in ("WIN", "LOSS"):
            continue
        if not r.get("odds") or not r.get("model_probability"):
            continue
        out.append({
            "event": r.get("event_id"), "ts": r.get("event_date") or "",
            "market": names.get(r.get("market") or "", r.get("market") or ""),
            "league": r.get("league") or "", "p": r["model_probability"], "odds": r["odds"],
            "y": 1 if r["result"] == "WIN" else 0,
        })
    return out
