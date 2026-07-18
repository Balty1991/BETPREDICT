#!/usr/bin/env python3
"""
superbet_live_odds.py — cote reale Superbet, automat, orar
=============================================================

Gasit prin recon (src/superbet_recon.py, investigatie manuala, 9 runde): endpoint
PUBLIC, JSON, raspunde la un GET simplu, fara sesiune de browser/cookies:

  https://production-superbet-offer-ro.freetls.fastly.net/v2/ro-RO/events/by-date
    ?currentStatus=active&offerState=prematch&startDate=...&endDate=...&sportId=5

Un singur request intoarce TOATE meciurile de fotbal (sportId=5) din fereastra
de zile ceruta, fiecare cu cotele lui incluse — nu trebuie interogat per meci.

Piete extrase (ID-uri gasite tot prin recon, din catalogul complet al unui meci):
  547    -> 1X2 ("Final")            outcomes: "1" / "X" / "2"
  539    -> BTTS ("Ambele echipe marcheaza (GG)")  outcomes: "Da" / "Nu"
  200734 -> Total goluri (Over/Under, toate liniile)  outcomes: "Peste N.N" / "Sub N.N"

Output: data/superbet_live_odds.json — lista de meciuri cu cote normalizate pe
outcome-urile folosite in restul sistemului (HOME/DRAW/AWAY, YES/NO, OVER/UNDER),
gata de potrivit (fuzzy pe nume echipa) cu compare_odds_cache.json in
superbet_edge_engine.py.

Politete: un singur request catre by-date per rulare (nu per-meci).
Ruleaza: python3 src/superbet_live_odds.py
"""
from __future__ import annotations
import json, os, re, sys, tempfile, unicodedata
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, "data")

BASE_URL = "https://production-superbet-offer-ro.freetls.fastly.net/v2/ro-RO/events/by-date"
SPORT_ID_FOTBAL = 5
WINDOW_DAYS = 10  # aliniat cu superbet_edge_engine.WINDOW_DAYS
TIMEOUT_S = 20

HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"),
    "Accept": "application/json",
    "Referer": "https://superbet.ro/",
}

MARKET_ID_1X2 = 547
MARKET_ID_BTTS = 539
MARKET_ID_TOTAL_GOLURI = 200734

OUTCOME_MAP_1X2 = {"1": "HOME", "X": "DRAW", "2": "AWAY"}
OUTCOME_MAP_BTTS = {"Da": "YES", "Nu": "NO"}
OU_LINE_TO_MARKET_KEY = {"1.5": "over_under_15", "2.5": "over_under_25", "3.5": "over_under_35"}

NOISE_TOKENS = {
    "fc", "cs", "cf", "afc", "sc", "ac", "ss", "ssc", "cd", "ud", "sk", "sd",
    "cfr", "fk", "if", "bk", "united", "club", "cska",
}


def _atomic_write(name: str, obj: Any) -> None:
    p = os.path.join(DATA, name)
    fd, tmp = tempfile.mkstemp(dir=DATA, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False, indent=2, default=str)
        os.replace(tmp, p)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)


def normalize_team_name(name: str) -> str:
    """Fara diacritice, lowercase, fara prefixe/sufixe de club comune —
    ca sa se poata potrivi 'Farul Constanța' (Pinnacle) cu 'Farul Constanta'
    sau 'FCV Farul Constanta' (Superbet), fara sa fie identice caracter cu caracter."""
    if not name:
        return ""
    n = unicodedata.normalize("NFKD", name)
    n = "".join(c for c in n if not unicodedata.combining(c))
    n = n.lower()
    n = re.sub(r"[^a-z0-9\s]", " ", n)
    tokens = [t for t in n.split() if t not in NOISE_TOKENS]
    return " ".join(tokens).strip()


# Prag minim de potrivire (nume echipa, normalizat) ca sa acceptam un meci din
# superbet_live_odds.json drept ACELASI meci dintr-o alta sursa (compare_odds_cache.json,
# signals_v6.json) — sub asta preferam sa NU potrivim deloc decat sa riscam sa aratam
# cota reala a altui meci. Folosit de superbet_edge_engine.py SI smart_accumulator.py.
LIVE_MATCH_MIN_SCORE = 0.6


def team_match_score(a: str, b: str) -> float:
    """Scor de similaritate 0..1 intre doua nume de echipa (brute, neormalizate).
    DOAR overlap de cuvinte (nu si SequenceMatcher.ratio pe stringul intreg) —
    ratio pe nume scurte cu cuvinte comune (ex. 'Real Madrid' vs 'Real Sociedad')
    da scoruri inselator de mari, ceea ce ar putea potrivi gresit doua echipe
    diferite. Un fals negativ aici e sigur (cade pe estimarea calibrata); un
    fals pozitiv ar arata un prag calculat pentru meciul GRESIT — inacceptabil
    cand miza e bani reali."""
    na, nb = normalize_team_name(a), normalize_team_name(b)
    if not na or not nb:
        return 0.0
    if na == nb:
        return 1.0
    ta, tb = set(na.split()), set(nb.split())
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / max(len(ta), len(tb))


