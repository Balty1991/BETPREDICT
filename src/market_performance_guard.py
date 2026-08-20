#!/usr/bin/env python3
"""market_performance_guard.py — poarta de selectie bazata pe performanta MASURATA.

Auditul din 21.07.2026 a aratat ca platforma isi masoara onest performanta
(adaptive_thresholds.json = ROI real decontat per piata, calibration_health.json
= calitatea calibrarii, sharp_paper_trades.json = CLV real, superbet_edge_history
= win rate real al picioarelor), dar NICIUN sistem de selectie nu folosea aceste
cifre. Rezultatul: piramida recomanda under35 (ROI masurat -20%, n=93), biletele
includeau picioare 1x2 (41% win rate real), iar semnalele value rulau cu CLV
mediu -2.24% si doar 14% din pariuri care bat cota de inchidere.

Acest modul transforma cifrele masurate in decizii:
  - market_guard()      -> per piata (format compact: under35, over15, homeWin...):
                           block/penalizare/boost dupa ROI real + calibrare
  - edge_market_guard() -> per piata în format Superbet Edge (1x2, btts,
                           over_under_25...) dupa win rate-ul real al picioarelor
  - clv_gate()          -> starea portii CLV pentru semnalele value
                           (regula clv_min_positive_rate exista in risk_state.json
                           dar nu era aplicata nicaieri)

Pragurile sunt intentionat conservatoare: penalizam/blocam doar cu esantion
suficient (n>=30 respectiv n>=50), ca sa nu reactionam la zgomot.
"""
from __future__ import annotations
import json
import os
from typing import Any, Dict

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(os.path.dirname(HERE), "data")

# Praguri de evidenta — sub aceste esantioane nu tragem concluzii.
MIN_N_PENALIZE = 30    # ROI negativ pe n>=30 -> penalizare
MIN_N_BLOCK = 50       # ROI <= -10% pe n>=50 -> blocat din recomandarile cu bani
# O pierdere foarte mare este suficient de informativă mai devreme decât una mică:
# la n>=30 și ROI <= -20%, suspendăm piața până când datele noi o reabilitează.
MIN_N_SEVERE_HOLD = 30
SEVERE_HOLD_ROI = -20.0
MIN_N_BOOST = 100      # ROI >= +5% pe n>=100 -> usor favorizat
MIN_N_CLV = 30         # sub 30 trade-uri cu CLV, poarta CLV ramane deschisa (fara verdict)


def _load(name: str, default: Any = None) -> Any:
    try:
        with open(os.path.join(DATA, name), "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def market_guard() -> Dict[str, Dict[str, Any]]:
    """Verdict per piata (format compact) din ROI-ul real decontat.

    Returneaza: {market: {"mult": float, "blocked": bool, "roi_pct": float,
                          "n": int, "reason": str}}
    Pietele fara date suficiente nu apar (tratate neutru de apelant).
    """
    at = _load("adaptive_thresholds.json", {}) or {}
    out: Dict[str, Dict[str, Any]] = {}
    for mk, rec in (at.get("by_market") or {}).items():
        st = (rec or {}).get("stats") or {}
        n = int(st.get("n") or 0)
        roi = float(st.get("roi_pct") or 0.0)
        if n < MIN_N_PENALIZE:
            continue
        if ((roi <= -10.0 and n >= MIN_N_BLOCK) or
                (roi <= SEVERE_HOLD_ROI and n >= MIN_N_SEVERE_HOLD)):
            severity = "pierderi severe" if roi <= SEVERE_HOLD_ROI and n < MIN_N_BLOCK else "pierderi sistemice"
            out[mk] = {"mult": 0.0, "blocked": True, "roi_pct": roi, "n": n,
                       "reason": f"{severity}: ROI real {roi}% pe {n} pariuri decontate — exclus din recomandari"}
        elif roi < 0.0:
            out[mk] = {"mult": 0.55, "blocked": False, "roi_pct": roi, "n": n,
                       "reason": f"ROI real {roi}% pe {n} pariuri — penalizat la selectie"}
        elif roi >= 5.0 and n >= MIN_N_BOOST:
            out[mk] = {"mult": 1.15, "blocked": False, "roi_pct": roi, "n": n,
                       "reason": f"ROI real +{roi}% pe {n} pariuri — usor favorizat"}
    return out


# Piata Superbet Edge ('1x2') acopera homeWin/draw/awayWin — win rate-ul real al
# picioarelor e masurat direct in superbet_edge_history.json pe acest format.
def edge_market_guard() -> Dict[str, Dict[str, Any]]:
    """Verdict per piata în format Superbet Edge, din win rate-ul real al picioarelor.

    Un picior sub 50% win rate real (n>=30) nu are ce cauta intr-un bilet
    acumulator — fiecare astfel de picior injumatateste sansele biletului.
    """
    hist = _load("superbet_edge_history.json", {}) or {}
    out: Dict[str, Dict[str, Any]] = {}
    for mk, rec in (hist.get("legs_by_market") or {}).items():
        n = int(rec.get("n_settled") or 0)
        wr = rec.get("win_rate_pct")
        if n < MIN_N_PENALIZE or wr is None:
            continue
        wr = float(wr)
        if wr < 50.0:
            out[mk] = {"blocked_in_tickets": True, "win_rate_pct": wr, "n": n,
                       "reason": f"win rate real {wr}% pe {n} picioare decontate — exclus din bilete"}
    return out


def clv_gate() -> Dict[str, Any]:
    """Poarta CLV pentru semnalele value — aplica regula din risk_state.json.

    CLV (closing line value) e cel mai cinstit predictor al profitului pe termen
    lung: daca sistematic NU batem cota de inchidere, piata spune ca pariurile
    noastre sunt pe partea gresita, indiferent de rezultatele pe termen scurt.
    """
    rules = (_load("risk_state.json", {}) or {}).get("rules") or {}
    min_rate = float(rules.get("clv_min_positive_rate") or 0.4)
    overall = (_load("sharp_paper_trades.json", {}) or {}).get("overall") or {}
    n = int(overall.get("n_with_clv") or 0)
    rate = overall.get("clv_positive_rate")
    if n < MIN_N_CLV or rate is None:
        return {"paused": False, "n_with_clv": n, "clv_positive_rate": rate,
                "min_required": min_rate, "reason": "esantion CLV insuficient — poarta deschisa"}
    rate = float(rate)
    if rate < min_rate:
        return {"paused": True, "n_with_clv": n, "clv_positive_rate": rate,
                "min_required": min_rate,
                "reason": (f"doar {round(rate * 100)}% din pariuri bat cota de inchidere "
                           f"(minim cerut {round(min_rate * 100)}%, n={n}) — semnalele value sunt "
                           "in pauza pana cand selectia redevine competitiva cu piata")}
    return {"paused": False, "n_with_clv": n, "clv_positive_rate": rate,
            "min_required": min_rate, "reason": "CLV peste pragul minim — poarta deschisa"}


if __name__ == "__main__":
    print("market_guard:", json.dumps(market_guard(), ensure_ascii=False, indent=1))
    print("edge_market_guard:", json.dumps(edge_market_guard(), ensure_ascii=False, indent=1))
    print("clv_gate:", json.dumps(clv_gate(), ensure_ascii=False, indent=1))
