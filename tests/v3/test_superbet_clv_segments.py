"""Superbet (potrivire, cote), best-price, CLV, segmente ligă×piață, raport săptămânal."""
from datetime import date, datetime, timezone

from betpredict.clv import clv_summary, compute_clv
from betpredict.ingest.superbet import SuperbetClient, ingest_superbet, match_events, name_sim, parse_odds, playable_odds
from betpredict.robot.engine import best_price
from betpredict.robot.params import threshold_ok
from betpredict.segments import decide, posterior
from betpredict.store import SCHEMA_VERSION, connect, init_db


def _db(tmp_path):
    conn = connect(tmp_path / "t.db")
    init_db(conn)
    return conn


def _match(conn, mid, ko, home, away, hid, aid, status="notstarted", ft=None):
    conn.execute("INSERT INTO match(id, league_id, kickoff_utc, home_id, away_id, home_name, away_name, status, ft_home, ft_away) "
                 "VALUES (?,?,?,?,?,?,?,?,?,?)", (mid, 1, ko, hid, aid, home, away, status, *(ft or (None, None))))


def _ev(eid, name, ko, h=None, a=None, odds=None):
    return {"eventId": eid, "matchName": name, "utcDate": ko, "homeTeamId": h, "awayTeamId": a, "odds": odds or []}


def test_schema_v3_idempotent(tmp_path):
    conn = _db(tmp_path)
    assert init_db(conn) == SCHEMA_VERSION == 3
    cols = {r[1] for r in conn.execute("PRAGMA table_info(prediction)")}
    assert {"odds_taken", "odds_taken_source", "odds_taken_at"} <= cols
    assert {r[1] for r in conn.execute("PRAGMA table_info(ticket_leg)")} >= {"odds_source", "closing_odds"}


def test_name_sim_variants_and_flags():
    assert name_sim("Paris Saint-Germain", "PSG") >= 0.8
    assert name_sim("AIK", "AIK Stockholm") >= 0.8
    assert name_sim("FC Steaua București", "FCSB") < 0.8 or True  # nu trebuie să crape
    assert name_sim("Arsenal", "Arsenal W") < 0.5  # femei ≠ bărbați
    assert name_sim("Ajax", "Ajax U21") < 0.5      # tineret ≠ seniori
    assert name_sim("Bayern München", "Bayern Munchen") >= 0.9


def test_parse_odds_markets_and_dnb_orientation():
    ev = _ev(1, "Alpha FC·Beta United", "2026-10-10T18:00:00Z", odds=[
        {"marketId": 547, "name": "1", "price": 2.1}, {"marketId": 547, "name": "X", "price": 3.3},
        {"marketId": 547, "name": "2", "price": 3.6}, {"marketId": 531, "name": "1X", "price": 1.3},
        {"marketId": 539, "name": "Da", "price": 1.8}, {"marketId": 200734, "name": "Peste 2.5", "price": 1.9},
        {"marketId": 200734, "name": "Sub 2.5", "price": 1.85},
        {"marketId": 555, "name": "Beta United", "price": 2.6}, {"marketId": 555, "name": "Alpha FC", "price": 1.5},
        {"marketId": 547, "name": "1", "price": 1.0, "status": "active"}, {"marketId": 539, "name": "Nu", "price": 2.0, "status": "suspended"},
    ])
    got = {(m, l, o): p for m, l, o, p in parse_odds(ev)}
    assert got[("1x2", 0.0, "HOME")] == 2.1 and got[("double_chance", 0.0, "1X")] == 1.3
    assert got[("btts", 0.0, "YES")] == 1.8 and ("btts", 0.0, "NO") not in got
    assert got[("over_under", 2.5, "OVER")] == 1.9 and got[("over_under", 2.5, "UNDER")] == 1.85
    assert got[("draw_no_bet", 0.0, "HOME")] == 1.5 and got[("draw_no_bet", 0.0, "AWAY")] == 2.6


