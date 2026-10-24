"""Orchestrare v3: ``python -m betpredict run {daily|refresh|learn|offline}``.

  daily   (03:07 UTC / 06:07 RO)  istoric/legacy (o dată), events ±zile, predicții BSD, cote, context,
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


SUPERBET_CAP = {"daily": 150, "refresh": 100, "closing": 40}  # refresh: și meciurile biletelor active fără id-uri Superbet


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
    try:
        from betpredict.ingest.boosts import today_doc
        from betpredict.publish.day import write_json as _wj

        _wj(out_root / "api" / "boosts" / "today.json", today_doc(conn))
        from betpredict.ingest.boosts import history_doc

        _wj(out_root / "api" / "boosts" / "history.json", history_doc(conn))
        from betpredict.experimental.supersocial import today_doc as ss_today

        _wj(out_root / "api" / "supersocial" / "today.json", ss_today(conn))
        from betpredict.builder.pattern80 import pattern_doc

        _wj(out_root / "api" / "stats" / "pattern80.json", pattern_doc(conn))
        from betpredict.experimental.supersocial import generator_doc

        _wj(out_root / "api" / "supersocial" / "generator.json", generator_doc(conn))
        from betpredict.builder.v4tickets import positive_markets
        from betpredict.experimental.supersocial import positive_keys

        # piețele cu ROI pozitiv pe rezultatele reale (pentru generator: „doar piețe pe plus”)
        _wj(out_root / "api" / "stats" / "positive_markets.json", {
            "stil": positive_keys(conn), "main": [{"market": k, "band": b, **v} for (k, b), v in positive_markets(conn).items()]})
        from betpredict.lab.segments import doc as segments_doc

        # profilurile de meci în care fiecare piață iese pe plus + meciurile de azi care se potrivesc
        _wj(out_root / "api" / "stats" / "segments.json", segments_doc(conn))
        from betpredict.experimental.supersocial import health_doc

        _wj(out_root / "api" / "stats" / "market_health.json", health_doc(conn))
        from betpredict.experimental.supersocial import clv_doc

        _wj(out_root / "api" / "stats" / "clv_strategy.json", clv_doc(conn))
        try:  # Superbet peste prețul corect Pinnacle (alerte + istoricul lor)
            from betpredict.publish.value_alerts import publish as va_publish

            _wj(out_root / "api" / "alerts" / "value.json", va_publish(conn))
        except sqlite3.OperationalError as exc:
            print(f"alerte valoare: {exc}")
        from betpredict.experimental.supersocial import history_doc as ss_history

        _wj(out_root / "api" / "supersocial" / "history.json", ss_history(conn))
        from betpredict.builder.test_tickets import stats_doc as test_stats

        _wj(out_root / "api" / "stats" / "test_tickets.json", test_stats(conn))
        from betpredict.experimental.supersocial import results_doc as ss_results

        _wj(out_root / "api" / "supersocial" / "results.json", ss_results(conn))
        from betpredict.publish.audit import audit_doc

        _wj(out_root / "api" / "stats" / "audit.json", audit_doc(conn))
        from betpredict.experimental.tipsters import report as tipsters_report

        _wj(out_root / "api" / "supersocial" / "tipsters.json", tipsters_report(conn))
        from betpredict.ingest.sb_catalog import doc as catalog_doc

        _wj(out_root / "api" / "supersocial" / "markets.json", catalog_doc(conn))
        from betpredict.lab.markets import load as markets_lab_doc

        ml = markets_lab_doc(conn)
        if ml:
            _wj(out_root / "api" / "lab" / "markets.json", ml)
    except Exception as exc:  # noqa: BLE001
        report["warnings"].append({"step": "boosts_publish", "error": f"{type(exc).__name__}: {exc}"})
    publish_journal(conn, out_root, today)
    publish_robot(conn, out_root, days_ahead=days_ahead)
    try:
        from betpredict.publish.weekly import publish_weekly

        publish_weekly(conn, out_root, today)
    except Exception as exc:  # noqa: BLE001
        report.setdefault("warnings", []).append({"step": "weekly_publish", "error": str(exc)})
    if step in ("daily", "offline"):
      try:  # v4: Bet Builder informativ (doar la rularea zilnică — refresh-ul rămâne rapid) + piețe experimentale + SuperAvantaj (azi și următoarele 2 zile)
        from betpredict.builder.betbuilder import publish_builder

        publish_builder(conn, out_root, [today + timedelta(days=o) for o in range(0, min(2, days_ahead) + 1)])
      except Exception as exc:  # noqa: BLE001
        report.setdefault("warnings", []).append({"step": "builder_publish", "error": str(exc)})
    else:
        try:
            from betpredict.builder.betbuilder import republish_cached

            republish_cached(conn, out_root, [today + timedelta(days=o) for o in range(0, 3)])
        except Exception as exc:  # noqa: BLE001
            report.setdefault("warnings", []).append({"step": "builder_republish", "error": str(exc)})
    try:
        from betpredict.experimental import track as EXP

        if step == "learn":
            EXP.settle(conn)  # cornerele/cartonașele vin din football-data (săptămânal)
        EXP.publish(conn, out_root, [today + timedelta(days=o) for o in range(-2, 3)])
    except Exception as exc:  # noqa: BLE001
        report.setdefault("warnings", []).append({"step": "experimental_publish", "error": str(exc)})
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
    import sys as _sys
    import time as _time
    _t0 = [_time.time()]
    report["timings"] = {}

    def tick(name: str) -> None:  # durata fiecărei etape (în raport + stderr, ca să se vadă în logul Actions)
        now_t = _time.time()
        report["timings"][name] = round(now_t - _t0[0], 1)
        print(f"[timing] {name}: {now_t - _t0[0]:.1f}s", file=_sys.stderr, flush=True)
        _t0[0] = now_t

    if client is not None and mode in ("daily", "refresh"):
        date_from = today - timedelta(days=days_back)
        fetch_ahead = days_ahead if mode == "daily" else min(days_ahead, REFRESH_FETCH_AHEAD)
        date_to = today + timedelta(days=fetch_ahead + 1)
        try:
            _step(report, "events", ingest_events, conn, client, date_from, date_to)
            _step(report, "predictions", ingest_predictions, conn, client, today - timedelta(days=1), date_to)
            if getattr(getattr(client, "settings", None), "is_paid", False):  # Unlimited: Pinnacle (cu deschidere) + grilă multi-casă → consens propriu
                from betpredict.ingest.multibook import collect_lineups, ingest_comparison

                _step(report, "odds", ingest_odds_feed, conn, client, bookmaker="pinnacle")
                _step(report, "multibook", ingest_comparison, conn, client, 72 if mode == "daily" else 36,
                      400 if mode == "daily" else 200)
                _step(report, "lineups", collect_lineups, conn, client, 2.0)
                from betpredict.ingest.corners import collect as collect_corners

                _step(report, "corners", collect_corners, conn, client, 3, 600 if mode == "daily" else 150)
                from betpredict.ingest.cards import collect as collect_cards

                _step(report, "cards", collect_cards, conn, client, 3, 600 if mode == "daily" else 150)
                _step(report, "context", collect_context, conn, client, 48 if mode == "daily" else 24,
                      400 if mode == "daily" else 250, mode == "daily", report)
            else:
                _step(report, "odds", ingest_odds_feed, conn, client)
                _step(report, "context", collect_context, conn, client, 72 if mode == "daily" else 24,
                      280 if mode == "daily" else 150, mode == "daily", report)
            if mode == "daily":
                _step(report, "backfill", backfill_current_season, conn, client, today)
        except StopRun:
            pass
        finally:
            client.save_quota()
    if mode in ("daily", "refresh"):
        from betpredict.ingest.apifootball import collect as collect_af

        try:  # cornere/cartonașe lipsă + absenți (doar cu APIFOOTBALL_KEY); o eroare aici nu oprește rularea
            _step(report, "apifootball", collect_af, conn)
        except Exception as exc:  # noqa: BLE001
            report["warnings"].append({"step": "apifootball", "error": type(exc).__name__, "detail": str(exc)})
            report["quota"] = client.quota.summary()
            report["client_stats"] = dict(client.stats)
            tick("bsd")

    if mode in ("daily", "refresh"):
        report["steps"]["superbet"] = superbet_step(conn, now, days_ahead=3 if mode == "daily" else 2,
                                                    max_requests=SUPERBET_CAP[mode])
        tick("superbet")

    if mode == "closing":
        # captura de dinaintea startului (:50): consens BSD (delta) + Superbet pe meciurile din următoarele ~2 h
        if client is not None:
            try:
                if getattr(getattr(client, "settings", None), "is_paid", False):
                    from betpredict.ingest.multibook import collect_lineups, ingest_comparison

                    _step(report, "odds", ingest_odds_feed, conn, client, bookmaker="pinnacle")
                    _step(report, "multibook", ingest_comparison, conn, client, 3, 80)
                    _step(report, "lineups", collect_lineups, conn, client, 1.5)
                else:
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
        from betpredict import selflearn

        if mode == "daily":  # autoînvățare zilnică (o dată pe zi, idempotent): recalibrare, segmente CLV/ROI, tuning bilete
            try:
                settle_all(conn, now)
                dl = selflearn.daily_learn(conn, today)
                report["steps"]["selflearn"] = {k: (v if k != "changes" else len(v)) for k, v in dl.items()}
                print(f"[selflearn] {report['steps']['selflearn']}", file=_sys.stderr, flush=True)
                from betpredict.builder.pyramid_auto import review as pyramid_review

                report["steps"]["pyramid_rules"] = pyramid_review(conn)  # campion/challenger regula de retragere
            except Exception as exc:  # noqa: BLE001 — învățarea nu oprește pipeline-ul
                report["warnings"].append({"step": "selflearn", "error": f"{type(exc).__name__}: {exc}"})
            tick("selflearn")
        selflearn.activate(conn)  # parametrii tunați pentru buildere (Biletul zilei, piramidă, Super bilete)
        robot = Robot(conn, now=now)
        report["steps"]["robot"] = robot.run(today - timedelta(days=0), today + timedelta(days=days_ahead))
        report["steps"]["robot"]["history_matches"] = robot.n_history
        tick("robot")
        report["steps"]["settle"] = settle_all(conn, now)
        tick("settle")
        # biletele se generează o dată pe zi (prima rulare cu date); refresh-ul nu le rescrie,
        # doar le generează dacă lipsesc. „AZI NU” se reevaluează cât timp mai sunt meciuri.
        report["steps"]["tickets"] = build_horizon(conn, today, days_ahead, now, rebuild_today=rebuild_tickets,
                                                   refresh_future=mode == "daily" or rebuild_tickets)
        tick("tickets")
        report["steps"]["pyramid"] = build_pyramid_day(conn, today, now)
        try:  # Piramida 1.40 (paralelă, stare separată)
            from betpredict.builder.pyramid import build_pyramid_140_day

            report["steps"]["pyramid140"] = build_pyramid_140_day(conn, today, now)
        except Exception as exc:  # noqa: BLE001
            report["steps"]["pyramid140"] = {"error": str(exc)}
        for _k, _fn in (("pyramid120", "build_pyramid_120_day"), ("pyramid160", "build_pyramid_160_day"), ("pyramid_boost", "build_pyramid_boost_day")):
            try:  # Piramidele sigure 1.20 și 1.60 (paralele, stare separată)
                from betpredict.builder import pyramid as _PY

                report["steps"][_k] = getattr(_PY, _fn)(conn, today, now)
            except Exception as exc:  # noqa: BLE001
                report["steps"][_k] = {"error": str(exc)}
        try:  # pornire curată a piramidelor păstrate (o singură dată): biletul de azi = treapta 1
            from betpredict.builder import pyramid as _PY

            report["steps"]["pyramid_reset"] = _PY.reset_tracks(conn, today, {
                "pyramid120": _PY.RULES_120, "pyramid140": _PY.RULES_140, "pyramid160": _PY.RULES_160, "pyramidboost": _PY.RULES_BOOST})
        except Exception as exc:  # noqa: BLE001
            report["steps"]["pyramid_reset"] = {"error": str(exc)}
        try:  # Piramida 2.00 Ligi mici
            from betpredict.builder.pyramid import build_pyramid_mici_day

            report["steps"]["pyramid_mici"] = build_pyramid_mici_day(conn, today, now)
        except Exception as exc:  # noqa: BLE001
            report["steps"]["pyramid_mici"] = {"error": str(exc)}
        for _k, _fn in (("pyramid_r5", "build_r5_day"), ("pyramid_r10", "build_r10_day")):
            try:  # piramide riscante ~5 / ~10 (adaptive, fără oprire după pierderi)
                from betpredict.builder import pyramid_risk as _PR

                report["steps"][_k] = getattr(_PR, _fn)(conn, today, now)
            except Exception as exc:  # noqa: BLE001
                report["steps"][_k] = {"error": str(exc)}
        try:  # cote mărite Superbet: probabilitate corectă + EV, decontare, bilet „Cote mărite +EV”
            from betpredict.ingest import boosts as BO

            report["steps"]["boosts"] = {"evaluated": BO.evaluate(conn), "settled": BO.settle(conn), "ticket": BO.build_ticket(conn, today, now)}
        except Exception as exc:  # noqa: BLE001
            report["warnings"].append({"step": "boosts", "error": f"{type(exc).__name__}: {exc}"})
        try:  # „Tiparul 80%+”: bilete scurte din predicțiile clasice ≥ 80% pe piețele care au ieșit pe plus
            from betpredict.builder.pattern80 import build as build_p80

            report["steps"]["pattern80"] = build_p80(conn, today, now)
        except Exception as exc:  # noqa: BLE001
            report["warnings"].append({"step": "pattern80", "error": f"{type(exc).__name__}: {exc}"})
        try:  # „Meciuri potrivite”: bilete din selecțiile care cad în profilurile de meci pe plus
            from betpredict.builder.segment_tickets import build as build_seg

            report["steps"]["segment_tickets"] = build_seg(conn, today, now)
        except Exception as exc:  # noqa: BLE001
            report["warnings"].append({"step": "segment_tickets", "error": f"{type(exc).__name__}: {exc}"})
        try:  # „O singură piață”: bilete de ~100 dintr-o singură piață pe multe meciuri (urmărite pe hârtie)
            from betpredict.builder.mono_tickets import build as build_mono

            report["steps"]["mono_tickets"] = build_mono(conn, today, now)
        except Exception as exc:  # noqa: BLE001
            report["warnings"].append({"step": "mono_tickets", "error": f"{type(exc).__name__}: {exc}"})
        try:  # rubrica „Test”: 10–20 de bilete pe zi în stilul Supersocial, ca să vedem câte prindem la volum mare
            from betpredict.builder.test_tickets import build as build_test

            report["steps"]["test_tickets"] = build_test(conn, today, now)
        except Exception as exc:  # noqa: BLE001
            report["warnings"].append({"step": "test_tickets", "error": f"{type(exc).__name__}: {exc}"})
        try:  # piețe experimentale (doar urmărite, nerecomandate)
            from betpredict.experimental import track as EXP

            report["steps"]["experimental"] = {**EXP.generate(conn, [today + timedelta(days=o) for o in range(0, 3)], now),
                                               **EXP.settle(conn)}
        except Exception as exc:  # noqa: BLE001
            report["warnings"].append({"step": "experimental", "error": f"{type(exc).__name__}: {exc}"})
    if mode == "learn":
        try:  # v4: cote istorice deschidere/închidere + cornere/pauză (football-data.co.uk), săptămânal
            from betpredict.ingest.footballdata import ingest_footballdata

            report["steps"]["footballdata"] = ingest_footballdata(conn, today)
        except Exception as exc:  # noqa: BLE001
            report["warnings"].append({"step": "footballdata", "error": str(exc)})
        try:  # laboratorul de piețe pe istoric (football-data), rezultat păstrat în DB și publicat la fiecare rulare
            from betpredict.lab.markets import run_db as markets_lab

            report["steps"]["markets_lab"] = markets_lab(conn, log=lambda *_: None)
        except Exception as exc:  # noqa: BLE001
            report["warnings"].append({"step": "markets_lab", "error": f"{type(exc).__name__}: {exc}"})
        report["steps"]["settle"] = settle_all(conn, now)
        report["steps"]["learn"] = {k: v for k, v in learn(conn).items() if k != "params"}
        try:
            from betpredict.publish.weekly import save_weekly

            w = save_weekly(conn, today)  # luni: raportul săptămânii încheiate (după reantrenare)
            report["steps"]["weekly"] = {"id": w["id"], "notify": w["notify"]}
        except Exception as exc:  # noqa: BLE001
            report["warnings"].append({"step": "weekly", "error": str(exc)})

    publish_all(conn, out_root, today, days_back, days_ahead, report, mode)
    tick("publish")
    report["finished_at"] = repo.now_iso()
    return report
