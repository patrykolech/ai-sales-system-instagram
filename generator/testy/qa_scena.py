#!/usr/bin/env python3
"""QA: sekwencja sceny co 2% przewiniecia. Skoki obrazu (roznica miedzy kolejnymi klatkami), duchy fokusu, kluczowe klatki.

    python testy/qa_scena.py --port 8790 --warianty salon_przyklad_15-logo,salon_przyklad_26-logo --ekran 390x844 --dpr 1 --zrzuty KAT

Skok: roznica (srednia bezwzgledna, w skali szarosci, obraz zmniejszony do 1/4) miedzy sasiednimi krokami wieksza niz 3x mediana
sasiednich i wieksza niz 4 (z 255). To heurystyka, nie dowod: zawsze obejrzyj klatki wokol zgloszonego p.
Duch fokusu: link lub przycisk z visibility: visible i krytyem < 0,15 (da sie na niego wejsc Tab-em, a nie widac go).
"""
from __future__ import annotations

import argparse
import io
import json
import statistics
from pathlib import Path

import numpy as np
from PIL import Image
from playwright.sync_api import sync_playwright

KLUCZ = [0, 0.04, 0.08, 0.12, 0.2, 0.3, 0.4, 0.55, 0.7, 0.85, 1.0]
STAN = """
() => [...document.querySelectorAll('a, button')].map(e => { const c = getComputedStyle(e); const r = e.getBoundingClientRect();
  return {t: (e.className || e.tagName).toString().slice(0, 28), vis: c.visibility, op: +(+c.opacity).toFixed(2), disp: c.display,
          wokno: r.bottom > 0 && r.top < innerHeight && r.width > 0}; })
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8790)
    ap.add_argument("--warianty", default="salon_przyklad_15-logo,salon_przyklad_26-logo")
    ap.add_argument("--ekran", default="390x844")
    ap.add_argument("--dpr", type=float, default=1)
    ap.add_argument("--krok", type=float, default=0.02)
    ap.add_argument("--zrzuty", default="")
    ap.add_argument("--wyj", default="")
    a = ap.parse_args()
    w, h = map(int, a.ekran.split("x"))
    mob = w < 700
    wynik = {}
    with sync_playwright() as p:
        b = p.chromium.launch()
        for wariant in a.warianty.split(","):
            ctx = b.new_context(viewport={"width": w, "height": h}, device_scale_factor=a.dpr, is_mobile=mob, has_touch=mob)
            s = ctx.new_page()
            kons = []
            s.on("console", lambda m: kons.append(f"{m.type}: {m.text}") if m.type in ("error", "warning") else None)
            s.on("pageerror", lambda e: kons.append(f"pageerror: {e}"))
            s.goto(f"http://127.0.0.1:{a.port}/{wariant}/index.html", wait_until="networkidle")
            s.evaluate("document.fonts.ready")
            if w < 1100:                                   # zdarzenie wheel wylacza podpowiedz, ale z Lenis (desktop) blokuje window.scrollTo
                s.evaluate("dispatchEvent(new Event('wheel'))")
                s.wait_for_timeout(500)
            else:
                s.wait_for_timeout(4200)                   # poczekaj, az podpowiedz (uchylenie 1,6 s + 1,45 s) sama sie skonczy
            s.add_style_tag(content=".przewin svg{animation:none!important}")
            zakres = s.evaluate("(() => { const t = ScrollTrigger.getAll()[0]; return [t.start, t.end]; })()")
            tryb = s.evaluate("document.documentElement.getAttribute('data-animator') + ' lenis=' + document.documentElement.classList.contains('lenis')")
            klatki, duchy, prev, roznice, ps = [], [], None, [], []
            n = int(round(1 / a.krok))
            for i in range(n + 1):
                pr = i / n
                s.evaluate("(y) => window.scrollTo(0, y)", zakres[0] + pr * (zakres[1] - zakres[0]))
                s.wait_for_timeout(300)
                png = s.screenshot()
                im = Image.open(io.BytesIO(png)).convert("L")
                small = np.asarray(im.resize((im.width // 4, im.height // 4), Image.BILINEAR), dtype=np.float64)
                if prev is not None:
                    roznice.append(float(np.abs(small - prev).mean()))
                    ps.append(pr)
                prev = small
                for e in s.evaluate(STAN):
                    if e["vis"] == "visible" and e["disp"] != "none" and e["op"] < 0.15 and e["wokno"]:
                        duchy.append((round(pr, 2), e["t"], e["op"]))
                if a.zrzuty and any(abs(pr - k) < a.krok / 2 + 1e-9 for k in KLUCZ):
                    Path(a.zrzuty).mkdir(parents=True, exist_ok=True)
                    Path(a.zrzuty, f"scena_{wariant}_{a.ekran}_p{int(round(pr * 100)):03d}.png").write_bytes(png)
            med = statistics.median(roznice)
            skoki = []
            for i, d in enumerate(roznice):
                sas = [roznice[j] for j in (i - 2, i - 1, i + 1, i + 2) if 0 <= j < len(roznice)]
                if d > 4 and d > 3 * statistics.median(sas):
                    skoki.append((round(ps[i], 2), round(d, 2)))
            wynik[wariant] = {"ekran": a.ekran, "tryb": tryb, "zakres_px": zakres, "mediana_roznicy": round(med, 3), "max_roznicy": round(max(roznice), 2),
                              "roznice": [round(x, 2) for x in roznice], "skoki": skoki, "duchy_fokusu": sorted(set(duchy))[:20], "konsola": kons}
            print(wariant, a.ekran, tryb, "mediana", round(med, 3), "max", round(max(roznice), 2), "skoki", skoki, "duchy", sorted(set(duchy))[:8], "konsola", kons[:2], flush=True)
            ctx.close()
        b.close()
    if a.wyj:
        Path(a.wyj).write_text(json.dumps(wynik, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
