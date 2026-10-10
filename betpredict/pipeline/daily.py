"""``daily-build`` (Etapa 0): program + predicții BSD + cote consens → SQLite → api/days.

Cost estimat pe planul Free (o rulare, fereastră ieri…+2 zile):
  * /events/       ~3–8 pagini (200/pagină)
  * /predictions/  ~3–8 pagini
  * /odds/         delta cu ``updated_after`` pe 7 piețe, ~10–60 pagini la prima rulare,
                   apoi mult mai puțin (doar liniile recitite de BSD)
Total: de regulă < 100 de cereri, mult sub ținta de < 3.500/zi din plan.
Endpointurile plătite (/odds/best/, /odds/comparison/) NU sunt folosite.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from betpredict.ingest.bsd_client import BSDClient
from betpredict.ingest.errors import BSDError, BudgetExceeded, QuotaExhausted
from betpredict.ingest.normalize import event_league, event_to_match, feed_row_to_odds, prediction_to_rows
from betpredict.ingest.quota import PRIORITY_NORMAL
from betpredict.publish.day import write_day
from betpredict.store import repo
from betpredict.timeutil import ro_date_of, ro_today

log = logging.getLogger("betpredict.daily")

ODDS_FEED_MARKETS = ("1x2", "over_under_15", "over_under_25", "over_under_35", "btts", "double_chance", "draw_no_bet")


class StopRun(Exception):
    pass


def _guard(report: Dict[str, Any], step: str, fn, *args, **kwargs):
    """Rulează un pas; bugetul/cota opresc tot run-ul, alte erori doar pasul."""
    try:
        return fn(*args, **kwargs)
    except (BudgetExceeded, QuotaExhausted) as exc:
        report["warnings"].append({"step": step, "error": type(exc).__name__, "detail": str(exc)})
        report["stopped_early"] = True
        raise StopRun(str(exc)) from None
    except BSDError as exc:
        report["warnings"].append({"step": step, "error": type(exc).__name__, "detail": str(exc), "status": exc.status})
        return None


def ingest_events(conn: sqlite3.Connection, client: BSDClient, date_from: date, date_to: date) -> int:
    now = repo.now_iso()
    n = 0
    with conn:
        for ev in client.paginate("events/", {"date_from": date_from.isoformat(), "date_to": date_to.isoformat()},
                                  priority=PRIORITY_NORMAL):
            m = event_to_match(ev, now)
            if m["id"] is None or not m["kickoff_utc"]:
                continue
            lg = event_league(ev)
            if lg:
                repo.upsert_league(conn, lg)
            repo.upsert_team(conn, m["home_id"], m["home_name"], m["league_id"])
            repo.upsert_team(conn, m["away_id"], m["away_name"], m["league_id"])
            repo.upsert_match(conn, m)
            n += 1
    backfill_league_names(conn, client)
    return n


def parse_league_detail(js: Any) -> Dict[str, Any]:
    """Răspunsul /leagues/{id}/ poate fi obiectul ligii sau {"league": {...}}; țara poate fi text sau obiect."""
    d = js.get("league") if isinstance(js, dict) and isinstance(js.get("league"), dict) else js
    if not isinstance(d, dict):
        return {}
    c = d.get("country")
    country = c.get("name") if isinstance(c, dict) else c
    return {"name": d.get("name") or d.get("league_name"), "country": country if isinstance(country, str) else None}


def backfill_league_names(conn: sqlite3.Connection, client: BSDClient, limit: int = 40) -> int:
    """Ligile fără nume (evenimentele trimit doar id-ul) => „Liga #99” în aplicație. Cerem detaliul ligii o dată."""
    ids = [r[0] for r in conn.execute(
        "SELECT DISTINCT m.league_id FROM match m LEFT JOIN league l ON l.id = m.league_id "
        "WHERE m.league_id IS NOT NULL AND (l.id IS NULL OR l.name IS NULL OR l.name = '') LIMIT ?", (limit,))]
    n = 0
    for lid in ids:
        try:
            info = parse_league_detail(client.get(f"leagues/{lid}/", cache_ttl=7 * 86400))
        except Exception:  # noqa: BLE001 — opțional; la prima eroare ne oprim (endpoint indisponibil)
            break
        if not info.get("name"):
            break
        with conn:
            conn.execute(
                "INSERT INTO league (id, name, country, updated_at) VALUES (?,?,?,?) "
                "ON CONFLICT(id) DO UPDATE SET name=excluded.name, country=COALESCE(league.country, excluded.country), updated_at=excluded.updated_at",
                (lid, info["name"], info.get("country"), repo.now_iso()))
        n += 1
    return n


