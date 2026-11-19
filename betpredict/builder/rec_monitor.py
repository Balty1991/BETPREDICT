"""Lista recomandată se verifică singură: pentru fiecare piață recomandată, cum a ieșit pe Superbet în ultimele zile
(cotele de închidere salvate în ``sb_offer_close`` și rezultatele meciurilor). O piață care pierde clar pe destule selecții
iese automat de pe bilete până își revine; cifrele apar și în Predicții → Top."""

from __future__ import annotations

import math
import re
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from betpredict.timeutil import canon_utc

DAYS = 30
MIN_N = 150          # sub atât nu decidem nimic
DROP_ROI = -0.06     # sub −6% pe cel puțin MIN_N selecții piața iese de pe bilete
COMBO = "COMBO"      # Peste 0.5 goluri + peste 7.5 cornere
# Revenire automată: o piață scoasă intră înapoi dacă în ultimele RECENT_DAYS zile a ieșit cel puțin pe zero
# (ROI ≥ REENABLE_ROI) pe destule selecții; altfel revine singură când ROI-ul pe 30 de zile urcă peste DROP_ROI.
RECENT_DAYS = 10
REENABLE_N = 50
REENABLE_ROI = 0.0
NIGHT_HOURS_RO = (0, 10)  # meciuri de noapte (ora României): 00–10
Z95 = 1.959964
PRIOR_N = 60              # selecții „virtuale” la break-even (ROI 0) în estimarea Bayes: micșorare pe eșantioane mici


def _ou(text: str, total: int) -> Optional[bool]:
    m = re.fullmatch(r"(Peste|Sub) (\d+\.5)", text.strip())
    if not m:
        return None
    return total > float(m.group(2)) if m.group(1) == "Peste" else total < float(m.group(2))


def settle(mn: str, oc: str, fh: int, fa: int, hh: Optional[int], ha: Optional[int],
           ch: Optional[int] = None, ca: Optional[int] = None) -> Optional[bool]:
    """Rezultatul unei selecții recomandate din scor (final, pauză) și cornere; None dacă nu se poate decide."""
    if mn == "Final":
        r = "1" if fh > fa else "X" if fh == fa else "2"
        return r == oc if oc in ("1", "X", "2") else None
    if mn == "Ambele echipe marchează (GG)":
        return (fh > 0 and fa > 0) if oc == "Da" else (not (fh > 0 and fa > 0)) if oc == "Nu" else None
    if mn == "Total goluri":
        return _ou(oc, fh + fa)
    if hh is None or ha is None:
        return None
    if mn == "Prima repriză - Total goluri":
        return _ou(oc, hh + ha)
    if mn == "A doua repriză - Interval goluri":
        m = re.fullmatch(r"(\d+)-(\d+)", oc.strip())
        h2 = fh + fa - hh - ha
        return int(m.group(1)) <= h2 <= int(m.group(2)) if m else None
    if re.sub(r"\s+", " ", mn.lower().replace(",", ".")).startswith("peste 0.5 goluri; peste 7.5 cornere"):
        if ch is None or ca is None:
            return None
        return fh + fa > 0 and ch + ca > 7.5
    return None


def wilson(k: int, n: int, z: float = Z95) -> Tuple[Optional[float], Optional[float]]:
    """Intervalul Wilson (95%) pentru rata de intrare k/n."""
    if n <= 0:
        return None, None
    p = k / n
    den = 1 + z * z / n
    mid = (p + z * z / (2 * n)) / den
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return max(0.0, mid - half), min(1.0, mid + half)


def _bucket() -> Dict[str, Any]:
    return {"n": 0, "won": 0, "ret": 0.0, "inv": 0.0}


def _add(b: Dict[str, Any], price: float, won: bool) -> None:
    b["n"] += 1
    b["won"] += int(won)
    b["ret"] += price if won else 0.0
    b["inv"] += 1.0 / price  # șansa „fără marjă zero”: suma 1/cotă = câte ar trebui să intre ca să fie pe zero


