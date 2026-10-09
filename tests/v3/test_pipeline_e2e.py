"""Pipeline complet cu un BSD simulat: ingest → Robot → bilete → piramidă → decontare → publicare."""

import json
import math
import random
import re
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse, parse_qs

import pytest

from betpredict.config import Settings
from betpredict.ingest.bsd_client import BSDClient
from betpredict.ingest.cache import DiskCache
from betpredict.ingest.quota import QuotaTracker
from betpredict.ingest.ratelimit import TokenBucket
from betpredict.pipeline.run import run_pipeline
from betpredict.store import connect, init_db
from betpredict.store import repo
from betpredict.timeutil import canon_utc, ro_today

from .conftest import FakeResp

NOW = datetime.now(timezone.utc).replace(microsecond=0)
TEAMS = list(range(1, 41))  # 2 ligi × 20 echipe
STRENGTH = {t: random.Random(t).uniform(-0.4, 0.4) for t in TEAMS}


def league_of(t):
    return 100 if t <= 20 else 200


def poisson(rng, lam):
    L, k, p = math.exp(-lam), 0, 1.0
    while True:
        p *= rng.random()
        if p < L:
            return k
        k += 1


def make_history(conn, n_days=500):
    rng = random.Random(7)
    rows = []
    mid = 10_000
    for d in range(n_days, 1, -1):
        day = NOW - timedelta(days=d)
        for lg, teams in ((100, TEAMS[:20]), (200, TEAMS[20:])):
            if d % 7:
                continue
            order = teams[:]
            rng.shuffle(order)
            for i in range(0, 20, 2):
                h, a = order[i], order[i + 1]
                lh = math.exp(0.25 + 0.15 + STRENGTH[h] - STRENGTH[a] * 0.5)
                la = math.exp(0.25 + STRENGTH[a] - STRENGTH[h] * 0.5)
                mid += 1
                rows.append((mid, lg, canon_utc(day.isoformat()), h, a, f"T{h}", f"T{a}", "finished",
                             poisson(rng, lh), poisson(rng, la), canon_utc(NOW.isoformat())))
    conn.executemany("""INSERT INTO match (id, league_id, kickoff_utc, home_id, away_id, home_name, away_name, status,
                        ft_home, ft_away, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)""", rows)
    repo.set_state(conn, "history.warehouse_imported", "test")
    repo.set_state(conn, "legacy.imported", "test")
    repo.set_state(conn, "backfill.finished_until", (NOW.date()).isoformat())
    conn.commit()


