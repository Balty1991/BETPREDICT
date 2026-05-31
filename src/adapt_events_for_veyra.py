"""
adapt_events_for_veyra.py — Construiește data/events.json + data/team_form_cache.json
pentru VEYRA din datele deja descărcate de pipeline-ul BETPREDICT.

Înlocuiește fetch_data_veyra.py (13+ minute) cu un adapter de secunde.
Surse: data/best_odds.json (odds) + data/predictions.json (probabilități BSD)
       data/team_form.json (formă echipe → team_form_cache.json pentru VEYRA).
"""
import json
from datetime import datetime, timezone
from pathlib import Path

DATA_DIR = Path("data")


def load_json(path, default=None):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def save_json(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, separators=(",", ":"))


def _form_score_from_string(form_str: str) -> float:
    """Calculează form_score din string W/D/L (ex: 'WWLLD')."""
    if not form_str:
        return 50.0
    pts = sum(3 if c == "W" else 1 if c == "D" else 0 for c in form_str.upper())
    return round(pts / (len(form_str) * 3) * 100, 1)


def _form_score(wins: int, draws: int, losses: int, sample: int) -> float:
    """PPG/3 * 100 — 0-100: 100=5W, 0=5L, ~67=3W1D1L."""
    if not sample:
        return 50.0
    ppg = (wins * 3 + draws) / sample
    return round(ppg / 3 * 100, 1)


def build_team_form_cache():
    """Construiește team_form_cache.json din team_form.json (sursă primară)
    și standings.json (sursă secundară — 853 echipe), pentru predict_current.py."""
    teams: dict = {}

    # ── Sursă secundară: standings.json (acoperire mare, date sezon) ────────
    standings_raw = load_json(DATA_DIR / "standings.json", {})
    for ldata in standings_raw.get("leagues", {}).values():
        played_season = 0
        for row in ldata.get("standings", []):
            tid = str(row.get("team_id", ""))
            if not tid:
                continue
            form_str  = row.get("form", "") or ""
            played_s  = int(row.get("played") or 0)
            gf_season = float(row.get("gf") or 0)

            teams[tid] = {
                "form_score":             _form_score_from_string(form_str),
                "form_string":            form_str,
                # Estimare avg_goals din statistici sezon (nu ultimele 5)
                "avg_goals_scored_last5": round(gf_season / played_s, 2) if played_s else 0,
                "avg_goals_conceded_last5": round(float(row.get("ga") or 0) / played_s, 2) if played_s else 0,
                "btts_last5":             0,
                "over15_pct":             0,
                "over25_pct":             0,
                "source":                 "standings",
            }

    # ── Sursă primară: team_form.json (ultimele 5 meciuri, mai precis) ──────
    raw = load_json(DATA_DIR / "team_form.json", {})
    for r in (raw.get("results", []) if isinstance(raw, dict) else []):
        tid = str(r.get("team_id", ""))
        if not tid:
            continue
        sample   = int(r.get("sample") or len(r.get("last_results", [])) or 0)
        wins     = int(r.get("wins", 0))
        draws    = int(r.get("draws", 0))
        losses   = int(r.get("losses", 0))
        form_str = r.get("form", "")
        avg_gf   = float(r.get("avg_gf") or 0)
        avg_ga   = float(r.get("avg_ga") or 0)
        btts_pct = float(r.get("btts_pct") or 0)

        # Suprascrie standings cu date mai precise (ultimele 5)
        teams[tid] = {
            "form_score":             _form_score(wins, draws, losses, sample),
            "form_string":            form_str,
            "avg_goals_scored_last5": avg_gf,
            "avg_goals_conceded_last5": avg_ga,
            "btts_last5":             round(btts_pct / 100 * sample, 1) if sample else 0,
            "over15_pct":             float(r.get("over15_pct") or 0),
            "over25_pct":             float(r.get("over25_pct") or 0),
            "wins":  wins, "draws": draws, "losses": losses, "sample": sample,
            "source": "team_form",
        }

    payload = {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "source":     "adapt_events_for_veyra (team_form.json + standings.json)",
        "count":      len(teams),
        "teams":      teams,
    }
    save_json(DATA_DIR / "team_form_cache.json", payload)
    from_tf  = sum(1 for t in teams.values() if t.get("source") == "team_form")
    from_std = len(teams) - from_tf
    print(f"team_form_cache.json scris: {len(teams)} echipe ({from_tf} team_form + {from_std} standings)")
    return len(teams)