def summarize(b: Dict[str, Any]) -> Dict[str, Any]:
    """n, intrate, ROI, interval Wilson pe rata de intrare transformat în ROI, și o estimare Bayes micșorată spre zero.

    ROI-ul unei selecții = intrare × cotă − 1; cu cotă medie de câștig ≈ n / Σ(1/cotă) (cota „break-even”), intervalul
    pe rata de intrare se traduce direct în interval pe ROI. Estimarea Bayes: Beta(1+w, 1+l) cu PRIOR_N selecții
    virtuale centrate pe break-even (ROI 0) — pe eșantioane mici rămâne aproape de 0, nu promite nimic."""
    n, w = b["n"], b["won"]
    out: Dict[str, Any] = {"n": n, "won": w}
    if not n:
        out.update(hit=None, roi=None, hit_ci=[None, None], roi_ci=[None, None], be_hit=None, bayes_roi=None, p_profit=None)
        return out
    be = b["inv"] / n  # rata de intrare necesară pentru ROI 0
    odds = 1.0 / be     # cota medie echivalentă
    roi = b["ret"] / n - 1
    lo, hi = wilson(w, n)
    a0, b0 = 1 + PRIOR_N * be, 1 + PRIOR_N * (1 - be)
    a, bb = a0 + w, b0 + (n - w)
    mean = a / (a + bb)
    var = a * bb / ((a + bb) ** 2 * (a + bb + 1))
    sd = math.sqrt(var)
    p_profit = 0.5 * math.erfc((be - mean) / (sd * math.sqrt(2))) if sd > 0 else (1.0 if mean > be else 0.0)
    out.update(hit=round(w / n, 4), roi=round(roi, 4), hit_ci=[round(lo, 4), round(hi, 4)],
               roi_ci=[round(lo * odds - 1, 4), round(hi * odds - 1, 4)], be_hit=round(be, 4),
               bayes_roi=round(mean * odds - 1, 4), p_profit=round(p_profit, 3))
    return out


def is_intl_league(name: Optional[str]) -> bool:
    from betpredict.builder.super_tickets import INTL

    return bool(INTL.search(name or ""))


def is_night(kickoff_utc: Optional[str]) -> bool:
    from zoneinfo import ZoneInfo

    try:
        h = datetime.fromisoformat((kickoff_utc or "").replace("Z", "+00:00")).astimezone(ZoneInfo("Europe/Bucharest")).hour
    except ValueError:
        return False
    return NIGHT_HOURS_RO[0] <= h < NIGHT_HOURS_RO[1]


def _rows(conn: sqlite3.Connection, since: str) -> List[tuple]:
    try:
        return conn.execute(
            """SELECT s.market_name, s.outcome, MAX(s.price), m.ft_home, m.ft_away, m.ht_home, m.ht_away, m.corners_home, m.corners_away,
                      m.kickoff_utc, l.name
               FROM sb_offer_close s JOIN match m ON m.id=s.match_id LEFT JOIN league l ON l.id=m.league_id
               WHERE m.status='finished' AND m.ft_home IS NOT NULL AND m.kickoff_utc>=?
               GROUP BY s.match_id, s.market_name, s.outcome""", (since,)).fetchall()
    except sqlite3.OperationalError:
        return []


def _key(mn: str, oc: str, rec: Dict[Tuple[str, str], tuple], combo_window: Tuple[float, float]):
    spec = rec.get((mn, oc))
    if spec:
        return (mn, oc), spec[2], spec[3]
    if re.sub(r"\s+", " ", (mn or "").lower().replace(",", ".")).startswith("peste 0.5 goluri; peste 7.5 cornere"):
        return COMBO, combo_window[0], combo_window[1]
    return None, 0.0, 0.0


def _collect(conn, rec, combo_window, now, days):
    """Pe piață: toate / cluburi / internaționale / zi / noapte / ultimele RECENT_DAYS zile."""
    since = canon_utc((now - timedelta(days=days)).isoformat())
    recent = canon_utc((now - timedelta(days=RECENT_DAYS)).isoformat())
    out: Dict[Any, Dict[str, Dict[str, Any]]] = {}
    for mn, oc, price, fh, fa, hh, ha, ch, ca, ko, league in _rows(conn, since):
        if not price or price <= 1:
            continue
        key, lo, hi = _key(mn, oc, rec, combo_window)
        if key is None or not lo <= price <= hi:
            continue
        won = settle(mn, oc, fh, fa, hh, ha, ch, ca)
        if won is None:
            continue
        seg = out.setdefault(key, {k: _bucket() for k in ("all", "club", "intl", "day", "night", "recent")})
        _add(seg["all"], price, won)
        _add(seg["intl" if is_intl_league(league) else "club"], price, won)
        _add(seg["night" if is_night(ko) else "day"], price, won)
        if (ko or "") >= recent:
            _add(seg["recent"], price, won)
    return out


