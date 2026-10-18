#!/usr/bin/env python3
"""Mod umbră live: NU pariază, NU face bilete. La fiecare rulare citește oferta live Superbet (1 cerere publică, 1X2)
și scrie pentru fiecare meci în joc: minut, scor, cartonașe, cornere, cotele live 1/X/2 și estimarea noastră in-play
(Poisson pe golurile rămase: λ dinainte de meci × minutele rămase / 90). Peste câteva săptămâni: backtest live.

Ieșire: o linie JSON pe meci, adăugată în live_shadow/YYYY-MM-DD.jsonl (fișierul se urcă în release-ul live-shadow).
"""
from __future__ import annotations

import json
import math
import sys
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

SB = "https://production-superbet-offer-ro.freetls.fastly.net/v2/ro-RO/events/by-date"
SITE = "https://balty1991.github.io/BETPREDICT/api/days/{d}.json"
HDR = {"User-Agent": "Mozilla/5.0 BetPredict-shadow", "Referer": "https://superbet.ro/"}


def get(url: str):
    req = urllib.request.Request(url, headers=HDR)
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read().decode("utf-8"))


def pois(k: int, lam: float) -> float:
    return math.exp(-lam) * lam ** k / math.factorial(k)


def inplay_1x2(h: int, a: int, lh: float, la: float, minute: int) -> dict:
    rem = max(0.0, (90 - min(minute, 90)) / 90)
    ph = pd = pa = 0.0
    for i in range(11):
        for j in range(11):
            p = pois(i, lh * rem) * pois(j, la * rem)
            x, y = h + i, a + j
            if x > y:
                ph += p
            elif x == y:
                pd += p
            else:
                pa += p
    s = ph + pd + pa
    return {"HOME": round(ph / s, 4), "DRAW": round(pd / s, 4), "AWAY": round(pa / s, 4)}


def main(out_dir: str = "live_shadow") -> int:
    now = datetime.now(timezone.utc)
    f = lambda t: t.strftime("%Y-%m-%d+%H:%M:%S")
    live = get(f"{SB}?offerState=live&sportId=5&startDate={f(now - timedelta(hours=3))}&endDate={f(now + timedelta(hours=1))}").get("data") or []
    lam = {}
    for d in {now.date(), (now - timedelta(hours=3)).date()}:
        try:
            for m in get(SITE.format(d=d.isoformat())).get("matches") or []:
                mo = m.get("model") or {}
                if m.get("superbet_event_id") and mo.get("lambda_home"):
                    lam[str(m["superbet_event_id"])] = (m["id"], mo["lambda_home"], mo["lambda_away"])
        except Exception:  # noqa: BLE001
            pass
    rows = []
    for e in live:
        md = e.get("metadata") or {}
        if md.get("status") in ("FINISHED", None) or not md.get("minutes"):
            continue
        odds = {o.get("name"): o.get("price") for o in e.get("odds") or []
                if o.get("marketName") == "Final" and o.get("status") == "active"}
        h, a = int(md.get("homeTeamScore") or 0), int(md.get("awayTeamScore") or 0)
        try:
            minute = int(str(md["minutes"]).split(":")[0])
        except ValueError:
            continue
        r = {"at": now.isoformat(timespec="seconds"), "sb_event_id": e.get("eventId"), "match": e.get("matchName"),
             "minute": minute, "period": md.get("periodStatus"), "score": [h, a],
             "yc": [md.get("homeTeamYellowCards"), md.get("awayTeamYellowCards")],
             "rc": [md.get("homeTeamRedCards"), md.get("awayTeamRedCards")],
             "corners": [md.get("homeTeamCorners"), md.get("awayTeamCorners")],
             "odds_1x2": {"HOME": odds.get("1"), "DRAW": odds.get("X"), "AWAY": odds.get("2")}}
        L = lam.get(str(e.get("eventId")))
        if L:
            r["match_id"], r["lambda"] = L[0], [L[1], L[2]]
            r["est_1x2"] = inplay_1x2(h, a, L[1], L[2], minute)
        rows.append(r)
    p = Path(out_dir)
    p.mkdir(exist_ok=True)
    with open(p / f"{now.date().isoformat()}.jsonl", "a", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"live: {len(live)} evenimente, {len(rows)} în joc, {sum('est_1x2' in r for r in rows)} cu estimare")
    return 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:]))