def upcoming_events(status_overrides=None):
    status_overrides = status_overrides or {}
    evs = []
    eid = 900_000
    for lg, teams in ((100, TEAMS[:20]), (200, TEAMS[20:])):
        for i in range(0, 20, 2):
            eid += 1
            h, a = teams[i], teams[i + 1]
            ko = NOW + timedelta(hours=2 + (eid % 10))
            lg_ev = lg + (i // 2)  # mai multe ligi în ziua de test (max. 2 selecții pe ligă în bilete)
            ev = {"id": eid, "league_id": lg_ev, "league_name": f"Liga {lg_ev}", "home_team_id": h, "home_team": f"T{h}",
                  "away_team_id": a, "away_team": f"T{a}", "event_date": ko.isoformat(), "status": "notstarted",
                  "home_score": None, "away_score": None,
                  "head_to_head": {"total_matches": 6, "home_wins": 3, "draws": 1, "away_wins": 2, "avg_total_goals": 2.5,
                                   "recent_matches": [{"date": "2026-01-01", "home": f"T{h}", "away": f"T{a}", "score": "2-1",
                                                       "home_score": 2, "away_score": 1}]}}
            ev.update(status_overrides.get(eid, {}))
            evs.append(ev)
    return evs


def fair_odds(p, margin=1.05):
    return round(max(1.01, 1 / (p * margin)), 2)


class SimBSD:
    def __init__(self):
        self.events = upcoming_events()
        self.calls = []

    def get(self, url, params=None, headers=None, timeout=None):
        u = urlparse(url)
        path = u.path.replace("/api/v2/", "", 1)
        self.calls.append(path)
        assert "odds/best" not in path and "comparison" not in path
        if path == "events/":
            if (params or {}).get("status") == "finished":
                return FakeResp(200, {"count": 0, "next": None, "results": []})
            return FakeResp(200, {"count": len(self.events), "next": None, "results": self.events},
                            {"RateLimit": '"football";r=7000;t=3600'})
        if path == "predictions/":
            res = []
            for ev in self.events:
                d = STRENGTH[ev["home_team_id"]] - STRENGTH[ev["away_team_id"]]
                ph = 45 + 40 * d
                res.append({"event": {"id": ev["id"]}, "model": {"version": "sim"},
                            "markets": {"match_result": {"prob_home": ph, "prob_draw": 26, "prob_away": 100 - ph - 26},
                                        "over_under": {"prob_over_15": 75, "prob_over_25": 52, "prob_over_35": 30},
                                        "btts": {"prob_yes": 52}}})
            return FakeResp(200, {"results": res, "next": None})
        if path == "odds/":
            market = (params or {}).get("market")
            rows = []
            for ev in self.events:
                d = STRENGTH[ev["home_team_id"]] - STRENGTH[ev["away_team_id"]]
                ph = min(0.85, max(0.1, 0.45 + 0.4 * d))
                pd = 0.26
                pa = 1 - ph - pd
                book = {"1x2": {"HOME": ph, "DRAW": pd, "AWAY": pa},
                        "over_under_15": {"over": 0.75, "under": 0.25},
                        "over_under_25": {"over": 0.52, "under": 0.48},
                        "over_under_35": {"over": 0.3, "under": 0.7},
                        "btts": {"yes": 0.52, "no": 0.48},
                        "double_chance": {"1X": ph + pd, "12": ph + pa, "X2": pd + pa}}.get(market, {})
                for o, p in book.items():
                    rows.append({"event_id": ev["id"], "market": market, "outcome": o, "decimal_odds": fair_odds(p),
                                 "opening_decimal_odds": fair_odds(p) + 0.05, "updated_at": canon_utc(NOW.isoformat())})
            return FakeResp(200, {"results": rows, "next": None})
        m = re.match(r"teams/(\d+)/form/", path)
        if m:
            return FakeResp(200, {"requested": 10, "overall": {"matches": 10, "won": 5, "drawn": 2, "lost": 3, "goals_for": 15,
                                                               "goals_against": 11, "points_per_match": 1.7, "form": "WWDLW"}})
        if re.match(r"teams/(\d+)/squad/", path):
            return FakeResp(200, {"players": [{"id": 1, "name": "X", "availability": "injured", "injury_type": "Knee"}]})
        if re.match(r"leagues/(\d+)/standings/", path):
            return FakeResp(200, {"standings": [{"team_id": t, "position": i + 1, "pts": 30 - i, "played": 10} for i, t in enumerate(TEAMS)]})
        return FakeResp(404, {})


@pytest.fixture
def env(tmp_path):
    conn = connect(tmp_path / "db.sqlite")
    init_db(conn)
    make_history(conn)
    sim = SimBSD()
    settings = Settings.from_env({"BSD_API_KEY": "k", "BETPREDICT_STATE_DIR": str(tmp_path / "state")})
    client = BSDClient(settings, env={"BSD_API_KEY": "k"}, session=sim,
                       quota=QuotaTracker(tmp_path / "q.json"), limiter=TokenBucket(1000, 1000, sleep=lambda s: None),
                       cache=DiskCache(tmp_path / "cache"), sleep=lambda s: None)
    return conn, client, sim, tmp_path


def test_full_daily_then_settle(env):
    conn, client, sim, tmp = env
    out = tmp / "site"
    rep = run_pipeline(conn, "daily", out, client=client, now=NOW)
    assert not rep["warnings"], rep["warnings"]
    assert rep["steps"]["robot"]["matches"] == 20
    assert rep["steps"]["robot"]["predictions"] > 100
    today = ro_today()
    days = sorted({json.loads((out / "api/days/index.json").read_text())["days"][i] for i in range(3)})
    assert days
    # fișierele din contract există
    for f in ["api/meta.json", "api/tickets/today.json", "api/tickets/history.json", "api/pyramid/state.json",
              "api/stats/summary.json", "api/stats/daily.json", "api/stats/monthly.json", "api/stats/calibration.json",
              "api/stats/learning.json"]:
        assert (out / f).exists(), f
    # toate predicțiile publicate sunt în jurnal, cu cotă ≥ 1.15
    all_preds = []
    for p in (out / "api/days").glob("????-??-??.json"):
        d = json.loads(p.read_text())
        assert d["schema"] == "betpredict.day.v1"
        for m in d["matches"]:
            for pr in m["predictions"]:
                assert pr["odds"] is None or pr["odds"] >= 1.15
                assert conn.execute("SELECT 1 FROM prediction WHERE id=?", (pr["id"],)).fetchone()
                all_preds.append(pr)
    assert all_preds
    match0 = json.loads(next((out / "api/days").glob("????-??-??.json")).read_text())
    # bilete
    tk = json.loads((out / "api/tickets/today.json").read_text())
    pyr = json.loads((out / "api/pyramid/state.json").read_text())
    assert pyr["today"]["status"] in ("pick", "no_bet")
    if pyr["today"]["status"] == "pick":
        assert 1.85 <= pyr["today"]["main"]["total_odds"] <= 2.2
        assert 1 <= pyr["today"]["main"]["legs_count"] <= 4
    for t in tk["tickets"]:
        target = t["target_odds"]
        assert target * 0.84 <= t["total_odds"] <= target * 1.26
        assert len({l["match_id"] for l in t["legs"]}) == len(t["legs"])  # max 1 pe meci
        assert all(l["odds"] >= 1.15 for l in t["legs"])

    # meciurile se termină: unul amânat (void), restul cu scor
    finished = {}
    for i, ev in enumerate(sim.events):
        if i == 0:
            finished[ev["id"]] = {"status": "postponed"}
        else:
            finished[ev["id"]] = {"status": "finished", "home_score": i % 3, "away_score": (i + 1) % 2,
                                  "event_date": (NOW - timedelta(hours=3)).isoformat()}
    sim.events = upcoming_events(finished)
    rep2 = run_pipeline(conn, "refresh", out, client=client, now=NOW + timedelta(hours=14))
    assert rep2["steps"]["settle"]["predictions"]["settled"] > 0
    pending = conn.execute("SELECT COUNT(*) FROM prediction WHERE shown_on_page='predictii' AND result IS NULL").fetchone()[0]
    assert pending == 0
    voided = conn.execute("SELECT COUNT(*) FROM prediction WHERE match_id=? AND result='void'", (sim.events[0]["id"],)).fetchone()[0]
    assert voided > 0
    assert conn.execute("SELECT COUNT(*) FROM ticket WHERE status='pending'").fetchone()[0] == 0
    summary = json.loads((out / "api/stats/summary.json").read_text())
    assert summary["overall"]["won"] + summary["overall"]["lost"] > 0
    assert summary["recommendations"]
    # nu s-a apelat niciun endpoint plătit
    assert not any("odds/best" in c or "comparison" in c for c in sim.calls)

    # learn rulează fără erori și publică learning.json
    rep3 = run_pipeline(conn, "learn", out, now=NOW + timedelta(hours=15))
    assert "learn" in rep3["steps"]
    assert json.loads((out / "api/stats/learning.json").read_text())["schema"] == "betpredict.learning.v1"
