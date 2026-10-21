import json
import sqlite3
from datetime import datetime, timezone

from betpredict.lab import segments as S
from betpredict.store.db import init_db


def _db():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    init_db(c)
    return c


def _pred(c, i, day, odds, p, won, market="over_under", line=1.5, sel="OVER", league=7, result=True):
    c.execute("INSERT INTO match (id, kickoff_utc, home_name, away_name, status, league_id) VALUES (?,?,?,?,?,?)",
              (i, f"{day}T18:00:00Z", f"H{i}", f"A{i}", "finished" if result else "notstarted", league))
    c.execute("INSERT INTO prediction (match_id, market, line, period, selection, p_model, p_calibrated, reasons_json, result, model_version, created_at) "
              "VALUES (?,?,?,?,?,?,?,?,?,?,?)", (i, market, line, "FT", sel, p, p, json.dumps({"odds_alt": {"superbet": odds}}),
                                                  ("won" if won else "lost") if result else None, "t", "x"))


def test_profile_found_only_when_positive_in_both_halves_and_today_matched():
    c = _db()
    i = 0
    for d in range(10):  # 10 zile, 8 selecții pe zi: cota 1.30 intră 7/8 (+14%), cota 2.0 intră 3/8 (−25%)
        for k in range(8):
            i += 1
            _pred(c, i, f"2026-10-{10 + d:02d}", 1.30, 0.8, k < 7)
            i += 1
            _pred(c, i, f"2026-10-{10 + d:02d}", 2.0, 0.45, k < 3, league=9)
    seg = S.find(c, since="2026-10-01")
    prof = seg.get("R:over_under:1.5:OVER", {})
    assert ("cota", "1.25-1.5") in prof and ("cota", "1.8-2.3") not in prof
    assert all(v["halves"][0] > 0 and v["halves"][1] > 0 for v in prof.values())
    _pred(c, 999, "2026-10-21", 1.32, 0.8, None, result=False)   # meci de azi în profilul bun
    _pred(c, 1000, "2026-10-21", 2.1, 0.45, None, league=9, result=False)  # în profilul prost
    d = S.doc(c, now=datetime(2026, 10, 21, 8, tzinfo=timezone.utc))
    ids = [x["match_id"] for x in d["today"]]
    assert 999 in ids and 1000 not in ids
    assert d["today"][0]["label"] == "Peste 1.5" and d["today"][0]["roi"] > 0


def test_profile_paused_when_last_week_negative():
    c = _db()
    i = 0
    for d in range(16):  # zilele 1–9: 8/8 intrate la 1.30; zilele 10–16: 6/8 (pe minus): pe ambele jumătăți tot pe plus
        for k in range(8):
            i += 1
            _pred(c, i, f"2026-10-{1 + d:02d}", 1.30, 0.8, k < (8 if d < 9 else 6))
    st = S.find(c, since="2026-09-01", today="2026-10-17")["R:over_under:1.5:OVER"][("cota", "1.25-1.5")]
    assert st["status"] == "pauză" and st["recent"]["roi"] < 0 and st["roi"] > 0

