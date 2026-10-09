"""Asamblează site-ul static pentru branch-ul ``gh-pages`` (build făcut în Actions).

Conținut:
  * ``frontend/dist`` (build Vite proaspăt — nu se mai comite nimic pe ``main``);
  * scripturile UI vechi, nehash-uite, din ``assets/`` (``accumulator_ui.js`` etc.) și
    tag-urile ``<script>`` injectate în ``index.html`` de pe ``main`` — până la Etapa 3;
  * ``data/*.json`` (doar nivelul de sus; fără ``warehouse/`` și ``debug/``) — UI-ul
    actual le citește din ``./data/``;
  * fișierele PWA de la rădăcină (manifest, sw.js, iconițe);
  * opțional ``api/`` generat de ``daily-build``.
"""

from __future__ import annotations

import json
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

# Bundle-urile Vite vechi comise pe main (ex. ``Dashboard-B0yUYT64.js``) — NU se copiază.
HASHED_ASSET = re.compile(r"^[A-Za-z0-9_]+-[A-Za-z0-9_-]{8}\.(js|css)$")
LEGACY_SCRIPT_TAG = re.compile(r'<script\s+src="(assets/[^"?]+\.js)(\?[^"]*)?"\s*>\s*</script>')
ROOT_FILES = ("manifest.json", "sw.js", "favicon.ico", "apple-touch-icon.png", "icon-192.png", "icon-512.png")
# Fișiere care nu trebuie să ajungă niciodată pe site.
FORBIDDEN_NAMES = (".env", "bsd_quota.json")
MAX_DATA_FILE_MB = 50


def legacy_script_tags(root_index_html: str) -> List[str]:
    return [m.group(0) for m in LEGACY_SCRIPT_TAG.finditer(root_index_html)]


def inject_scripts(html: str, tags: List[str]) -> str:
    missing = []
    for tag in tags:
        src = LEGACY_SCRIPT_TAG.match(tag).group(1)  # type: ignore[union-attr]
        if f'src="{src}' not in html:
            missing.append(tag)
    if not missing:
        return html
    block = "".join(f"\n    {t}" for t in missing)
    m = re.search(r"\n?([ \t]*)</body>", html)
    if m:
        return html[: m.start()] + block + "\n" + m.group(1) + "</body>" + html[m.end():]
    return html + block + "\n"


def assemble_site(
    repo_root: Path,
    dist_dir: Path,
    out_dir: Path,
    api_dir: Optional[Path] = None,
    include_data: bool = True,
) -> Dict[str, object]:
    repo_root, dist_dir, out_dir = Path(repo_root), Path(dist_dir), Path(out_dir)
    if not (dist_dir / "index.html").exists():
        raise FileNotFoundError(f"lipsește {dist_dir}/index.html — rulează întâi build-ul frontend")
    if out_dir.exists():
        shutil.rmtree(out_dir)
    shutil.copytree(dist_dir, out_dir)

    # 1) scripturi/CSS vechi nehash-uite + iconițe
    legacy_assets = repo_root / "assets"
    copied_legacy = 0
    if legacy_assets.is_dir():
        for item in legacy_assets.iterdir():
            if item.is_file() and HASHED_ASSET.match(item.name):
                continue
            dest = out_dir / "assets" / item.name
            if dest.exists():
                continue
            if item.is_dir():
                shutil.copytree(item, dest)
            else:
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(item, dest)
            copied_legacy += 1

    # 2) tag-urile <script> injectate în index.html de pe main
    root_index = repo_root / "index.html"
    tags = legacy_script_tags(root_index.read_text(encoding="utf-8")) if root_index.exists() else []
    index = out_dir / "index.html"
    index.write_text(inject_scripts(index.read_text(encoding="utf-8"), tags), encoding="utf-8")

    # 3) fișiere PWA de la rădăcină
    for name in ROOT_FILES:
        src = repo_root / name
        if src.exists() and not (out_dir / name).exists():
            shutil.copy2(src, out_dir / name)

    # 4) date JSON (doar nivelul de sus)
    data_files = 0
    skipped_big: List[str] = []
    if include_data and (repo_root / "data").is_dir():
        (out_dir / "data").mkdir(exist_ok=True)
        for f in sorted((repo_root / "data").glob("*.json")):
            if f.name in FORBIDDEN_NAMES:
                continue
            if f.stat().st_size > MAX_DATA_FILE_MB * 1024 * 1024:
                skipped_big.append(f.name)
                continue
            shutil.copy2(f, out_dir / "data" / f.name)
            data_files += 1

    # 5) API nou (api/days/*.json)
    if api_dir and Path(api_dir).is_dir():
        shutil.copytree(api_dir, out_dir / "api", dirs_exist_ok=True)

    (out_dir / ".nojekyll").write_text("", encoding="utf-8")
    info = {
        "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "legacy_assets": copied_legacy,
        "legacy_script_tags": len(tags),
        "data_files": data_files,
        "skipped_big_data": skipped_big,
    }
    (out_dir / "build-info.json").write_text(json.dumps(info, indent=1), encoding="utf-8")
    return info


SECRET_PATTERNS = (
    re.compile(r"Authorization['\"]?\s*[:=]\s*[`'\"]Token"),
    re.compile(r"BSD_API_KEY"),
    re.compile(r"[?&]token=[A-Za-z0-9]{16,}"),
)


def scan_for_secrets(root: Path, extensions=(".js", ".html", ".ts", ".tsx", ".json", ".css")) -> List[str]:
    """Caută tipare care ar însemna că browserul trimite cheia BSD. Întoarce fișierele suspecte."""
    hits: List[str] = []
    for f in Path(root).rglob("*"):
        if not f.is_file() or f.suffix not in extensions or "node_modules" in f.parts:
            continue
        if f.suffix == ".json" and f.stat().st_size > 5 * 1024 * 1024:
            continue
        try:
            text = f.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for rx in SECRET_PATTERNS:
            if rx.search(text):
                hits.append(f"{f.relative_to(root)}: {rx.pattern}")
                break
    return hits
