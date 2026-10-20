"""Piramide riscante ~5 și ~10: mai multe selecții cu cote mici (~5: 3–5 la 1.20–1.90; ~10: 4–6 la 1.20–2.10),
nu 2 cote mari riscante (cererea lui Alin, 21.10.2026). EV realist ≥ 0, doar piețe sănătoase.

Fără oprire automată după pierderi. În locul ei, reorganizare adaptivă după fiecare pierdere:
- piețele și ligile sunt reclasate după calibrarea și ROI-ul recent (ultimele 30 de zile decontate);
- se schimbă amestecul de selecții (familia de piață a biletului pierdut e evitată la pasul următor);
- ținta de cotă se mută în interiorul benzii (spre capătul de jos după pierderi, spre cel de sus după câștiguri);
- seria se reia de la treapta 1 cu miza mică fixă din bugetul săptămânal (1–2 lei). Niciodată martingale:
  miza de start nu crește după pierderi.
"""

from __future__ import annotations

import itertools
import math
import sqlite3
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from betpredict.builder import pyramid as P
from betpredict.builder.pool import Cand

BASE = {"start_bank": 2.0, "profit_withdraw_pct": 0.0, "withdraw_steps": [], "withdraw_pct": 0.0,
        "target_multiple": 10**9, "target_withdraw_pct": 0.0, "pause_after_losses": 0,
        "min_legs": 2, "max_legs": 4, "min_ev": 0.0, "leg_odds": [1.25, 4.5], "leg_min_p": 0.25}
RULES_R5: Dict[str, Any] = {**BASE, "target_odds": 5.0, "band": [4.0, 6.5], "max_steps": 5, "suggest_at": 2, "variant": "pr5", "alt_variant": "pr5_alt",
                            "min_legs": 3, "max_legs": 5, "leg_odds": [1.20, 1.90], "leg_min_p": 0.55}
RULES_R10: Dict[str, Any] = {**BASE, "target_odds": 10.0, "band": [8.0, 13.0], "max_steps": 4, "suggest_at": 2, "variant": "pr10", "alt_variant": "pr10_alt",
                             "min_legs": 4, "max_legs": 6, "leg_odds": [1.20, 2.10], "leg_min_p": 0.50}
KEY_R5, KEY_R10 = "pyramidr5.day.", "pyramidr10.day."
SCORE_DAYS, SCORE_MIN_N = 30, 30


def family(market: str) -> str:
    return (market or "").split("|")[0]


def fam(c: Cand) -> str:
    """Familia selecției: piața robotului (over_under, btts...) sau familia Stil (cornere, cartonașe, reprize...)."""
    if c.market == "ss":
        from betpredict.experimental.supersocial import family as ss_family

        return "ss:" + ss_family(c.selection)
    return family(c.market)


def offer_pool(conn: sqlite3.Connection, day: date, now: Optional[datetime]) -> List[Cand]:
    """Toată oferta Superbet a zilei (piețele Stil: cornere, cartonașe, reprize, goluri pe echipă), cu probabilitatea modelului.
    Doar prețuri reale Superbet (fără Bet Builder estimat). Decontare prin settle_legs (market 'ss|0')."""
    from betpredict.experimental import supersocial as SS

    now = now or datetime.now(timezone.utc)
    out: List[Cand] = []
    try:
        cs = SS.candidates(conn, now, horizon_h=30, band=(1.2, 5.0))
    except Exception:  # noqa: BLE001
        return out
    for c in cs:
        if not c.get("odds") or c.get("est") or not c.get("p") or (c["kickoff_utc"] or "")[:10] > (day + timedelta(days=1)).isoformat():
            continue
        out.append(Cand(None, c["match_id"], c["league_id"], None, c["kickoff_utc"], c["home"], c["away"], "ss", 0.0, c["key"],
                        float(c["odds"]), float(c["p"]), float(c["p"]) * float(c["odds"]) - 1, "B", 60, odds_source="superbet"))
    return out


