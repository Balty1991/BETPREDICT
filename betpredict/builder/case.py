"""Cazul pe meci pentru o selecție: formă, clasament, H2H, goluri așteptate.

Nu e un text lipit peste orice cotă. Întoarce propozițiile care susțin selecția, sau None
dacă faptele o contrazic ori nu spun nimic despre ea. O combinație trece doar dacă trec
ambele părți (rezultat și goluri).
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple


def support_lines(market: str, selection: str, ctx: Optional[Dict[str, Any]],
                  lh: Optional[float], la: Optional[float]) -> Optional[List[str]]:
    ctx = ctx or {}
    side, rest = _split(market, selection)
    side_lines = _side(side, ctx, lh, la) if side else []
    rest_lines = _rest(rest, ctx, lh, la) if rest else []
    if side and not side_lines:
        return None
    if rest and not rest_lines:
        return None
    lines: List[str] = []
    for line in (side_lines or [])[:2] + (rest_lines or [])[:2]:
        if line not in lines:
            lines.append(line)
    return lines or None


def _split(market: str, selection: str) -> Tuple[str, str]:
    if market == "bb" and "|" in (selection or ""):
        _name, outcome = selection.split("|", 1)
        side, _, rest = outcome.partition(" & ")
        return side.strip(), rest.strip()
    if market == "1x2":
        return {"HOME": "1", "DRAW": "X", "AWAY": "2"}.get(selection, ""), ""
    if market == "btts":
        return "", "GG Da" if selection == "YES" else "GG Nu"
    if market == "over_under":
        kind = "Peste" if selection == "OVER" else "Sub"
        return "", f"{kind}"
    return "", ""


def _signals(ctx: Dict[str, Any], lh: Optional[float], la: Optional[float]) -> Tuple[List[str], List[str]]:
    """Propoziții care țin cu gazdele, separat de cele care țin cu oaspeții."""
    home: List[str] = []
    away: List[str] = []
    form = ctx.get("form") or {}
    fh, fa = form.get("home") or {}, form.get("away") or {}
    hp, ap = fh.get("ppm"), fa.get("ppm")
    if isinstance(hp, (int, float)) and isinstance(ap, (int, float)):
        if hp >= ap + 0.15:
            home.append(f"Formă: gazde {hp:.2f} pct/meci, oaspeți {ap:.2f}")
        elif ap >= hp + 0.15:
            away.append(f"Formă: oaspeți {ap:.2f} pct/meci, gazde {hp:.2f}")
    st = ctx.get("standings") or {}
    hpos = (st.get("home") or {}).get("position")
    apos = (st.get("away") or {}).get("position")
    if hpos and apos:
        if hpos + 3 <= apos:
            home.append(f"Clasament: gazde locul {hpos}, oaspeți locul {apos}")
        elif apos + 3 <= hpos:
            away.append(f"Clasament: oaspeți locul {apos}, gazde locul {hpos}")
    if lh is not None and la is not None:
        if lh >= la + 0.20:
            home.append(f"Goluri așteptate: {lh:.2f}–{la:.2f}")
        elif la >= lh + 0.20:
            away.append(f"Goluri așteptate: {lh:.2f}–{la:.2f}, oaspeții mai mult")
    h2h = ctx.get("h2h") or {}
    hw, aw, dr, tot = h2h.get("home_wins"), h2h.get("away_wins"), h2h.get("draws"), h2h.get("total")
    if isinstance(tot, int) and tot >= 4 and isinstance(hw, int) and isinstance(aw, int):
        if hw >= aw + 2:
            home.append(f"H2H ({tot}): {hw}-{dr or 0}-{aw}")
        elif aw >= hw + 2:
            away.append(f"H2H ({tot}): {hw}-{dr or 0}-{aw} pentru oaspeți")
    return home, away


def _side(code: str, ctx: Dict[str, Any], lh: Optional[float], la: Optional[float]) -> Optional[List[str]]:
    code = code.lower().replace(" ", "")
    if code not in {"1", "2", "1x", "x2", "12"}:
        return None
    home, away = _signals(ctx, lh, la)
    if code in {"1", "1x"}:
        return home if len(home) > len(away) else None
    if code in {"2", "x2"}:
        return away if len(away) > len(home) else None
    # 12: doar când o echipă e clar înaintea celeilalte
    if abs(len(home) - len(away)) >= 1 and (home or away):
        lead = home if len(home) > len(away) else away
        return lead[:2] + ["Una dintre echipe e mai puternică, egalul e mai puțin probabil"]
    h2h = ctx.get("h2h") or {}
    tot, dr = h2h.get("total"), h2h.get("draws")
    if isinstance(tot, int) and isinstance(dr, int) and tot >= 5 and dr / tot >= 0.40:
        return None
    return None


def _rest(text: str, ctx: Dict[str, Any], lh: Optional[float], la: Optional[float]) -> Optional[List[str]]:
    t = text.strip().lower()
    total = lh + la if lh is not None and la is not None else None
    h2h = ctx.get("h2h") or {}
    avg = h2h.get("avg_goals") if isinstance(h2h.get("avg_goals"), (int, float)) else None
    btts = h2h.get("btts_rate") if isinstance(h2h.get("btts_rate"), (int, float)) else None
    if t in {"gg nu", "nu"}:
        if lh is not None and la is not None and min(lh, la) >= 1.20 and (btts is None or btts >= 0.55):
            return None
        if lh is not None and la is not None and min(lh, la) <= 0.95:
            return [f"Una marchează puțin: {lh:.2f} și {la:.2f} goluri așteptate"]
        if btts is not None and btts <= 0.45:
            return [f"H2H: ambele au marcat în {btts:.0%} din directe"]
        return []
    if t in {"gg da", "da"}:
        if lh is not None and la is not None and min(lh, la) < 0.70:
            return None
        if lh is not None and la is not None and min(lh, la) >= 0.95:
            return [f"Ambele au goluri așteptate: {lh:.2f} și {la:.2f}"]
        if btts is not None and btts >= 0.55:
            return [f"H2H: ambele au marcat în {btts:.0%} din directe"]
        return []
    if t.startswith("sub ") or t.startswith("peste "):
        try:
            line = float(t.split()[1])
        except (IndexError, ValueError):
            return []
        under = t.startswith("sub")
        if total is None and avg is None:
            return []
        if under:
            if total is not None and total >= line + 0.45:
                return None
            if total is not None and total <= line + 0.05:
                return [f"Goluri așteptate {total:.2f}, sub {line:g}"]
            if avg is not None and avg <= line:
                return [f"Directele au medie {avg:.2f} goluri"]
            return []
        if total is not None and total <= line - 0.55:
            return None
        if total is not None and total >= line - 0.15:
            return [f"Goluri așteptate {total:.2f}, peste {line:g}"]
        if avg is not None and avg >= line:
            return [f"Directele au medie {avg:.2f} goluri"]
        return []
    if "-" in t and t.replace("-", "").replace(".", "").isdigit():
        lo_s, hi_s = t.split("-", 1)
        lo, hi = float(lo_s), float(hi_s)
        if total is None:
            return None
        if lo - 0.3 <= total <= hi + 0.3:
            return [f"Goluri așteptate {total:.2f}, în intervalul {lo:g}–{hi:g}"]
        return None
    return []
