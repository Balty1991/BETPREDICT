"""Orchestrare v3: ``python -m betpredict run {daily|refresh|learn|offline}``.

  daily   (00:15 UTC)  istoric/legacy (o dată), events ±zile, predicții BSD, cote, context,
                       Robot, bilete + piramidă pentru azi, decontare, publicare
  refresh (orar)       events (rezultate), cote delta, context (cache), Robot pe meciurile
                       nejucate, decontare, publicare — fără a regenera biletele
  learn   (luni)       autoînvățare + walk-forward, apoi publicare
  offline              fără API: doar Robot + bilete + publicare din DB (teste/local)
"""

from __future__ import annotations

import json
import sqlite3
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from betpredict.ingest.bsd_client import BSDClient
from betpredict.ingest.errors import BSDError, BudgetExceeded, QuotaExhausted
from betpredict.ingest.quota import PRIORITY_LOW
from betpredict.pipeline.daily import StopRun, ingest_events, ingest_odds_feed, ingest_predictions
from betpredict.publish.day import write_day
from betpredict.publish.journal import publish_journal
from betpredict.publish.robot import publish_robot
from betpredict.publish.outputs import publish_meta, publish_pyramid, publish_stats, publish_tickets
from betpredict.store import repo
from betpredict.timeutil import ro_today

ROOT_DATA = Path(__file__).resolve().parents[2] / "data"


def _step(report: Dict[str, Any], name: str, fn, *a, **k):
    try:
        res = fn(*a, **k)
        report["steps"][name] = res
        return res
    except (BudgetExceeded, QuotaExhausted) as exc:
        report["warnings"].append({"step": name, "error": type(exc).__name__, "detail": str(exc)})
        report["stopped_early"] = True
        raise StopRun(str(exc)) from None
    except BSDError as exc:
        report["warnings"].append({"step": name, "error": type(exc).__name__, "detail": str(exc), "status": exc.status})
        return None


def bootstrap(conn: sqlite3.Connection, data_dir: Path = ROOT_DATA) -> Dict[str, Any]:
    """O singură dată: istoricul din data/warehouse + jurnalul vechi."""
    from betpredict.ingest.history import import_warehouse
    from betpredict.store.legacy_import import import_legacy

    out: Dict[str, Any] = {}
    if (data_dir / "warehouse").is_dir():
        out["warehouse"] = import_warehouse(conn, data_dir / "warehouse")
    if not repo.get_state(conn, "legacy.imported"):
        out["legacy"] = import_legacy(conn, data_dir)
        with conn:
            repo.set_state(conn, "legacy.imported", repo.now_iso())
    return out


def backfill_current_season(conn: sqlite3.Connection, client: BSDClient, today: date, chunk_days: int = 60) -> Dict[str, Any]:
    """Completează rezultatele de după depozitul vechi (care se oprește în aug. 2026), pe bucăți."""
    last = repo.get_state(conn, "backfill.finished_until")
    if not last:
        # Ultimul meci terminat ÎNAINTE de fereastra ingerată zilnic (azi − 5 zile). Vechea condiție
        # (MAX peste tot, inclusiv meciurile de ieri) declara istoricul „la zi” și lăsa o gaură
        # (mijloc aug. → oct. 2026) în forma echipelor folosită de Robot.
        row = conn.execute("SELECT MAX(kickoff_utc) FROM match WHERE status='finished' AND kickoff_utc < ?",
                           ((today - timedelta(days=5)).isoformat(),)).fetchone()
        last = (row[0] or (today - timedelta(days=60)).isoformat())[:10]
    start = date.fromisoformat(last)
    if start >= today - timedelta(days=1):
        return {"up_to_date": last}
    end = min(today - timedelta(days=1), start + timedelta(days=chunk_days))
    n = 0
    now = repo.now_iso()
    from betpredict.ingest.normalize import event_league, event_to_match

    with conn:
        for ev in client.paginate("events/", {"date_from": start.isoformat(), "date_to": end.isoformat(), "status": "finished"},
                                  priority=PRIORITY_LOW, max_pages=150):
            m = event_to_match(ev, now)
            if m["id"] is None or not m["kickoff_utc"]:
                continue
            lg = event_league(ev)
            if lg:
                repo.upsert_league(conn, lg)
            repo.upsert_match(conn, m)
            n += 1
        repo.set_state(conn, "backfill.finished_until", end.isoformat())
    return {"from": start.isoformat(), "to": end.isoformat(), "events": n}


SUPERBET_CAP = {"daily": 150, "refresh": 60, "closing": 40}


def superbet_step(conn: sqlite3.Connection, now: Optional[datetime], days_ahead: int = 2, max_requests: int = 60,
                  closing_only: bool = False) -> Dict[str, Any]:
    """Cote jucabile Superbet; orice eroare de rețea e raportată, nu oprește rularea."""
    try:
        from betpredict.ingest.superbet import ingest_superbet

        return ingest_superbet(conn, now=now, days_ahead=days_ahead, max_requests=max_requests, closing_only=closing_only)
    except Exception as exc:  # noqa: BLE001
        return {"error": f"{type(exc).__name__}: {exc}"}