def recent_scores(conn: sqlite3.Connection, before: str, days: int = SCORE_DAYS) -> Dict[str, Dict[str, float]]:
    """Scor = ROI recent (micșorat spre −5%) + abaterea de calibrare (realizat − p). Pe familie de piață și pe ligă."""
    lo = (datetime.fromisoformat(before[:10]) - timedelta(days=days)).date().isoformat()
    rows = conn.execute(
        """SELECT p.market, m.league_id, p.p_calibrated, p.odds_shown, p.result FROM prediction p JOIN match m ON m.id=p.match_id
           WHERE p.result IN ('won','lost') AND p.odds_shown > 1 AND p.p_calibrated IS NOT NULL AND m.kickoff_utc >= ? AND m.kickoff_utc < ?""",
        (lo, before)).fetchall()
    out: Dict[str, Dict[str, float]] = {"market": {}, "league": {}}
    agg: Dict[Tuple[str, Any], List[float]] = {}
    for mk, lg, p, o, r in rows:
        w = 1.0 if r == "won" else 0.0
        for key in (("market", family(mk)), ("league", lg)):
            a = agg.setdefault(key, [0, 0.0, 0.0, 0.0])
            a[0] += 1; a[1] += w; a[2] += p; a[3] += (o - 1) if w else -1
    for (kind, k), (n, w, p, pl) in agg.items():
        if n >= SCORE_MIN_N:
            out[kind][str(k)] = round((pl + 30 * -0.05) / (n + 30) + (w - p) / n, 4)
    return out


def adapt(conn: sqlite3.Connection, rules: Dict[str, Any], day: date) -> Dict[str, Any]:
    """Starea adaptivă din ultimele bilete decontate ale pistei: țintă în bandă și familia de evitat."""
    last = conn.execute("SELECT id, status FROM ticket WHERE kind='pyramid' AND variant=? AND status IN ('won','lost') AND day < ? "
                        "ORDER BY day DESC, id DESC LIMIT 4", (rules["variant"], day.isoformat())).fetchall()
    losses = 0
    for r in last:
        if r[1] != "lost":
            break
        losses += 1
    lo, hi = rules["band"]
    t = rules["target_odds"]
    if losses:
        t = max(lo, t * (0.9 ** min(losses, 3)))        # după pierderi: ținta coboară în bandă
    elif last and last[0][1] == "won":
        t = min(hi, t * 1.1)
    avoid: List[str] = []
    if losses and last:
        from betpredict.experimental.supersocial import family as ss_family

        avoid = sorted({("ss:" + ss_family(x[1])) if x[0] == "ss|0" else family(x[0])
                        for x in conn.execute("SELECT market, selection FROM ticket_leg WHERE ticket_id=?", (last[0][0],))})
    return {"losses": losses, "target": round(t, 2), "band": [round(max(lo, t * 0.85), 2), round(min(hi, t * 1.2), 2)], "avoid": avoid}


TIERS = (("ev", "EV realist ≥ 0"), ("ev3", "cel mai bun EV peste −3%"), ("p", "cea mai mare șansă calibrată"))


