#!/usr/bin/env python3
"""BetPredict Player Intelligence v1.

Implementează endpointurile BSD API v2 pentru Players fără să atingă UI-ul:
- /api/v2/players/
- /api/v2/players/{id}/
- /api/v2/players/{id}/stats/
- /api/v2/players/{id}/transfers/
- /api/v2/players/{id}/career/
- /api/v2/players/{id}/national-team/

Script sigur pentru GitHub Actions:
- seed din team_squads/team_intelligence/predictions/signals;
- limitat prin env ca să nu rupă timeout-ul;
- scriere atomică;
- nu oprește workflow-ul dacă un endpoint dă 404/empty.
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple


ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
DEBUG_DIR = DATA_DIR / "debug"

BASE_V2 = os.environ.get("BSD_BASE_V2", "https://sports.bzzoiro.com/api/v2").rstrip("/")
API_KEY = os.environ.get("BSD_API_KEY", "").strip()

TEAM_LIMIT = int(os.environ.get("BETPREDICT_PLAYER_TEAM_LIMIT", "8") or 8)
PLAYER_LIMIT = int(os.environ.get("BETPREDICT_PLAYER_LIMIT", "32") or 32)
PLAYERS_PER_TEAM_LIMIT = int(os.environ.get("BETPREDICT_PLAYERS_PER_TEAM_LIMIT", "80") or 80)
STATS_LIMIT = int(os.environ.get("BETPREDICT_PLAYER_STATS_LIMIT", "120") or 120)
TRANSFERS_LIMIT = int(os.environ.get("BETPREDICT_PLAYER_TRANSFERS_LIMIT", "50") or 50)
HTTP_TIMEOUT = int(os.environ.get("BETPREDICT_PLAYER_HTTP_TIMEOUT", "15") or 15)
HTTP_SLEEP = float(os.environ.get("BETPREDICT_PLAYER_HTTP_SLEEP", "0.06") or 0.06)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_json(path: Path, default: Any) -> Any:
    try:
        if not path.exists():
            return default
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def as_int(value: Any) -> Optional[int]:
    try:
        if value is None or value == "":
            return None
        return int(value)
    except Exception:
        return None


def as_float(value: Any, default: Optional[float] = None) -> Optional[float]:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except Exception:
        return default


def compact_count(payload: Any) -> int:
    if isinstance(payload, list):
        return len(payload)
    if isinstance(payload, dict):
        if isinstance(payload.get("results"), list):
            return len(payload["results"])
        if isinstance(payload.get("players"), list):
            return len(payload["players"])
        if isinstance(payload.get("stats"), list):
            return len(payload["stats"])
        if isinstance(payload.get("seasons"), list):
            return len(payload["seasons"])
        if isinstance(payload.get("transfers"), list):
            return len(payload["transfers"])
        if "count" in payload:
            return as_int(payload.get("count")) or 0
        return 1 if payload else 0
    return 0


def extract_rows(payload: Any) -> List[Dict[str, Any]]:
    """Extrage lista relevantă din formele uzuale BSD."""
    if isinstance(payload, list):
        return [x for x in payload if isinstance(x, dict)]
    if not isinstance(payload, dict):
        return []
    for key in ("results", "players", "stats", "seasons", "transfers", "career", "items"):
        rows = payload.get(key)
        if isinstance(rows, list):
            return [x for x in rows if isinstance(x, dict)]
    return []


def short_payload(payload: Any, max_rows: int = 3) -> Any:
    """Versiune scurtă pentru debug, să nu umflăm fișierele."""
    if isinstance(payload, dict):
        out = dict(payload)
        for key in ("results", "players", "stats", "seasons", "transfers"):
            if isinstance(out.get(key), list):
                out[key] = out[key][:max_rows]
        return out
    if isinstance(payload, list):
        return payload[:max_rows]
    return payload


def request_json(path: str, params: Optional[Dict[str, Any]] = None, label: str = "") -> Tuple[Any, Dict[str, Any]]:
    """GET JSON cu raportare compactă. Nu aruncă excepții în sus."""
    params = {k: v for k, v in (params or {}).items() if v is not None and v != ""}
    query = urllib.parse.urlencode(params, doseq=True)
    url = f"{BASE_V2}{path}"
    if query:
        url = f"{url}?{query}"

    headers = {
        "Accept": "application/json",
        "User-Agent": "BetPredict-Player-Intelligence/1.0",
    }
    if API_KEY:
        headers["Authorization"] = f"Token {API_KEY}"

    started = time.time()
    meta: Dict[str, Any] = {
        "label": label or path,
        "path": path,
        "params": params,
        "ok": False,
        "status": None,
        "count": 0,
        "elapsed_ms": 0,
    }

    try:
        req = urllib.request.Request(url, headers=headers, method="GET")
        with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as resp:
            raw = resp.read()
            text = raw.decode("utf-8", errors="replace")
            payload = json.loads(text) if text.strip() else {}
            meta["ok"] = 200 <= int(resp.status) < 300
            meta["status"] = int(resp.status)
            meta["count"] = compact_count(payload)
            meta["elapsed_ms"] = int((time.time() - started) * 1000)
            if HTTP_SLEEP > 0:
                time.sleep(HTTP_SLEEP)
            return payload, meta
    except urllib.error.HTTPError as exc:
        meta["status"] = int(exc.code)
        meta["elapsed_ms"] = int((time.time() - started) * 1000)
        try:
            body = exc.read().decode("utf-8", errors="replace")
            meta["error"] = body[:240]
        except Exception:
            meta["error"] = str(exc)
        return {}, meta
    except Exception as exc:
        meta["status"] = "error"
        meta["elapsed_ms"] = int((time.time() - started) * 1000)
        meta["error"] = str(exc)[:240]
        return {}, meta


def player_id_from_row(row: Dict[str, Any]) -> Optional[int]:
    for key in ("id", "player_id"):
        pid = as_int(row.get(key))
        if pid:
            return pid
    player = row.get("player")
    if isinstance(player, dict):
        return as_int(player.get("id") or player.get("player_id"))
    return None


def player_name_from_row(row: Dict[str, Any]) -> str:
    player = row.get("player")
    if isinstance(player, dict):
        name = player.get("name") or player.get("short_name")
        if name:
            return str(name)
    return str(row.get("name") or row.get("short_name") or row.get("player_name") or "")


def seed_teams(limit: int = TEAM_LIMIT) -> List[Dict[str, Any]]:
    """Alege echipele unde merită să căutăm jucători."""
    teams: Dict[str, Dict[str, Any]] = {}

    def add(team_id: Any, name: Any, source: str, score: float = 1.0) -> None:
        tid = as_int(team_id)
        if not tid:
            return
        key = str(tid)
        row = teams.setdefault(key, {
            "team_id": tid,
            "name": name or f"Team {tid}",
            "sources": [],
            "priority_score": 0.0,
        })
        if source not in row["sources"]:
            row["sources"].append(source)
        row["priority_score"] += float(score or 0)
        if name and str(row.get("name", "")).startswith("Team "):
            row["name"] = name

    team_intel = read_json(DATA_DIR / "team_intelligence.json", {"results": []})
    for i, row in enumerate(team_intel.get("results", []) if isinstance(team_intel, dict) else []):
        add(row.get("team_id"), row.get("name"), "team_intelligence", 10.0 + max(0, 20 - i) / 2)

    team_squads = read_json(DATA_DIR / "team_squads.json", {"results": []})
    for i, row in enumerate(team_squads.get("results", []) if isinstance(team_squads, dict) else []):
        add(row.get("team_id"), row.get("name"), "team_squads", 8.0 + max(0, 20 - i) / 3)

    signals = read_json(DATA_DIR / "signals.json", {"signals": []})
    for i, row in enumerate(signals.get("signals", [])[:50] if isinstance(signals, dict) else []):
        add(row.get("home_team_id"), row.get("home_team"), "signals", 6.0 + max(0, 25 - i) / 8)
        add(row.get("away_team_id"), row.get("away_team"), "signals", 6.0 + max(0, 25 - i) / 8)

    preds = read_json(DATA_DIR / "predictions.json", {"results": []})
    rows = preds.get("results", []) if isinstance(preds, dict) else []
    for row in sorted(rows, key=lambda p: p.get("smartbet_score") or 0, reverse=True)[:50]:
        ev = row.get("event") if isinstance(row.get("event"), dict) else {}
        score = 2.0 + float(row.get("smartbet_score") or 0) / 20
        add(ev.get("home_team_id"), ev.get("home_team"), "predictions", score)
        add(ev.get("away_team_id"), ev.get("away_team"), "predictions", score)

    out = sorted(teams.values(), key=lambda x: x.get("priority_score") or 0, reverse=True)
    for row in out:
        row["priority_score"] = round(float(row.get("priority_score") or 0), 2)
    return out[:limit]


def seed_players_from_local_files() -> Dict[str, Dict[str, Any]]:
    players: Dict[str, Dict[str, Any]] = {}

    def add(row: Dict[str, Any], source: str, team_id: Any = None, team_name: Any = None, score: float = 1.0) -> None:
        pid = player_id_from_row(row)
        if not pid:
            return
        key = str(pid)
        item = players.setdefault(key, {
            "player_id": pid,
            "name": player_name_from_row(row) or f"Player {pid}",
            "team_ids": [],
            "team_names": [],
            "sources": [],
            "priority_score": 0.0,
            "seed": {},
        })
        if source not in item["sources"]:
            item["sources"].append(source)
        tid = as_int(team_id or row.get("team_id") or row.get("current_team_id"))
        if tid and tid not in item["team_ids"]:
            item["team_ids"].append(tid)
        if team_name and team_name not in item["team_names"]:
            item["team_names"].append(str(team_name))
        name = player_name_from_row(row)
        if name and str(item.get("name", "")).startswith("Player "):
            item["name"] = name
        item["priority_score"] += float(score or 0)
        # seed compact
        for k in ("position", "specific_position", "nationality", "jersey_number", "market_value_eur", "date_of_birth"):
            if row.get(k) is not None:
                item["seed"][k] = row.get(k)

    team_squads = read_json(DATA_DIR / "team_squads.json", {"results": []})
    for ti, squad in enumerate(team_squads.get("results", []) if isinstance(team_squads, dict) else []):
        team_id = squad.get("team_id")
        team_name = squad.get("name")
        for pi, p in enumerate(squad.get("players", []) if isinstance(squad, dict) else []):
            add(p, "team_squads", team_id, team_name, score=8.0 + max(0, 40 - pi) / 10 + max(0, 12 - ti) / 2)

    team_intel = read_json(DATA_DIR / "team_intelligence.json", {"results": []})
    for ti, team in enumerate(team_intel.get("results", []) if isinstance(team_intel, dict) else []):
        for pi, p in enumerate(team.get("squad_preview", []) if isinstance(team, dict) else []):
            add(p, "team_intelligence", team.get("team_id"), team.get("name"), score=5.0 + max(0, 12 - pi) / 8)

    return players


def enrich_players_from_api_list(players: Dict[str, Dict[str, Any]], teams: List[Dict[str, Any]], reports: List[Dict[str, Any]]) -> None:
    for team in teams:
        team_id = team.get("team_id")
        if not team_id:
            continue
        payload, meta = request_json(
            "/players/",
            {"team_id": team_id, "limit": PLAYERS_PER_TEAM_LIMIT},
            label=f"players_list_team_{team_id}",
        )
        reports.append(meta)
        for i, row in enumerate(extract_rows(payload)):
            pid = player_id_from_row(row)
            if not pid:
                continue
            key = str(pid)
            item = players.setdefault(key, {
                "player_id": pid,
                "name": player_name_from_row(row) or f"Player {pid}",
                "team_ids": [],
                "team_names": [],
                "sources": [],
                "priority_score": 0.0,
                "seed": {},
            })
            if "players_list" not in item["sources"]:
                item["sources"].append("players_list")
            tid = as_int(row.get("current_team_id") or row.get("team_id") or team_id)
            if tid and tid not in item["team_ids"]:
                item["team_ids"].append(tid)
            if team.get("name") and team["name"] not in item["team_names"]:
                item["team_names"].append(str(team["name"]))
            name = player_name_from_row(row)
            if name and str(item.get("name", "")).startswith("Player "):
                item["name"] = name
            item["priority_score"] += 7.0 + max(0, 40 - i) / 10 + float(team.get("priority_score") or 0) / 8
            for k in ("position", "specific_position", "nationality", "jersey_number", "market_value_eur", "contract_until", "date_of_birth", "current_team_id"):
                if row.get(k) is not None:
                    item["seed"][k] = row.get(k)


def pick_players(players: Dict[str, Dict[str, Any]], limit: int = PLAYER_LIMIT) -> List[Dict[str, Any]]:
    out = sorted(players.values(), key=lambda x: x.get("priority_score") or 0, reverse=True)
    for row in out:
        row["priority_score"] = round(float(row.get("priority_score") or 0), 2)
        row["team_ids"] = row.get("team_ids", [])[:4]
        row["team_names"] = row.get("team_names", [])[:4]
    return out[:limit]


def profile_summary(detail: Dict[str, Any], seed: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "player_id": seed.get("player_id"),
        "name": detail.get("name") or seed.get("name"),
        "short_name": detail.get("short_name"),
        "position": detail.get("position") or seed.get("seed", {}).get("position"),
        "specific_position": detail.get("specific_position") or seed.get("seed", {}).get("specific_position"),
        "jersey_number": detail.get("jersey_number") or seed.get("seed", {}).get("jersey_number"),
        "date_of_birth": detail.get("date_of_birth") or seed.get("seed", {}).get("date_of_birth"),
        "height_cm": detail.get("height_cm"),
        "weight_kg": detail.get("weight_kg"),
        "preferred_foot": detail.get("preferred_foot"),
        "nationality": detail.get("nationality") or seed.get("seed", {}).get("nationality"),
        "current_team_id": detail.get("current_team_id") or (seed.get("team_ids") or [None])[0],
        "national_team_id": detail.get("national_team_id"),
        "market_value_eur": detail.get("market_value_eur") or seed.get("seed", {}).get("market_value_eur"),
        "contract_until": detail.get("contract_until") or seed.get("seed", {}).get("contract_until"),
        "availability": detail.get("availability"),
    }


def main() -> int:
    print("\n[Player Intelligence v1] BSD API v2 players...")
    DEBUG_DIR.mkdir(parents=True, exist_ok=True)

    if not API_KEY:
        debug = {
            "updated_at": now_iso(),
            "source": "player_intelligence_v1",
            "error": "BSD_API_KEY missing; skipped safely",
            "players_requested": 0,
            "players_saved": 0,
        }
        write_json(DEBUG_DIR / "player_intelligence_debug.json", debug)
        print("  ⚠ BSD_API_KEY lipsă — skip sigur.")
        return 0

    reports: List[Dict[str, Any]] = []
    teams = seed_teams(TEAM_LIMIT)
    local_players = seed_players_from_local_files()
    local_count = len(local_players)

    enrich_players_from_api_list(local_players, teams, reports)
    players = pick_players(local_players, PLAYER_LIMIT)

    profiles: List[Dict[str, Any]] = []
    stats_profiles: List[Dict[str, Any]] = []
    transfers_rows: List[Dict[str, Any]] = []
    career_rows: List[Dict[str, Any]] = []
    national_rows: List[Dict[str, Any]] = []
    combined: List[Dict[str, Any]] = []
    player_reports: List[Dict[str, Any]] = []

    for i, seed in enumerate(players):
        pid = seed.get("player_id")
        if not pid:
            continue
        print(f"  → player {pid}: {seed.get('name', '—')}")

        detail_payload, detail_meta = request_json(f"/players/{pid}/", label=f"player_detail_{pid}")
        stats_payload, stats_meta = request_json(f"/players/{pid}/stats/", {"limit": STATS_LIMIT}, label=f"player_stats_{pid}")
        transfers_payload, transfers_meta = request_json(f"/players/{pid}/transfers/", {"limit": TRANSFERS_LIMIT}, label=f"player_transfers_{pid}")
        career_payload, career_meta = request_json(f"/players/{pid}/career/", label=f"player_career_{pid}")
        national_payload, national_meta = request_json(f"/players/{pid}/national-team/", label=f"player_national_team_{pid}")

        reports.extend([detail_meta, stats_meta, transfers_meta, career_meta, national_meta])

        detail = detail_payload if isinstance(detail_payload, dict) else {}
        summary = profile_summary(detail, seed)
        name = summary.get("name") or seed.get("name") or f"Player {pid}"

        stats_list = extract_rows(stats_payload)
        transfers_list = extract_rows(transfers_payload)
        career_list = extract_rows(career_payload)
        national_count = compact_count(national_payload)

        profile_row = {
            **summary,
            "seed": seed,
            "detail": detail,
        }
        stats_row = {
            "player_id": pid,
            "name": name,
            "count": len(stats_list),
            "results": stats_list[:STATS_LIMIT],
            "raw_shape": "results" if stats_list else ("dict" if isinstance(stats_payload, dict) and stats_payload else "empty"),
        }
        transfers_row = {
            "player_id": pid,
            "name": name,
            "count": len(transfers_list),
            "results": transfers_list[:TRANSFERS_LIMIT],
        }
        career_row = {
            "player_id": pid,
            "name": name,
            "count": len(career_list),
            "seasons": career_list,
            "raw": career_payload if isinstance(career_payload, dict) and not career_list else None,
        }
        national_row = {
            "player_id": pid,
            "name": name,
            "count": national_count,
            "national_team": national_payload if isinstance(national_payload, dict) else {},
        }

        combined_row = {
            "player_id": pid,
            "name": name,
            "position": summary.get("position"),
            "specific_position": summary.get("specific_position"),
            "nationality": summary.get("nationality"),
            "current_team_id": summary.get("current_team_id"),
            "market_value_eur": summary.get("market_value_eur"),
            "availability": summary.get("availability"),
            "sources": seed.get("sources", []),
            "priority_score": seed.get("priority_score"),
            "profile": {k: v for k, v in summary.items() if v is not None},
            "stats_count": len(stats_list),
            "transfers_count": len(transfers_list),
            "career_count": len(career_list),
            "national_team_available": bool(national_payload),
            "stats_preview": stats_list[:5],
            "transfer_preview": transfers_list[:5],
            "career_preview": career_list[:5],
            "national_team": national_row["national_team"],
        }

        profiles.append(profile_row)
        stats_profiles.append(stats_row)
        transfers_rows.append(transfers_row)
        career_rows.append(career_row)
        national_rows.append(national_row)
        combined.append(combined_row)

        player_reports.append({
            "player_id": pid,
            "name": name,
            "detail_status": detail_meta.get("status"),
            "stats_status": stats_meta.get("status"),
            "transfers_status": transfers_meta.get("status"),
            "career_status": career_meta.get("status"),
            "national_status": national_meta.get("status"),
            "detail_count": detail_meta.get("count"),
            "stats_count": len(stats_list),
            "transfers_count": len(transfers_list),
            "career_count": len(career_list),
            "national_count": national_count,
        })

    summary = {
        "teams_seeded": len(teams),
        "players_from_local_files": local_count,
        "players_selected": len(players),
        "players_saved": len(combined),
        "with_detail": sum(1 for r in player_reports if (r.get("detail_count") or 0) > 0),
        "with_stats": sum(1 for r in player_reports if (r.get("stats_count") or 0) > 0),
        "with_transfers": sum(1 for r in player_reports if (r.get("transfers_count") or 0) > 0),
        "with_career": sum(1 for r in player_reports if (r.get("career_count") or 0) > 0),
        "with_national_team": sum(1 for r in player_reports if (r.get("national_count") or 0) > 0),
        "endpoint_ok": sum(1 for r in reports if r.get("ok") and (r.get("count") or 0) > 0),
        "endpoint_empty": sum(1 for r in reports if r.get("ok") and (r.get("count") or 0) == 0),
        "endpoint_404": sum(1 for r in reports if r.get("status") == 404),
        "endpoint_errors": sum(1 for r in reports if not r.get("ok") and r.get("status") != 404),
    }

    stamp = now_iso()
    write_json(DATA_DIR / "player_intelligence.json", {
        "updated_at": stamp,
        "source": "player_intelligence_v1",
        "count": len(combined),
        "summary": summary,
        "results": combined,
    })
    write_json(DATA_DIR / "player_profiles.json", {
        "updated_at": stamp,
        "source": "player_profiles_v1",
        "count": len(profiles),
        "results": profiles,
    })
    write_json(DATA_DIR / "player_stats_profiles.json", {
        "updated_at": stamp,
        "source": "player_stats_profiles_v1",
        "count": len(stats_profiles),
        "results": stats_profiles,
    })
    write_json(DATA_DIR / "player_transfers.json", {
        "updated_at": stamp,
        "source": "player_transfers_v1",
        "count": len(transfers_rows),
        "results": transfers_rows,
    })
    write_json(DATA_DIR / "player_careers.json", {
        "updated_at": stamp,
        "source": "player_careers_v1",
        "count": len(career_rows),
        "results": career_rows,
    })
    write_json(DATA_DIR / "player_national_teams.json", {
        "updated_at": stamp,
        "source": "player_national_teams_v1",
        "count": len(national_rows),
        "results": national_rows,
    })
    write_json(DEBUG_DIR / "player_intelligence_debug.json", {
        "updated_at": stamp,
        "source": "player_intelligence_v1",
        "base_url": BASE_V2,
        "limits": {
            "team_limit": TEAM_LIMIT,
            "player_limit": PLAYER_LIMIT,
            "players_per_team_limit": PLAYERS_PER_TEAM_LIMIT,
            "stats_limit": STATS_LIMIT,
            "transfers_limit": TRANSFERS_LIMIT,
        },
        "summary": summary,
        "teams": teams,
        "player_reports": player_reports,
        "endpoint_reports_sample": reports[:120],
        "notes": [
            "players list is queried by team_id for priority teams only, not global full index.",
            "workflow continues even if some player subresources are empty or 404.",
            "UI integration can be added later from player_intelligence.json and player_profiles.json.",
        ],
    })

    print(
        "Player Intelligence: "
        f"players={summary['players_saved']} "
        f"detail={summary['with_detail']} "
        f"stats={summary['with_stats']} "
        f"career={summary['with_career']} "
        f"national={summary['with_national_team']} "
        f"errors={summary['endpoint_errors']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