def test_match_events_names_time_alias(tmp_path):
    conn = _db(tmp_path)
    _match(conn, 1, "2026-10-10T18:00:00Z", "Paris Saint-Germain", "Olympique Lyonnais", 10, 11)
    _match(conn, 2, "2026-10-10T18:00:00Z", "Arsenal", "Chelsea", 12, 13)
    _match(conn, 3, "2026-10-10T20:00:00Z", "Real Madrid", "Barcelona", 14, 15)
    conn.execute("INSERT INTO team_alias(source, ext_team_id, team_id, ext_name, learned_at) VALUES ('superbet','r1',14,'Real','x'),('superbet','b1',15,'Barca','x')")
    ms = conn.execute("SELECT id, kickoff_utc, home_id, away_id, home_name, away_name FROM match").fetchall()
    evs = [
        _ev(100, "PSG·Olympique Lyonnais", "2026-10-10T18:00:00Z"),
        _ev(101, "Arsenal W·Chelsea W", "2026-10-10T18:00:00Z"),       # femei: respins
        _ev(102, "Arsenal·Chelsea", "2026-10-11T18:00:00Z"),           # altă zi: respins
        _ev(103, "Real M.·FC Barca", "2026-10-10T21:00:00Z", "r1", "b1"),  # alias + oră mutată
    ]
    out = match_events(conn, evs, ms)
    assert out[1]["ext_id"] == "100"
    assert 2 not in out
    assert out[3]["ext_id"] == "103" and out[3]["method"] == "alias"


class _Sess:
    def __init__(self, bulk, detail):
        self.bulk, self.detail, self.calls = bulk, detail, []

    def get(self, url, params=None, timeout=None, headers=None):
        self.calls.append(url)

        class R:
            status_code = 200
            headers = {}

            def __init__(s, p):
                s.p = p

            def json(s):
                return s.p
        if "/events/by-date" in url:
            return R({"data": self.bulk})
        return R({"data": [self.detail]})


def test_ingest_and_playable_best_price(tmp_path):
    conn = _db(tmp_path)
    now = datetime(2026, 10, 10, 12, 0, tzinfo=timezone.utc)
    _match(conn, 1, "2026-10-10T18:00:00Z", "Alpha FC", "Beta United", 1, 2)
    odds = [{"marketId": 547, "name": "1", "price": 2.2}, {"marketId": 547, "name": "X", "price": 3.2}, {"marketId": 547, "name": "2", "price": 3.4}]
    ev = _ev(500, "Alpha FC·Beta United", "2026-10-10T18:00:00Z", "a", "b", odds)
    det = dict(ev, odds=odds + [{"marketId": 539, "name": "Da", "price": 1.75}])
    conn.execute("INSERT INTO prediction(match_id, market, line, period, selection, model_version, created_at, is_pick, grade, ev) "
                 "VALUES (1,'1x2',0,'FT','HOME','robot-v1','2026-10-10T08:00:00Z',1,'A',0.05)")
    conn.commit()
    sess = _Sess([ev], det)
    client = SuperbetClient(max_requests=10, session=sess, sleep=lambda s: None)
    rep = ingest_superbet(conn, now=now, days_ahead=1, client=client) if "client" in ingest_superbet.__code__.co_varnames else None
    if rep is None:  # semnătura fără client injectabil
        import betpredict.ingest.superbet as sb
        orig = sb.SuperbetClient
        sb.SuperbetClient = lambda *a, **k: client
        try:
            rep = ingest_superbet(conn, now=now, days_ahead=1)
        finally:
            sb.SuperbetClient = orig
    assert conn.execute("SELECT ext_id FROM ext_event WHERE match_id=1").fetchone()[0] == "500"
    pl = playable_odds(conn, [1], now)
    assert pl[1]["1x2"]["HOME"] == 2.2
    o, src = best_price(2.2, 2.05)
    assert (o, src) == (2.2, "superbet")
    o, src = best_price(None, 2.05)
    assert (o, src) == (2.05, "bsd_consensus")


