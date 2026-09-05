#!/usr/bin/env python3
"""Betfair Exchange snapshot adapter for BetPredict.

Read-only by design: this module only authenticates and reads market data. It
never places bets. Without BETFAIR_APP_KEY and BETFAIR_SESSION_TOKEN (or
certificate-login credentials), it writes a disabled status and exits cleanly.

Output: data/betfair_exchange.json
"""
from __future__ import annotations

import json
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import requests

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
OUTPUT = DATA / "betfair_exchange.json"
BETTING_URL = "https://api.betfair.com/exchange/betting/json-rpc/v1"
LOGIN_URL = "https://identitysso-cert.betfair.com/api/certlogin"
APP_KEY = os.environ.get("BETFAIR_APP_KEY", "").strip()
SESSION_TOKEN = os.environ.get("BETFAIR_SESSION_TOKEN", "").strip()
USERNAME = os.environ.get("BETFAIR_USERNAME", "").strip()
PASSWORD = os.environ.get("BETFAIR_PASSWORD", "").strip()
CERT_PATH = os.environ.get("BETFAIR_CERT_PATH", "").strip()
KEY_PATH = os.environ.get("BETFAIR_KEY_PATH", "").strip()
MIN_MATCHED_VOLUME = float(os.environ.get("BETFAIR_MIN_MATCHED_VOLUME", "100") or 100)
MAX_SPREAD_PCT = float(os.environ.get("BETFAIR_MAX_SPREAD_PCT", "3") or 3)
MAX_AGE_SECONDS = int(os.environ.get("BETFAIR_MAX_AGE_SECONDS", "900") or 900)

MARKET_MAP = {
    "MATCH_ODDS": "1x2",
    "OVER_UNDER_15": "over_under_15",
    "OVER_UNDER_25": "over_under_25",
    "OVER_UNDER_35": "over_under_35",
    "BOTH_TEAMS_TO_SCORE": "btts",
}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def atomic_write(path: Path, payload: Any) -> None:
    DATA.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=DATA, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)


def norm_name(value: Any) -> str:
    value = re.sub(r"[^a-z0-9 ]+", " ", str(value or "").lower())
    return re.sub(r"\s+", " ", value).strip()


def event_key(home: Any, away: Any) -> Tuple[str, str]:
    return norm_name(home), norm_name(away)


def _jsonrpc(method: str, params: Dict[str, Any], token: str) -> Any:
    headers = {
        "X-Application": APP_KEY,
        "X-Authentication": token,
        "Content-Type": "application/json",
    }
    payload = [{"jsonrpc": "2.0", "method": method, "params": params, "id": 1}]
    response = requests.post(BETTING_URL, headers=headers, json=payload, timeout=30)
    response.raise_for_status()
    body = response.json()
    if not isinstance(body, list) or not body or "result" not in body[0]:
        raise RuntimeError(f"Betfair RPC error: {body}")
    return body[0]["result"]


def get_session_token() -> Optional[str]:
    if SESSION_TOKEN:
        return SESSION_TOKEN
    if not (APP_KEY and USERNAME and PASSWORD and CERT_PATH and KEY_PATH):
        return None
    with open(CERT_PATH, "rb") as cert, open(KEY_PATH, "rb") as key:
        response = requests.post(
            LOGIN_URL,
            headers={"X-Application": APP_KEY, "Content-Type": "application/x-www-form-urlencoded"},
            data={"username": USERNAME, "password": PASSWORD},
            cert=(CERT_PATH, KEY_PATH),
            timeout=30,
        )
    response.raise_for_status()
    body = response.json()
    token = body.get("sessionToken")
    if not token:
        raise RuntimeError(f"Betfair login failed: {body.get('loginStatus', 'unknown')}")
    return str(token)


def _catalogue(token: str) -> List[Dict[str, Any]]:
    return _jsonrpc(
        "SportsAPING/v1.0/listMarketCatalogue",
        {
            "filter": {"eventTypeIds": ["1"], "marketTypeCodes": list(MARKET_MAP)},
            "marketProjection": ["EVENT", "MARKET_START_TIME", "RUNNER_DESCRIPTION", "TOTAL_MATCHED"],
            "sort": "FIRST_TO_START",
            "maxResults": int(os.environ.get("BETFAIR_MAX_MARKETS", "200") or 200),
        },
        token,
    ) or []


def _books(token: str, market_ids: Iterable[str]) -> List[Dict[str, Any]]:
    ids = list(market_ids)
    if not ids:
        return []
    return _jsonrpc(
        "SportsAPING/v1.0/listMarketBook",
        {
            "marketIds": ids,
            "priceProjection": {"priceData": ["EX_BEST_OFFERS", "EX_TRADED"], "virtualise": True},
        },
        token,
    ) or []


