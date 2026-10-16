import sqlite3

from betpredict.publish.audit import audit_doc
from betpredict.store import db as DB


def test_audit_doc_lists_markets_with_status_and_timing():
    c = sqlite3.connect(":memory:"); c.row_factory = sqlite3.Row; DB.init_db(c)
    c.execute("""CREATE TABLE IF NOT EXISTS ss_track (match_id INTEGER, mkey TEXT, kickoff_utc TEXT, p REAL, odds REAL,
                 updated_at TEXT, result TEXT, odds_first REAL, PRIMARY KEY (match_id, mkey))""")
    for i in range(40):
        c.execute("INSERT INTO ss_track VALUES (?, 'G25', '2026-10-1%dT12:00:00Z', 0.7, 1.40, 'x', ?, 1.38)" % (i % 5), (i, "won" if i % 4 else "lost"))
    d = audit_doc(c)
    g = next(x for x in d["stil"] if x["key"] == "G25")
    assert g["n"] == 40 and g["roi"] == round(30 * 1.40 / 40 - 1, 4) and g["status"]
    assert d["timing"] and d["robot"] == [] and isinstance(d["boosts"], list)


def test_audit_splits_stil_tickets_with_and_without_boost():
    c = sqlite3.connect(":memory:"); c.row_factory = sqlite3.Row; DB.init_db(c)
    for i, (st, boost) in enumerate([("won", True), ("lost", True), ("lost", False), ("lost", False)]):
        cur = c.execute("INSERT INTO ticket (kind, variant, created_by, total_odds, stake, status, created_at) VALUES ('acca_stil','x','robot',30,1,?, 'x')", (st,))
        for j in range(4):
            c.execute("INSERT INTO ticket_leg (ticket_id, match_id, market, selection, odds, result) VALUES (?,?,?,?,?,?)",
                      (cur.lastrowid, j, "ss|0", "G25", 2.3, "won" if st == "won" or j else "lost"))
        if boost:
            c.execute("INSERT INTO ticket_leg (ticket_id, match_id, market, selection, odds, result) VALUES (?,9,'boost|0','b',2.0,?)",
                      (cur.lastrowid, "won" if st == "won" else "lost"))
    d = {x["name"]: x for x in audit_doc(c)["boost_split"]}
    w, wo = d["Cu cotă mărită"], d["Fără cotă mărită"]
    assert (w["n"], w["won"], w["roi"], w["avg_legs"], w["boost_win_rate"]) == (2, 1, 14.0, 5.0, 0.5)
    assert (wo["n"], wo["won"], wo["roi"], wo["leg_win_rate"]) == (2, 0, -1.0, 0.75)
