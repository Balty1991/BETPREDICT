#!/usr/bin/env python3
"""
Injectează sau actualizează Match Data Pack UI în index.html.
Versiune layout fix: pas25fix.
"""

from pathlib import Path
import re

ROOT = Path(__file__).parent.parent.resolve()
INDEX = ROOT / "index.html"
SCRIPT = '<script src="assets/match_data_pack_ui.js?v=pas25fix"></script>'

def main() -> None:
    if not INDEX.exists():
        print("index.html lipsește — skip inject")
        return

    html = INDEX.read_text(encoding="utf-8")

    # Înlocuiește orice versiune veche a scriptului, inclusiv pas25.
    pattern = re.compile(r'<script\s+src=["\']assets/match_data_pack_ui\.js\?v=[^"\']+["\']\s*></script>')
    if pattern.search(html):
        html = pattern.sub(SCRIPT, html)
        INDEX.write_text(html, encoding="utf-8")
        print("Match Data Pack UI version actualizat la pas25fix")
        return

    if "assets/match_data_pack_ui.js" in html:
        html = re.sub(
            r'<script\s+src=["\']assets/match_data_pack_ui\.js["\']\s*></script>',
            SCRIPT,
            html
        )
        INDEX.write_text(html, encoding="utf-8")
        print("Match Data Pack UI script actualizat")
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
