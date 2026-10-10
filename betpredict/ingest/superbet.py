"""Cote JUCABILE Superbet (RO) → ``odds_snapshot`` (source='superbet').

Endpoint public (fără cont/cookie), găsit în ``src/superbet_recon.py`` / ``src/superbet_live_odds.py``:

* ``/v2/ro-RO/events/by-date?offerState=prematch&sportId=5&startDate&endDate`` — toate meciurile
  de fotbal din fereastră, dar DOAR piața preselectată (1X2);
* ``/v2/ro-RO/events/{id}`` — catalogul complet (1X2, șansă dublă, DNB, total goluri, GG).

Politețe / limite: cereri secvențiale, ≥ 0,5 s între ele, plafon de cereri pe rulare, oprire la
429/403 (fără reîncercări agresive), timeout 20 s. Detaliile se cer doar pentru meciurile unde Robotul
are ceva de spus (pick, grad A/B, EV > 0, selecții din bilete active) și doar dacă citirea anterioară
e veche (> 4 h; < 25 min în ultimele 2 h înainte de start — pentru linia de închidere).

Potrivirea cu meciurile BSD (fără ID comun): ora de start (± 15 min) + similaritatea numelor de echipe
(fără diacritice/prefixe de club, tokeni + prefixe + SequenceMatcher), cu verificări de echipe
feminine/tineret și unicitate (un eveniment Superbet ↔ un meci BSD). Potrivirile sigure învață
aliasuri de echipă (ID Superbet → ID BSD), iar aliasurile fac potrivirile viitoare exacte.
"""

from __future__ import annotations

import json
import logging
import re
import sqlite3
import time
import unicodedata
from datetime import datetime, timedelta, timezone
from difflib import SequenceMatcher
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from betpredict.store import repo
from betpredict.timeutil import canon_utc

log = logging.getLogger(__name__)

SOURCE = "superbet"
BASE = "https://production-superbet-offer-ro.freetls.fastly.net/v2/ro-RO"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Accept": "application/json",
    "Referer": "https://superbet.ro/",
}
MIN_INTERVAL_S = 0.5
TIMEOUT_S = 20
TIME_TOL_MIN = 15
DETAIL_STALE_H = 4.0
CLOSING_WINDOW_H = 2.0
CLOSING_STALE_MIN = 25
FRESH_H = 6.0              # cotele Superbet mai vechi de atât nu se folosesc pentru EV
CLOSE_VALID_H = 3.0        # ultima citire trebuie să fie în ultimele 3 h înainte de start ca să fie „închidere”

M_1X2, M_DC, M_DNB, M_BTTS, M_TOTAL = 547, 531, 555, 539, 200734
NOISE = {"fc", "cf", "afc", "sc", "ac", "ss", "ssc", "cd", "ud", "sk", "sd", "fk", "if", "aif", "bk", "ff", "club", "de",
         "cs", "csm", "acs", "fcsb_", "sv", "vfb", "vfl", "tsg", "rc", "rcd", "sl", "ca", "cp", "the", "and", "kv", "krc",
         "nk", "hnk", "gnk", "pfc", "ofk", "fsv", "bsc", "real_", "athletic_", "sporting_", "1", "calcio", "f", "c"}
YOUTH = re.compile(r"\b(u ?\d{2}|sub ?\d{2}|youth|juniors?|ii|b|reserves?|w|women|fem(inin)?|feminino|femenino|ladies|dames)\b")


# ------------------------------------------------------------------ nume
def _ascii(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "")
    return "".join(c for c in s if not unicodedata.combining(c)).lower()


def norm_name(name: str) -> str:
    n = re.sub(r"[^a-z0-9 ]", " ", _ascii(name))
    toks = [t for t in n.split() if t not in NOISE]
    return " ".join(toks)


def _flags(name: str) -> frozenset:
    n = re.sub(r"[^a-z0-9 ]", " ", _ascii(name))
    out = set()
    for m in YOUTH.finditer(n):
        t = m.group(0).replace(" ", "")
        if t in ("w", "women", "fem", "feminin", "feminino", "femenino", "ladies", "dames"):
            out.add("W")
        elif t.startswith(("u", "sub")):
            out.add("U" + re.sub(r"\D", "", t))
        else:
            out.add("R")  # rezerve / echipa a doua
    return frozenset(out)


