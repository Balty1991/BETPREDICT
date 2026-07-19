#!/usr/bin/env python3
"""
pyramid_tracker.py — BetPredict v7 Pyramid State Tracker (Faza 2+3)
========================================================================

Urmărește, pas cu pas, ce s-ar întâmpla DACĂ ai urma exact sugestiile zilnice
ale pyramid_assistant.py — două piramide în paralel, cum a fost cerut:
  "safe" — țintă ~1.30 cotă/pas, din pool-ul cel mai de încredere (10 pași)
  "risk" — țintă ~2.50 cotă/pas, pool mai larg (5 pași)

IMPORTANT — e un tracker "în umbră" (paper), NU plasează pariuri reale și NU
știe dacă tu ai plasat efectiv pariul pe Superbet. Motivul: sistemul nu are
acces la contul tău Superbet, iar a PRESUPUNE că ai urmat sugestia ar fi
neonest. Rolul lui: (1) validare continuă, live, a "realistic_completion"
din Faza 1 — nu doar un backtest static, ci un test viu, care se acumulează
zi de zi; (2) o regulă FORMALĂ, consecventă de retragere parțială — exact
ce făceai tu manual (din instinct/frică), dar aplicată identic de fiecare
dată, nu după cum simți în momentul respectiv.

Regula de retragere (implicită, vezi WITHDRAW_FROM_STEP/WITHDRAW_PCT mai jos):
  De la pasul 5 în sus, la fiecare câștig, se retrage 50% din profitul
  acumulat (peste miza inițială) — restul + miza inițială continuă piramida.

Ciclu per track (safe/risk):
  - Dacă exista un pas "pending" (inregistrat, in asteptarea rezultatului),
    incearca sa-l deconteze din recent_results.json.
      WIN  -> bankroll *= cota; aplica regula de retragere; step += 1
      LOSS -> reset la pasul 0, bankroll = miza initiala
  - Daca NU exista pending (sau tocmai s-a decontat), inregistreaza candidatul
    cu scorul cel mai mare pentru pasul urmator, din pyramid_assistant.json.

Output: data/pyramid_state.json
Ruleaza standalone (dupa pyramid_assistant.py): python3 src/pyramid_tracker.py
"""
from __future__ import annotations
import json, os, sys, tempfile
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, "data")
sys.path.insert(0, HERE)
sys.path.insert(0, ROOT)

from sharp_clv_logger import _settle, _results_index
from pyramid_assistant import MARKET_MAP, _realistic_completion, _historical_leg_win_rate, _local_date_ro, _TZ_RO

STATE_FILE = "pyramid_state.json"

INITIAL_STAKE_LEI = 10.0   # miza de start (paper) — simbolica, nu conteaza suma exacta
WITHDRAW_FROM_STEP = 5     # de la ce pas (inclusiv) incepe retragerea partiala automata
WITHDRAW_PCT = 0.50        # % din profitul acumulat (peste miza initiala) retras la fiecare castig de la acest pas in sus

TRACKS = {
    "safe": {"label": "Piramidă sigură (~1.30/pas)", "pool_source": "current_step_pool", "max_step": 10},
    "risk": {"label": "Piramidă risc (~2.50/pas)", "pool_source": "pools_by_target:t2_50", "max_step": 5},
}


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
            json.dump(obj, f, ensure_ascii=False, indent=2, default=str)
        os.replace(tmp, p)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)


def _pool_for_step(pyramid_data: Dict[str, Any], pool_source: str, step: int) -> List[Dict[str, Any]]:
    if pool_source == "current_step_pool":
        return pyramid_data.get("current_step_pool", {}).get(str(step), []) or []
    if pool_source.startswith("pools_by_target:"):
        tk = pool_source.split(":", 1)[1]
        return pyramid_data.get("pools_by_target", {}).get(tk, {}).get(str(step), []) or []
    return []


def _fresh_track(label: str) -> Dict[str, Any]:
    return {
        "label": label,
        "initial_stake_lei": INITIAL_STAKE_LEI,
        "step": 0,
        "bankroll_lei": INITIAL_STAKE_LEI,
        "total_withdrawn_lei": 0.0,
        "peak_step_reached": 0,
        "n_runs_completed": 0,   # de cate ori a ajuns la pasul maxim
        "n_resets": 0,           # de cate ori a picat (a inceput din nou)
        "pending": None,
        "history": [],
    }


def _apply_withdrawal(step: int, bankroll: float, initial_stake: float) -> (float, float):
    """La pasul WITHDRAW_FROM_STEP+, retrage WITHDRAW_PCT din profitul acumulat
    (peste miza initiala). Sistematizeaza retragerile partiale facute manual —
    aceeasi regula, de fiecare data, nu dupa cat de curajos/speriat te simti."""
    if step < WITHDRAW_FROM_STEP:
        return round(bankroll, 2), 0.0
    profit = max(0.0, bankroll - initial_stake)
    withdrawn = round(profit * WITHDRAW_PCT, 2)
    return round(bankroll - withdrawn, 2), withdrawn


