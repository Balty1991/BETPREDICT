#!/usr/bin/env python3
"""
BetPredict Pro — Live Scores Fetcher (v23 Exact Live Window)
============================================================

Implementare conform BSD API v2 docs:
  - GET /api/v2/events/live/
  - query params API-side: league_id, season_id, team_id
  - ignoră date_from/date_to/status pentru live, conform docs
  - fiecare row păstrează last_updated
  - dacă last_updated nu s-a schimbat, refolosim enrichment-ul vechi
  - enrich doar când e necesar: stats / incidents / lineups
"""

from __future__ import annotations