def pick(pool: List[Cand], rules: Dict[str, Any], scores: Dict[str, Dict[str, float]], st: Dict[str, Any],
         taken: Optional[set] = None) -> Dict[str, Any]:
    """Mereu cel mai bun bilet disponibil, cu treapta folosită: EV ≥ 0 → cel mai bun EV peste −3% → cea mai mare șansă."""
    lo, hi = st["band"]
    llo, lhi = rules["leg_odds"]
    paused = set(st.get("paused") or [])

    def score(c: Cand) -> float:  # calibrare + ROI recent (doar pentru clasare; nu mai taie piețe întregi)
        return scores["market"].get(fam(c), scores["market"].get(family(c.market), 0.0)) + scores["league"].get(str(c.league_id), 0.0)

    def ok(c: Cand) -> bool:
        if not (c.playable and llo <= c.odds <= lhi and c.p_honest >= rules["leg_min_p"]):
            return False
        if fam(c) in st["avoid"] or c.selection in paused or f"{c.market}|{c.line:g}" in paused:
            return False
        return True

    per: Dict[int, List[Cand]] = {}
    for c in pool:
        if ok(c):
            per.setdefault(c.match_id, []).append(c)
    # cele mai bune 2 selecții pe meci (EV realist + scor), apoi primele 18 meciuri
    best = []
    for cs in per.values():
        cs.sort(key=lambda c: c.ev_honest + 0.5 * score(c), reverse=True)
        best.extend(cs[:2])
    best.sort(key=lambda c: c.ev_honest + 0.5 * score(c), reverse=True)
    cands = best[:24]
    combos = []
    for k in range(rules["min_legs"], rules["max_legs"] + 1):
        for cb in itertools.combinations(cands, k):
            if len({c.match_id for c in cb}) < k or not P.one_league_each(cb):
                continue
            o = math.prod(c.odds for c in cb)
            if not (lo <= o <= hi):
                continue
            p = math.prod(c.p_honest for c in cb)
            ev = p * o - 1
            shared = sum((c.match_id, c.selection) in (taken or set()) for c in cb)
            # fără penalizare pentru selecții în plus: preferăm mai multe cote mici decât una mare
            rank = ev + 0.5 * sum(score(c) for c in cb) / k - 0.05 * abs(math.log(o / st["target"])) - 0.03 * shared
            combos.append((list(cb), p, ev, rank, shared))
    name = f"~{rules['target_odds']:g}"
    if not combos:
        return {"status": "no_bet", "main": None, "alternatives": [], "tier": None, "pool": len(cands),
                "reason": f"Azi fără Piramida {name}: nu sunt {rules['min_legs']}–{rules['max_legs']} meciuri diferite (cotă {llo:g}–{lhi:g} pe selecție) care să dea cota {lo:g}–{hi:g}."}
    if taken:  # cel mult o selecție comună cu cealaltă piramidă riscantă, când există variante
        few = [x for x in combos if x[4] <= 1]
        combos = few or combos
    chosen = None
    for tier, _ in TIERS:
        if tier == "ev":
            xs = [x for x in combos if x[2] >= rules["min_ev"]]
        elif tier == "ev3":
            xs = [x for x in combos if x[2] >= -0.03]
        else:
            xs = sorted(combos, key=lambda x: x[1], reverse=True)[:1]
        if xs:
            chosen = (tier, max(xs, key=lambda x: x[3]) if tier != "p" else xs[0])
            break
    tier, (main, p_main, ev, _, _sh) = chosen
    o = math.prod(c.odds for c in main)
    tname = dict(TIERS)[tier]
    why = f"{len(main)} selecții, cotă {o:.2f}, șansă realistă {p_main:.0%}, EV {ev:+.1%} · ales după: {tname}"
    if st["losses"]:
        why += f" · reorganizată după {st['losses']} {'pierdere' if st['losses'] == 1 else 'pierderi'}: țintă {st['target']:g}" + (f", fără {', '.join(st['avoid'])}" if st["avoid"] else "")
    return {"status": "pick", "main": (main, p_main), "alternatives": [], "reason": why, "tier": tier, "pool": len(cands)}


def _paused(conn: sqlite3.Connection) -> List[str]:
    try:
        return [r[0] for r in conn.execute("SELECT mkey FROM market_state WHERE status='paused'")]
    except sqlite3.Error:
        return []


def _taken(conn: sqlite3.Connection, day: date, other_variant: str) -> set:
    return {(r[0], r[1]) for r in conn.execute(
        "SELECT tl.match_id, tl.selection FROM ticket_leg tl JOIN ticket t ON t.id=tl.ticket_id WHERE t.kind='pyramid' AND t.variant=? AND t.day=? "
        "AND t.status!='replaced'", (other_variant, day.isoformat()))}


def build_day(conn: sqlite3.Connection, day: date, now: Optional[datetime], rules: Dict[str, Any], prefix: str, key: str) -> Dict[str, Any]:
    st = {**adapt(conn, rules, day), "paused": _paused(conn)}
    scores = recent_scores(conn, (now or datetime.now(timezone.utc)).strftime("%Y-%m-%dT%H:%M:%SZ"))

    info: Dict[str, Any] = {}

    def picker(pool, r):
        extra = offer_pool(conn, day, now)
        other = "pr5" if r["variant"] == "pr10" else "pr10"
        res = pick(pool + extra, r, scores, st, _taken(conn, day, other))
        info.update({"pool_robot": len(pool), "pool_offer": len(extra), "tier": res.get("tier")})
        return res
    out = P._build_track_day(conn, day, now, False, prefix, key, rules, picker, rules["variant"])
    out["adapt"] = {k: st[k] for k in ("losses", "target", "band", "avoid")}
    out.update(info)
    return out


def build_r5_day(conn, day, now=None):
    return build_day(conn, day, now, RULES_R5, "pyramidr5", KEY_R5)


def build_r10_day(conn, day, now=None):
    return build_day(conn, day, now, RULES_R10, "pyramidr10", KEY_R10)