def _tok_sim(a: str, b: str) -> float:
    if a == b:
        return 1.0
    if len(a) >= 3 and len(b) >= 3 and (a.startswith(b) or b.startswith(a)):
        return 0.9
    r = SequenceMatcher(None, a, b).ratio()
    return r if r >= 0.8 else 0.0


def name_sim(a: str, b: str) -> float:
    """0..1. Echipe feminine/tineret/rezerve nu se potrivesc niciodată cu prima echipă."""
    if _flags(a) != _flags(b):
        return 0.0
    na, nb = norm_name(a), norm_name(b)
    if not na or not nb:
        return 0.0
    if na == nb:
        return 1.0
    ta, tb = na.split(), nb.split()
    short, long_ = (ta, tb) if len(ta) <= len(tb) else (tb, ta)
    tok = sum(max(_tok_sim(x, y) for y in long_) for x in short) / max(len(ta), len(tb))
    # nume compuse lipite ("Rapid Bucuresti" vs "Rapid Bucureşti", "Al-Ahli" vs "Al Ahli")
    whole = SequenceMatcher(None, na.replace(" ", ""), nb.replace(" ", "")).ratio()
    # tokenul principal identic (ex. "Galatasaray" vs "Galatasaray Istanbul")
    head = 0.8 if (len(short) == 1 and len(short[0]) >= 3 and short[0] in long_) else 0.0
    # inițiale: "PSG" ↔ "Paris Saint Germain", "QPR" ↔ "Queens Park Rangers"
    ini = 0.0
    if len(short) == 1 and 2 <= len(short[0]) <= 4 and len(long_) >= 2:
        if short[0] == "".join(t[0] for t in long_)[: len(short[0])] and len(long_) <= len(short[0]) + 1:
            ini = 0.8
    return max(tok, whole if whole >= 0.88 else 0.0, head, ini)


# ------------------------------------------------------------------ client
class SuperbetClient:
    def __init__(self, max_requests: int = 80, session=None, sleep=time.sleep):
        self.max_requests = max_requests
        self.calls = 0
        self.errors: List[str] = []
        self.blocked = False
        self._last = 0.0
        self._sleep = sleep
        self._session = session

    def _get(self, path: str) -> Optional[Dict[str, Any]]:
        if self.blocked or self.calls >= self.max_requests:
            return None
        if self._session is None:
            import requests

            self._session = requests.Session()
            self._session.headers.update(HEADERS)
        wait = MIN_INTERVAL_S - (time.monotonic() - self._last)
        if wait > 0:
            self._sleep(wait)
        self.calls += 1
        self._last = time.monotonic()
        try:
            r = self._session.get(BASE + path, timeout=TIMEOUT_S)
        except Exception as exc:  # noqa: BLE001 — rețea: nu oprim pipeline-ul
            self.errors.append(f"{type(exc).__name__}")
            if len(self.errors) >= 3:
                self.blocked = True
            return None
        if r.status_code in (403, 429):
            self.errors.append(str(r.status_code))
            self.blocked = True  # respectăm limita: nu mai cerem nimic în rularea asta
            return None
        if r.status_code >= 400:
            self.errors.append(str(r.status_code))
            if len(self.errors) >= 3:
                self.blocked = True
            return None
        try:
            return r.json()
        except ValueError:
            self.errors.append("json")
            return None

    def by_date(self, start: datetime, end: datetime) -> List[Dict[str, Any]]:
        f = lambda d: d.strftime("%Y-%m-%d+%H:%M:%S")  # noqa: E731
        js = self._get(f"/events/by-date?currentStatus=active&offerState=prematch&startDate={f(start)}&endDate={f(end)}&sportId=5")
        return (js or {}).get("data") or []

    def event(self, ext_id: Any) -> Optional[Dict[str, Any]]:
        js = self._get(f"/events/{ext_id}")
        data = (js or {}).get("data") or []
        return data[0] if data else None


# ------------------------------------------------------------------ parsare
def teams_of(ev: Dict[str, Any]) -> Tuple[str, str]:
    name = ev.get("matchName") or ""
    parts = re.split(r"\s*[·•]\s*|\s+-\s+|\s+vs\.?\s+", name, maxsplit=1)
    return (parts[0].strip(), parts[1].strip()) if len(parts) == 2 else (name.strip(), "")


