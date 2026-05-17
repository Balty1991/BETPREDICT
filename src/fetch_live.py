#!/usr/bin/env python3
"""
BetPredict Pro — Live Scores Fetcher
======================================
Rulează la fiecare 5 minute via GitHub Actions.
Endpoint: GET /api/v2/events/live/
"""

import os
import json
import requests
import sys
from datetime import datetime, timezone
from pathlib import Path

API_KEY  = os.environ.get("BSD_API_KEY", "")
BASE_V2  = "https://sports.bzzoiro.com/api/v2"
HEADERS  = {"Authorization": f"Token {API_KEY}"}
DATA_DIR = Path(__file__).parent.parent / "data"

# Ligi urmărite (filtrare opțională)
WATCHED_LEAGUE_IDS = {1, 2, 3, 4, 5, 6, 7, 8, 10, 23}

def fetch_live():
    print("🔴 Live Scores...")
    
    try:
        r = requests.get(
            f"{BASE_V2}/events/live/",
            headers=HEADERS,
            timeout=30
        )
        r.raise_for_status()
        data = r.json()
    except requests.exceptions.HTTPError as e:
        print(f"  ✗ HTTP {e.response.status_code}")
        if e.response.status_code == 401:
            print("  ⚠ API key invalidă!")
        _save_empty()
        return
    except Exception as e:
        print(f"  ✗ Eroare: {e}")
        _save_empty()
        return
    
    # BSD v2 live returnează {"events": [...]} sau {"results": [...]}
    events = data.get("events", data.get("results", []))
    
    # Normalizează câmpurile
    normalized = []
    for ev in events:
        # Câmpuri standard
        ev.setdefault("home_score", ev.get("score_home") or ev.get("home_goals") or 0)
        ev.setdefault("away_score", ev.get("score_away") or ev.get("away_goals") or 0)
        ev.setdefault("minute",     ev.get("time_elapsed") or ev.get("time") or 0)
        
        # Filtrează opțional după ligile urmărite
        league_id = (ev.get("league", {}).get("id") if isinstance(ev.get("league"), dict)
                     else ev.get("league_id"))
        
        if not WATCHED_LEAGUE_IDS or league_id in WATCHED_LEAGUE_IDS:
            normalized.append(ev)
    
    _save(normalized)

def _save(events):
    DATA_DIR.mkdir(exist_ok=True)
    path = DATA_DIR / "live.json"
    tmp  = path.with_suffix(".tmp")
    
    output = {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "count":      len(events),
        "events":     events
    }
    
    tmp.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)
    print(f"  ✓ live.json ({len(events)} meciuri live)")

def _save_empty():
    _save([])

if __name__ == "__main__":
    if not API_KEY:
        print("✗ BSD_API_KEY nu este setat!")
        sys.exit(1)
    
    fetch_live()
