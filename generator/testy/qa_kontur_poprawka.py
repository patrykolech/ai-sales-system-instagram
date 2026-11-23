#!/usr/bin/env python3
"""QA runda 2: kontur slowa na jasnej skorze (P2-4). Mierzy obecny CSS i kandydatow wstrzyknietych w strone w przegladarce
(zrodla NIE sa zmieniane).

    python testy/qa_kontur_poprawka.py --port 8796 --wyj docs/qa/r2_kontur_poprawka.json --zrzuty docs/qa/r2_kontur

Metoda (ta sama co w qa_slowo.py, plus dwie wiarygodniejsze):
 - "stary": kontrast koloru konturu do jasnosci zdjecia pod pikselami konturu (jak w rundzie 1; nie widzi ciemnej krawedzi).
 - "sasiedztwo": dla pikseli rdzenia konturu (kremowa linia 1,2 px) kontrast do pierscienia pikseli tuz obok (1-3 px urzadzenia od
   rdzenia), czyli po zlozeniu z ciemna krawedzia. Tak widzi to oko: linia na tle sasiedztwa. Podzial: wszystkie piksele w kolach
   oraz tylko jasna skora (luminancja zdjecia >= 0,45).
 - "ciemna_krawedz": udzial pikseli rdzenia, ktore maja po obu stronach ciemny pierscien (luminancja <= 0,18)
"""
from __future__ import annotations

import argparse
import io
import json
import re
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage as ndi
from playwright.sync_api import sync_playwright

KAND = {
    "obecny": "",
    "A_0.70_4.2px": ".slowo--kontur::before{-webkit-text-stroke:4.2px rgb(var(--tlo-ciemne-rgb) / .70)!important}",
    "D_0.80_4.6px": ".slowo--kontur::before{-webkit-text-stroke:4.6px rgb(var(--tlo-ciemne-rgb) / .80)!important}",
    "E_0.85_4.4px": ".slowo--kontur::before{-webkit-text-stroke:4.4px rgb(var(--tlo-ciemne-rgb) / .85)!important}",
    "B_0.85_5px": ".slowo--kontur::before{-webkit-text-stroke:5px rgb(var(--tlo-ciemne-rgb) / .85)!important}",
    "C_0.92_6px_rdzen1.4": ".slowo--kontur{-webkit-text-stroke:1.4px var(--slowo-kolor)!important}.slowo--kontur::before{-webkit-text-stroke:6px rgb(var(--tlo-ciemne-rgb) / .92)!important}",
}

GEOM = """
() => {
  const r = e => { const b = e.getBoundingClientRect(); return {x: b.left, y: b.top, w: b.width, h: b.height}; };
  const kola = [...document.querySelectorAll('.kolo')].filter(k => { const c = getComputedStyle(k); return c.display !== 'none' && +c.opacity > 0.05; }).map(k => { const b = r(k); return {cx: b.x + b.w / 2, cy: b.y + b.h / 2, r: b.w / 2}; });
  return {kola, kolor: getComputedStyle(document.querySelector('.slowo')).color, stroke: getComputedStyle(document.querySelector('.slowo--kontur')).webkitTextStrokeWidth,
          ciemny: getComputedStyle(document.documentElement).getPropertyValue('--tlo-ciemne').trim()};
}
"""


def lum(rgb):
    c = np.asarray(rgb, dtype=np.float64) / 255.0
    c = np.where(c <= 0.03928, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)
    return 0.2126 * c[..., 0] + 0.7152 * c[..., 1] + 0.0722 * c[..., 2]


def png(s):
    return np.asarray(Image.open(io.BytesIO(s.screenshot())).convert("RGB")).astype(np.float64)


def kr(a, b):
    hi, lo = np.maximum(a, b), np.minimum(a, b)
    return (hi + 0.05) / (lo + 0.05)


