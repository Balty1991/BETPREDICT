#!/usr/bin/env python3
"""Generează toate iconițele (PWA, favicon, Android) din sigla vectorială assets/icons/src/glyph.py.

Sigla: „B” neon cyan→violet într-un inel de șansă (ca ProbRing din aplicație), pe navy adânc.
Rulează din rădăcină:  python3 mobile/scripts/gen_icons.py   (cere playwright + Pillow; rezultatul se comite).
"""
import sys
from pathlib import Path
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "assets/icons/src"))
from glyph import svg  # noqa: E402
from playwright.sync_api import sync_playwright  # noqa: E402

RES = ROOT / "mobile/android/app/src/main/res"
ICONS = ROOT / "assets/icons"
DENS = {"mdpi": 1, "hdpi": 1.5, "xhdpi": 2, "xxhdpi": 3, "xxxhdpi": 4}

L = {}
with sync_playwright() as p:
    b = p.chromium.launch()
    pg = b.new_page(viewport={"width": 1024, "height": 1024})
    for k in ("full", "bleed", "fg", "mono", "monobig"):
        kind = "mono" if k == "monobig" else k
        s = svg(kind, 1024)
        if k == "monobig":  # glyph-ul alb pe toată suprafața (notificare)
            s = s.replace('<g transform="translate(50 50) scale(0.62) translate(-50 -50)">', "<g>")
        pg.set_content(f'<html><body style="margin:0;background:transparent">{s}</body></html>')
        out = ICONS / "src" / f"{k}.png"
        pg.locator("svg").screenshot(path=str(out), omit_background=True)
        L[k] = Image.open(out).convert("RGBA")
    b.close()


def save(img, path):
    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path, optimize=True)


def rs(img, s):
    return img.resize((round(s), round(s)), Image.LANCZOS)


def circle(img):
    m = Image.new("L", img.size, 0)
    ImageDraw.Draw(m).ellipse((0, 0, img.width - 1, img.height - 1), fill=255)
    out = img.copy()
    out.putalpha(m)
    return out


# PWA / web
for s in (32, 48, 72, 96, 128, 144, 180, 192, 256, 384, 512, 1024):
    save(rs(L["full"], s), ICONS / f"icon-{s}.png")
for s in (192, 512):
    save(rs(L["bleed"], s), ICONS / f"icon-{s}-maskable.png")
    save(rs(L["full"], s), ROOT / f"icon-{s}.png")
save(rs(L["bleed"], 180), ROOT / "apple-touch-icon.png")
rs(L["full"], 256).save(ROOT / "favicon.ico", sizes=[(16, 16), (32, 32), (48, 48), (64, 64)])

# Android
for d, k in DENS.items():
    save(rs(L["full"], 48 * k), RES / f"mipmap-{d}/ic_launcher.png")
    save(circle(rs(L["bleed"], 48 * k)), RES / f"mipmap-{d}/ic_launcher_round.png")
    save(rs(L["fg"], 108 * k), RES / f"mipmap-{d}/ic_launcher_foreground.png")
    save(rs(L["mono"], 108 * k), RES / f"mipmap-{d}/ic_launcher_monochrome.png")
    n = rs(L["monobig"], 24 * k)
    save(n, RES / f"drawable-{d}/ic_stat_notify.png")
k = 3
canvas = Image.new("RGBA", (288 * k, 288 * k), (0, 0, 0, 0))
logo = rs(L["fg"], 288 * k * 0.95)
canvas.alpha_composite(logo, ((canvas.width - logo.width) // 2,) * 2)
save(canvas, RES / "drawable-xxhdpi/splash_icon.png")
save(rs(L["full"], 120 * k), RES / "drawable-xxhdpi/splash_logo.png")
print("ok")
