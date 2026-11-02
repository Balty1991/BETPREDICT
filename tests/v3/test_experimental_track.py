import sqlite3

from betpredict.experimental import track


def test_superbet_price_requires_exact_market_selection_and_fresh_timestamp():
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE sb_offer (match_id INTEGER, market_name TEXT, outcome TEXT, price REAL, observed_at TEXT)")
    conn.execute("INSERT INTO sb_offer VALUES (1, 'Prima repriză - Total goluri', 'Peste 0.5', 1.55, '2026-11-02T10:00:00Z')")
    now = "2026-11-02T12:00:00Z"

    assert track._superbet_price(conn, 1, "h1", 0.5, "OVER", now) == (1.55, "2026-11-02T10:00:00Z")
    assert track._superbet_price(conn, 1, "h1", 1.5, "OVER", now) == (None, None)
    assert track._superbet_price(conn, 1, "h1", 0.5, "UNDER", now) == (None, None)
    assert track._superbet_price(conn, 1, "cards", 0.5, "OVER", now) == (None, None)
    assert track._superbet_price(conn, 1, "h1", 0.5, "OVER", "2026-11-02T17:00:01Z") == (None, None)


def test_paper_stats_use_only_settled_rows_with_saved_superbet_odds():
    conn = sqlite3.connect(":memory:")
    track.ensure(conn)
    conn.executemany(
        "INSERT INTO exp_prediction (match_id, market, line, selection, p, created_at, result, odds) VALUES (?,?,?,?,?,?,?,?)",
        [
            (1, "corners", 8.5, "OVER", 0.6, "2026-11-01T00:00:00Z", "won", 2.0),
            (2, "corners", 8.5, "OVER", 0.6, "2026-11-01T00:00:00Z", "lost", 2.0),
            (3, "corners", 8.5, "OVER", 0.6, "2026-11-01T00:00:00Z", "won", None),
            (4, "corners", 8.5, "OVER", 0.6, "2026-11-01T00:00:00Z", None, 2.0),
        ],
    )
    conn.row_factory = sqlite3.Row

    s = track.stats(conn)["corners_8.5_over"]
    assert s["n"] == 3
    assert s["won"] == 2
    assert s["lost"] == 1
    assert s["n_with_superbet_odds"] == 2
    # (2.0 - 1) + (-1) = 0 profit across two equal paper stakes.
    assert s["paper_roi"] == 0.0
    assert s["ticket_eligible"] is False
