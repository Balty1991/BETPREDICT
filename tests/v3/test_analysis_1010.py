"""Analiza 09–10.10: decontare Bet Builder doar pe meciuri terminate, calibrarea cozilor DC, widget piramidă, piețe experimentale."""
import json
from datetime import date

import numpy as np

from betpredict.experimental import models as M
from betpredict.experimental import track as E
from betpredict.model.v2 import tail_calibrate
from betpredict.store import db as DB


def _conn(tmp_path):
    c = DB.connect(tmp_path / "t.db")
    DB.init_db(c)
    return c


def _match(conn, mid, status, fh, fa, hh, ha, ko="2026-10-10T18:00:00Z"):
    conn.execute("INSERT INTO match (id, kickoff_utc, home_name, away_name, status, ft_home, ft_away, ht_home, ht_away, league_id) "
                 "VALUES (?,?,?,?,?,?,?,?,?,1)", (mid, ko, "Rapid", "Dinamo", status, fh, fa, hh, ha))


def test_tail_calibration_shrinks_extremes():
    p = tail_calibrate(np.array([0.03, 0.5]), "o45")
    assert 0.045 < p[0] < 0.06  # P(Sub 4.5) 0.97 → ~0.95
    assert p[1] < 0.5
    assert tail_calibrate(np.array([0.97]), "o05")[0] < 0.97


def test_builder_not_settled_on_live_score(tmp_path):
    from betpredict.builder.betbuilder import settle_suggestions
    from betpredict.store import repo
    c = _conn(tmp_path)
    _match(c, 1, "1st_half", 0, 0, 0, 0)
    _match(c, 2, "finished", 2, 1, 1, 0)
    legs = json.dumps({"legs": ["ht_sub_2.5", "ft_sub_4.5"], "template": None,
                       "superbet": {"market": "Total goluri prima repriză & Total goluri", "outcome": "Sub 2.5 & Sub 4.5"}})
    for mid in (1, 2):
        c.execute("INSERT INTO bb_suggestion (match_id, day, legs_json, label, p_joint, fair_odds, min_odds, source, created_at, result) "
                  "VALUES (?,?,?,?,?,?,?,?,?,?)", (mid, "2026-10-10", legs, "x", 0.6, 1.6, 1.7, "model", repo.now_iso(), "lost"))
    c.commit()
    st = settle_suggestions(c)
    assert st["reset_live"] == 2
    res = dict(c.execute("SELECT match_id, result FROM bb_suggestion").fetchall())
    assert res == {1: None, 2: "won"}


def test_widget_pyramid_after_loss(tmp_path):
    from betpredict.publish.outputs import widget_pyramid
    c = _conn(tmp_path)
    c.execute("INSERT INTO pyramid_run (id, start_date, start_bank, status, current_step, current_bank) VALUES (1,'2026-10-09',100,'lost',1,0)")
    c.execute("INSERT INTO ticket (id, kind, variant, total_odds, status, created_at, day) VALUES (55,'pyramid','principal',1.86,'lost','x','2026-10-10')")
    c.execute("INSERT INTO pyramid_step (run_id, step_no, date, ticket_id, bank_before, result, bank_after) VALUES (1,2,'2026-10-10',55,187,'lost',0)")
    w = widget_pyramid(c, date(2026, 10, 10), {"status": "pick"}, {"id": 55, "status": "lost", "legs": [1, 2, 3]},
                       {"status": "lost", "step": 1, "bank": 0.0, "start_bank": 100.0})
    assert w["step"] == 1 and w["step_no"] == 2  # widget-ul vechi afișează step+1 = treapta 2
    assert w["restart"] and w["next_step"] == 1 and w["next_bank"] == 100.0 and w["stake_bank"] == 187


def test_experimental_models_and_tracking(tmp_path):
    P = M.goal_markets(1.5, 1.0)
    assert abs(P[("team_home", 0.5, "OVER")] - (1 - np.exp(-1.5))) < 1e-9
    assert abs(P[("h1", 0.5, "OVER")] + P[("h1", 0.5, "UNDER")] - 1) < 1e-9
    assert 0.4 < M.p_over_nb(9.5, 10.0, M.CORNER_R) < 0.6
    c = _conn(tmp_path)
    _match(c, 7, "finished", 2, 1, 1, 0)
    E.ensure(c)
    for (mk, ln, sel), p in P.items():
        c.execute("INSERT INTO exp_prediction (match_id, market, line, selection, p, day, created_at) VALUES (7,?,?,?,?,?,?)",
                  (mk, ln, sel, p, "2026-10-10", "x"))
    c.commit()
    assert E.settle(c)["settled"] == len(P)
    r = dict(c.execute("SELECT market||line||selection, result FROM exp_prediction").fetchall())
    assert r["team_home1.5OVER"] == "won" and r["h11.5OVER"] == "lost" and r["h20.5OVER"] == "won"
    E.publish(c, tmp_path, [date(2026, 10, 10)])
    doc = json.loads((tmp_path / "api" / "experimental" / "2026-10-10.json").read_text())
    assert doc["recommended"] is False and doc["matches"][0]["markets"]
    assert all(not v["proven"] for v in E.stats(c).values())