def ingest_predictions(conn: sqlite3.Connection, client: BSDClient, date_from: date, date_to: date) -> int:
    now = repo.now_iso()
    n = 0
    with conn:
        for pred in client.paginate("predictions/", {"date_from": date_from.isoformat(), "date_to": date_to.isoformat()}):
            match_id, rows = prediction_to_rows(pred, now)
            if match_id is None or not rows:
                continue
            exists = conn.execute("SELECT 1 FROM match WHERE id=?", (match_id,)).fetchone()
            if not exists:
                ev = pred.get("event") if isinstance(pred.get("event"), dict) else {}
                m = event_to_match(ev, now)
                if m["id"] is not None and m["kickoff_utc"]:
                    lg = event_league(ev)
                    if lg:
                        repo.upsert_league(conn, lg)
                    repo.upsert_match(conn, m)
            n += repo.upsert_provider_predictions(conn, rows)
    return n


def ingest_odds_feed(conn: sqlite3.Connection, client: BSDClient, markets=ODDS_FEED_MARKETS, max_pages: int = 40) -> int:
    """Polling delta pe ``/odds/`` cu ``updated_after`` (consens pe Free)."""
    total = 0
    observed = repo.now_iso()
    for market in markets:
        state_key = f"odds_feed.updated_after.{market}"
        since = repo.get_state(conn, state_key)
        params: Dict[str, Any] = {"market": market}
        if since:
            params["updated_after"] = since
        newest: Optional[str] = since
        batch: List[Dict[str, Any]] = []
        for row in client.paginate("odds/", params, max_pages=max_pages):
            o = feed_row_to_odds(row, observed)
            if o:
                batch.append(o)
            ts = row.get("updated_at")
            if ts and (newest is None or str(ts) > newest):
                newest = str(ts)
        with conn:
            total += repo.insert_odds(conn, batch)
            if newest:
                repo.set_state(conn, state_key, newest)
    return total


def run_daily_build(
    conn: sqlite3.Connection,
    client: BSDClient,
    out_root: Path,
    day: Optional[date] = None,
    days_back: int = 1,
    days_ahead: int = 2,
    with_odds: bool = True,
) -> Dict[str, Any]:
    day = day or ro_today()
    date_from = day - timedelta(days=days_back)
    # +1 zi: meciurile de după 21:00 UTC aparțin deja zilei următoare în România.
    date_to = day + timedelta(days=days_ahead + 1)
    report: Dict[str, Any] = {
        "started_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "day": day.isoformat(),
        "window_utc": [date_from.isoformat(), date_to.isoformat()],
        "has_api_key": client.has_key,
        "plan": client.settings.plan,
        "steps": {},
        "warnings": [],
        "stopped_early": False,
    }
    try:
        report["steps"]["events"] = _guard(report, "events", ingest_events, conn, client, date_from, date_to)
        report["steps"]["predictions"] = _guard(report, "predictions", ingest_predictions, conn, client, date_from, date_to)
        if with_odds:
            report["steps"]["odds_rows"] = _guard(report, "odds", ingest_odds_feed, conn, client)
    except StopRun:
        pass
    finally:
        client.save_quota()

    published = []
    for offset in range(-days_back, days_ahead + 1):
        d = day + timedelta(days=offset)
        published.append(str(write_day(conn, d, out_root).relative_to(out_root)))
    report["published"] = published
    report["client_stats"] = dict(client.stats)
    report["quota"] = client.quota.summary()
    report["finished_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    meta_dir = Path(out_root) / "api"
    meta_dir.mkdir(parents=True, exist_ok=True)
    (meta_dir / "meta.json").write_text(json.dumps({
        "generated_at": report["finished_at"],
        "day": report["day"],
        "quota": {k: report["quota"].get(k) for k in ("effective_remaining", "daily_quota", "exhausted")},
        "stopped_early": report["stopped_early"],
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    return report


__all__ = ["run_daily_build", "ingest_events", "ingest_predictions", "ingest_odds_feed", "ro_date_of"]
