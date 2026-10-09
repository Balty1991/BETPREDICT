#!/usr/bin/env python3
"""Generează iconițele Android (launcher, adaptive, round, splash, notificare) din sigla BP.

Sursa: assets/icons/icon-1024.png (aceeași siglă ca PWA-ul). Rulează din mobile/:
    python3 scripts/gen_icons.py
Rezultatul se comite în android/app/src/main/res (build-ul din CI nu are nevoie de Pillow).
"""
from pathlib import Path
from PIL import Image, ImageDraw, ImageFilter

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "assets/icons/icon-1024.png"
RES = ROOT / "mobile/android/app/src/main/res"
BG = (11, 18, 32, 255)  # #0b1220, fundalul aplicației
DENS = {"mdpi": 1, "hdpi": 1.5, "xhdpi": 2, "xxhdpi": 3, "xxxhdpi": 4}

src = Image.open(SRC).convert("RGBA")
W = src.width
# Pătratul plin, fără colțurile rotunjite transparente (≈10% pe fiecare latură).
crop = src.crop((int(W * 0.10),) * 2 + (int(W * 0.90),) * 2)


def save(img, path):
    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path, optimize=True)


def circle(img):
    m = Image.new("L", img.size, 0)
    ImageDraw.Draw(m).ellipse((0, 0, img.width - 1, img.height - 1), fill=255)
    out = img.copy()
    out.putalpha(m)
    return out


for d, k in DENS.items():
    # Iconița clasică (Android < 8): sigla întreagă, cu colțurile ei rotunjite.
    s = round(48 * k)
    save(src.resize((s, s), Image.LANCZOS), RES / f"mipmap-{d}/ic_launcher.png")
    save(circle(crop.resize((s, s), Image.LANCZOS)), RES / f"mipmap-{d}/ic_launcher_round.png")
    # Adaptive (Android 8+): stratul de 108dp, din care se vede mijlocul de 72dp.
    # Pătratul siglei ocupă 76dp: acoperă complet zona vizibilă (72dp), iar litera B rămâne aerisită în zona sigură.
    full = round(108 * k)
    inner = round(76 * k)
    fg = Image.new("RGBA", (full, full), (0, 0, 0, 0))
    off = (full - inner) // 2
    fg.paste(crop.resize((inner, inner), Image.LANCZOS), (off, off))
    save(fg, RES / f"mipmap-{d}/ic_launcher_foreground.png")

# Splash Android 12+: iconiță fără fundal propriu, pe un cerc vizibil de 192dp din 288dp.
k = 3
canvas = Image.new("RGBA", (288 * k, 288 * k), (0, 0, 0, 0))
logo = src.resize((150 * k, 150 * k), Image.LANCZOS)
canvas.paste(logo, ((288 * k - logo.width) // 2,) * 2, logo)
save(canvas, RES / "drawable-xxhdpi/splash_icon.png")
# Splash Android < 12: sigla de 120dp centrată pe fundalul închis (vezi drawable/splash.xml).
save(src.resize((120 * k, 120 * k), Image.LANCZOS), RES / "drawable-xxhdpi/splash_logo.png")

# Iconița mică a notificării: doar litera B, albă pe transparent (Android colorează singur).
px = src.load()
mask = Image.new("L", src.size, 0)
mp = mask.load()
for y in range(src.height):
    for x in range(src.width):
        r, g, b, a = px[x, y]
        if a > 200 and max(r, g, b) > 150 and (max(r, g, b) - min(r, g, b)) > 60:
            mp[x, y] = 255
mask = mask.filter(ImageFilter.MedianFilter(5))
# Păstrează doar cea mai mare zonă (litera B), fără colțarele ramei și punctele decorative.
small = mask.resize((256, 256), Image.NEAREST)
sp = small.load()
seen, best = set(), []
for y0 in range(256):
    for x0 in range(256):
        if sp[x0, y0] and (x0, y0) not in seen:
            comp, stack = [], [(x0, y0)]
            seen.add((x0, y0))
            while stack:
                x, y = stack.pop()
                comp.append((x, y))
                for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
                    if 0 <= nx < 256 and 0 <= ny < 256 and sp[nx, ny] and (nx, ny) not in seen:
                        seen.add((nx, ny))
                        stack.append((nx, ny))
            if len(comp) > len(best):
                best = comp
keep = Image.new("L", (256, 256), 0)
kp = keep.load()
for c in best:
    kp[c] = 255
keep = keep.resize(src.size, Image.NEAREST).filter(ImageFilter.MaxFilter(9))
from PIL import ImageChops
mask = ImageChops.multiply(mask, keep)
xs = [c[0] for c in best]
ys = [c[1] for c in best]
f = src.width / 256
bbox = (int(min(xs) * f) - 4, int(min(ys) * f) - 4, int((max(xs) + 1) * f) + 4, int((max(ys) + 1) * f) + 4)
glyph = mask.crop(bbox)
side = max(glyph.size)
sq = Image.new("L", (side, side), 0)
sq.paste(glyph, ((side - glyph.width) // 2, (side - glyph.height) // 2))
for d, k in DENS.items():
    s = round(24 * k)
    pad = round(2 * k)
    a = sq.resize((s - 2 * pad, s - 2 * pad), Image.LANCZOS)
    out = Image.new("RGBA", (s, s), (255, 255, 255, 0))
    white = Image.new("RGBA", a.size, (255, 255, 255, 255))
    white.putalpha(a)
    out.paste(white, (pad, pad), white)
    save(out, RES / f"drawable-{d}/ic_stat_notify.png")
print("ok", bbox)

# Iconiță monocromă (Android 13+, „iconițe tematice”): litera B pe 108dp, ~44dp în centru.
for d, k in DENS.items():
    full = round(108 * k)
    g = round(44 * k)
    a = sq.resize((g, g), Image.LANCZOS)
    out = Image.new("RGBA", (full, full), (255, 255, 255, 0))
    white = Image.new("RGBA", a.size, (255, 255, 255, 255))
    white.putalpha(a)
    out.paste(white, ((full - g) // 2,) * 2, white)
    save(out, RES / f"mipmap-{d}/ic_launcher_monochrome.png")
