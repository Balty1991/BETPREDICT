"""Piramide ~5 și ~10. Reguli din 25.10.2026 (aprobate de Alin, după 1/8 și 0/8 cu 5–12 selecții la 1.15–1.40):
2–4 selecții, cota minimă 1.40 pe selecție, EV realist ≥ −3% (întâi EV ≥ 0, apoi cel mai bun peste −3%; altfel nu se
publică nimic), fără meciuri cu start între 00:00 și 07:00 ora României. Multe cote mici înmulțeau marja casei
(Superbet ia ~4% pe fiecare selecție), iar meciurile de noapte (America de Sud/Asia) aveau cele mai slabe rezultate.

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
                            "min_legs": 2, "max_legs": 4, "leg_odds": [1.40, 4.5], "min_ev": 0.0, "floor_ev": -0.03, "no_night": True}
RULES_R10: Dict[str, Any] = {**BASE, "target_odds": 10.0, "band": [8.0, 13.0], "max_steps": 4, "suggest_at": 2, "variant": "pr10", "alt_variant": "pr10_alt",
                             "min_legs": 2, "max_legs": 4, "leg_odds": [1.40, 4.5], "min_ev": 0.0, "floor_ev": -0.03, "no_night": True}
KEY_R5, KEY_R10 = "pyramidr5.day.", "pyramidr10.day."
SCORE_DAYS, SCORE_MIN_N = 30, 30
NIGHT_HOURS = range(0, 7)  # 00:00–06:59 ora României: fără selecții (25.10)


def night_kickoff(kickoff_utc: Optional[str]) -> bool:
    """Start între 00:00 și 07:00 ora României (Europe/Bucharest, cu ora de vară/iarnă)."""
    if not kickoff_utc:
        return False
    try:
        from zoneinfo import ZoneInfo

        k = datetime.fromisoformat(kickoff_utc.replace("Z", "+00:00"))
        if k.tzinfo is None:
            k = k.replace(tzinfo=timezone.utc)
        return k.astimezone(ZoneInfo("Europe/Bucharest")).hour in NIGHT_HOURS
    except (ValueError, KeyError):
        return False


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


def pick_greedy(pool: List[Cand], rules: Dict[str, Any], st: Dict[str, Any], taken: Optional[set] = None) -> Dict[str, Any]:
    """Acumulare: cele mai sigure selecții (cota 1.15–1.40) până când cota totală intră în bandă."""
    lo, hi = st["band"]
    llo, lhi = rules["leg_odds"]
    llo = max(llo, round(lo ** (1 / rules["max_legs"]), 3))  # cu cel mult max_legs selecții trebuie să ajungem la bandă
    paused = set(st.get("paused") or [])
    rel = st.get("rel") or {}
    best: Dict[int, Cand] = {}
    for c in pool:
        if not (c.playable and llo <= c.odds <= lhi and c.p_honest >= rules["leg_min_p"]):
            continue
        if fam(c) in st["avoid"] or c.selection in paused or f"{c.market}|{c.line:g}" in paused or getattr(c, "price_suspect", False):
            continue
        if taken and (c.match_id, c.selection) in taken:
            continue
        q = P.q_leg(c, rel)
        if c.match_id not in best or q > P.q_leg(best[c.match_id], rel):
            best[c.match_id] = c
    # ideal 1.20–1.30: în afara intervalului se pierde puțin din prioritate
    order = sorted(best.values(), key=lambda c: P.q_leg(c, rel) - (0.0 if 1.20 <= c.odds <= 1.30 else 0.01), reverse=True)
    legs: List[Cand] = []
    leagues: set = set()
    for c in order:
        if c.league_id is not None and c.league_id in leagues:
            continue
        o = math.prod(x.odds for x in legs) * c.odds
        if o > hi:
            continue
        legs.append(c)
        if c.league_id is not None:
            leagues.add(c.league_id)
        if o >= lo and len(legs) >= rules["min_legs"]:
            break
        if len(legs) >= rules["max_legs"]:
            break
    o = math.prod(x.odds for x in legs) if legs else 0
    name = f"~{rules['target_odds']:g}"
    if not legs or not (lo <= o <= hi) or len(legs) < rules["min_legs"]:
        return {"status": "no_bet", "main": None, "alternatives": [], "tier": None, "pool": len(best),
                "reason": f"Azi fără Piramida {name}: nu sunt destule selecții sigure (cota {llo:g}–{lhi:g}, șansă ≥ "
                          f"{rules['leg_min_p']:.0%}) în ligi diferite ca să ajungem la cota {lo:g}–{hi:g}."}
    p = math.prod(P.q_leg(c, rel) for c in legs)
    why = (f"{len(legs)} selecții sigure (cotă medie {o ** (1 / len(legs)):.2f}) acumulate până la cota {o:.2f}, "
           f"șansă {p:.0%}, EV {p * o - 1:+.1%}")
    return {"status": "pick", "main": (legs, p), "alternatives": [], "reason": why, "tier": "acumulare", "pool": len(best)}


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
        if rules.get("no_night") and night_kickoff(c.kickoff_utc):
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
            xs = [x for x in combos if x[2] >= rules.get("floor_ev", -0.03)]
        elif "floor_ev" in rules:  # ~5/~10 (25.10): sub −3% EV nu se publică nimic
            xs = []
        else:
            xs = sorted(combos, key=lambda x: x[1], reverse=True)[:1]
        if xs:
            chosen = (tier, max(xs, key=lambda x: x[3]) if tier != "p" else xs[0])
            break
    if chosen is None:
        return {"status": "no_bet", "main": None, "alternatives": [], "tier": None, "pool": len(cands),
                "reason": f"Azi fără Piramida {name}: nicio combinație de {rules['min_legs']}–{rules['max_legs']} selecții (cotă ≥ {llo:g}) cu EV realist ≥ −3%."}
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
        if r.get("greedy"):
            res = pick_greedy(pool + extra, r, {**st, "rel": P.reliability(conn)}, _taken(conn, day, other))
        else:
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


# ───────────── Piramida 100+ (25.10.2026, pe hârtie) ─────────────
# 5 pași la cota ~2.5 (2.5^5 ≈ 100), reinvestire totală, după pierdere reia cu 2 lei. Selecții DOAR din piesele cu rezultat
# pozitiv la cota Superbet urmărită (11–24.10): H2G13 (gazdele 1-3 goluri, 503 sel., ROI +4.3%), Cartonașe Sub 4.5/5.5
# (356 sel., +6.7%). Fără ligile slabe (calea100.BAD_LEAGUES), fără start 00–07. O selecție pe meci, întâi cotele mici,
# până la ținta 2.5 (max 10 selecții). Backtest walk-forward (reguli fixate pe 11–17.10, test 18–24.10): pas 48% câștigat,
# ROI pas +41% (44 bilete), dar biletele aceleiași zile sunt legate → eșantion real ~14 zile. De aceea: experimental, pe hârtie.
KEYS_100 = frozenset({"H2G13", "YCU45", "YCU55"})
RULES_R100: Dict[str, Any] = {**BASE, "target_odds": 2.5, "band": [2.5, 3.125], "max_steps": 5, "suggest_at": 5, "variant": "pr100",
                              "alt_variant": "pr100_alt", "min_legs": 1, "max_legs": 10, "leg_odds": [1.15, 3.0], "min_ev": -1.0,
                              "no_night": True, "paper": True, "keys": sorted(KEYS_100)}
KEY_R100 = "pyramidr100.day."


def pick_r100(pool: List[Cand], rules: Dict[str, Any] = RULES_R100, bad_leagues: Optional[set] = None) -> Dict[str, Any]:
    """Lacom, ca în backtest: cotele cele mai mici întâi, câte una pe meci, până la ținta de cotă."""
    T, cap = rules["target_odds"], rules["band"][1]
    llo, lhi = rules["leg_odds"]
    best: Dict[int, Cand] = {}
    for c in pool:
        if c.market != "ss" or c.selection not in KEYS_100 or not (llo <= c.odds <= lhi):
            continue
        if rules.get("no_night") and night_kickoff(c.kickoff_utc):
            continue
        if bad_leagues and (c.league or "") in bad_leagues:
            continue
        if c.match_id not in best or c.odds < best[c.match_id].odds:
            best[c.match_id] = c
    legs: List[Cand] = []
    o = 1.0
    for c in sorted(best.values(), key=lambda c: (c.odds, c.kickoff_utc or "")):
        if legs and o * c.odds > cap:
            continue
        legs.append(c); o *= c.odds
        if o >= T or len(legs) >= rules["max_legs"]:
            break
    if not legs or o < T:
        return {"status": "no_bet", "main": None, "alternatives": [], "tier": None, "pool": len(best),
                "reason": f"Azi fără Piramida 100+: nu sunt destule selecții H2G13 / Cartonașe Sub 4.5–5.5 ca să ajungem la cota {T:g}. Pauza nu rupe seria."}
    p = math.prod(c.p for c in legs)
    return {"status": "pick", "main": (legs, p), "alternatives": [], "tier": "p100", "pool": len(best),
            "reason": f"{len(legs)} selecții (H2G13 / Cartonașe Sub), cele mai mici cote, cota {o:.2f} · pe hârtie (experimental)"}


def build_r100_day(conn, day, now=None):
    from betpredict.builder.calea100 import BAD_LEAGUES

    names = {r[0]: r[1] for r in conn.execute("SELECT id, name FROM league")}

    def picker(_pool, r):
        extra = offer_pool(conn, day, now)
        for c in extra:
            c.league = c.league or names.get(c.league_id)
        return pick_r100(extra, r, set(BAD_LEAGUES))
    return P._build_track_day(conn, day, now, False, "pyramidr100", KEY_R100, RULES_R100, picker, "pr100")
