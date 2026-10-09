"""Transformă răspunsurile BSD v2 în rânduri pentru schema SQLite."""

from __future__ import annotations

import json
import re
from typing import Any, Dict, Iterable, List, Optional, Tuple

from betpredict.timeutil import canon_utc

FINISHED = {"finished", "ft", "ended", "aet", "pen"}
VOID_STATUSES = {"cancelled", "canceled", "postponed", "abandoned", "unresolved"}

# Pe /api/v2/odds/ numele pieței e vocabularul vechi, doar FT.
LEGACY_MARKET_MAP: Dict[str, Tuple[str, float]] = {
    "1x2": ("1x2", 0.0),
    "over_under_05": ("over_under", 0.5),
    "over_under_15": ("over_under", 1.5),
    "over_under_25": ("over_under", 2.5),
    "over_under_35": ("over_under", 3.5),
    "over_under_45": ("over_under", 4.5),
    "btts": ("btts", 0.0),
    "double_chance": ("double_chance", 0.0),
    "draw_no_bet": ("draw_no_bet", 0.0),
}

# /api/v2/events/{id}/odds/ — consens FT (planul Free).
CONSENSUS_FIELDS: Dict[str, Tuple[str, float, str]] = {
    "home_win": ("1x2", 0.0, "HOME"),
    "draw": ("1x2", 0.0, "DRAW"),
    "away_win": ("1x2", 0.0, "AWAY"),
    "over_15_goals": ("over_under", 1.5, "OVER"),
    "under_15_goals": ("over_under", 1.5, "UNDER"),
    "over_25_goals": ("over_under", 2.5, "OVER"),
    "under_25_goals": ("over_under", 2.5, "UNDER"),
    "over_35_goals": ("over_under", 3.5, "OVER"),
    "under_35_goals": ("over_under", 3.5, "UNDER"),
    "btts_yes": ("btts", 0.0, "YES"),
    "btts_no": ("btts", 0.0, "NO"),
}


def as_int(v: Any) -> Optional[int]:
    try:
        if v is None or v == "":
            return None
        return int(float(v))
    except (TypeError, ValueError):
        return None


def as_float(v: Any) -> Optional[float]:
    try:
        if v is None or v == "":
            return None
        return float(v)
    except (TypeError, ValueError):
        return None


def _name(v: Any) -> Optional[str]:
    if isinstance(v, dict):
        return v.get("name")
    return v if isinstance(v, str) else None


def _id(row: Dict[str, Any], flat: str, nested: str) -> Optional[int]:
    if row.get(flat) is not None:
        return as_int(row.get(flat))
    obj = row.get(nested)
    return as_int(obj.get("id")) if isinstance(obj, dict) else None


def event_to_match(ev: Dict[str, Any], updated_at: str) -> Dict[str, Any]:
    status = str(ev.get("status") or "").lower() or None
    round_label = ev.get("round_label") or ev.get("round_name") or ev.get("round_number")
    return {
        "id": as_int(ev.get("id") or ev.get("event_id")),
        "season_id": _id(ev, "season_id", "season"),
        "league_id": _id(ev, "league_id", "league"),
        "kickoff_utc": canon_utc(ev.get("event_date") or ev.get("start_time") or ev.get("kickoff")),
        "home_id": _id(ev, "home_team_id", "home_team"),
        "away_id": _id(ev, "away_team_id", "away_team"),
        "home_name": _name(ev.get("home_team")),
        "away_name": _name(ev.get("away_team")),
        "status": status,
        "stage": ev.get("stage"),
        "round": str(round_label) if round_label not in (None, "") else None,
        "ft_home": as_int(ev.get("home_score")),
        "ft_away": as_int(ev.get("away_score")),
        "ht_home": as_int(ev.get("home_score_ht")),
        "ht_away": as_int(ev.get("away_score_ht")),
        "venue_id": as_int(ev.get("venue_id")),
        "referee_id": as_int(ev.get("referee_id")),
        "raw_json": json.dumps(ev, ensure_ascii=False, separators=(",", ":")),
        "updated_at": updated_at,
    }


