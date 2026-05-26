"""Equity Curve — Pilon 8.

Construiește time-series-ul bankroll-ului din selection_journal:
units câștigate per zi, cumulativ, peak, drawdown actual, best/worst day.

Răspunde la întrebarea fundamentală "fac bani?" cu un grafic real,
nu doar un agregat.

⚠ Trebuie să producă EXACT aceleași numere ca tab-ul ACUR din UI
(assets/perf_dashboard.js → renderDailyStats):
  - filtru: status='settled' AND result in {WIN, LOST}
  - data: timezone local (Europe/Bucharest), nu UTC
  - stake: fix 1.0u per pariu
  - profit per pariu: (odds-1) pe WIN, -1.0 pe LOST

Output: data/equity_curve.json
"""
from __future__ import annotations
import json
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"

# Aceeași zona orară ca în UI (toLocaleDateString('ro-RO')).
# Folosim ZoneInfo dacă e disponibil; altfel UTC+3 (Europe/Bucharest vara) ca fallback.
try:
    from zoneinfo import ZoneInfo
    LOCAL_TZ = ZoneInfo("Europe/Bucharest")
except Exception:
    LOCAL_TZ = timezone(timedelta(hours=3))


def _safe_float(x, default=0.0):
    try:
        return float(x) if x is not None else default
    except (TypeError, ValueError):
        return default


def _local_day(iso: str) -> str:
    """Returnează cheia zi (YYYY-MM-DD) în timezone-ul local, ca în ACUR."""
    if not iso:
        return ""
    try:
        # Acceptă atât 'Z' cât și offset. Python ≥3.11 suportă 'Z' nativ.
        s = iso.replace("Z", "+00:00") if iso.endswith("Z") else iso
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(LOCAL_TZ).strftime("%Y-%m-%d")
    except Exception:
        return iso[:10]


def build_equity_curve() -> dict:
    journal_path = DATA / "selection_journal.json"
    if not journal_path.exists():
        return {"updated_at": datetime.now(timezone.utc).isoformat(), "points": [], "summary": {}}

    journal = json.loads(journal_path.read_text())
    results = journal.get("results", []) or []

    # Filtrare identică cu ACUR (perf_dashboard.js → renderDailyStats):
    # status='settled' + result truthy. Orice non-WIN = pierdere (1u stake).
    by_day = defaultdict(lambda: {"wins": 0, "losses": 0, "units": 0.0, "n": 0, "stake_total": 0.0})
    for r in results:
        if r.get("status") != "settled":
            continue
        outcome = r.get("result")
        if not outcome:
            continue
        day = _local_day(r.get("event_date") or r.get("settled_at") or "")
        if not day:
            continue
        odds = _safe_float(r.get("odds"), 0.0)
        is_win = outcome == "WIN"
        by_day[day]["n"] += 1
        by_day[day]["stake_total"] += 1.0  # stake fix 1u, ca în ACUR
        if is_win:
            by_day[day]["wins"] += 1
            by_day[day]["units"] += (odds - 1) if odds > 0 else 0.0
        else:
            by_day[day]["losses"] += 1
            by_day[day]["units"] -= 1.0

    days = sorted(by_day.keys())
    points = []
    cumulative = 0.0
    peak = 0.0
    max_drawdown = 0.0

    for day in days:
        b = by_day[day]
        cumulative += b["units"]
        peak = max(peak, cumulative)
        drawdown = cumulative - peak  # negativ când e sub peak
        max_drawdown = min(max_drawdown, drawdown)
        wr = round(100 * b["wins"] / b["n"], 1) if b["n"] else 0.0
        points.append({
            "date": day,
            "n": b["n"],
            "wins": b["wins"],
            "losses": b["losses"],
            "win_rate": wr,
            "units_delta": round(b["units"], 3),
            "stake_total": round(b["stake_total"], 2),
            "units_cumulative": round(cumulative, 3),
            "drawdown_from_peak": round(drawdown, 3),
        })

    # Summary metrics
    total_n = sum(p["n"] for p in points)
    total_wins = sum(p["wins"] for p in points)
    total_stake = sum(p["stake_total"] for p in points)
    final_units = round(cumulative, 3)
    roi_pct = round(100 * final_units / total_stake, 2) if total_stake > 0 else 0.0
    wr_total = round(100 * total_wins / total_n, 1) if total_n else 0.0

    best_day = max(points, key=lambda p: p["units_delta"], default=None)
    worst_day = min(points, key=lambda p: p["units_delta"], default=None)

    # Current drawdown (from latest peak)
    current_dd = round(final_units - peak, 3) if points else 0.0
    current_dd_pct = round(100 * current_dd / peak, 2) if peak > 0 else 0.0

    # Status label
    if final_units > 0 and current_dd_pct >= -10:
        status, status_label = "good", "PROFITABIL"
    elif final_units > 0:
        status, status_label = "warn", "PROFITABIL · DD"
    elif final_units > -2:
        status, status_label = "warn", "NEUTRU"
    else:
        status, status_label = "bad", "PIERDERE"

    summary = {
        "n_days": len(points),
        "n_bets": total_n,
        "wins": total_wins,
        "win_rate": wr_total,
        "units_final": final_units,
        "stake_total": round(total_stake, 2),
        "roi_pct": roi_pct,
        "peak_units": round(peak, 3),
        "max_drawdown_units": round(max_drawdown, 3),
        "current_drawdown_units": current_dd,
        "current_drawdown_pct": current_dd_pct,
        "best_day": {"date": best_day["date"], "units": best_day["units_delta"]} if best_day else None,
        "worst_day": {"date": worst_day["date"], "units": worst_day["units_delta"]} if worst_day else None,
        "status": status,
        "status_label": status_label,
    }

    return {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "source": "selection_journal.json",
        "points": points,
        "summary": summary,
    }


def main():
    out = build_equity_curve()
    out_path = DATA / "equity_curve.json"
    out_path.write_text(json.dumps(out, indent=2, ensure_ascii=False))
    s = out["summary"]
    print(f"[equity_curve] wrote {out_path}")
    print(f"  days: {s.get('n_days')} | bets: {s.get('n_bets')} | WR: {s.get('win_rate')}%")
    print(f"  units: {s.get('units_final')} | ROI: {s.get('roi_pct')}% | peak: {s.get('peak_units')}u")
    print(f"  current DD: {s.get('current_drawdown_units')}u ({s.get('current_drawdown_pct')}%) · max DD: {s.get('max_drawdown_units')}u")
    print(f"  status: {s.get('status_label')}")


if __name__ == "__main__":
    main()
