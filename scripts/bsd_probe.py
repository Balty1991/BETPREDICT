"""Sondează endpointurile BSD cu cheia din BSD_API_KEY (nu o afișează). Rulat în GitHub Actions."""
import collections
import json
import os
import time
from datetime import date, timedelta

import requests

B = "https://sports.bzzoiro.com/api/v2/"
H = {"Authorization": f"Token {os.environ['BSD_API_KEY']}"}
out = {"calls": 0}


def g(path, **p):
    out["calls"] += 1
    r = requests.get(B + path, headers=H, params=p, timeout=30)
    try:
        return r.status_code, r.json()
    except ValueError:
        return r.status_code, None


today = date.today()
evs = []
for d in range(0, 3):
    s, js = g("events/", date_from=(today + timedelta(days=d)).isoformat(), date_to=(today + timedelta(days=d)).isoformat(), limit=200)
    evs += js.get("results", [])
out["events_3d"] = len(evs)
books = collections.Counter()
pin_events = 0
nb = []
markets = collections.Counter()
sample_pin = None
for e in evs[:40]:
    s, js = g(f"events/{e['id']}/odds/comparison/")
    if s != 200 or not js:
        out.setdefault("cmp_status", collections.Counter())[s] += 1
        continue
    bk = set()
    for mk, outs in (js.get("markets") or {}).items():
        markets[mk] += 1
        for o in outs.values():
            bk |= set((o.get("bookmakers") or {}).keys())
            if "pinnacle" in (o.get("bookmakers") or {}) and not sample_pin:
                sample_pin = {"market": mk, **o["bookmakers"]["pinnacle"]}
    books.update(bk)
    nb.append(len(bk))
    pin_events += "pinnacle" in bk
out.update(books_top=books.most_common(25), median_books=sorted(nb)[len(nb) // 2] if nb else 0, pin_events=f"{pin_events}/{len(nb)}",
           markets=markets.most_common(30), sample_pin=sample_pin)
ev = next((e for e in evs if True), None)
s, js = g("odds/", bookmaker_slug="pinnacle", limit=200)
out["odds_pinnacle"] = [s, js.get("count") if isinstance(js, dict) else None, (js.get("results") or [None])[:1] if isinstance(js, dict) else None]
s, js = g("odds/best/", market="1x2", limit=5)
out["odds_best"] = [s, js.get("count") if isinstance(js, dict) else None, (js.get("results") or [None])[:1] if isinstance(js, dict) else str(js)[:300]]
# lineups: meciuri terminate ieri + cele de azi aproape de start
s, fin = g("events/", date_from=(today - timedelta(days=1)).isoformat(), date_to=(today - timedelta(days=1)).isoformat(), status="finished", limit=10)
lu = []
for e in (fin.get("results") or [])[:5] + evs[:5]:
    s, js = g(f"events/{e['id']}/lineups/")
    lu.append([e["id"], e.get("status"), s, sorted(js.keys())[:12] if isinstance(js, dict) else None, json.dumps(js)[:300]])
out["lineups"] = lu
# rate limit: 60 cereri rapide
t = time.time(); codes = collections.Counter()
for _ in range(60):
    codes[g("bookmakers/")[0]] += 1
out["burst60"] = [dict(codes), round(time.time() - t, 1)]
s, js = g("coverage/")
out["coverage"] = str(js)[:400]
print("PROBE_JSON " + json.dumps(out, ensure_ascii=False, default=str))
