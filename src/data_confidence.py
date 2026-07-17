#!/usr/bin/env python3
"""
data_confidence.py — scor de încredere în DATE per meci
=======================================================

Problema: modelul dă „Over 1.5 81% · Risc: Sigur" la fel pentru un meci amical
fără istoric (formă „—", fără lineup, fără xG) ca pentru un meci cu date complete.
Eticheta de risc reflectă DOAR probabilitatea, nu cât de multe date reale o susțin.

Acest modul calculează cât de bine e ACOPERIT fiecare meci cu date reale din API:
  - formă recentă (câte meciuri istorice per echipă)
  - istoric direct (H2H sample)
  - lineup-uri confirmate
  - xG disponibil
  - adâncime cote (câți bookmakeri)
  - ligă clasată (standings) vs amical/echipă națională

Tier:  COMPLETE >=70 · PARTIAL >=45 · REDUS >=25 · INSUFICIENT <25

Predicțiile pe meciuri INSUFICIENT/REDUS nu ar trebui tratate ca „sigure".
v7_edge_index și smart_accumulator folosesc acest scor ca poartă de calitate.

Output: data/data_confidence.json  (by_event: {eid: {...}})
Ruleaza:  python3 src/data_confidence.py
"""
from __future__ import annotations
import json, os, sys, tempfile
from datetime import datetime, timezone
from typing import Any, Dict

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, "data")
sys.path.insert(0, ROOT)

try:
    from analytics_core import safe_float
except Exception:
    def safe_float(v, d=0.0):
        try:
            x = float(v); return d if x != x else x
        except Exception:
            return d

TIERS = [(70, "COMPLETE", "Date complete"), (45, "PARTIAL", "Date parțiale"),
         (25, "REDUS", "Date reduse"), (0, "INSUFICIENT", "Date insuficiente")]


def _load(name: str, default: Any = None) -> Any:
    try:
        with open(os.path.join(DATA, name), "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def _atomic_write(name: str, obj: Any) -> None:
    p = os.path.join(DATA, name)
    fd, tmp = tempfile.mkstemp(dir=DATA, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False, indent=2)
        os.replace(tmp, p)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)


def _team_form_samples() -> Dict[str, int]:
    """team_id (str) -> nr. de meciuri istorice cunoscute (lungimea form_string).
    Folosește team_form_cache.json (2000+ echipe, sursa afișată în UI) + fallback
    la team_form.json (sample explicit)."""
    samples: Dict[str, int] = {}
    tfc = (_load("team_form_cache.json", {}) or {}).get("teams", {})
    if isinstance(tfc, dict):
        for tid, v in tfc.items():
            if isinstance(v, dict):
                samples[str(tid)] = len((v.get("form_string") or "").strip())
    tf = _load("team_form.json", {}) or {}
    rows = tf.get("results") or (tf if isinstance(tf, list) else [])
    for r in rows:
        if isinstance(r, dict) and r.get("team_id") is not None:
            tid = str(r.get("team_id"))
            samples[tid] = max(samples.get(tid, 0), int(safe_float(r.get("sample"))))
    return samples


def _index_by_event(obj: Any) -> Dict[Any, Dict[str, Any]]:
    rows = (obj or {}).get("results") if isinstance(obj, dict) else obj
    if isinstance(obj, dict) and not rows:
        rows = [v for v in obj.values() if isinstance(v, dict)]
    out = {}
    for r in (rows or []):
        if isinstance(r, dict) and r.get("event_id") is not None:
            out[str(r.get("event_id"))] = r
    return out


def _odds_depth_index() -> Dict[str, int]:
    """event_id -> nr. de piețe cu cote (proxy de adâncime a pieței)."""
    bo = _load("best_odds.json", {}) or {}
    depth: Dict[str, int] = {}
    for r in (bo.get("results") or []):
        eid = str(r.get("event_id"))
        depth[eid] = depth.get(eid, 0) + 1
    return depth


def _score_form(sample: float) -> int:
    if sample >= 5: return 22
    if sample >= 3: return 14
    if sample >= 1: return 6
    return 0


def _tier(score: float):
    for thr, code, label in TIERS:
        if score >= thr:
            return code, label
    return "INSUFICIENT", "Date insuficiente"


def main() -> int:
    ew = _load("events_window.json", {}) or {}
    events = ew.get("results") or []
    form_samples = _team_form_samples()
    h2h_idx = _index_by_event(_load("h2h_context.json", {}))
    xg_idx = _index_by_event(_load("xg_context.json", {}))
    lineup_idx = _index_by_event(_load("lineup_intelligence.json", {}))
    odds_depth = _odds_depth_index()

    by_event: Dict[str, Any] = {}
    for e in events:
        eid = str(e.get("event_id") or e.get("id"))
        if eid in by_event:
            continue
        h_samp = form_samples.get(str(e.get("home_team_id")), 0)
        a_samp = form_samples.get(str(e.get("away_team_id")), 0)
        h2h = h2h_idx.get(eid) or {}
        h2h_samp = safe_float(h2h.get("sample"))
        lineup = lineup_idx.get(eid) or {}
        has_lineup = bool(lineup.get("available"))
        has_xg = eid in xg_idx and safe_float(xg_idx[eid].get("xg_total")) > 0
        depth = odds_depth.get(eid, 0)

        factors = {
            "form_home": _score_form(h_samp),
            "form_away": _score_form(a_samp),
            "h2h": (14 if h2h_samp >= 5 else 9 if h2h_samp >= 3 else 4 if h2h_samp >= 1 else 0),
            "lineup": 16 if has_lineup else 0,
            "xg": 14 if has_xg else 0,
            "odds_depth": 12 if depth >= 5 else 6 if depth >= 2 else 0,
        }
        score = min(100, sum(factors.values()))
        code, label = _tier(score)

        by_event[eid] = {
            "score": score, "tier": code, "label": label,
            "factors": factors,
            "form_sample": {"home": int(h_samp), "away": int(a_samp)},
            "h2h_sample": int(h2h_samp),
            "has_lineup": has_lineup, "has_xg": has_xg, "odds_markets": depth,
            "reliable": score >= 45,  # PARTIAL+ = destul de fiabil pentru pariat
        }

    from collections import Counter
    tier_dist = Counter(v["tier"] for v in by_event.values())
    out = {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "source": "data_confidence_v1",
        "note": "Scor de acoperire cu date reale per meci. Predicțiile pe meciuri "
                "INSUFICIENT/REDUS nu trebuie tratate ca sigure, oricât de mare e probabilitatea.",
        "summary": {
            "n_events": len(by_event),
            "tier_distribution": dict(tier_dist),
            "reliable_pct": round(sum(1 for v in by_event.values() if v["reliable"])
                                  / max(1, len(by_event)) * 100, 1),
        },
        "by_event": by_event,
    }
    _atomic_write("data_confidence.json", out)
    print(f"[data_confidence] {len(by_event)} meciuri | tiers: {dict(tier_dist)} | "
          f"fiabile (PARTIAL+): {out['summary']['reliable_pct']}%")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
