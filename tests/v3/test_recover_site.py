import json
import sqlite3

from betpredict.store import db as DB
from betpredict.tools import recover_site as R


def _ticket(i, day, kind="pyramid", variant="p120", status="won", odds=1.2, created="2026-10-25T05:00:00+00:00"):
    return {"id": i, "kind": kind, "variant": variant, "created_by": "robot", "date": day, "created_at": created, "target_odds": 1.2,
            "total_odds_published": odds, "p_ticket": 0.8, "ev": -0.03, "status": status, "payout": odds if status == "won" else None,
            "variant_label": variant, "bucket": "Piramidă 1.20", "legs": [
                {"match_id": 1, "market": "1x2", "line": None, "selection": "HOME", "odds": odds, "result": status if status != "pending" else None}]}


def test_recover_pyramid_series_and_moves_today_to_end(tmp_path):
    c = sqlite3.connect(":memory:"); c.row_factory = sqlite3.Row; DB.init_db(c)
    c.execute("INSERT INTO match (id, kickoff_utc, home_name, away_name, status) VALUES (1,'2026-10-25T18:00:00Z','A','B','finished')")
    for i in range(1, 1101):  # baza restaurată are istoric vechi
        c.execute("INSERT INTO ticket (id, kind, status, created_at, day) VALUES (?, 'acca_value', 'lost', '2026-10-01T00:00:00', '2026-10-01')", (i,))
    from betpredict.builder.pyramid import ensure_track_tables
    ensure_track_tables(c, "pyramid120")
    c.execute("INSERT INTO ticket (id, kind, variant, status, payout, created_at, day, total_odds) VALUES (1101,'pyramid','p120','won',1.2,'2026-10-24T01:00:00','2026-10-24',1.2)")
    c.execute("INSERT INTO pyramid120_run (id, start_date, start_bank, status, current_step, current_bank) VALUES (3,'2026-10-24',100,'active',1,120)")
    c.execute("INSERT INTO pyramid120_step (run_id, step_no, date, ticket_id, stake, odds, result, bank_before, bank_after) VALUES (3,1,'2026-10-24',1101,100,1.2,'won',100,120)")
    # după restaurare: biletul de azi cu un id folosit atunci pe site (1102) și treapta lui
    c.execute("INSERT INTO ticket (id, kind, variant, status, created_at, day, total_odds) VALUES (1102,'pyramid','p120','pending','2026-10-28T06:30:00','2026-10-28',1.18)")
    c.execute("INSERT INTO pyramid120_step (run_id, step_no, date, ticket_id, stake, odds, bank_before) VALUES (3,2,'2026-10-28',1102,120,1.18,120)")
    snap = tmp_path / "snap"; (snap / "tickets").mkdir(parents=True); (snap / "pyramid").mkdir()
    site = [_ticket(1102, "2026-10-25"), _ticket(1103, "2026-10-26", odds=1.25)]
    (snap / "tickets" / "2026-10-26.json").write_text(json.dumps({"tickets": site}))
    st = {"track": "1.20", "rules": {"start_bank": 100.0}, "runs": [{"id": 3, "start_date": "2026-10-24", "steps": 3, "bank": 180.0, "status": "active", "withdrawn": 0}],
          "history": [{"date": "2026-10-26", "status": "pick", "ticket_id": 1103, "odds": 1.25, "result": "won"},
                      {"date": "2026-10-25", "status": "pick", "ticket_id": 1102, "odds": 1.2, "result": "won"},
                      {"date": "2026-10-24", "status": "pick", "ticket_id": 1101, "odds": 1.2, "result": "won"}]}
    (snap / "pyramid" / "state_120.json").write_text(json.dumps(st))
    out = R.recover(c, snap)
    assert out["remapped"] == 1 and out["tickets"]["added"] == 2
    steps = [tuple(r) for r in c.execute("SELECT step_no, date, result, bank_before, bank_after FROM pyramid120_step WHERE run_id=3 ORDER BY step_no")]
    assert steps[:3] == [(1, "2026-10-24", "won", 100, 120), (2, "2026-10-25", "won", 120, 144.0), (3, "2026-10-26", "won", 144.0, 180.0)]
    assert steps[3][:3] == (4, "2026-10-28", None) and steps[3][3] == 180.0
    moved = c.execute("SELECT ticket_id FROM pyramid120_step WHERE run_id=3 AND step_no=4").fetchone()[0]
    assert moved != 1102 and c.execute("SELECT day FROM ticket WHERE id=?", (moved,)).fetchone()[0] == "2026-10-28"
    assert c.execute("SELECT current_step, current_bank FROM pyramid120_run WHERE id=3").fetchone()[:] == (3, 180.0)
    assert R.recover(c, snap) == {"skipped": "deja făcută"}
