#!/usr/bin/env python3
"""
superbet_recon.py — investigatie unica: cum isi ia Superbet.ro cotele de pe server?
======================================================================================

NU e parte din pipeline-ul orar. Se ruleaza manual (workflow_dispatch), o singura
data (sau de cate ori e nevoie in faza de investigatie), ca sa afle:
  1. Ce request-uri XHR/fetch (JSON) face pagina cand incarci un meci — echivalentul
     automat al "F12 -> Network -> Fetch/XHR" facut manual in Chrome.
  2. Structura reala a raspunsului (nume de campuri, cum sunt reprezentate cotele).

Rezultatul (data/superbet_recon.json + screenshot) e folosit ca sa se scrie apoi
un scraper real, robust — in loc sa ghicim orb selectoare CSS/API care se pot
schimba oricand.

Politete: o singura vizita de pagina, fara request-uri repetate, User-Agent normal
de browser (Playwright/Chromium implicit) — nu incearca sa ocoleasca nicio protectie
anti-bot; daca site-ul blocheaza sau cere CAPTCHA, scriptul se opreste si raporteaza,
nu insista.

Ruleaza: python3 src/superbet_recon.py "Universitatea Craiova" "UTA Arad"
"""
from __future__ import annotations
import json, os, sys, tempfile
from datetime import datetime, timezone
from typing import Any, Dict, List

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, "data")

SEARCH_URL = "https://superbet.ro/"
NAV_TIMEOUT_MS = 20000
WAIT_AFTER_LOAD_MS = 4000


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