def _settle_pending(track: Dict[str, Any], res_idx: Dict[Any, Dict[str, Any]], now: str) -> None:
    pend = track.get("pending")
    if not pend:
        return
    r = res_idx.get(pend.get("event_id"))
    if not r:
        return
    hs, as_ = r.get("home_score"), r.get("away_score")
    if hs is None or as_ is None:
        return
    sm, so = MARKET_MAP.get(pend.get("market"), (None, None))
    if not sm:
        track["pending"] = None
        return
    w = _settle(sm, so, int(hs), int(as_))
    if w is None:
        return  # piata neinteleasa — nu putem decide, ramane pending (nu ar trebui sa se intample)

    entry = dict(pend)
    entry["final_score"] = f"{int(hs)}-{int(as_)}"
    entry["settled_at"] = now

    if w:
        new_bankroll = round(pend["stake_lei"] * pend["odds"], 2)
        new_step = track["step"] + 1
        after_withdraw, withdrawn = _apply_withdrawal(new_step, new_bankroll, track["initial_stake_lei"])
        entry["result"] = "WIN"
        entry["bankroll_after"] = new_bankroll
        entry["withdrawn_lei"] = withdrawn
        track["bankroll_lei"] = after_withdraw
        track["total_withdrawn_lei"] = round(track["total_withdrawn_lei"] + withdrawn, 2)
        track["step"] = new_step
        track["peak_step_reached"] = max(track["peak_step_reached"], new_step)
    else:
        entry["result"] = "LOSS"
        entry["bankroll_after"] = 0.0
        entry["withdrawn_lei"] = 0.0
        track["n_resets"] += 1
        track["step"] = 0
        track["bankroll_lei"] = track["initial_stake_lei"]

    track["history"].append(entry)
    track["history"] = track["history"][-200:]  # nu crestem nelimitat
    track["pending"] = None


def _register_next(track: Dict[str, Any], pool_source: str, max_step: int,
                   pyramid_data: Dict[str, Any], now: str) -> None:
    if track.get("pending"):
        return
    target_step = track["step"] + 1
    if target_step > max_step:
        # ai terminat piramida (toate treptele castigate) — o nouă rundă începe de la 0
        track["n_runs_completed"] += 1
        track["step"] = 0
        target_step = 1
    candidates = _pool_for_step(pyramid_data, pool_source, target_step)
    if not candidates:
        return  # niciun candidat de incredere azi pt. acest pas — asteptam, nu fortam
    top = candidates[0]
    track["pending"] = {
        "step": target_step, "event_id": top.get("event_id"),
        "home_team": top.get("home_team"), "away_team": top.get("away_team"),
        "league": top.get("league"), "event_date": top.get("event_date"),
        "market": top.get("market"), "market_label": top.get("market_label"),
        "odds": top.get("odds"), "bookmaker": top.get("bookmaker"),
        "adj_prob": top.get("adj_prob"),
        "pyramid_ready_score": top.get("pyramid_ready_score"),
        "calibration_status": top.get("calibration_status"),
        "stake_lei": track["bankroll_lei"],
        "registered_at": now,
    }


def _drop_stale_pending(track: Dict[str, Any]) -> None:
    """Tracker paper: pending-ul e doar o sugestie, nu un pariu plasat. Daca sugestia
    e pentru ALTA zi decat cea curenta (ex: ramasa de ieri), o eliminam ca sa
    inregistram pontul de AZI."""
    pend = track.get("pending")
    if not pend:
        return
    d = _local_date_ro(pend)  # foloseste pend['event_date']
    if d is None or d != datetime.now(_TZ_RO).date() or pend.get("adj_prob") in (None, 0):
        track["pending"] = None


def main() -> int:
    pyramid_data = _load("pyramid_assistant.json", {}) or {}
    recent = _load("recent_results.json", {}) or {}
    res_idx = _results_index(recent)
    now = datetime.now(timezone.utc).isoformat()

    state = _load(STATE_FILE, {}) or {}
    tracks = state.get("tracks", {})

    for key, cfg in TRACKS.items():
        track = tracks.get(key) or _fresh_track(cfg["label"])
        track["label"] = cfg["label"]  # tine eticheta la zi daca s-a schimbat
        _settle_pending(track, res_idx, now)
        _drop_stale_pending(track)
        _register_next(track, cfg["pool_source"], cfg["max_step"], pyramid_data, now)
        tracks[key] = track

    hist = _historical_leg_win_rate()
    out = {
        "updated_at": now,
        "source": "pyramid_tracker_v1",
        "disclaimer": (
            "Tracker ÎN UMBRĂ (paper) — nu știe dacă ai plasat efectiv pariul pe Superbet, "
            "doar urmărește ce s-ar fi întâmplat dacă ai fi urmat exact sugestia zilei. "
            "Regula de retragere (de la pasul "
            f"{WITHDRAW_FROM_STEP}, {int(WITHDRAW_PCT*100)}% din profit la fiecare câștig) "
            "e fixă și consecventă — nu se schimbă după cât de încrezător/speriat te simți în ziua respectivă."
        ),
        "withdrawal_rule": {"from_step": WITHDRAW_FROM_STEP, "pct_of_profit": WITHDRAW_PCT},
        "historical_track_record": hist,
        "tracks": tracks,
    }
    _atomic_write(STATE_FILE, out)
    for key, track in tracks.items():
        pend = track.get("pending")
        pend_note = (f"pending: {pend['home_team']} vs {pend['away_team']} @ {pend['odds']}"
                     if pend else "fara candidat azi")
        print(f"[pyramid_tracker] {key}: step={track['step']} bankroll={track['bankroll_lei']} "
              f"retras_total={track['total_withdrawn_lei']} resets={track['n_resets']} | {pend_note}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