def test_clv_prediction_and_ticket(tmp_path):
    conn = _db(tmp_path)
    _match(conn, 1, "2026-10-10T18:00:00Z", "A", "B", 1, 2, "finished", (1, 0))
    _match(conn, 2, "2026-10-10T18:00:00Z", "C", "D", 3, 4, "finished", (0, 0))
    snap = "INSERT INTO odds_snapshot(match_id, market, line, period, outcome, decimal, source, observed_at) VALUES (?,?,0,'FT',?,?,?,?)"
    conn.execute(snap, (1, "1x2", "HOME", 2.0, "bsd_consensus", "2026-10-10T08:00:00Z"))
    conn.execute(snap, (1, "1x2", "HOME", 1.8, "bsd_consensus", "2026-10-10T17:50:00Z"))
    conn.execute(snap, (1, "1x2", "HOME", 1.5, "bsd_consensus", "2026-10-10T19:00:00Z"))  # după start: ignorat
    conn.execute(snap, (2, "1x2", "DRAW", 3.0, "superbet", "2026-10-10T08:00:00Z"))
    conn.execute(snap, (2, "1x2", "DRAW", 3.3, "superbet", "2026-10-10T17:30:00Z"))
    conn.execute("INSERT INTO ext_event(match_id, source, ext_id, checked_at) VALUES (2,'superbet','9','2026-10-10T17:30:00Z')")
    ins = ("INSERT INTO prediction(id, match_id, market, line, period, selection, model_version, created_at, odds_shown, odds_source, "
           "odds_taken, odds_taken_source, day, shown_on_page) VALUES (?,?,'1x2',0,'FT',?,'robot-v1','2026-10-10T08:00:00Z',?,?,?,?,'2026-10-10','page')")
    conn.execute(ins, (1, 1, "HOME", 2.0, "bsd_consensus", 2.0, "bsd_consensus"))
    conn.execute(ins, (2, 2, "DRAW", 3.0, "superbet", 3.0, "superbet"))
    conn.execute("INSERT INTO ticket(id, kind, created_by, total_odds, status, created_at, day) VALUES (7,'acca_safe','robot',6.0,'pending','2026-10-10T08:00:00Z','2026-10-10')")
    conn.execute("INSERT INTO ticket_leg(ticket_id, prediction_id, match_id, market, selection, odds, odds_source) VALUES (7,1,1,'1x2','HOME',2.0,'bsd_consensus'),(7,2,2,'1x2','DRAW',3.0,'superbet')")
    conn.commit()
    rep = compute_clv(conn, now=datetime(2026, 10, 10, 21, 0, tzinfo=timezone.utc), since_day="2026-10-01")
    assert rep["predictions"] == 2 and rep["tickets"] == 1
    c1, c2 = (conn.execute("SELECT clv FROM prediction WHERE id=?", (i,)).fetchone()[0] for i in (1, 2))
    assert abs(c1 - (2.0 / 1.8 - 1)) < 1e-3 and abs(c2 - (3.0 / 3.3 - 1)) < 1e-3
    t = conn.execute("SELECT clv FROM ticket WHERE id=7").fetchone()[0]
    assert abs(t - (6.0 / (1.8 * 3.3) - 1)) < 1e-3
    s = clv_summary([c1, c2])
    assert s["n"] == 2 and s["beat_rate"] == 0.5


def test_clv_superbet_stale_closing_ignored(tmp_path):
    conn = _db(tmp_path)
    _match(conn, 2, "2026-10-10T18:00:00Z", "C", "D", 3, 4, "finished", (0, 0))
    conn.execute("INSERT INTO odds_snapshot(match_id, market, line, period, outcome, decimal, source, observed_at) VALUES (2,'1x2',0,'FT','DRAW',3.0,'superbet','2026-10-10T08:00:00Z')")
    conn.execute("INSERT INTO ext_event(match_id, source, ext_id, checked_at) VALUES (2,'superbet','9','2026-10-10T08:00:00Z')")  # >3h înainte
    conn.execute("INSERT INTO prediction(id, match_id, market, line, period, selection, model_version, created_at, odds_taken, odds_taken_source, day, shown_on_page) "
                 "VALUES (2,2,'1x2',0,'FT','DRAW','robot-v1','2026-10-10T08:00:00Z',3.0,'superbet','2026-10-10','page')")
    conn.commit()
    compute_clv(conn, now=datetime(2026, 10, 10, 21, 0, tzinfo=timezone.utc), since_day="2026-10-01")
    assert conn.execute("SELECT clv FROM prediction WHERE id=2").fetchone()[0] is None


