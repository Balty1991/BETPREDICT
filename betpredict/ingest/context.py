"""Context pe meci din endpointurile Free: formă (/teams/{id}/form/), H2H (inclus în
/events/), clasament (/leagues/{id}/standings/), absențe (/teams/{id}/squad/).

Bugetul: doar meciurile din următoarele ~36h, cache pe disc (formă/lot 12h, clasament 6h),
plafon de echipe per rulare. Orice eroare de endpoint lasă contextul parțial, nu oprește run-ul.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from betpredict.ingest.bsd_client import BSDClient
from betpredict.ingest.errors import BSDError, BudgetExceeded, QuotaExhausted
from betpredict.ingest.normalize import as_int
from betpredict.ingest.quota import PRIORITY_LOW, PRIORITY_NORMAL
from betpredict.store import repo
from betpredict.timeutil import canon_utc

FORM_TTL = 12 * 3600
SQUAD_TTL = 12 * 3600
STANDINGS_TTL = 6 * 3600


def summarize_form(block: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not isinstance(block, dict) or not block.get("matches"):
        return None
    return {
        "played": block.get("matches"), "w": block.get("won"), "d": block.get("drawn"), "l": block.get("lost"),
        "gf": block.get("goals_for"), "ga": block.get("goals_against"),
        "ppm": block.get("points_per_match"), "sequence": (block.get("form") or "")[:10],
    }


def parse_form(payload: Any, venue: str) -> Optional[Dict[str, Any]]:
    if not isinstance(payload, dict):
        return None
    overall = summarize_form(payload.get("overall"))
    if not overall:
        return None
    overall["last"] = payload.get("requested") or overall["played"]
    side = summarize_form(payload.get(venue))
    if side:
        overall["venue"] = {"played": side["played"], "ppm": side["ppm"], "gf": side["gf"], "ga": side["ga"]}
    return overall


def parse_h2h(raw: Any) -> Optional[Dict[str, Any]]:
    if not isinstance(raw, dict) or not raw.get("total_matches"):
        return None
    recent = raw.get("recent_matches") or []
    goals = [(as_int(m.get("home_score")), as_int(m.get("away_score"))) for m in recent if isinstance(m, dict)]
    goals = [(h, a) for h, a in goals if h is not None and a is not None]
    n = len(goals)
    return {
        "total": raw.get("total_matches"), "home_wins": raw.get("home_wins"), "draws": raw.get("draws"),
        "away_wins": raw.get("away_wins"),
        "avg_goals": round(raw["avg_total_goals"], 2) if isinstance(raw.get("avg_total_goals"), (int, float)) else None,
        "over25_rate": round(sum(1 for h, a in goals if h + a > 2.5) / n, 2) if n else None,
        "btts_rate": round(sum(1 for h, a in goals if h > 0 and a > 0) / n, 2) if n else None,
        "recent": [{"date": str(m.get("date") or "")[:10], "home": m.get("home"), "away": m.get("away"),
                    "score": m.get("score")} for m in recent[:5] if isinstance(m, dict)],
    }


def parse_squad(payload: Any) -> List[Dict[str, Any]]:
    players = []
    if isinstance(payload, dict):
        players = payload.get("players") or payload.get("results") or payload.get("squad") or []
    elif isinstance(payload, list):
        players = payload
    out = []
    for p in players:
        if not isinstance(p, dict):
            continue
        status = p.get("availability") or "available"
        if status in ("injured", "doubtful", "suspended"):
            out.append({"player": p.get("short_name") or p.get("name"), "player_id": p.get("id") or p.get("player_id"),
                        "position": p.get("position"), "status": status, "reason": p.get("injury_type") or None,
                        "return": p.get("injury_expected_return")})
    return out


def parse_standings(payload: Any) -> Dict[int, Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    if isinstance(payload, dict):
        rows = list(payload.get("standings") or payload.get("results") or [])
        groups = payload.get("groups")
        if not rows and isinstance(groups, dict):
            for g in groups.values():
                if isinstance(g, list):
                    rows.extend(g)
    out: Dict[int, Dict[str, Any]] = {}
    total = len(rows)
    for r in rows:
        if not isinstance(r, dict):
            continue
        tid = as_int(r.get("team_id"))
        if tid is None:
            continue
        zone = r.get("zone") if isinstance(r.get("zone"), dict) else {}
        out[tid] = {"position": r.get("position"), "points": r.get("pts") or r.get("points"), "played": r.get("played"),
                    "gd": r.get("gd"), "form": r.get("form"), "zone": zone.get("type") or zone.get("key"),
                    "zone_label": zone.get("label"), "teams": total}
    return out


def collect_context(conn: sqlite3.Connection, client: BSDClient, hours_ahead: int = 36, max_teams: int = 400,
                    with_squads: bool = True, report: Optional[Dict[str, Any]] = None) -> Dict[str, int]:
    now = datetime.now(timezone.utc)
    lo, hi = canon_utc(now.isoformat()), canon_utc((now + timedelta(hours=hours_ahead)).isoformat())
    matches = conn.execute(
        "SELECT id, league_id, home_id, away_id, raw_json FROM match WHERE kickoff_utc >= ? AND kickoff_utc < ? "
        "AND (status IS NULL OR status IN ('notstarted','upcoming','scheduled')) ORDER BY kickoff_utc",
        (lo, hi),
    ).fetchall()
    stats = {"matches": len(matches), "forms": 0, "squads": 0, "standings": 0, "errors": 0}
    form_cache: Dict[tuple, Optional[Dict[str, Any]]] = {}
    squad_cache: Dict[int, List[Dict[str, Any]]] = {}
    standings_cache: Dict[int, Dict[int, Dict[str, Any]]] = {}
    teams_used = 0
    stop = False

    def safe(fn, *a, **k):
        nonlocal stop
        if stop:
            return None
        try:
            return fn(*a, **k)
        except (BudgetExceeded, QuotaExhausted) as exc:
            stop = True
            if report is not None:
                report.setdefault("warnings", []).append({"step": "context", "error": type(exc).__name__, "detail": str(exc)})
            return None
        except BSDError:
            stats["errors"] += 1
            return None

    for m in matches:
        ctx: Dict[str, Any] = {}
        raw = json.loads(m["raw_json"]) if m["raw_json"] else {}
        h2h = parse_h2h(raw.get("head_to_head"))
        if h2h:
            ctx["h2h"] = h2h
        lid = m["league_id"]
        if lid is not None and lid not in standings_cache:
            standings_cache[lid] = parse_standings(safe(client.get, f"leagues/{lid}/standings/", cache_ttl=STANDINGS_TTL)) or {}
            stats["standings"] += 1 if standings_cache[lid] else 0
        st = standings_cache.get(lid) or {}
        if st.get(m["home_id"]) or st.get(m["away_id"]):
            ctx["standings"] = {"home": st.get(m["home_id"]), "away": st.get(m["away_id"])}
        form: Dict[str, Any] = {}
        absences: Dict[str, Any] = {}
        for side, tid in (("home", m["home_id"]), ("away", m["away_id"])):
            if tid is None:
                continue
            key = (tid, side)
            if key not in form_cache:
                if teams_used >= max_teams:
                    form_cache[key] = None
                else:
                    teams_used += 1
                    payload = safe(client.get, f"teams/{tid}/form/", {"last": 10}, cache_ttl=FORM_TTL)
                    form_cache[key] = parse_form(payload, side)
                    stats["forms"] += 1 if form_cache[key] else 0
            if form_cache[key]:
                form[side] = form_cache[key]
            if with_squads:
                if tid not in squad_cache:
                    payload = safe(client.get, f"teams/{tid}/squad/", priority=PRIORITY_LOW, cache_ttl=SQUAD_TTL)
                    squad_cache[tid] = parse_squad(payload) if payload is not None else []
                    stats["squads"] += 1 if payload is not None else 0
                absences[side] = squad_cache[tid][:10]
        if form:
            ctx["form"] = form
        if any(absences.values()):
            ctx["absences"] = absences
        if ctx:
            with conn:
                conn.execute(
                    "INSERT INTO match_context(match_id, context_json, updated_at) VALUES (?,?,?) "
                    "ON CONFLICT(match_id) DO UPDATE SET context_json=excluded.context_json, updated_at=excluded.updated_at",
                    (m["id"], json.dumps(ctx, ensure_ascii=False), repo.now_iso()),
                )
    return stats


__all__ = ["collect_context", "parse_form", "parse_h2h", "parse_squad", "parse_standings", "PRIORITY_NORMAL"]