def main() -> int:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("[superbet_recon] playwright nu e instalat — 'pip install playwright && playwright install chromium'")
        return 1

    home_team = sys.argv[1] if len(sys.argv) > 1 else "Universitatea Craiova"
    away_team = sys.argv[2] if len(sys.argv) > 2 else "UTA Arad"

    captured: List[Dict[str, Any]] = []
    console_errors: List[str] = []
    steps: List[str] = []

    def on_response(response):
        try:
            rtype = response.request.resource_type
            ctype = response.headers.get("content-type", "")
            if rtype in ("xhr", "fetch") and "json" in ctype.lower():
                body = None
                try:
                    body = response.json()
                except Exception:
                    body = None
                captured.append({
                    "url": response.url,
                    "status": response.status,
                    "resource_type": rtype,
                    "content_type": ctype,
                    "body_sample": _truncate(body),
                })
        except Exception:
            pass

    def _truncate(obj: Any, max_chars: int = 4000) -> Any:
        s = json.dumps(obj, ensure_ascii=False, default=str) if obj is not None else None
        if s is None:
            return None
        return json.loads(s) if len(s) <= max_chars else {"_truncated": True, "preview": s[:max_chars]}

    def _click_visible_text(page, text: str, exact: bool, steps: List[str]) -> bool:
        """Incearca toate elementele cu acest text (nu doar .first — pot exista
        duplicate ascunse, ex. meniu mobil vs desktop) si da click pe primul
        vizibil + activabil. Returneaza True daca a reusit."""
        try:
            matches = page.get_by_text(text, exact=exact).all()
        except Exception as e:
            steps.append(f"lookup for {text!r} failed: {e}")
            return False
        if not matches:
            steps.append(f"no elements found with text {text!r}")
            return False
        for i, el in enumerate(matches):
            try:
                if el.is_visible():
                    el.click(timeout=3000)
                    steps.append(f"clicked {text!r} (match {i+1}/{len(matches)})")
                    page.wait_for_timeout(3000)
                    return True
            except Exception as e:
                steps.append(f"{text!r} match {i+1}/{len(matches)} click failed: {e}")
        steps.append(f"{text!r}: {len(matches)} match(es) found, none visible/clickable")
        return False

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.on("response", on_response)
        page.on("console", lambda m: console_errors.append(m.text) if m.type == "error" else None)
        page.set_default_navigation_timeout(NAV_TIMEOUT_MS)

        try:
            steps.append(f"goto {SEARCH_URL}")
            page.goto(SEARCH_URL, wait_until="domcontentloaded")
            page.wait_for_timeout(WAIT_AFTER_LOAD_MS)
        except Exception as e:
            steps.append(f"goto FAILED: {e}")
            browser.close()
            _write_result(home_team, away_team, steps, captured, console_errors, None, "")
            return 0

        homepage_title = page.title()
        steps.append(f"homepage title: {homepage_title!r}")

        # 1) Accepta cookie banner-ul (OneTrust) daca apare, altfel poate bloca click-urile.
        cookie_selectors = [
            "#onetrust-accept-btn-handler", 'button:has-text("Accept")',
            'button:has-text("Acceptă")', 'button:has-text("De acord")',
        ]
        for sel in cookie_selectors:
            try:
                el = page.query_selector(sel)
                if el:
                    el.click(timeout=3000)
                    steps.append(f"clicked cookie consent via: {sel}")
                    page.wait_for_timeout(1000)
                    break
            except Exception as e:
                steps.append(f"cookie selector {sel} failed: {e}")

        # 1b) Diagnostic: ce e clickabil pe pagina curenta (utile daca inca suntem
        # blocati pe un ecran gen "Intro"/gate, ca sa stim exact ce sa dam click runda viitoare).
        try:
            btn_texts = [t.strip() for t in page.locator("button").all_inner_texts() if t.strip()]
            link_texts = [t.strip() for t in page.locator("a").all_inner_texts() if t.strip()]
            steps.append(f"visible button texts ({len(btn_texts)}): {btn_texts[:40]}")
            steps.append(f"visible link texts ({len(link_texts)}): {link_texts[:40]}")
        except Exception as e:
            steps.append(f"clickable-text diagnostic failed: {e}")

        # 2) Runda 3 a aratat ca homepage-ul e un ecran "Intro" (gate) cu link-uri
        #    Sport / Casino / Casino Live — trebuie intrat intai pe "Sport".
        # Runda 4: link-ul exista in DOM (aparea in lista de texte) dar `.first`
        #    cu is_visible(timeout=...) a raportat "not visible" — probabil exista
        #    duplicate (meniu mobil ascuns) si `.first` nimerea unul ascuns.
        #    Acum incercam toate elementele, nu doar primul.
        if _click_visible_text(page, "Sport", exact=True, steps=steps):
            page.wait_for_timeout(1000)

        # 2b) Diagnostic din nou, dupa ce am intrat (sperat) in sectiunea Sport.
        try:
            btn_texts2 = [t.strip() for t in page.locator("button").all_inner_texts() if t.strip()]
            link_texts2 = [t.strip() for t in page.locator("a").all_inner_texts() if t.strip()]
            steps.append(f"[post-Sport] visible button texts ({len(btn_texts2)}): {btn_texts2[:40]}")
            steps.append(f"[post-Sport] visible link texts ({len(link_texts2)}): {link_texts2[:40]}")
            steps.append(f"[post-Sport] url: {page.url}")
        except Exception as e:
            steps.append(f"[post-Sport] clickable-text diagnostic failed: {e}")

        # 2c) Incearca sa navigheze prin UI: Fotbal -> SuperLiga -> un meci.
        for label in ["Fotbal", "SuperLiga", "Superliga"]:
            _click_visible_text(page, label, exact=False, steps=steps)

        try:
            mid_screenshot = os.path.join(DATA, "superbet_recon_tournament.png")
            page.screenshot(path=mid_screenshot, full_page=False)
            steps.append(f"tournament-page screenshot saved: {mid_screenshot}")
        except Exception as e:
            steps.append(f"tournament screenshot failed: {e}")

        # 3) Incearca sa dea click pe primul meci vizibil din lista, ca sa ajunga pe pagina
        #    de detaliu (unde ar trebui sa fie request-ul cu cotele 1X2/BTTS/O-U).
        match_link_selectors = [
            'a[href*="meci"]', 'a[href*="match"]', '[data-testid*="match" i]',
            '[class*="match-row" i]', '[class*="event-row" i]',
        ]
        clicked_match = False
        for sel in match_link_selectors:
            try:
                el = page.query_selector(sel)
                if el:
                    el.click(timeout=3000)
                    steps.append(f"clicked match row via: {sel}")
                    clicked_match = True
                    page.wait_for_timeout(3000)
                    break
            except Exception as e:
                steps.append(f"match selector {sel} failed: {e}")
        if not clicked_match:
            steps.append("no clickable match row found with known selectors")

        page.wait_for_timeout(WAIT_AFTER_LOAD_MS)

        screenshot_path = os.path.join(DATA, "superbet_recon.png")
        try:
            page.screenshot(path=screenshot_path, full_page=False)
            steps.append(f"screenshot saved: {screenshot_path}")
        except Exception as e:
            steps.append(f"screenshot failed: {e}")

        html_content = page.content()
        steps.append(f"final page html length: {len(html_content)}")

        browser.close()

    _write_result(home_team, away_team, steps, captured, console_errors, homepage_title, html_content)
    print(f"[superbet_recon] {len(captured)} raspunsuri JSON XHR/fetch capturate. Vezi data/superbet_recon.json")
    for c in captured[:10]:
        print(f"  {c['status']} {c['url'][:100]}")
    return 0


def _write_result(home_team, away_team, steps, captured, console_errors, title, html_content=""):
    body_text = _strip_html_tags(html_content)
    out = {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "source": "superbet_recon_v1",
        "note": "Investigatie unica, NU parte din pipeline-ul orar. Scop: identifica request-urile "
                "JSON reale ale site-ului Superbet, ca sa se poata scrie apoi un scraper fiabil.",
        "query": {"home_team": home_team, "away_team": away_team},
        "page_title": title,
        "steps": steps,
        "console_errors": console_errors[:20],
        "n_json_responses_captured": len(captured),
        "json_responses": captured[:40],
        "visible_body_text_sample": body_text[:3000],
    }
    _atomic_write("superbet_recon.json", out)


def _strip_html_tags(html: str) -> str:
    import re
    text = re.sub(r"<script[^>]*>.*?</script>", " ", html, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<style[^>]*>.*?</style>", " ", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


if __name__ == "__main__":
    raise SystemExit(main())