def kickoff_of(ev: Dict[str, Any]) -> Optional[str]:
    if ev.get("utcDate"):
        return canon_utc(str(ev["utcDate"]))
    if ev.get("unixDateMillis"):
        return canon_utc(datetime.fromtimestamp(ev["unixDateMillis"] / 1000, tz=timezone.utc).isoformat())
    return None


def parse_odds(ev: Dict[str, Any]) -> List[Tuple[str, float, str, float]]:
    """(piață, linie, rezultat, cotă) în convenția BSD (1x2/double_chance/draw_no_bet/over_under/btts)."""
    home, away = teams_of(ev)
    out: List[Tuple[str, float, str, float]] = []
    dnb: List[Tuple[str, float]] = []
    for o in ev.get("odds") or []:
        if (o.get("status") or "active") != "active":
            continue
        try:
            price = float(o.get("price"))
        except (TypeError, ValueError):
            continue
        if price <= 1.0:
            continue
        mid, name = o.get("marketId"), str(o.get("name") or "").strip()
        if mid == M_1X2 and name in ("1", "X", "2"):
            out.append(("1x2", 0.0, {"1": "HOME", "X": "DRAW", "2": "AWAY"}[name], price))
        elif mid == M_DC and name in ("1X", "12", "X2"):
            out.append(("double_chance", 0.0, name, price))
        elif mid == M_BTTS and name in ("Da", "Nu"):
            out.append(("btts", 0.0, "YES" if name == "Da" else "NO", price))
        elif mid == M_TOTAL:
            m = re.match(r"(Peste|Sub)\s+([\d.]+)$", name)
            if m and float(m.group(2)) in (0.5, 1.5, 2.5, 3.5, 4.5):
                out.append(("over_under", float(m.group(2)), "OVER" if m.group(1) == "Peste" else "UNDER", price))
        elif mid == M_DNB:
            dnb.append((name, price))
    if len(dnb) == 2:
        (n1, p1), (n2, p2) = dnb
        s1h, s1a = name_sim(n1, home), name_sim(n1, away)
        first_home = s1h >= s1a  # implicit: ordinea Superbet (gazde, oaspeți)
        out.append(("draw_no_bet", 0.0, "HOME", p1 if first_home else p2))
        out.append(("draw_no_bet", 0.0, "AWAY", p2 if first_home else p1))
    return out


# ------------------------------------------------------------------ potrivire
def _minutes(a: str, b: str) -> float:
    pa = datetime.fromisoformat(a.replace("Z", "+00:00"))
    pb = datetime.fromisoformat(b.replace("Z", "+00:00"))
    return abs((pa - pb).total_seconds()) / 60.0


def _aliases(conn: sqlite3.Connection) -> Dict[str, int]:
    return {r[0]: r[1] for r in conn.execute("SELECT ext_team_id, team_id FROM team_alias WHERE source=?", (SOURCE,))}


def match_events(conn: sqlite3.Connection, events: Sequence[Dict[str, Any]], matches: Sequence[sqlite3.Row],
                 now_iso: Optional[str] = None) -> Dict[int, Dict[str, Any]]:
    """{match_id: {"ext_id", "score", "method", "ev"}} — greedy pe scor, unicitate în ambele sensuri."""
    alias = _aliases(conn)
    by_hour: Dict[str, List[Dict[str, Any]]] = {}
    for ev in events:
        ko = kickoff_of(ev)
        if ko:
            ev["_ko"] = ko
            ev["_teams"] = teams_of(ev)
            by_hour.setdefault(ko[:10], []).append(ev)
    cands: List[Tuple[float, int, str, str, Dict[str, Any]]] = []
    for m in matches:
        ko = m["kickoff_utc"]
        if not ko:
            continue
        day = ko[:10]
        pool = by_hour.get(day, []) + by_hour.get(_shift_day(day, -1), []) + by_hour.get(_shift_day(day, 1), [])
        for ev in pool:
            dt = _minutes(ko, ev["_ko"])
            ah = alias.get(str(ev.get("homeTeamId"))) == m["home_id"] if ev.get("homeTeamId") else False
            aa = alias.get(str(ev.get("awayTeamId"))) == m["away_id"] if ev.get("awayTeamId") else False
            if ah and aa and dt <= 180:
                cands.append((2.0 - dt / 1000, m["id"], str(ev["eventId"]), "alias", ev))
                continue
            if dt > TIME_TOL_MIN:
                continue
            sh, sa = name_sim(m["home_name"] or "", ev["_teams"][0]), name_sim(m["away_name"] or "", ev["_teams"][1])
            if ah:
                sh = 1.0
            if aa:
                sa = 1.0
            lo, avg = min(sh, sa), (sh + sa) / 2
            hi = max(sh, sa)
            ok = ((avg >= 0.8 and lo >= 0.5) or ((ah or aa) and lo >= 0.4) or (lo >= 0.7)
                  # o echipă identică + aceeași oră de start (o echipă nu joacă două meciuri deodată)
                  or (hi >= 0.99 and lo >= 0.25 and dt <= 5))
            if ok:
                cands.append((avg - dt / 1000, m["id"], str(ev["eventId"]), "alias+nume" if (ah or aa) else "nume", ev))
    cands.sort(key=lambda x: -x[0])
    used_m, used_e, out = set(), set(), {}
    for sc, mid, eid, how, ev in cands:
        if mid in used_m or eid in used_e:
            continue
        used_m.add(mid)
        used_e.add(eid)
        out[mid] = {"ext_id": eid, "score": round(min(sc, 1.0), 3), "method": how, "ev": ev}
    return out


