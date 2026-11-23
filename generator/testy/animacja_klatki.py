"""Klatki scrubu: 390x844 (12 punktow), 360x640 i 1440x900 (6 punktow) dla wybranych wariantow + montaze do testy/animacja/.

    python testy/animacja_klatki.py                      # 3 glowne wariantow (salon_przyklad_15, salon_przyklad_26, salon_przyklad_14)
    python testy/animacja_klatki.py --wszystkie          # wszystkie 6
"""
import argparse
import sys

from PIL import Image, ImageDraw
from playwright.sync_api import sync_playwright

from animacja_lib import *

ap = argparse.ArgumentParser()
ap.add_argument("--wszystkie", action="store_true")
ap.add_argument("--ekrany", default="390x844,360x640,1440x900")
a = ap.parse_args()

PUNKTY = {
    "390x844": [0, 4, 10, 18, 26, 30, 40, 55, 65, 75, 85, 100],
    "360x640": [0, 10, 18, 30, 55, 75, 100],
    "1440x900": [0, 10, 18, 30, 55, 75, 100],
}
DPR = {"390x844": 2, "360x640": 2, "1440x900": 1}
KL = WYJ / "klatki"
KL.mkdir(parents=True, exist_ok=True)


def montaz(pliki, etykiety, wyj, kolumny, skala):
    ims = [Image.open(f).convert("RGB") for f in pliki]
    ims = [im.resize((int(im.width * skala), int(im.height * skala)), Image.LANCZOS) for im in ims]
    w, h = ims[0].size
    wiersze = (len(ims) + kolumny - 1) // kolumny
    s = Image.new("RGB", (kolumny * (w + 6), wiersze * (h + 6 + 16)), (60, 60, 60))
    dr = ImageDraw.Draw(s)
    for i, (im, e) in enumerate(zip(ims, etykiety)):
        x, y = (i % kolumny) * (w + 6), (i // kolumny) * (h + 6 + 16)
        s.paste(im, (x, y + 16))
        dr.text((x + 4, y + 2), e, fill=(255, 255, 255))
    s.save(wyj, quality=88)


raport = []
with sync_playwright() as p:
    for wariant in (WARIANTY if a.wszystkie else GLOWNE):
        for ekran in a.ekrany.split(","):
            w, h = (int(x) for x in ekran.split("x"))
            przegladarka, ctx = nowy_kontekst(p, w, h, dpr=DPR[ekran])
            strona, wpisy = otworz(ctx, wariant)
            strona.mouse.click(4, h - 4)                   # konczy podpowiedz (uchylenie), zeby klatka p=0 byla spoczynkowa
            strona.wait_for_timeout(300)
            pliki, et = [], []
            for pr in PUNKTY[ekran]:
                przewin_do(strona, pr / 100, czekaj=420 if w >= 1100 else 260)
                f = KL / f"{wariant}__{ekran}__{pr:03d}.jpg"
                strona.screenshot(path=str(f), type="jpeg", quality=90)
                pliki.append(f)
                et.append(f"{wariant} {ekran} p={pr}%")
            raport.append({"wariant": wariant, "ekran": ekran, "konsola": wpisy,
                           "poziomy_scroll": strona.evaluate("document.documentElement.scrollWidth > document.documentElement.clientWidth")})
            montaz(pliki, et, WYJ / f"montaz_{wariant}_{ekran}.jpg", 6 if w < 700 else 4, 0.5 if DPR[ekran] == 2 else 0.5)
            przegladarka.close()
for r in raport:
    print(r)