def _fmt_date(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d+%H:%M:%S")


def fetch_superbet_events() -> List[Dict[str, Any]]:
    import requests
    now = datetime.now(timezone.utc)
    start, end = _fmt_date(now), _fmt_date(now + timedelta(days=WINDOW_DAYS))
    url = (f"{BASE_URL}?currentStatus=active&offerState=prematch"
           f"&startDate={start}&endDate={end}&sportId={SPORT_ID_FOTBAL}")
    resp = requests.get(url, headers=HEADERS, timeout=TIMEOUT_S)
    resp.raise_for_status()
    return resp.json().get("data") or []


def _extract_markets(odds: List[Dict[str, Any]]) -> Dict[str, Dict[str, float]]:
    markets: Dict[str, Dict[str, float]] = {}
    for o in odds or []:
        mid = o.get("marketId")
        name = (o.get("name") or "").strip()
        price = o.get("price")
        if price is None:
            continue
        if mid == MARKET_ID_1X2 and name in OUTCOME_MAP_1X2:
            markets.setdefault("1x2", {})[OUTCOME_MAP_1X2[name]] = price
        elif mid == MARKET_ID_BTTS and name in OUTCOME_MAP_BTTS:
            markets.setdefault("btts", {})[OUTCOME_MAP_BTTS[name]] = price
        elif mid == MARKET_ID_TOTAL_GOLURI:
            m = re.match(r"(Peste|Sub)\s+([\d.]+)", name)
            if m:
                key = OU_LINE_TO_MARKET_KEY.get(m.group(2))
                if key:
                    outcome = "OVER" if m.group(1) == "Peste" else "UNDER"
                    markets.setdefault(key, {})[outcome] = price
    return markets


def build_live_odds(events: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    """`events` injectabil pentru teste; implicit (None) le ia de la Superbet."""
    error = None
    if events is None:
        try:
            events = fetch_superbet_events()
        except Exception as e:
            events, error = [], str(e)

    matches: List[Dict[str, Any]] = []
    for ev in events:
        parts = (ev.get("matchName") or "").split("·")
        if len(parts) != 2:
            continue
        home_sb, away_sb = parts[0].strip(), parts[1].strip()
        markets = _extract_markets(ev.get("odds") or [])
        if not markets:
            continue
        matches.append({
            "superbet_event_id": ev.get("eventId"),
            "home_team_superbet": home_sb,
            "away_team_superbet": away_sb,
            "home_team_norm": normalize_team_name(home_sb),
            "away_team_norm": normalize_team_name(away_sb),
            "match_date": ev.get("matchDate"),
            "tournament_id": ev.get("tournamentId"),
            "markets": markets,
        })

    return {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "source": "superbet_live_odds_v1",
        "note": "Cote reale Superbet, luate automat prin endpoint-ul public gasit prin "
                "recon (src/superbet_recon.py) — nu mai e nevoie de calibrare manuala "
                "din screenshot-uri pentru meciurile acoperite aici.",
        "window_days": WINDOW_DAYS,
        "fetch_error": error,
        "n_raw_events": len(events),
        "n_matches_with_markets": len(matches),
        "matches": matches,
    }


def find_live_match(live_matches: List[Dict[str, Any]], home_team: str, away_team: str,
                    event_dt: Optional[datetime], min_score: float = LIVE_MATCH_MIN_SCORE
                    ) -> Optional[Dict[str, Any]]:
    """Cauta in `live_matches` (din superbet_live_odds.json) meciul care corespunde
    (home_team, away_team, event_dt) dintr-o alta sursa. Cere data identica (aceeasi
    zi calendaristica UTC) si scor minim de nume pt. AMBELE echipe — ca sa nu riscam
    sa potrivim gresit doua meciuri diferite cu nume asemanatoare. Daca nu suntem
    siguri, intoarcem None (sursa apelanta trebuie sa aiba un fallback sigur)."""
    if not live_matches or not event_dt:
        return None
    date_key = event_dt.strftime("%Y-%m-%d")
    best, best_score = None, 0.0
    for m in live_matches:
        md = m.get("match_date") or ""
        if not md.startswith(date_key):
            continue
        sh = team_match_score(home_team, m.get("home_team_superbet", ""))
        sa = team_match_score(away_team, m.get("away_team_superbet", ""))
        score = min(sh, sa)
        if score > best_score:
            best_score, best = score, m
    return best if best_score >= min_score else None


def _load_existing(name: str) -> Optional[Dict[str, Any]]:
    try:
        with open(os.path.join(DATA, name), "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def main() -> int:
    out = build_live_odds()
    # protect_empty: daca fetch-ul a esuat (sau a intors 0 meciuri) si avem deja un
    # fisier bun de la o rulare anterioara, NU il stergem — smart_accumulator.py si
    # superbet_edge_engine.py depind acum de datele astea; o eroare tranzitorie de
    # retea nu trebuie sa goleasca brusc bilete/watchlist care functionau.
    if out["n_matches_with_markets"] == 0:
        prev = _load_existing("superbet_live_odds.json")
        if prev and prev.get("n_matches_with_markets", 0) > 0:
            prev["fetch_error"] = out.get("fetch_error") or "0 meciuri la ultima rulare — pastrat fisierul anterior"
            prev["stale_since"] = out["updated_at"]
            out = prev
        else:
            _atomic_write("superbet_live_odds.json", out)
    else:
        _atomic_write("superbet_live_odds.json", out)
    err = f" | EROARE: {out['fetch_error']}" if out.get("fetch_error") else ""
    print(f"[superbet_live_odds] {out['n_matches_with_markets']}/{out.get('n_raw_events', 0)} "
          f"meciuri cu cote extrase{err}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