def _best_prices(book: Dict[str, Any], runner_id: Any) -> Tuple[Optional[float], Optional[float], float]:
    runner = next((r for r in book.get("runners", []) if r.get("selectionId") == runner_id), {})
    ex = runner.get("ex", {}) or {}
    backs = ex.get("availableToBack", []) or []
    lays = ex.get("availableToLay", []) or []
    back = float(backs[0]["price"]) if backs else None
    lay = float(lays[0]["price"]) if lays else None
    traded = sum(float(x.get("size", 0)) for x in (ex.get("tradedVolume", []) or []))
    return back, lay, traded


def canonical_outcome(market_type: str, runner_name: Any) -> Optional[str]:
    name = str(runner_name or "").strip().upper()
    if market_type == "1x2":
        return {"HOME": "HOME", "DRAW": "DRAW", "AWAY": "AWAY"}.get(name)
    if market_type == "btts":
        return {"YES": "YES", "NO": "NO"}.get(name)
    if market_type.startswith("over_under_"):
        if name.startswith("OVER"):
            return "OVER"
        if name.startswith("UNDER"):
            return "UNDER"
    return None


def normalize_snapshot(catalogue: List[Dict[str, Any]], books: List[Dict[str, Any]], source_time: Optional[str] = None) -> Dict[str, Any]:
    by_market = {str(b.get("marketId")): b for b in books}
    rows: List[Dict[str, Any]] = []
    for market in catalogue:
        market_type = MARKET_MAP.get(market.get("marketType"))
        event = market.get("event") or {}
        book = by_market.get(str(market.get("marketId")), {})
        if market_type is None or not event or book.get("status") in {"CLOSED", "SUSPENDED"}:
            continue
        runners = {r.get("selectionId"): r for r in market.get("runners", [])}
        for runner_id, desc in runners.items():
            back, lay, traded = _best_prices(book, runner_id)
            if back is None or back <= 1.01 or traded < MIN_MATCHED_VOLUME:
                continue
            spread_pct = ((lay - back) / back * 100) if lay and lay >= back else None
            if spread_pct is not None and spread_pct > MAX_SPREAD_PCT:
                continue
            outcome = canonical_outcome(market_type, desc.get("runnerName"))
            if not outcome:
                continue
            rows.append({
                "event_id": event.get("id"),
                "event_name": event.get("name"),
                "home_team": event.get("name", "").split(" v ", 1)[0],
                "away_team": event.get("name", "").split(" v ", 1)[1] if " v " in event.get("name", "") else None,
                "event_date": market.get("marketStartTime") or event.get("openDate"),
                "market_id": market.get("marketId"),
                "market_type": market_type,
                "outcome": outcome,
                "selection_id": runner_id,
                "best_back_odds": back,
                "best_back_size": (book.get("runners") or [{}])[0].get("totalMatched") if False else None,
                "best_lay_odds": lay,
                "last_traded_odds": (book.get("runners") or [{}])[0].get("lastPriceTraded"),
                "matched_volume": traded,
                "spread_pct": round(spread_pct, 4) if spread_pct is not None else None,
                "captured_at": source_time or now_iso(),
                "source": "betfair_exchange",
            })
    return {"updated_at": source_time or now_iso(), "source": "betfair_exchange_read_only", "count": len(rows), "rows": rows}


def main() -> int:
    if not APP_KEY:
        atomic_write(OUTPUT, {"updated_at": now_iso(), "source": "betfair_exchange", "status": "disabled", "reason": "BETFAIR_APP_KEY missing", "count": 0, "rows": []})
        print("[betfair] disabled: BETFAIR_APP_KEY missing")
        return 0
    try:
        token = get_session_token()
        if not token:
            raise RuntimeError("provide BETFAIR_SESSION_TOKEN or certificate-login credentials")
        catalogue = _catalogue(token)
        books = _books(token, [str(x.get("marketId")) for x in catalogue if x.get("marketId")])
        out = normalize_snapshot(catalogue, books)
        out["status"] = "ok"
        atomic_write(OUTPUT, out)
        print(f"[betfair] markets={len(catalogue)} rows={out['count']}")
        return 0
    except Exception as exc:
        atomic_write(OUTPUT, {"updated_at": now_iso(), "source": "betfair_exchange", "status": "error", "error": str(exc), "count": 0, "rows": []})
        print(f"[betfair] unavailable: {exc}")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["normalize_snapshot", "event_key", "norm_name"]
