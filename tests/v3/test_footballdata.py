from datetime import date

from betpredict.ingest.footballdata import ingest_footballdata, parse_csv, seasons_for
from betpredict.store import connect, init_db

CSV = """Div,Date,Time,HomeTeam,AwayTeam,FTHG,FTAG,HTHG,HTAG,Referee,HC,AC,HY,AY,AvgH,AvgD,AvgA,MaxH,MaxD,MaxA,AvgCH,AvgCD,AvgCA,Avg>2.5,Avg<2.5
E0,15/08/2025,20:00,Liverpool,Bournemouth,4,2,1,0,A Taylor,6,7,1,2,1.31,5.96,8.31,1.34,6.6,9.4,1.29,6.02,8.68,1.36,3.13
"""


def test_seasons():
    assert seasons_for(date(2026, 10, 10)) == ["2627", "2526", "2425"]
    assert seasons_for(date(2026, 3, 1), 1) == ["2526"]


def test_parse_and_ingest(tmp_path):
    rows = parse_csv(CSV, "E0", "2526")
    assert rows[0]["day"] == "2025-08-15" and rows[0]["avgc_h"] == 1.29 and rows[0]["hc"] == 6
    conn = connect(tmp_path / "x.db")
    init_db(conn)
    conn.execute("INSERT INTO match(id, kickoff_utc, home_name, away_name, status) VALUES (1, '2025-08-15T19:00:00Z', 'Liverpool FC', 'AFC Bournemouth', 'finished')")
    conn.commit()
    st = ingest_footballdata(conn, date(2025, 9, 1), divs=("E0",), seasons=("2526",), pause=0, fetcher=lambda d, s: CSV)
    assert st["rows"] == 1 and st["linked"] == 1
    r = conn.execute("SELECT corners_home, ht_home FROM match WHERE id=1").fetchone()
    assert r[0] == 6 and r[1] == 1