def stat(x):
    if x.size == 0:
        return None
    return {"n": int(x.size), "mediana": round(float(np.median(x)), 2), "p10": round(float(np.percentile(x, 10)), 2),
            "pod3": round(float((x < 3).mean()), 3), "pod2": round(float((x < 2).mean()), 3)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8796)
    ap.add_argument("--warianty", default="salon_przyklad_15-logo,salon_przyklad_14-logo,salon_przyklad_12-logo,salon_przyklad_26-logo")
    ap.add_argument("--ekrany", default="390x844,390x720,1440x900")
    ap.add_argument("--dpr", type=float, default=2)
    ap.add_argument("--zrzuty", default="")
    ap.add_argument("--wyj", default="")
    a = ap.parse_args()
    wynik = {}
    with sync_playwright() as p:
        b = p.chromium.launch()
        for wariant in a.warianty.split(","):
            wynik[wariant] = {}
            for ekran in a.ekrany.split(","):
                w, h = map(int, ekran.split("x"))
                mob = w < 700
                ctx = b.new_context(viewport={"width": w, "height": h}, device_scale_factor=a.dpr, is_mobile=mob, has_touch=mob)
                s = ctx.new_page()
                s.goto(f"http://127.0.0.1:{a.port}/{wariant}/index.html", wait_until="networkidle")
                s.evaluate("document.fonts.ready")
                s.evaluate("dispatchEvent(new Event('wheel'))")
                s.add_style_tag(content=".przewin svg{animation:none!important}")
                s.wait_for_timeout(600)
                g = s.evaluate(GEOM)
                rgb = [int(x) for x in re.findall(r"\d+", g["kolor"])[:3]]
                Lc = float(lum(np.array(rgb)))
                dpr = a.dpr
                H = int(h * dpr)
                W = int(w * dpr)
                yy, xx = np.mgrid[0:H, 0:W]
                in_kola = np.zeros((H, W), bool)
                for k in g["kola"]:
                    in_kola |= ((xx / dpr - k["cx"]) ** 2 + (yy / dpr - k["cy"]) ** 2) < (k["r"] * 0.94) ** 2
                st = s.add_style_tag(content=".slowo--kontur{visibility:hidden!important}")
                B = png(s)
                st.evaluate("e => e.remove()")
                LB = lum(B)
                wynik[wariant][ekran] = {}
                for nazwa, css in KAND.items():
                    t = s.add_style_tag(content=css) if css else None
                    s.wait_for_timeout(120)
                    A = png(s)
                    # rdzen: tylko kremowa linia (bez ciemnej krawedzi)
                    t2 = s.add_style_tag(content=".slowo--kontur::before{display:none!important}")
                    C = png(s)
                    t2.evaluate("e => e.remove()")
                    if a.zrzuty:
                        Path(a.zrzuty).mkdir(parents=True, exist_ok=True)
                        im = Image.fromarray(A.astype(np.uint8))
                        im.save(Path(a.zrzuty) / f"{wariant}_{ekran}_{nazwa}.png")
                    core = (np.abs(C - B).sum(axis=2) > 36) & in_kola
                    halo_all = (np.abs(A - B).sum(axis=2) > 36) & in_kola
                    # stary pomiar: kolor konturu vs zdjecie pod pikselami konturu (rdzen + krawedz)
                    stary = kr(Lc, LB[halo_all])
                    # sasiedztwo: pierscien 1-3 px urzadzenia od rdzenia, ale juz zlozony z krawedzia (A)
                    d1 = ndi.binary_dilation(core, iterations=1)
                    d3 = ndi.binary_dilation(core, iterations=3)
                    ring = d3 & ~d1 & in_kola
                    LA = lum(A)
                    # piksel pierscienia -> kontrast do rdzenia (kolor)
                    sas = kr(Lc, LA[ring])
                    jasna = ring & (LB > 0.45)
                    sas_jasna = kr(Lc, LA[jasna])
                    ciemny_udzial = float((LA[ring] <= 0.18).mean()) if ring.any() else None
                    wynik[wariant][ekran][nazwa] = {"stary_pomiar": stat(stary), "sasiedztwo": stat(sas), "sasiedztwo_jasna_skora": stat(sas_jasna),
                                                    "ciemna_krawedz_udzial": None if ciemny_udzial is None else round(ciemny_udzial, 3)}
                    if t:
                        t.evaluate("e => e.remove()")
                ctx.close()
        b.close()
    for wv, ek in wynik.items():
        print("==", wv)
        for e, kk in ek.items():
            for n, m in kk.items():
                sj = m["sasiedztwo_jasna_skora"]
                print(f"  {e:9} {n:22} stary med {m['stary_pomiar'] and m['stary_pomiar']['mediana']} <3 {m['stary_pomiar'] and m['stary_pomiar']['pod3']}"
                      f" | sasiedztwo med {m['sasiedztwo'] and m['sasiedztwo']['mediana']} <3 {m['sasiedztwo'] and m['sasiedztwo']['pod3']}"
                      f" | jasna skora med {sj and sj['mediana']} <3 {sj and sj['pod3']} n {sj and sj['n']}")
    if a.wyj:
        Path(a.wyj).write_text(json.dumps(wynik, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
