"""CLI: ``python -m betpredict <comandă>``."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import date
from pathlib import Path
from typing import List, Optional

from betpredict import __version__
from betpredict.config import ROOT, Settings


def _print(obj) -> None:
    print(json.dumps(obj, ensure_ascii=False, indent=2, default=str))


def cmd_quota(args, settings: Settings) -> int:
    from betpredict.ingest.quota import QuotaTracker

    q = QuotaTracker(settings.quota_file, daily_quota=0 if settings.is_paid else settings.daily_quota,
                     reserve=settings.reserve)
    _print({"plan": settings.plan, "quota_file": str(settings.quota_file), **q.summary()})
    return 0


def cmd_db_init(args, settings: Settings) -> int:
    from betpredict.store import connect, init_db, table_counts

    conn = connect(args.db or settings.db_path)
    v = init_db(conn)
    _print({"db": str(args.db or settings.db_path), "schema_version": v, "tables": table_counts(conn)})
    return 0


def cmd_db_import_legacy(args, settings: Settings) -> int:
    from betpredict.store import connect, init_db
    from betpredict.store.legacy_import import import_legacy, legacy_overview

    conn = connect(args.db or settings.db_path)
    init_db(conn)
    res = import_legacy(conn, Path(args.data_dir))
    res["legacy_overview"] = legacy_overview(conn)
    _print(res)
    return 0


def cmd_db_export_parquet(args, settings: Settings) -> int:
    from betpredict.store import connect, init_db
    from betpredict.store.parquet import export_parquet

    conn = connect(args.db or settings.db_path)
    init_db(conn)
    _print(export_parquet(conn, Path(args.out)))
    return 0


def cmd_daily_build(args, settings: Settings) -> int:
    from betpredict.ingest.bsd_client import BSDClient
    from betpredict.pipeline.daily import run_daily_build
    from betpredict.store import connect, init_db

    if args.max_requests is not None:
        settings.max_requests_per_run = args.max_requests
    client = BSDClient(settings)
    if not client.has_key:
        print("EROARE: lipsește variabila de mediu BSD_API_KEY (secret GitHub Actions).", file=sys.stderr)
        return 2
    conn = connect(args.db or settings.db_path)
    init_db(conn)
    day = date.fromisoformat(args.date) if args.date else None
    report = run_daily_build(conn, client, Path(args.out), day=day, days_back=args.days_back,
                             days_ahead=args.days_ahead, with_odds=not args.no_odds)
    if args.report:
        Path(args.report).parent.mkdir(parents=True, exist_ok=True)
        Path(args.report).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    _print(report)
    return 0


def cmd_run(args, settings: Settings) -> int:
    from betpredict.ingest.bsd_client import BSDClient
    from betpredict.pipeline.run import run_pipeline
    from betpredict.store import connect, init_db

    if args.max_requests is not None:
        settings.max_requests_per_run = args.max_requests
    client = None
    if args.mode in ("daily", "refresh", "closing"):
        client = BSDClient(settings)
        if not client.has_key:
            print("EROARE: lipsește variabila de mediu BSD_API_KEY (secret GitHub Actions).", file=sys.stderr)
            return 2
    conn = connect(args.db or settings.db_path)
    init_db(conn)
    day = date.fromisoformat(args.date) if args.date else None
    report = run_pipeline(conn, args.mode, Path(args.out), client=client, today=day,
                          days_ahead=args.days_ahead, rebuild_tickets=args.rebuild_tickets)
    if args.report:
        Path(args.report).parent.mkdir(parents=True, exist_ok=True)
        Path(args.report).write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    _print({k: v for k, v in report.items() if k != "steps"} | {"steps": list(report["steps"].keys())})
    return 0


def cmd_backtest(args, settings: Settings) -> int:
    from betpredict.model.backtest import run_backtest
    from betpredict.store import connect, init_db

    conn = connect(args.db or settings.db_path)
    init_db(conn)
    res = run_backtest(conn, Path(args.warehouse), eval_from=args.eval_from, tune_from=args.tune_from,
                       out=Path(args.out) if args.out else None, quick=args.quick)
    _print({k: res[k] for k in ("model_only", "with_market", "roi", "adaptive_roi", "runtime_s")})
    return 0


def cmd_train(args, settings: Settings) -> int:
    from betpredict.model.v2 import fit_artifact, save_artifact, weekly_cycle
    from betpredict.store import connect, init_db

    conn = connect(args.db or settings.db_path)
    init_db(conn)
    if args.cycle:
        _print(weekly_cycle(conn))
        return 0
    art = fit_artifact(conn, cutoff=args.cutoff, holdout_days=args.holdout_days)
    if not args.dry_run:
        save_artifact(conn, art, "champion")
    _print({k: art[k] for k in ("engine", "trained_at", "train_to", "n_train", "metrics", "fit_seconds")})
    return 0


def cmd_publish_day(args, settings: Settings) -> int:
    from betpredict.publish.day import write_day
    from betpredict.store import connect, init_db
    from betpredict.timeutil import ro_today

    conn = connect(args.db or settings.db_path)
    init_db(conn)
    day = date.fromisoformat(args.date) if args.date else ro_today()
    print(write_day(conn, day, Path(args.out)))
    return 0


def cmd_site_assemble(args, settings: Settings) -> int:
    from betpredict.publish.site import assemble_site, scan_for_secrets

    info = assemble_site(Path(args.repo_root), Path(args.dist), Path(args.out),
                         api_dir=Path(args.api) if args.api else None, include_data=not args.no_data)
    hits = [h for h in scan_for_secrets(Path(args.out), extensions=(".js", ".html")) if not h.startswith("data/")]
    info["secret_scan_hits"] = hits
    _print(info)
    return 1 if hits else 0


def cmd_scan_secrets(args, settings: Settings) -> int:
    from betpredict.publish.site import scan_for_secrets

    hits: List[str] = []
    for p in args.paths:
        hits += [f"{p}/{h}" for h in scan_for_secrets(Path(p))]
    if hits:
        print("Posibilă expunere a cheii BSD în cod de browser:", file=sys.stderr)
        for h in hits:
            print("  -", h, file=sys.stderr)
        return 1
    print("OK: niciun tipar de cheie API în", ", ".join(args.paths))
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="betpredict", description="BETPREDICT 3.0 — Etapa 0 (fundație)")
    p.add_argument("--version", action="version", version=__version__)
    p.add_argument("-v", "--verbose", action="store_true")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("quota", help="contorul de cereri BSD de azi").set_defaults(fn=cmd_quota)

    db = sub.add_parser("db", help="bază de date SQLite").add_subparsers(dest="db_cmd", required=True)
    s = db.add_parser("init", help="creează/migrează schema")
    s.add_argument("--db")
    s.set_defaults(fn=cmd_db_init)
    s = db.add_parser("import-legacy", help="importă selection_journal.json + performance_summary.json")
    s.add_argument("--db")
    s.add_argument("--data-dir", default=str(ROOT / "data"))
    s.set_defaults(fn=cmd_db_import_legacy)
    s = db.add_parser("export-parquet", help="exportă tabelele principale în Parquet")
    s.add_argument("--db")
    s.add_argument("--out", required=True)
    s.set_defaults(fn=cmd_db_export_parquet)

    s = sub.add_parser("daily-build", help="program + predicții BSD + cote consens → DB → api/days")
    s.add_argument("--db")
    s.add_argument("--date", help="ziua din România (YYYY-MM-DD); implicit azi")
    s.add_argument("--days-back", type=int, default=1)
    s.add_argument("--days-ahead", type=int, default=2)
    s.add_argument("--no-odds", action="store_true")
    s.add_argument("--max-requests", type=int, default=None, help="plafon de cereri pentru această rulare")
    s.add_argument("--out", default="site_api")
    s.add_argument("--report")
    s.set_defaults(fn=cmd_daily_build)

    s = sub.add_parser("run", help="pipeline v3: daily | refresh | closing | learn | offline")
    s.add_argument("mode", choices=["daily", "refresh", "closing", "learn", "offline"])
    s.add_argument("--db")
    s.add_argument("--date", help="ziua din România (YYYY-MM-DD); implicit azi")
    s.add_argument("--out", default="site_api")
    s.add_argument("--max-requests", type=int, default=None)
    s.add_argument("--rebuild-tickets", action="store_true", help="regenerează manual biletele zilei")
    s.add_argument("--days-ahead", type=int, default=6, help="câte zile înainte se publică (implicit 6)")
    s.add_argument("--report")
    s.set_defaults(fn=cmd_run)

    s = sub.add_parser("backtest", help="Robot v2: backtest walk-forward pe istoric (logloss/Brier/ECE/ROI pe piață)")
    s.add_argument("--db")
    s.add_argument("--warehouse", default=str(ROOT / "data" / "warehouse"))
    s.add_argument("--eval-from", default="2024-07-01")
    s.add_argument("--tune-from", default="2023-07-01")
    s.add_argument("--out", default="backtest_v2.json")
    s.add_argument("--quick", action="store_true")
    s.set_defaults(fn=cmd_backtest)

    s = sub.add_parser("train", help="Robot v2: antrenează campionul (sau --cycle: campion vs challenger)")
    s.add_argument("--db")
    s.add_argument("--cutoff")
    s.add_argument("--holdout-days", type=float, default=0.0)
    s.add_argument("--cycle", action="store_true")
    s.add_argument("--dry-run", action="store_true")
    s.set_defaults(fn=cmd_train)

    s = sub.add_parser("publish-day", help="regenerează api/days/<zi>.json din DB")
    s.add_argument("--db")
    s.add_argument("--date")
    s.add_argument("--out", default="site_api")
    s.set_defaults(fn=cmd_publish_day)

    s = sub.add_parser("site-assemble", help="asamblează site-ul pentru gh-pages")
    s.add_argument("--repo-root", default=str(ROOT))
    s.add_argument("--dist", default=str(ROOT / "frontend" / "dist"))
    s.add_argument("--out", default="_site")
    s.add_argument("--api")
    s.add_argument("--no-data", action="store_true")
    s.set_defaults(fn=cmd_site_assemble)

    s = sub.add_parser("scan-secrets", help="verifică să nu existe cheia API în codul de browser")
    s.add_argument("paths", nargs="+")
    s.set_defaults(fn=cmd_scan_secrets)
    return p


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    return int(args.fn(args, Settings.from_env()) or 0)
