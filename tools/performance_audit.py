#!/usr/bin/env python3
"""Audit reproductibil al jurnalului de selecții BETPREDICT."""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from statistics import mean
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"


def load_json(name: str) -> dict[str, Any]:
    with (DATA / name).open(encoding="utf-8") as handle:
        return json.load(handle)


def num(value: Any, fallback: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback


def group_report(rows: list[dict[str, Any]], label: str, key_fn: Callable[[dict[str, Any]], str], minimum: int = 1) -> None:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[key_fn(row) or "(lipsă)"].append(row)

    output = []
    for key, group in groups.items():
        count = len(group)
        wins = sum(1 for x in group if x.get("result") == "WIN")
        profit = sum(num(x.get("profit_units")) for x in group)
        roi = profit / count * 100 if count else 0.0
        avg_odds = mean(num(x.get("odds")) for x in group)
        output.append((roi, key, count, wins / count * 100, profit, avg_odds))

    output.sort(key=lambda item: (item[0], item[2]))
    print(f"\n## {label} (n >= {minimum})")
    print("grup | n | win rate | profit unități | ROI | cotă medie")
    for roi, key, count, wr, profit, avg_odds in output:
        if count >= minimum:
            print(f"{key} | {count} | {wr:.1f}% | {profit:+.2f} | {roi:+.1f}% | {avg_odds:.2f}")


def main() -> None:
    journal = load_json("selection_journal.json")
    rows = [x for x in journal.get("results", []) if x.get("status") == "settled" and x.get("result") in {"WIN", "LOSS", "VOID"}]
    actionable = [x for x in rows if x.get("result") in {"WIN", "LOSS"}]
    wins = [x for x in actionable if x.get("result") == "WIN"]
    losses = [x for x in actionable if x.get("result") == "LOSS"]
    profit = sum(num(x.get("profit_units")) for x in actionable)
    roi = profit / len(actionable) * 100 if actionable else 0.0

    print("# Audit performanță BETPREDICT")
    print(f"Jurnal actualizat: {journal.get('updated_at')}")
    print(f"Selecții settle-uite analizabile: {len(actionable)}")
    print(f"Win rate: {len(wins) / len(actionable) * 100:.1f}%" if actionable else "Win rate: n/a")
    print(f"Profit: {profit:+.2f} unități | ROI: {roi:+.2f}%")
    print(f"Cotă medie WIN: {mean(num(x.get('odds')) for x in wins):.2f}" if wins else "Cotă medie WIN: n/a")
    print(f"Cotă medie LOSS: {mean(num(x.get('odds')) for x in losses):.2f}" if losses else "Cotă medie LOSS: n/a")

    group_report(actionable, "Strategie", lambda x: str(x.get("strategy")), minimum=5)
    group_report(actionable, "Piață", lambda x: str(x.get("market_canonical") or x.get("market")), minimum=5)
    group_report(actionable, "Ligă", lambda x: str(x.get("league")), minimum=10)
    group_report(actionable, "Sursă", lambda x: str(x.get("source")), minimum=5)
    group_report(actionable, "Bandă de cote", lambda x: f"{int(num(x.get('odds')) * 10) / 10:.1f}-{int(num(x.get('odds')) * 10) / 10 + 0.1:.1f}", minimum=10)

    thresholds = load_json("adaptive_thresholds.json")
    print("\n## Praguri adaptive curente")
    for market, details in sorted((thresholds.get("by_market") or {}).items()):
        stats = details.get("stats") or {}
        recommendation = details.get("recommended") or {}
        print(
            f"{market} | n={stats.get('n', 0)} | roi={num(stats.get('roi_pct')):+.1f}% | "
            f"status={recommendation.get('status', 'n/a')} | "
            f"min_edge={recommendation.get('min_edge', 'n/a')} | "
            f"odds={recommendation.get('odd_min', 'n/a')}-{recommendation.get('odd_max', 'n/a')}"
        )


if __name__ == "__main__":
    main()
