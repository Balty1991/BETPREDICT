"""Autoînvățare zilnică: recalibrare cu shrinkage, idempotență, auto-tuning bilete, „Ce a învățat Robotul”."""
import json
import random
from datetime import date

from betpredict import selflearn as SL
from betpredict.robot import MODEL_VERSION
from betpredict.robot.params import load_params
from betpredict.store import connect, init_db

TODAY = date(2026, 10, 11)


def _db(tmp_path):
    conn = connect(tmp_path / "t.db")
    init_db(conn)
    return conn


def _seed(conn, n=400, p=0.6, true=0.45, seed=1):
    rnd = random.Random(seed)
    for i in range(n):
        conn.execute("INSERT INTO match(id, league_id, kickoff_utc, home_id, away_id, home_name, away_name, status) VALUES (?,?,?,?,?,?,?,?)",
                     (i + 1, 39, "2026-10-01T12:00:00Z", 1, 2, "A", "B", "finished"))
        won = rnd.random() < true
        conn.execute("""INSERT INTO prediction(match_id, market, line, selection, p_calibrated, model_version, created_at, shown_on_page,
                        result, profit_1u, day, reasons_json) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                     (i + 1, "btts", 0.0, "YES", p, MODEL_VERSION, "2026-10-01", "predictii", "won" if won else "lost",
                      0.8 if won else -1.0, "2026-10-05", json.dumps({"p_cal0": p})))
    conn.commit()


def test_recal_shrinks_overconfident_market(tmp_path):
    conn = _db(tmp_path)
    _seed(conn)
    out = SL.daily_learn(conn, TODAY)
    params = load_params(conn)
    b = params["daily_recal"]["market"]["btts"]["b"]
    assert -SL.B_CAP <= b < -0.1  # supraîncredere → corecție negativă, micșorată
    p = SL.recal_apply(params, "btts", 39, 0.6)
    assert 0.45 < p < 0.6
    assert out["changes"] and any(c["type"] == "daily_recal" for c in out["changes"])
    n_log = conn.execute("SELECT COUNT(*) FROM learning_log").fetchone()[0]
    assert SL.daily_learn(conn, TODAY) == {"skipped": "already_ran_today"}
    again = SL.daily_learn(conn, TODAY, force=True)  # aceleași date → fără schimbări noi în jurnal
    assert not [c for c in again["changes"] if c["type"] == "daily_recal"]
    assert conn.execute("SELECT COUNT(*) FROM learning_log").fetchone()[0] == n_log


def test_small_sample_no_recal(tmp_path):
    conn = _db(tmp_path)
    _seed(conn, n=20)
    SL.daily_learn(conn, TODAY)
    assert SL.recal_apply(load_params(conn), "btts", 39, 0.6) == 0.6


def test_ticket_tuning_bounded(tmp_path):
    conn = _db(tmp_path)
    _seed(conn, n=100, p=0.8, true=0.5)
    for k in range(25):
        conn.execute("INSERT INTO ticket(id, kind, variant, created_by, stake, status, created_at, day) VALUES (?,?,?,?,?,?,?,?)",
                     (k + 1, "value", "biletul_zilei", "robot", 0.1, "lost", "2026-10-05", "2026-10-05"))
        for j in range(4):
            pid = k * 4 + j + 1
            conn.execute("INSERT INTO ticket_leg(ticket_id, prediction_id, match_id, market, selection, odds) VALUES (?,?,?,?,?,?)",
                         (k + 1, pid, pid, "btts|0", "YES", 1.3))
    conn.commit()
    params = load_params(conn)
    ch = SL.tune_tickets(conn, params, TODAY)
    v = params["ticket_tuning"]["biletul_zilei"]["leg_p"]
    assert ch and v == 0.72
    assert SL.tuned("biletul_zilei", "leg_p", 0.70, params) == 0.72
    for _ in range(10):
        SL.tune_tickets(conn, params, TODAY)
    assert params["ticket_tuning"]["biletul_zilei"]["leg_p"] <= SL.TUNE_SPECS["biletul_zilei"]["leg_p"][2]


def test_learned_section_in_weekly(tmp_path):
    from betpredict.publish.weekly import build_weekly, contract_report

    conn = _db(tmp_path)
    _seed(conn)
    SL.daily_learn(conn, date(2026, 10, 9))
    # jurnalul scrie ora reală; raportul filtrează pe săptămâna simulată (altfel pică din 12.10.2026)
    conn.execute("UPDATE learning_log SET run_at='2026-10-09T06:00:00+00:00'")
    conn.commit()
    d = build_weekly(conn, TODAY)
    ln = d["learned"]
    assert ln["title"] == "Ce a învățat Robotul" and ln["change_counts"].get("daily_recal")
    assert len(ln["metrics_trend"]) == 6 and ln["metrics_trend"][-1]["n"] == 400
    rep = contract_report(d)
    assert rep is None or rep["learned"]["summary"]
