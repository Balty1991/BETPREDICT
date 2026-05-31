"""
veyra_to_signals.py — Convertor VEYRA ev_signals_v2.json → BETPREDICT signals.json

Preia output-ul motorului VEYRA Supreme Engine v5 și îl mapează în formatul
așteptat de UI-ul BETPREDICT (signals.json). Rulat după predict_current.py.
"""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

DATA_DIR = Path("data")

MARKET_LABEL = {
    "home_win":  "1 Victorie acasă",
    "draw":      "Egal",
    "away_win":  "X Victorie deplasare",
    "btts":      "BTTS",
    "over15":    "Over 1.5G",
    "over25":    "Over 2.5G",
    "under35":   "Under 3.5G",
}

MARKET_CANONICAL = {
    "home_win":  "homeWin",
    "draw":      "draw",
    "away_win":  "awayWin",
    "btts":      "btts",
    "over15":    "over15",
    "over25":    "over25",
    "under35":   "under35",
}

# Mapa calitate VEYRA → grade BETPREDICT
QUALITY_TO_GRADE = {
    "A": "A+",
    "B": "A",
    "C": "B",
}


def load_json(path: Path, default=None):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def save_json(path: Path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, separators=(",", ":"))


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def convert_signal(sig: dict) -> dict:
    """Converteste un semnal VEYRA în formatul BETPREDICT signals.json."""
    market_key = sig.get("market", "")
    quality_gate = sig.get("quality_gate", "B")
    grade = QUALITY_TO_GRADE.get(quality_gate, "B")

    final_prob = sig.get("final_prob") or sig.get("adjusted_prob", 0)
    if final_prob > 1:
        final_prob = final_prob / 100.0
    adj_prob = round(final_prob * 100, 1)

    ev_pct = sig.get("ev_pct", 0)
    edge_pp = sig.get("edge_pp", 0)

    # EV ca fracție (BETPREDICT stochează 0.0x, nu %)
    ev_val = ev_pct / 100.0 if ev_pct else 0.0

    # Score 0-100
    score = sig.get("score", 50)

    # Smartbet score v6 = score VEYRA
    smartbet_score_v6 = round(score, 1)
    display_score = round(score, 1)

    # Calibrated prob = final_prob VEYRA (deja blend + calibrare)
    calibrated_prob = round(final_prob, 4)

    home = sig.get("home") or sig.get("home_team", "")
    away = sig.get("away") or sig.get("away_team", "")
    league = sig.get("league", "")
    if isinstance(league, dict):
        league = league.get("name", "")

    event_date = sig.get("event_date") or sig.get("date", "")
    if event_date and len(event_date) == 10:
        event_date = event_date + "T00:00:00Z"

    # Model vs market gap
    nv_prob = sig.get("nv_prob", 0)
    if nv_prob and nv_prob < 1:
        gap_pp = round((final_prob - nv_prob) * 100, 1)
    else:
        gap_pp = None

    blend = sig.get("blend", {})
    sources = [k for k, v in blend.get("values", {}).items() if v is not None]

    out = {
        "event_id": sig.get("event_id"),
        "home_team": home,
        "away_team": away,
        "home_team_id": sig.get("home_team_id"),
        "away_team_id": sig.get("away_team_id"),
        "league": league,
        "league_id": sig.get("league_id"),
        "event_date": event_date,
        "market": MARKET_CANONICAL.get(market_key, market_key),
        "market_label": MARKET_LABEL.get(market_key, market_key),
        "adj_prob": adj_prob,
        "calibrated_prob": calibrated_prob,
        "confidence": round((sig.get("agreement", 0.6)) * 100, 1),
        "smartbet_score": smartbet_score_v6,
        "smartbet_score_v6": smartbet_score_v6,
        "display_score": display_score,
        "quality_grade": grade,
        "quality_grade_v6": grade,
        "odds": sig.get("odds"),
        "odds_real": True,
        "ev": ev_val,
        "ev_calibrated": ev_val,
        "ev_pct": f"{ev_pct:.1f}%",
        "edge_pp": edge_pp,
        "kelly_pct": f"{sig.get('kelly_pct', 0):.1f}%",
        "strategy": "veyra_engine",
        "strategy_label": "VEYRA Engine v5",
        "strategy_icon": "🎯",
        "strategy_color": "#2BE5C5",
        "model_vs_market_gap_pp": gap_pp,
        # VEYRA-specific fields
        "wfv_auc": sig.get("wfv_auc"),
        "test_ece": sig.get("test_ece"),
        "agreement": sig.get("agreement"),
        "reliability": sig.get("reliability"),
        "lineup_risk": sig.get("lineup_risk"),
        "context_risk": sig.get("context_risk"),
        "risk_tier": sig.get("risk_tier"),
        "signal": sig.get("signal"),
        "rationale": sig.get("rationale"),
        "blend_sources": sources,
        "model_prob_catboost": sig.get("model_prob"),
        "api_prob_bsd": sig.get("api_prob"),
        "poisson_prob": sig.get("poisson_prob"),
        "h2h_matches": sig.get("h2h_matches"),
        "h2h_btts_rate": sig.get("h2h_btts_rate"),
        "h2h_avg_goals": sig.get("h2h_avg_goals"),
        "home_form_score": sig.get("home_form_score"),
        "away_form_score": sig.get("away_form_score"),
        "home_form_string": sig.get("home_form_string"),
        "away_form_string": sig.get("away_form_string"),
        "is_local_derby": sig.get("is_local_derby"),
        "best_bookmaker": sig.get("best_bookmaker"),
        "engine_version": "veyra-supreme-engine-v5",
    }
    # Curăță None-urile pentru a reduce dimensiunea JSON
    return {k: v for k, v in out.items() if v is not None}


