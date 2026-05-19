#!/usr/bin/env python3
"""
Injectează Match Data Pack UI în index.html fără să rescrie manual aplicația.
Rulează în workflow după generarea datelor.
"""

from pathlib import Path

ROOT = Path(__file__).parent.parent.resolve()
INDEX = ROOT / "index.html"
SCRIPT = '<script src="assets/match_data_pack_ui.js?v=pas25"></script>'

def main() -> None:
    if not INDEX.exists():
        print("index.html lipsește — skip inject")
        return
    html = INDEX.read_text(encoding="utf-8")
    if "assets/match_data_pack_ui.js" in html:
        print("Match Data Pack UI deja injectat")
        return
    marker = "</body>"
    if marker in html:
        html = html.replace(marker, f"  {SCRIPT}\n{marker}", 1)
    else:
        html += "\n" + SCRIPT + "\n"
    INDEX.write_text(html, encoding="utf-8")
    print("Match Data Pack UI injectat în index.html")

if __name__ == "__main__":
    main()