def _shift_day(day: str, n: int) -> str:
    from datetime import date as _d

    return (_d.fromisoformat(day) + timedelta(days=n)).isoformat()


def learn_aliases(conn: sqlite3.Connection, m: sqlite3.Row, ev: Dict[str, Any], score: float, stamp: str) -> int:
    if score < 0.85:
        return 0
    n = 0
    home, away = ev.get("_teams") or teams_of(ev)
    for ext, tid, nm in ((ev.get("homeTeamId"), m["home_id"], home), (ev.get("awayTeamId"), m["away_id"], away)):
        if ext and tid is not None:
            conn.execute("INSERT INTO team_alias(source, ext_team_id, team_id, ext_name, learned_at) VALUES (?,?,?,?,?) "
                         "ON CONFLICT(source, ext_team_id) DO NOTHING", (SOURCE, str(ext), tid, nm, stamp))
            n += 1
    return n


# ------------------------------------------------------------------ ingestie
def _last_prices(conn: sqlite3.Connection, match_ids: Iterable[int]) -> Dict[Tuple, float]:
    ids = list(match_ids)
    if not ids:
        return {}
    out = {}
    for mid, mk in repo.latest_odds(conn, ids, source=SOURCE).items():
        for key, by in mk.items():
            for o, v in by.items():
                out[(mid, key, o)] = v
    return out


def _store(conn: sqlite3.Connection, mid: int, prices: List[Tuple[str, float, str, float]], last: Dict[Tuple, float], stamp: str) -> int:
    rows = []
    for market, line, outcome, price in prices:
        key = repo.market_key(market, line)
        if last.get((mid, key, outcome)) == price:
            continue  # stocăm doar schimbările (ultima citire e ținută în ext_event.checked_at/detail_at)
        rows.append({"match_id": mid, "market": market, "line": line, "period": "FT", "outcome": outcome, "decimal": price,
                     "opening_decimal": None, "previous_decimal": last.get((mid, key, outcome)), "movement": None,
                     "source": SOURCE, "observed_at": stamp})
        last[(mid, key, outcome)] = price
    return repo.insert_odds(conn, rows)


def _interesting(conn: sqlite3.Connection, start: str, end: str) -> List[int]:
    """Meciurile unde Robotul are ceva de spus: pick, A/B, EV > 0 sau selecții în bilete active."""
    from betpredict.robot import MODEL_VERSION

    rows = conn.execute(
        """SELECT DISTINCT p.match_id FROM prediction p JOIN match m ON m.id = p.match_id
           WHERE p.model_version = ? AND p.result IS NULL AND m.kickoff_utc >= ? AND m.kickoff_utc < ?
             AND (p.is_pick = 1 OR p.grade IN ('A','B') OR COALESCE(p.ev, -1) > 0)
           UNION
           SELECT DISTINCT tl.match_id FROM ticket_leg tl JOIN ticket t ON t.id = tl.ticket_id JOIN match m ON m.id = tl.match_id
           WHERE t.status = 'pending' AND m.kickoff_utc >= ? AND m.kickoff_utc < ?""",
        (MODEL_VERSION, start, end, start, end)).fetchall()
    return [r[0] for r in rows]