def _post(n, n_clv, clv_sum, profit, clv2=None):
    return posterior({"n": n, "n_clv": n_clv, "clv": clv_sum, "clv2": clv2 if clv2 is not None else (clv_sum / max(n_clv, 1)) ** 2 * n_clv + 0.002 * n_clv, "profit": profit})


def test_segment_shrinkage_and_decisions():
    small = _post(5, 5, -0.5, -3.0)          # -10% CLV pe 5 selecții: prea puțin, nu se oprește
    assert decide(small, None)[0] is None
    bad = _post(80, 80, -0.04 * 80, -12.0)   # -4% CLV pe 80
    assert bad["clv_post"] < -0.01 and decide(bad, None)[0] == "off"
    good = _post(120, 120, 0.04 * 120, 2.0)
    assert decide(good, None)[0] == "boost"
    # histerezis: oprit rămâne oprit până CLV micșorat ≥ 0
    meh = _post(40, 40, -0.001 * 40, -1.0)
    assert decide(meh, "off")[0] == "off"
    assert decide(_post(40, 40, 0.02 * 40, 1.0), "off")[0] is None


def test_threshold_ok_respects_segments():
    params = {"thresholds": {"1x2": {"min_ev": 0.03}}, "segments": {"7|1x2": {"action": "off"}, "8|1x2": {"action": "boost"}}}
    assert threshold_ok(params, "1x2", 7, 0.5) is False
    assert threshold_ok(params, "1x2", 8, 0.025) is True
    assert threshold_ok(params, "1x2", 9, 0.025) is False


def test_weekly_report_notify(tmp_path):
    from betpredict.publish.weekly import build_weekly, save_weekly, weekly_doc, week_id

    conn = _db(tmp_path)
    r = build_weekly(conn, date(2026, 10, 19))
    assert r["notify"]["id"].startswith("weekly-") and r["notify"]["title"]
    save_weekly(conn, date(2026, 10, 19))
    doc = weekly_doc(conn, date(2026, 10, 19))
    assert doc["latest"]["id"] == r["id"] and len(doc["history"]) >= 1
    assert week_id(date(2026, 10, 19)).startswith("2026-W")


def test_weekly_contract_report():
    from betpredict.publish.weekly import contract_report

    blk = {"n": 10, "won": 6, "lost": 4, "void": 0, "pending": 0, "win_rate": 0.6, "roi_pct": 4.2, "profit": 0.42, "clv_n": 8, "clv_avg": 0.012}
    empty = {"n": 0, "won": 0, "lost": 0, "void": 0, "pending": 0, "win_rate": None, "roi_pct": None, "profit": 0}
    d = {"id": "2026-W41", "from": "2026-10-05", "to": "2026-10-11", "generated_at": "2026-10-12T04:00:00Z",
         "blocks": {"pick": blk, "recomandate": blk, "toate": blk, "valoare": blk},
         "tickets": [{"kind": "acca_safe", "n": 3, "won": 2, "lost": 1, "pending": 0, "profit": 0.5, "staked": 3.0, "roi_pct": 16.7}],
         "changes": [{}], "segments": {"off": [], "boost": []}, "best_markets": [], "worst_markets": []}
    r = contract_report(d)
    assert r["schema"] == "betpredict.report.weekly.v1" and r["week"] == "2026-W41"
    assert abs(r["summary"]["predictions"]["roi"] - 0.042) < 1e-9 and r["summary"]["predictions"]["winrate"] == 0.6
    assert len(r["headline"]) <= 120 and len(r["highlights"]) <= 5 and all(len(h) <= 80 for h in r["highlights"])
    assert abs(r["summary"]["tickets"]["roi"] - 0.5 / 3) < 1e-3
    d2 = dict(d, blocks={k: empty for k in d["blocks"]}, tickets=[])
    assert contract_report(d2) is None
