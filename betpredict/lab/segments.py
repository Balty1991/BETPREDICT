"""Meciurile potrivite pentru fiecare piață: profilurile de meci (cotă, șansă, ligă) în care piața a ieșit pe plus.

Nu ascundem piețe: pentru fiecare piață (clasice și Stil Supersocial) căutăm *unde* merge — în ce bandă de cotă, la ce
șansă a Robotului, în ce ligă — și apoi alegem meciurile de azi care cad în acele profiluri.

Un profil e păstrat doar dacă e pe plus la cota Superbet reală în AMBELE jumătăți ale istoricului (în ordinea timpului),
cu ROI micșorat spre −5% (cât pierde un pariu la întâmplare), ca să nu prindem norocul. Cu cât sunt mai multe date, cu atât
profilurile devin mai sigure; până atunci sunt puține și marcate ca atare."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional, Tuple

from betpredict.timeutil import canon_utc

ODDS_BANDS = ((1.0, 1.25), (1.25, 1.5), (1.5, 1.8), (1.8, 2.3), (2.3, 100.0))
P_BANDS = ((0.0, 0.5), (0.5, 0.65), (0.65, 0.8), (0.8, 1.01))
MIN_N, MIN_HALF = 30, 12          # selecții în profil / în fiecare jumătate
PRIOR_N, PRIOR_ROI = 30, -0.05    # micșorare spre ROI-ul unui pariu la întâmplare
MAX_TODAY = 60


def _band(x: float, bands) -> Optional[Tuple[float, float]]:
    for lo, hi in bands:
        if lo <= x < hi:
            return lo, hi
    return None


def _dims(odds: float, p: float, league: Any) -> List[Tuple[str, str]]:
    """Profilurile în care cade o selecție: cotă, șansă, ligă și ligă × cotă."""
    ob, pb = _band(odds, ODDS_BANDS), _band(p, P_BANDS)
    out = []
    if ob:
        out.append(("cota", f"{ob[0]:g}-{ob[1]:g}"))
    if pb:
        out.append(("sansa", f"{int(pb[0] * 100)}-{min(100, int(pb[1] * 100))}"))
    if league is not None:
        out.append(("liga", str(league)))
        if ob:
            out.append(("liga_cota", f"{league}|{ob[0]:g}-{ob[1]:g}"))
    return out


def _history(conn: sqlite3.Connection, since: str) -> List[Tuple[str, str, float, float, Any, bool]]:
    """(piață, zi, cotă Superbet, șansă, ligă, câștigat) — clasice (ultima versiune a predicției) și Stil (urmărite)."""
    out = []
    last: Dict[Tuple, Tuple] = {}
    for r in conn.execute(
            """SELECT p.match_id, p.market, p.line, p.selection, p.p_calibrated, p.reasons_json, p.result, m.league_id,
                      substr(m.kickoff_utc,1,10) d
               FROM prediction p JOIN match m ON m.id=p.match_id
               WHERE p.period='FT' AND p.result IN ('won','lost') AND m.kickoff_utc >= ? ORDER BY p.id""", (since,)):
        try:
            sb = (json.loads(r[5] or "{}").get("odds_alt") or {}).get("superbet")
        except ValueError:
            sb = None
        if not sb or sb <= 1 or r[4] is None:
            continue
        key = (r[0], r[1], float(r[2] or 0), r[3])
        last[key] = (f"R:{r[1]}:{float(r[2] or 0):g}:{r[3]}", r[8], float(sb), float(r[4]), r[7], r[6] == "won")
    out.extend(last.values())
    try:
        for mk, o, p, res, lg, d in conn.execute(
                """SELECT s.mkey, s.odds, s.p, s.result, m.league_id, substr(s.kickoff_utc,1,10) FROM ss_track s
                   JOIN match m ON m.id=s.match_id WHERE s.result IN ('won','lost') AND s.odds > 1 AND s.kickoff_utc >= ?""", (since,)):
            out.append((mk, d, float(o), float(p), lg, res == "won"))
    except sqlite3.OperationalError:
        pass
    return out


def _shrunk(n: int, pl: float) -> float:
    return (pl + PRIOR_N * PRIOR_ROI) / (n + PRIOR_N)


def find(conn: sqlite3.Connection, since: str = "2026-10-09") -> Dict[str, Dict[Tuple[str, str], Dict[str, float]]]:
    """Profilurile pe plus, pe piață: {piață: {(dimensiune, valoare): {n, roi, roi_shrunk, win_rate, halves}}}."""
    rows = _history(conn, since)
    # jumătățile se iau pe fiecare piață (piețele Stil sunt urmărite de mai puțin timp decât cele clasice)
    per: Dict[str, set] = {}
    for r in rows:
        per.setdefault(r[0], set()).add(r[1])
    mids = {mk: sorted(ds)[len(ds) // 2] for mk, ds in per.items() if len(ds) >= 4}
    agg: Dict[Tuple[str, str, str], List[float]] = {}
    for mk, d, o, p, lg, w in rows:
        if mk not in mids:
            continue
        pl = (o - 1) if w else -1.0
        h = 0 if d < mids[mk] else 1
        for dim in _dims(o, p, lg):
            a = agg.setdefault((mk, *dim), [0, 0.0, 0, 0, 0.0, 0, 0.0])  # n, pl, won, n0, pl0, n1, pl1
            a[0] += 1; a[1] += pl; a[2] += w
            a[3 + 2 * h] += 1; a[4 + 2 * h] += pl
    out: Dict[str, Dict[Tuple[str, str], Dict[str, float]]] = {}
    for (mk, dim, val), (n, pl, won, n0, pl0, n1, pl1) in agg.items():
        if n < MIN_N or n0 < MIN_HALF or n1 < MIN_HALF:
            continue
        if _shrunk(n, pl) <= 0 or pl0 <= 0 or pl1 <= 0:
            continue
        out.setdefault(mk, {})[(dim, val)] = {"n": n, "roi": round(pl / n, 4), "roi_shrunk": round(_shrunk(n, pl), 4),
                                               "win_rate": round(won / n, 4), "halves": [round(pl0 / n0, 4), round(pl1 / n1, 4)]}
    return out


def _upcoming(conn: sqlite3.Connection, now: datetime, horizon_h: int) -> Iterable[Dict[str, Any]]:
    lo, hi = canon_utc((now + timedelta(minutes=10)).isoformat()), canon_utc((now + timedelta(hours=horizon_h)).isoformat())
    last: Dict[Tuple, Dict[str, Any]] = {}
    for r in conn.execute(
            """SELECT p.id, p.match_id, p.market, p.line, p.selection, p.p_calibrated, p.reasons_json, m.kickoff_utc, m.league_id,
                      m.home_name, m.away_name FROM prediction p JOIN match m ON m.id=p.match_id
               WHERE p.period='FT' AND p.result IS NULL AND m.kickoff_utc > ? AND m.kickoff_utc <= ? ORDER BY p.id""", (lo, hi)):
        try:
            sb = (json.loads(r[6] or "{}").get("odds_alt") or {}).get("superbet")
        except ValueError:
            sb = None
        key = (r[1], r[2], float(r[3] or 0), r[4])
        if not sb or sb <= 1 or r[5] is None:
            last.pop(key, None)
            continue
        last[key] = {"mkey": f"R:{r[2]}:{float(r[3] or 0):g}:{r[4]}", "prediction_id": r[0], "match_id": r[1], "market": r[2],
                     "line": float(r[3] or 0), "selection": r[4], "p": float(r[5]), "odds": float(sb), "kickoff_utc": r[7],
                     "league_id": r[8], "home": r[9], "away": r[10]}
    yield from last.values()
    try:
        from betpredict.experimental import supersocial as SS

        lift = SS.key_lift(conn)
        for c in SS.candidates(conn, now, horizon_h=horizon_h):
            if c.get("odds") and not c.get("est") and c.get("p") and not SS.is_robot(c["key"]) and c["key"] not in SS.BB_KEYS:
                yield {"mkey": c["key"], "match_id": c["match_id"], "market": "ss", "line": 0.0, "selection": c["key"],
                       "label": SS.label(c["key"]), "p": float(SS.realistic_p(c, lift)), "odds": float(c["odds"]),
                       "kickoff_utc": c["kickoff_utc"], "league_id": c["league_id"], "home": c["home"], "away": c["away"]}
    except Exception:  # noqa: BLE001 — fără ofertă Stil: rămân clasicele
        return


def _add_picks(conn: sqlite3.Connection, rows: List[Dict[str, Any]]) -> None:
    """Eticheta, evenimentul și selecția Superbet (cu id-uri), ca selecția să intre direct pe biletul din aplicație."""
    from betpredict.publish.outputs import _robot_pick, _sb_pick
    from betpredict.robot.markets import label_ro

    names: Dict[int, Dict[str, Any]] = {}
    for x in rows:
        r = conn.execute("SELECT ext_id FROM ext_event WHERE match_id=? AND source='superbet'", (x["match_id"],)).fetchone()
        x["sb_event_id"] = r[0] if r else None
        if x["market"] == "ss":
            from betpredict.experimental import supersocial as SS

            if x["match_id"] not in names:
                names[x["match_id"]] = SS.offer_now(conn, x["match_id"], x["home"], x["away"], names=True)
            nm = names[x["match_id"]].get(x["selection"])
            x["sb_pick"] = _sb_pick(conn, x["match_id"], *nm) if nm else None
        else:
            x["label"] = label_ro(x["market"], x["line"], x["selection"])
            x["sb_pick"] = _robot_pick(conn, x["match_id"], x["market"], x["line"], x["selection"])


DIM_RO = {"cota": "cota", "sansa": "șansa Robotului", "liga": "liga", "liga_cota": "liga × cota"}


def doc(conn: sqlite3.Connection, now: Optional[datetime] = None, horizon_h: int = 36) -> Dict[str, Any]:
    """Profilurile pe plus + meciurile din următoarele ore care cad în ele (cel mai bun profil al fiecărei selecții)."""
    now = now or datetime.now(timezone.utc)
    seg = find(conn)
    leagues = {r[0]: r[1] for r in conn.execute("SELECT id, name FROM league")} if seg else {}

    def desc(dim: str, val: str) -> str:
        if dim == "cota":
            return f"cota {val.replace('-', '–')}"
        if dim == "sansa":
            return f"șansa Robotului {val.replace('-', '–')}%"
        lg, _, ob = val.partition("|")
        name = leagues.get(int(lg)) if lg.isdigit() else lg
        return f"{name or 'liga'}" + (f", cota {ob.replace('-', '–')}" if ob else "")

    today: List[Dict[str, Any]] = []
    for c in _upcoming(conn, now, horizon_h):
        hits = [(s, d) for d in _dims(c["odds"], c["p"], c["league_id"]) if (s := seg.get(c["mkey"], {}).get(d))]
        if not hits:
            continue
        best, d = max(hits, key=lambda x: x[0]["roi_shrunk"])
        ev = c["p"] * c["odds"] - 1
        if ev < -0.05:  # profilul e pe plus, dar Robotul vede selecția clar sub cotă: nu o propunem
            continue
        today.append({**{k: v for k, v in c.items() if k != "mkey"}, "key": c["mkey"], "profile": desc(*d), "dim": d[0],
                      "roi": best["roi"], "roi_shrunk": best["roi_shrunk"], "n": best["n"], "win_rate": best["win_rate"],
                      "profiles": len(hits), "ev": round(ev, 4)})
    today.sort(key=lambda x: (-x["profiles"], -x["roi_shrunk"], -x["p"]))
    # cel mult 10 selecții din aceeași piață și una pe meci în aceeași piață (să nu fie o listă cu o singură piață)
    seen, per, picked = set(), {}, []
    for x in today:
        if (x["match_id"], x["key"]) in seen or per.get(x["key"], 0) >= 10:
            continue
        seen.add((x["match_id"], x["key"])); per[x["key"]] = per.get(x["key"], 0) + 1
        picked.append(x)
    today = picked[:MAX_TODAY]
    _add_picks(conn, today)
    flat = [{"key": mk, "dim": d, "value": v, "profile": desc(d, v), **s} for mk, ss in seg.items() for (d, v), s in ss.items()]
    flat.sort(key=lambda x: -x["roi_shrunk"])
    return {"generated_at": canon_utc(now.isoformat()), "segments": flat[:200], "today": today,
            "note": "Profiluri (cotă, șansă, ligă) pe plus la cota Superbet în ambele jumătăți ale istoricului, ROI micșorat spre −5%. "
                    "Meciurile de azi care cad într-un profil, cu EV estimat de cel puțin −5%."}