def ingest_superbet(conn: sqlite3.Connection, now: Optional[datetime] = None, days_ahead: int = 3,
                    max_requests: int = 80, closing_only: bool = False, client: Optional[SuperbetClient] = None) -> Dict[str, Any]:
    """Bulk (1X2, toate meciurile) + detalii (toate piețele) pentru meciurile relevante."""
    now = now or datetime.now(timezone.utc)
    client = client or SuperbetClient(max_requests=max_requests)
    stamp = canon_utc(now.isoformat())
    horizon = now + (timedelta(hours=CLOSING_WINDOW_H + 1) if closing_only else timedelta(days=days_ahead + 1))
    events: List[Dict[str, Any]] = []
    t0 = now
    step = timedelta(hours=CLOSING_WINDOW_H + 1) if closing_only else timedelta(days=2)
    while t0 < horizon and not client.blocked:
        t1 = min(horizon, t0 + step)
        events.extend(client.by_date(t0, t1))
        t0 = t1
    stats: Dict[str, Any] = {"events": len(events), "matched": 0, "new_aliases": 0, "odds_rows": 0, "details": 0}
    if not events:
        stats.update(calls=client.calls, errors=client.errors[:5], blocked=client.blocked)
        return stats
    matches = conn.execute(
        "SELECT id, kickoff_utc, home_id, away_id, home_name, away_name FROM match WHERE kickoff_utc > ? AND kickoff_utc < ? "
        "AND (status IS NULL OR status IN ('notstarted','upcoming','scheduled'))",
        (stamp, canon_utc(horizon.isoformat()))).fetchall()
    by_id = {m["id"]: m for m in matches}
    # potrivirile existente rămân (ID Superbet stabil); restul se caută
    known = {r["match_id"]: r for r in conn.execute("SELECT * FROM ext_event WHERE source=?", (SOURCE,))}
    ev_by_id = {str(e.get("eventId")): e for e in events}
    mapping: Dict[int, Dict[str, Any]] = {}
    for mid, r in known.items():
        if mid in by_id and r["ext_id"] in ev_by_id:
            mapping[mid] = {"ext_id": r["ext_id"], "score": r["score"], "method": r["method"], "ev": ev_by_id[r["ext_id"]]}
    taken = {v["ext_id"] for v in mapping.values()} | {r["ext_id"] for r in known.values()}
    new = match_events(conn, [e for e in events if str(e.get("eventId")) not in taken],
                       [m for m in matches if m["id"] not in known])
    last = _last_prices(conn, list(mapping) + list(new))
    with conn:
        for mid, x in new.items():
            ev = x["ev"]
            conn.execute(
                "INSERT INTO ext_event(match_id, source, ext_id, score, method, ext_name, matched_at) VALUES (?,?,?,?,?,?,?) "
                "ON CONFLICT(match_id, source) DO UPDATE SET ext_id=excluded.ext_id, score=excluded.score, method=excluded.method, "
                "ext_name=excluded.ext_name, matched_at=excluded.matched_at",
                (mid, SOURCE, x["ext_id"], x["score"], x["method"], ev.get("matchName"), stamp))
            stats["new_aliases"] += learn_aliases(conn, by_id[mid], ev, x["score"] if x["method"] != "alias" else 1.0, stamp)
            mapping[mid] = x
        for mid, x in mapping.items():
            stats["odds_rows"] += _store(conn, mid, parse_odds(x["ev"]), last, stamp)
            conn.execute("UPDATE ext_event SET checked_at=? WHERE match_id=? AND source=?", (stamp, mid, SOURCE))
    stats["matched"] = len(mapping)
    stats["new_matches"] = len(new)
    # detalii: meciurile relevante, cele mai apropiate de start întâi
    detail_at = {r["match_id"]: r["detail_at"] for r in conn.execute("SELECT match_id, detail_at FROM ext_event WHERE source=?", (SOURCE,))}
    want = set(_interesting(conn, stamp, canon_utc(horizon.isoformat())))
    todo = []
    for mid in sorted((m for m in mapping if m in want), key=lambda m: by_id[m]["kickoff_utc"]):
        ko = datetime.fromisoformat(by_id[mid]["kickoff_utc"].replace("Z", "+00:00"))
        last_d = detail_at.get(mid)
        age_h = 1e9 if not last_d else (now - datetime.fromisoformat(last_d.replace("Z", "+00:00"))).total_seconds() / 3600
        near = (ko - now).total_seconds() / 3600 <= CLOSING_WINDOW_H
        if age_h >= DETAIL_STALE_H or (near and age_h * 60 >= CLOSING_STALE_MIN):
            todo.append(mid)
    for mid in todo:
        ev = client.event(mapping[mid]["ext_id"])
        if client.blocked or ev is None:
            if client.blocked:
                break
            continue
        stats["details"] += 1
        with conn:
            stats["odds_rows"] += _store(conn, mid, parse_odds(ev), last, stamp)
            stats["offer_rows"] = stats.get("offer_rows", 0) + store_offer(conn, mid, ev, stamp)
            conn.execute("UPDATE ext_event SET detail_at=?, checked_at=? WHERE match_id=? AND source=?", (stamp, stamp, mid, SOURCE))
    with conn:  # oferta brută e doar pentru meciurile viitoare (Bet Builder / piețe experimentale) — nu o arhivăm
        cutoff = canon_utc((now - timedelta(hours=6)).isoformat())
        stats["offer_pruned"] = conn.execute(
            "DELETE FROM sb_offer WHERE match_id IN (SELECT id FROM match WHERE kickoff_utc < ?)", (cutoff,)).rowcount
    stats.update(calls=client.calls, errors=client.errors[:5], blocked=client.blocked, wanted_details=len(todo))
    return stats