def event_league(ev: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    lid = _id(ev, "league_id", "league")
    if lid is None:
        return None
    league = ev.get("league") if isinstance(ev.get("league"), dict) else {}
    name = ev.get("league_name") or league.get("name") or (ev.get("league") if isinstance(ev.get("league"), str) else None)
    return {"id": lid, "name": name, "country": ev.get("country") or league.get("country")}


def _norm_outcome(o: Any) -> str:
    s = str(o or "").strip()
    up = s.upper()
    return {"1": "HOME", "X": "DRAW", "2": "AWAY"}.get(up, up)


def feed_row_to_odds(row: Dict[str, Any], observed_fallback: str) -> Optional[Dict[str, Any]]:
    """Un rând din ``GET /api/v2/odds/`` (consens pe Free) → ``odds_snapshot``."""
    event = row.get("event") if isinstance(row.get("event"), dict) else {}
    match_id = as_int(row.get("event_id") or event.get("id"))
    raw_market = str(row.get("market") or "").lower()
    price = as_float(row.get("decimal_odds") or row.get("odds"))
    if match_id is None or not raw_market or price is None or price <= 1.0:
        return None
    market, line = LEGACY_MARKET_MAP.get(raw_market, (raw_market, 0.0))
    if row.get("line") is not None and as_float(row.get("line")) is not None:
        line = float(row["line"])
    m = re.match(r"^total_corners_?(\d)(\d)$", raw_market)
    if m:
        market, line = "total_corners", float(f"{m.group(1)}.{m.group(2)}")
    slug = str(row.get("bookmaker_slug") or "consensus")
    return {
        "match_id": match_id,
        "market": market,
        "line": line or 0.0,
        "period": str(row.get("period") or "FT").upper(),
        "outcome": _norm_outcome(row.get("outcome")),
        "decimal": price,
        "opening_decimal": as_float(row.get("opening_decimal_odds")),
        "previous_decimal": as_float(row.get("previous_decimal_odds")),
        "movement": (row.get("movement") or None),
        "source": "bsd_consensus" if slug == "consensus" else f"bsd:{slug}",
        "observed_at": row.get("updated_at") or observed_fallback,
    }


def consensus_to_odds(match_id: int, payload: Dict[str, Any], observed_at: str) -> List[Dict[str, Any]]:
    """``GET /events/{id}/odds/`` (cele 11 chei FT) → rânduri ``odds_snapshot``."""
    odds = payload.get("odds") if isinstance(payload.get("odds"), dict) else payload
    out: List[Dict[str, Any]] = []
    stamp = payload.get("last_update_at") or observed_at
    for field, (market, line, outcome) in CONSENSUS_FIELDS.items():
        price = as_float((odds or {}).get(field))
        if price is None or price <= 1.0:
            continue
        out.append({
            "match_id": match_id, "market": market, "line": line, "period": "FT", "outcome": outcome,
            "decimal": price, "opening_decimal": None, "previous_decimal": None, "movement": None,
            "source": "bsd_consensus", "observed_at": stamp,
        })
    return out


def _p(v: Any) -> Optional[float]:
    """BSD dă probabilitățile pe piețe în 0–100 (contract vechi) → 0–1."""
    f = as_float(v)
    if f is None:
        return None
    return round(f / 100.0, 4) if f > 1.0 else round(f, 4)


def prediction_to_rows(pred: Dict[str, Any], fetched_at: str) -> Tuple[Optional[int], List[Dict[str, Any]]]:
    event = pred.get("event") if isinstance(pred.get("event"), dict) else {}
    match_id = as_int(event.get("id") or pred.get("event_id"))
    markets = pred.get("markets") if isinstance(pred.get("markets"), dict) else {}
    version = (pred.get("model") or {}).get("version") if isinstance(pred.get("model"), dict) else None
    rows: List[Dict[str, Any]] = []

    def add(market: str, line: float, sel: str, p: Optional[float]) -> None:
        if p is None or not (0.0 <= p <= 1.0):
            return
        rows.append({"match_id": match_id, "source": "bsd", "market": market, "line": line,
                     "selection": sel, "probability": p, "model_version": version, "fetched_at": fetched_at})

    mr = markets.get("match_result") or {}
    add("1x2", 0.0, "HOME", _p(mr.get("prob_home")))
    add("1x2", 0.0, "DRAW", _p(mr.get("prob_draw")))
    add("1x2", 0.0, "AWAY", _p(mr.get("prob_away")))
    ou = markets.get("over_under") or {}
    for key, line in (("prob_over_15", 1.5), ("prob_over_25", 2.5), ("prob_over_35", 3.5)):
        p = _p(ou.get(key))
        add("over_under", line, "OVER", p)
        add("over_under", line, "UNDER", None if p is None else round(1 - p, 4))
    bt = _p((markets.get("btts") or {}).get("prob_yes"))
    add("btts", 0.0, "YES", bt)
    add("btts", 0.0, "NO", None if bt is None else round(1 - bt, 4))
    dnb = _p((markets.get("draw_no_bet") or {}).get("prob_home"))
    add("draw_no_bet", 0.0, "HOME", dnb)
    add("draw_no_bet", 0.0, "AWAY", None if dnb is None else round(1 - dnb, 4))
    corners = markets.get("corners") or {}
    for key, line in (("prob_over_85", 8.5), ("prob_over_95", 9.5), ("prob_over_105", 10.5)):
        add("total_corners", line, "OVER", _p(corners.get(key)))
    return match_id, rows


def iter_nonempty(rows: Iterable[Optional[Dict[str, Any]]]) -> List[Dict[str, Any]]:
    return [r for r in rows if r]