def decide(all_: Dict[str, Any], recent: Dict[str, Any]) -> Tuple[str, str]:
    """on / off / reenabled, cu motivul (română)."""
    n, roi = all_.get("n") or 0, all_.get("roi")
    if n < MIN_N or roi is None:
        return "on", f"prea puține selecții ({n} < {MIN_N}): nu decidem nimic"
    if roi >= DROP_ROI:
        return "on", f"ROI {roi:+.1%} pe {n} selecții, peste pragul {DROP_ROI:+.0%}"
    rn, rr = recent.get("n") or 0, recent.get("roi")
    if rn >= REENABLE_N and rr is not None and rr >= REENABLE_ROI:
        return "reenabled", (f"ROI {roi:+.1%} pe {n}, dar ultimele {RECENT_DAYS} zile {rr:+.1%} pe {rn}: "
                             "a revenit, intră din nou pe bilete")
    return "off", f"ROI {roi:+.1%} pe {n} selecții, sub pragul {DROP_ROI:+.0%}: stă pe bară până își revine"


def market_stats(conn: sqlite3.Connection, rec: Dict[Tuple[str, str], tuple], combo_window: Tuple[float, float],
                 now: Optional[datetime] = None, days: int = DAYS) -> Dict[Any, Dict[str, Any]]:
    """Pe fiecare piață recomandată (în fereastra ei de cote): selecții, intrate, ROI la cota de închidere Superbet,
    intervale (Wilson, Bayes), pe segmente, și dacă piața stă pe bară (``off``) — cu regula de revenire automată."""
    now = now or datetime.now(timezone.utc)
    out: Dict[Any, Dict[str, Any]] = {}
    for key, seg in _collect(conn, rec, combo_window, now, days).items():
        b = summarize(seg["all"])
        segs = {k: summarize(v) for k, v in seg.items() if k != "all"}
        status, why = decide(b, segs["recent"])
        b.update(ret=round(seg["all"]["ret"], 4), off=status == "off", status=status, why=why, days=days, segments=segs)
        out[key] = b
    return out


def _label(key, rec) -> Dict[str, Any]:
    if key == COMBO:
        return {"key": COMBO, "market_name": "Peste 0.5 goluri; Peste 7.5 cornere", "outcome": "", "market": "bb", "selection": COMBO}
    spec = rec.get(key) or ("", "")
    return {"key": f"{key[0]}|{key[1]}", "market_name": key[0], "outcome": key[1], "market": spec[0], "selection": spec[1]}


def monitor_doc(conn: sqlite3.Connection, now: Optional[datetime] = None, days: int = DAYS,
                rec: Optional[Dict[Tuple[str, str], tuple]] = None,
                combo_window: Tuple[float, float] = (1.40, 1.60)) -> Dict[str, Any]:
    """Raportul pentru aplicație (JSON): fiecare piață recomandată, ROI pe 30 de zile cu intervale, pe cluburi /
    internaționale / zi / noapte / ultimele zile, și starea (în joc, pe bară, revenită). Fără nume de persoane."""
    now = now or datetime.now(timezone.utc)
    if rec is None:
        from betpredict.builder.super_tickets import REC as rec  # noqa: N811
    stats = market_stats(conn, rec, combo_window, now, days)
    markets = []
    for key in list(rec) + [COMBO]:
        st = stats.get(key)
        lo, hi = (rec[key][2], rec[key][3]) if key in rec else combo_window
        row = {**_label(key, rec), "window": [lo, hi]}
        if st is None:
            row.update(n=0, status="on", why="nicio selecție decontată în fereastră", segments={})
        else:
            row.update(st)
        markets.append(row)
    total = _bucket()
    for st in stats.values():
        total["n"] += st["n"]; total["won"] += st["won"]; total["ret"] += st["ret"]
    tot = {"n": total["n"], "won": total["won"], "roi": round(total["ret"] / total["n"] - 1, 4) if total["n"] else None}
    return {"generated_at": canon_utc(now.isoformat()), "days": days, "recent_days": RECENT_DAYS,
            "rules": {"min_n": MIN_N, "drop_roi": DROP_ROI, "reenable_n": REENABLE_N, "reenable_roi": REENABLE_ROI,
                      "night_hours_ro": list(NIGHT_HOURS_RO)},
            "total": tot, "off": [m["key"] for m in markets if m.get("status") == "off"], "markets": markets,
            "note": "ROI la cotele de închidere Superbet; intervale 95% (Wilson pe rata de intrare). Marja casei e reală: "
                    "un ROI mic pe puține selecții nu e un avantaj dovedit."}