# piețele speciale păstrate brut (pentru piețe noi experimentale și Bet Builder): după nume, nu după id
OFFER_PREFIXES = ("Total goluri", "Prima repriză", "A doua repriză", "Total cornere", "Repriza cu cele mai multe goluri",
                  "1X2 & ", "Șansă dublă & ", "Total goluri & GG", "GG & ", "Conduce oricând", "Fiecare echipă")
OFFER_IDS = {231194}  # combinații predefinite („Bet Builder” Superbet), cu preț public


def store_offer(conn: sqlite3.Connection, mid: int, ev: Dict[str, Any], stamp: str) -> int:
    n = 0
    for o in ev.get("odds") or []:
        if (o.get("status") or "active") != "active":
            continue
        mname = str(o.get("marketName") or "")
        if not (o.get("marketId") in OFFER_IDS or mname.startswith(OFFER_PREFIXES)):
            continue
        try:
            price = float(o.get("price"))
        except (TypeError, ValueError):
            continue
        if price <= 1.0:
            continue
        conn.execute(
            "INSERT INTO sb_offer(match_id, market_id, market_name, outcome, line, price, observed_at) VALUES (?,?,?,?,?,?,?) "
            "ON CONFLICT(match_id, market_name, outcome) DO UPDATE SET price=excluded.price, observed_at=excluded.observed_at, line=excluded.line",
            (mid, o.get("marketId"), mname, str(o.get("name") or ""), str(o.get("specialBetValue") or ""), price, stamp))
        n += 1
    return n


def playable_odds(conn: sqlite3.Connection, match_ids: List[int], now: Optional[datetime] = None) -> Dict[int, Dict[str, Dict[str, float]]]:
    """Cotele Superbet proaspete (citite în ultimele ``FRESH_H`` ore): 1X2 din bulk, restul din detalii."""
    if not match_ids:
        return {}
    now = now or datetime.now(timezone.utc)
    lim = canon_utc((now - timedelta(hours=FRESH_H)).isoformat())
    q = ",".join("?" for _ in match_ids)
    fresh = {r["match_id"]: r for r in conn.execute(
        f"SELECT match_id, checked_at, detail_at FROM ext_event WHERE source=? AND match_id IN ({q})", [SOURCE, *match_ids])}
    ids = [m for m, r in fresh.items() if (r["checked_at"] or "") >= lim]
    out: Dict[int, Dict[str, Dict[str, float]]] = {}
    for mid, mk in repo.latest_odds(conn, ids, source=SOURCE).items():
        det_ok = (fresh[mid]["detail_at"] or "") >= lim
        out[mid] = {k: v for k, v in mk.items() if k == "1x2" or det_ok}
    return out
