import json
import sqlite3
from datetime import datetime, timedelta, timezone

import pytest

from betpredict.publish import match_analysis as MA
from betpredict.store import db as DB

NOW = datetime(2026, 11, 19, 8, 0, tzinfo=timezone.utc)

OFFER = {
    ("A doua repriză - Interval goluri", "1-3"): 1.33, ("A doua repriză - Interval goluri", "1-2"): 1.80,
    ("A doua repriză - Total goluri", "Peste 0.5"): 1.27, ("A doua repriză - Total goluri", "Sub 0.5"): 3.40,
    ("A doua repriză - Total goluri", "Peste 2.5"): 4.85, ("A doua repriză - Total goluri", "Sub 2.5"): 1.14,
    ("A doua repriză - Total goluri", "Peste 3.5"): 11.0, ("A doua repriză - Total goluri", "Sub 3.5"): 1.02,
    ("Prima repriză - Total goluri", "Peste 1.5"): 3.0, ("Prima repriză - Total goluri", "Sub 1.5"): 1.36,
    ("Total goluri", "Peste 1.5"): 1.35, ("Total goluri", "Sub 1.5"): 3.15,
    ("Ambele echipe marchează (GG)", "Da"): 1.75, ("Ambele echipe marchează (GG)", "Nu"): 1.95,
    ("Final", "1"): 2.40, ("Final", "X"): 3.20, ("Final", "2"): 2.95,
}


def _db():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    DB.init_db(c)
    c.execute("CREATE TABLE IF NOT EXISTS sb_offer_close (match_id INTEGER, market_name TEXT, outcome TEXT, line TEXT, price REAL, observed_at TEXT)")
    c.execute("INSERT INTO league (id, name) VALUES (1, 'Liga Test')")
    c.execute("INSERT INTO league (id, name) VALUES (2, 'International Friendlies')")
    # istoric: echipele 10 (gazdă) și 20 (oaspete) contra altora, cu scor la pauză
    mid = 1000
    for i in range(12):
        ko = (NOW - timedelta(days=3 + i * 7)).strftime("%Y-%m-%dT%H:%M:%SZ")
        for team in (10, 20):
            mid += 1
            c.execute("INSERT INTO match (id, league_id, kickoff_utc, home_id, away_id, home_name, away_name, status, ft_home, ft_away, ht_home, ht_away) "
                      "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", (mid, 1, ko, team, 99, f"T{team}", "Alta", "finished", 2, 1, 1, 0))
    for i in range(3):  # H2H
        mid += 1
        ko = (NOW - timedelta(days=200 + i * 100)).strftime("%Y-%m-%dT%H:%M:%SZ")
        c.execute("INSERT INTO match (id, league_id, kickoff_utc, home_id, away_id, home_name, away_name, status, ft_home, ft_away, ht_home, ht_away) "
                  "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", (mid, 1, ko, 20, 10, "T20", "T10", "finished", 1, 1, 0, 1))
    return c


def _upcoming(c, mid, ko, league=1, home=10, away=20, offer=OFFER):
    c.execute("INSERT INTO match (id, league_id, kickoff_utc, home_id, away_id, home_name, away_name, status) VALUES (?,?,?,?,?,?,?,?)",
              (mid, league, ko, home, away, f"T{home}", f"T{away}", "notstarted"))
    for (mn, oc), p in offer.items():
        c.execute("INSERT INTO sb_offer (match_id, market_name, outcome, line, price, observed_at) VALUES (?,?,?,?,?,?)",
                  (mid, mn, oc, "", p, "2026-11-19T07:00:00Z"))


def test_devig_power_sums_to_one_and_shades_longshots():
    ps = MA.devig([11.0, 1.02])
    assert sum(ps) == pytest.approx(1.0)
    prop = (1 / 11.0) / (1 / 11.0 + 1 / 1.02)
    assert ps[0] < prop  # marja apasă mai mult pe outsider
    assert MA.devig([1.0, 2.0]) is None


def test_fair_probabilities_from_offer():
    p13, ov = MA.fair_prob(OFFER, MA.MARKETS["H2G13"][3])
    p05, _ = MA.fair_prob(OFFER, ("over", MA.H2, 0.5))
    p35, _ = MA.fair_prob(OFFER, ("over", MA.H2, 3.5))
    assert p13 == pytest.approx(p05 - p35)
    assert 0.65 < p13 < 0.80 and ov > 0
    h, _ = MA.fair_prob(OFFER, ("1x2", "1"))
    x, _ = MA.fair_prob(OFFER, ("1x2", "X"))
    a, ov3 = MA.fair_prob(OFFER, ("1x2", "2"))
    assert h + x + a == pytest.approx(1.0)
    assert ov3 == pytest.approx(1 / 2.4 + 1 / 3.2 + 1 / 2.95 - 1)
    assert MA.fair_prob({}, ("over", MA.FT, 1.5)) == (None, None)


def test_publish_writes_analysis_with_form_h2h_league_and_status(tmp_path):
    c = _db()
    _upcoming(c, 1, "2026-11-19T18:00:00Z")                      # seara, club
    _upcoming(c, 2, "2026-11-20T03:00:00Z", league=2)            # noaptea, amical
    _upcoming(c, 3, "2026-11-23T18:00:00Z")                      # peste 3 zile: nu intră
    (tmp_path / "api" / "match").mkdir(parents=True)
    (tmp_path / "api" / "match" / "555.json").write_text("{}")   # meci vechi: se șterge
    n = MA.publish_match_analysis(c, tmp_path, NOW)
    assert n == 2
    folder = tmp_path / "api" / "match"
    assert not (folder / "555.json").exists() and not (folder / "3.json").exists()
    d = json.loads((folder / "1.json").read_text())
    assert d["schema"] == MA.SCHEMA and d["match"]["day"] == "2026-11-19"
    by = {m["key"]: m for m in d["markets"]}
    h2 = by["H2G13"]
    assert h2["status"] == "recommended" and h2["fair_p"] and h2["overround"] > 0 and h2["why"]
    assert h2["margin"] == pytest.approx(1 - 1.33 * h2["fair_p"], abs=1e-3)
    assert by["H2G12"]["status"] == "avoid" and "peste fereastra" in by["H2G12"]["why"][0]
    assert by["DRAW"]["status"] == "avoid"
    assert d["form"]["home"]["played"] == 6 and d["form"]["home"]["last"][0]["result"] == "W"
    assert d["form"]["away"]["rates"]["H2G13"]["n"] == 10
    assert d["h2h"]["n"] == 3 and d["h2h"]["draws"] == 3
    assert d["league_profile"]["n_ht"] >= 24 and d["league_profile"]["h2_avg"] is not None
    assert {f["code"] for f in d["risk"]} >= {"thin", "no_ref"} and "night" not in {f["code"] for f in d["risk"]}
    assert d["verdict"].startswith("Recomandat")
    n2 = json.loads((folder / "2.json").read_text())
    codes = {f["code"] for f in n2["risk"]}
    assert {"intl", "night"} <= codes and n2["match"]["intl"] and n2["match"]["night"]
    assert all(m["status"] != "recommended" for m in n2["markets"])  # risc mare → cel mult „atenție”
    idx = json.loads((folder / "index.json").read_text())
    assert [m["id"] for m in idx["matches"]] == [1, 2] and "H2G13" in idx["matches"][0]["recommended"]


def test_no_offer_no_files(tmp_path):
    c = _db()
    assert MA.publish_match_analysis(c, tmp_path, NOW) == 0
    assert json.loads((tmp_path / "api" / "match" / "index.json").read_text())["count"] == 0