def main():
    print("=== VEYRA → BETPREDICT signals adapter ===")

    veyra_path = DATA_DIR / "ev_signals_v2.json"
    if not veyra_path.exists():
        print("ev_signals_v2.json lipseste — skip")
        return

    veyra = load_json(veyra_path, {})
    raw_signals = veyra.get("signals", []) if isinstance(veyra, dict) else []

    if not raw_signals:
        print("Niciun semnal VEYRA — skip")
        return

    converted = [convert_signal(s) for s in raw_signals]

    # Filtrare minimă: pastram doar semnale cu grade A+/A/B si odds >= 1.35
    GOOD_GRADES = {"A+", "A", "B"}
    veyra_filtered = [
        s for s in converted
        if s.get("quality_grade_v6") in GOOD_GRADES
        and (s.get("odds") or 0) >= 1.35
        and (s.get("ev") or 0) > 0
    ]

    # ── Merge cu signals.json existent (motorul vechi) ──────────────────────
    existing = load_json(DATA_DIR / "signals.json", {})
    old_signals = existing.get("signals", []) if isinstance(existing, dict) else []

    # VEYRA are prioritate: construim set de (event_id, market) acoperite de VEYRA
    veyra_keys = {
        (str(s.get("event_id", "")), s.get("market", ""))
        for s in veyra_filtered
    }

    # Pastram semnalele vechi care NU sunt acoperite de VEYRA
    old_kept = [
        s for s in old_signals
        if (str(s.get("event_id", "")), s.get("market", "")) not in veyra_keys
        and s.get("strategy") != "veyra_engine"  # elimina VEYRA vechi
    ]

    # Combinam: VEYRA pe primul loc, restul dupa
    merged = veyra_filtered + old_kept
    merged.sort(key=lambda x: x.get("display_score", x.get("smartbet_score_v6", 0)), reverse=True)

    supreme = veyra.get("supreme_summary", {}) if isinstance(veyra, dict) else {}

    # Rebuild by_strategy: dict ca în motorul v6
    old_by_strategy = existing.get("by_strategy", {}) if isinstance(existing, dict) else {}
    if isinstance(old_by_strategy, list):
        # Convertim din list → dict dacă e nevoie
        old_by_strategy = {item.get("strategy", "?"): item for item in old_by_strategy if isinstance(item, dict)}

    by_strategy = dict(old_by_strategy)  # copie
    # Elimina intrările VEYRA vechi, reinjectăm fresh
    by_strategy.pop("veyra_engine", None)
    if veyra_filtered:
        by_strategy["veyra_engine"] = [s for s in veyra_filtered]

    # Rebuild strategy_stats
    old_stats = existing.get("strategy_stats", {}) if isinstance(existing, dict) else {}
    strategy_stats = dict(old_stats)
    strategy_stats["veyra_engine"] = {
        "count": len(veyra_filtered),
        "avg_score": round(supreme.get("avg_score", 0), 1),
        "avg_agreement": round(supreme.get("avg_agreement_pct", 0), 1),
    }

    payload = {
        "updated_at": now_iso(),
        "count": len(merged),
        "signals": merged,
        "by_strategy": by_strategy,
        "strategy_stats": strategy_stats,
        "_pipeline_version": "veyra-supreme-engine-v5+engine-v6",
        "_v6_enhanced": True,
        "_v6_stats": {
            "total_raw": len(raw_signals),
            "veyra_after_filter": len(veyra_filtered),
            "old_engine_kept": len(old_kept),
            "merged_total": len(merged),
            "elite_count": supreme.get("elite_count", 0),
            "quality_a_count": supreme.get("quality_a_count", 0),
        },
    }

    save_json(DATA_DIR / "signals.json", payload)
    print(
        f"signals.json scris: {len(merged)} semnale total "
        f"({len(veyra_filtered)} VEYRA + {len(old_kept)} motor vechi)"
    )

    # Scrie si versiunea VEYRA separata (pentru referinta)
    save_json(DATA_DIR / "ev_signals_v2.json", veyra)

    # Re-rulează journal update după merge — semnalele VEYRA ajung acum în istoric
    try:
        import importlib, sys as _sys
        _sys.path.insert(0, str(Path(__file__).parent))
        fd = importlib.import_module("fetch_daily")
        fd.update_selection_journal()
        print("[journal] Actualizat cu semnale VEYRA")
    except Exception as _je:
        print(f"[WARN] Journal update post-VEYRA esuat: {_je}")


if __name__ == "__main__":
    main()