def main():
    print("=== adapt_events_for_veyra: build events.json from existing data ===")

    # ── 0. Build team_form_cache.json pentru VEYRA ────────────────────────
    build_team_form_cache()

    # ── 1. Odds din best_odds.json ────────────────────────────────────────
    best_odds_raw = load_json(DATA_DIR / "best_odds.json", {})
    best_odds_list = best_odds_raw.get("results", []) if isinstance(best_odds_raw, dict) else []

    # Index per event_id (1x2 market only)
    odds_idx: dict = {}
    for row in best_odds_list:
        eid = str(row.get("event_id") or "")
        if not eid or row.get("market") not in ("1x2", "match_winner", None):
            continue
        if eid in odds_idx:
            continue  # keep first
        odds_idx[eid] = {
            "odds_home": row.get("home_odds") or row.get("odds_1"),
            "odds_draw": row.get("draw_odds") or row.get("odds_x"),
            "odds_away": row.get("away_odds") or row.get("odds_2"),
        }

    # ── 2. Probabilități BSD din predictions.json ─────────────────────────
    preds_raw = load_json(DATA_DIR / "predictions.json", {})
    preds_list = preds_raw.get("results", []) if isinstance(preds_raw, dict) else []

    # Build prediction lookup: {event_id_str: pred}
    pred_idx: dict = {}
    for p in preds_list:
        ev = p.get("event") or {}
        eid = str(ev.get("id") or p.get("event_id") or p.get("id") or "")
        if eid:
            pred_idx[eid] = p

    # ── 3. Construiește events din best_odds_list ─────────────────────────
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    events = []
    seen = set()

    for row in best_odds_list:
        eid = str(row.get("event_id") or "")
        if not eid or eid in seen:
            continue
        seen.add(eid)

        event_date = row.get("event_date", "")
        date_str = str(event_date)[:10]
        if date_str < today:
            continue  # trecut

        odds = odds_idx.get(eid, {})
        pred = pred_idx.get(eid, {})
        pred_ev = pred.get("event", {})
        mr = (pred.get("markets") or {}).get("match_result", {})

        event = {
            "event_id": int(eid) if eid.isdigit() else eid,
            "id": int(eid) if eid.isdigit() else eid,
            "event_date": event_date,
            "date": event_date,
            "status": "scheduled",
            "home_team": row.get("home_team") or pred_ev.get("home_team", ""),
            "away_team": row.get("away_team") or pred_ev.get("away_team", ""),
            "home_team_id": row.get("home_team_id") or pred_ev.get("home_team_id"),
            "away_team_id": row.get("away_team_id") or pred_ev.get("away_team_id"),
            "league_id": row.get("league_id") or pred_ev.get("league_id"),
            "league": row.get("league_name") or pred_ev.get("league_name", "Unknown"),
            "odds_home": odds.get("odds_home"),
            "odds_draw": odds.get("odds_draw"),
            "odds_away": odds.get("odds_away"),
            # Probabilități BSD (0-100)
            "home_win_probability": mr.get("prob_home"),
            "draw_probability": mr.get("prob_draw"),
            "away_win_probability": mr.get("prob_away"),
        }

        # Over/under din predictions markets
        ou = (pred.get("markets") or {}).get("over_under", {})
        if ou:
            event["over_25_probability"] = ou.get("prob_over_25")
            event["under_25_probability"] = ou.get("prob_under_25")
            event["over_15_probability"] = ou.get("prob_over_15")
            event["over_35_probability"] = ou.get("prob_over_35")

        btts = (pred.get("markets") or {}).get("btts", {})
        if btts:
            event["btts_probability"] = btts.get("prob_yes")

        events.append(event)

    # ── 4. Adaugă eventurile din predictions.json care nu sunt în best_odds
    for p in preds_list:
        ev = p.get("event") or {}
        eid = str(ev.get("id") or p.get("event_id") or p.get("id") or "")
        if not eid or eid in seen:
            continue
        event_date = ev.get("event_date", "")
        date_str = str(event_date)[:10]
        if date_str < today:
            continue
        seen.add(eid)
        mr = (p.get("markets") or {}).get("match_result", {})
        event = {
            "event_id": int(eid) if eid.isdigit() else eid,
            "id": int(eid) if eid.isdigit() else eid,
            "event_date": event_date,
            "date": event_date,
            "status": "scheduled",
            "home_team": ev.get("home_team", ""),
            "away_team": ev.get("away_team", ""),
            "home_team_id": ev.get("home_team_id"),
            "away_team_id": ev.get("away_team_id"),
            "league_id": ev.get("league_id"),
            "league": ev.get("league_name", "Unknown"),
            "odds_home": None,
            "odds_draw": None,
            "odds_away": None,
            "home_win_probability": mr.get("prob_home"),
            "draw_probability": mr.get("prob_draw"),
            "away_win_probability": mr.get("prob_away"),
        }
        events.append(event)

    out = {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "count": len(events),
        "results": events,
        "source": "adapt_events_for_veyra",
    }
    save_json(DATA_DIR / "events.json", out)
    with_odds = sum(1 for e in events if e.get("odds_home"))
    print(f"events.json scris: {len(events)} meciuri ({with_odds} cu cote 1x2)")


if __name__ == "__main__":
    main()