def publish_all(conn: sqlite3.Connection, out_root: Path, today: date, days_back: int, days_ahead: int,
                report: Dict[str, Any], step: str) -> None:
    days = [today + timedelta(days=o) for o in range(-days_back, days_ahead + 1)]
    for d in days:
        write_day(conn, d, out_root)
    publish_tickets(conn, out_root, days, today)
    publish_pyramid(conn, out_root, today)
    publish_stats(conn, out_root)
    publish_journal(conn, out_root, today)
    publish_robot(conn, out_root, days_ahead=days_ahead)
    try:
        from betpredict.publish.weekly import publish_weekly

        publish_weekly(conn, out_root, today)
    except Exception as exc:  # noqa: BLE001
        report.setdefault("warnings", []).append({"step": "weekly_publish", "error": str(exc)})
    publish_meta(conn, out_root, today, report.get("quota"), report.get("warnings", []), step)


# Orizontul de program: BSD Free întoarce /events/ și cotele de consens pentru meciurile deja
# programate (de regulă ~1 săptămână înainte). Rularea zilnică citește tot orizontul;
# refresh-ul orar recitește doar zilele apropiate (cote/ore se schimbă), ca să economisim cota.
DEFAULT_DAYS_AHEAD = 6
REFRESH_FETCH_AHEAD = 2


def run_pipeline(conn: sqlite3.Connection, mode: str, out_root: Path, client: Optional[BSDClient] = None,
                 today: Optional[date] = None, days_back: int = 3, days_ahead: int = DEFAULT_DAYS_AHEAD,
                 rebuild_tickets: bool = False, now: Optional[datetime] = None) -> Dict[str, Any]:
    from betpredict.builder.pyramid import build_pyramid_day
    from betpredict.builder.tickets import build_horizon
    from betpredict.ingest.context import collect_context
    from betpredict.learn import learn
    from betpredict.robot.engine import Robot
    from betpredict.settle import settle_all

    today = today or ro_today()
    report: Dict[str, Any] = {"mode": mode, "day": today.isoformat(), "started_at": repo.now_iso(), "steps": {},
                              "warnings": [], "stopped_early": False}
    report["steps"]["bootstrap"] = bootstrap(conn)  # idempotent (rulează efectiv o singură dată)

    if client is not None and mode in ("daily", "refresh"):
        date_from = today - timedelta(days=days_back)
        fetch_ahead = days_ahead if mode == "daily" else min(days_ahead, REFRESH_FETCH_AHEAD)
        date_to = today + timedelta(days=fetch_ahead + 1)
        try:
            _step(report, "events", ingest_events, conn, client, date_from, date_to)
            _step(report, "predictions", ingest_predictions, conn, client, today - timedelta(days=1), date_to)
            _step(report, "odds", ingest_odds_feed, conn, client)
            _step(report, "context", collect_context, conn, client, 36 if mode == "daily" else 12,
                  400 if mode == "daily" else 120, mode == "daily", report)
            if mode == "daily":
                _step(report, "backfill", backfill_current_season, conn, client, today)
        except StopRun:
            pass
        finally:
            client.save_quota()
            report["quota"] = client.quota.summary()
            report["client_stats"] = dict(client.stats)

    if mode in ("daily", "refresh"):
        report["steps"]["superbet"] = superbet_step(conn, now, days_ahead=3 if mode == "daily" else 2,
                                                    max_requests=SUPERBET_CAP[mode])

    if mode == "closing":
        # captura de dinaintea startului (:50): consens BSD (delta) + Superbet pe meciurile din următoarele ~2 h
        if client is not None:
            try:
                _step(report, "odds", ingest_odds_feed, conn, client)
            except StopRun:
                pass
            finally:
                client.save_quota()
                report["quota"] = client.quota.summary()
        report["steps"]["superbet"] = superbet_step(conn, now, closing_only=True, max_requests=SUPERBET_CAP["closing"])
        report["steps"]["settle"] = settle_all(conn, now)
        report["finished_at"] = repo.now_iso()
        return report  # fără publicare: următorul refresh publică (DB-ul e salvat în release)

    if mode in ("daily", "refresh", "offline"):
        robot = Robot(conn, now=now)
        report["steps"]["robot"] = robot.run(today - timedelta(days=0), today + timedelta(days=days_ahead))
        report["steps"]["robot"]["history_matches"] = robot.n_history
        report["steps"]["settle"] = settle_all(conn, now)
        # biletele se generează o dată pe zi (prima rulare cu date); refresh-ul nu le rescrie,
        # doar le generează dacă lipsesc. „AZI NU” se reevaluează cât timp mai sunt meciuri.
        report["steps"]["tickets"] = build_horizon(conn, today, days_ahead, now, rebuild_today=rebuild_tickets,
                                                   refresh_future=mode == "daily" or rebuild_tickets)
        report["steps"]["pyramid"] = build_pyramid_day(conn, today, now)
    if mode == "learn":
        report["steps"]["settle"] = settle_all(conn, now)
        report["steps"]["learn"] = {k: v for k, v in learn(conn).items() if k != "params"}
        try:
            from betpredict.publish.weekly import save_weekly

            w = save_weekly(conn, today)  # luni: raportul săptămânii încheiate (după reantrenare)
            report["steps"]["weekly"] = {"id": w["id"], "notify": w["notify"]}
        except Exception as exc:  # noqa: BLE001
            report["warnings"].append({"step": "weekly", "error": str(exc)})

    publish_all(conn, out_root, today, days_back, days_ahead, report, mode)
    report["finished_at"] = repo.now_iso()
    return report
