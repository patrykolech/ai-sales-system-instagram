#!/usr/bin/env python3
"""QA: duze slowo przez zdjecia (.slowo i .slowo--kontur) w stanie zamknietym.

    python testy/qa_slowo.py --port 8790 --warianty ... --ekrany 390x844,390x720,360x640,1440x900

1. Tusz slowa (renderowany osobno, bialy na czarnym) vs wieczko: ile pikseli liter wpada pod okrag wieczka (regula: litery nigdy nie chowaja sie
   za wieczkiem, bo znika ogonek w "e") i ile nachodzi na linki paska u gory.
2. Kontrast konturu na zdjeciach w kolach: piksele konturu (roznica ekranu z konturem i bez) wewnatrz kol, kontrast koloru konturu
   do jasnosci zdjecia pod spodem (WCAG, 3:1 dla grafiki).
3. Zapasowe fonty: --blokuj-font blokuje woff2, wtedy mierzy szerokosc slowa wzgledem okna.
"""
from __future__ import annotations

import argparse
import io
import json
from pathlib import Path

import numpy as np
from PIL import Image
from playwright.sync_api import sync_playwright

GEOM = """
() => {
  const r = e => { const b = e.getBoundingClientRect(); return {x: b.left, y: b.top, w: b.width, h: b.height}; };
  const L = r(document.querySelector('.panel-przod img.warstwa'));
  const kola = [...document.querySelectorAll('.kolo')].filter(k => { const c = getComputedStyle(k); return c.display !== 'none' && +c.opacity > 0.05; }).map(k => { const b = r(k); return {m: k.dataset.miejsce, cx: b.x + b.w / 2, cy: b.y + b.h / 2, r: b.w / 2}; });
  const sl = document.querySelector('.slowo');
  return {lid: {cx: L.x + L.w / 2, cy: L.y + L.h / 2, r: L.w / 2}, kola,
    linki: ['.pasek__profil', '.pasek__cta'].map(s => r(document.querySelector(s))),
    slowo: sl.textContent, fs: parseFloat(getComputedStyle(sl).fontSize), vw: innerWidth, vh: innerHeight,
    kolor: getComputedStyle(sl).color, fam: getComputedStyle(sl).fontFamily, stroke: getComputedStyle(document.querySelector('.slowo--kontur')).webkitTextStrokeWidth};
}
"""


def lum(rgb):
    c = rgb / 255.0
    c = np.where(c <= 0.03928, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)
    return 0.2126 * c[..., 0] + 0.7152 * c[..., 1] + 0.0722 * c[..., 2]


def png(s, dpr):
    return np.asarray(Image.open(io.BytesIO(s.screenshot())).convert("RGB")).astype(np.float64)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8790)
    ap.add_argument("--warianty", default="salon_przyklad_15-logo,salon_przyklad_26-logo,salon_przyklad_14-logo,salon_przyklad_12-logo")
    ap.add_argument("--ekrany", default="390x844,390x720,360x640,1440x900")
    ap.add_argument("--dpr", type=float, default=2)
    ap.add_argument("--blokuj-font", action="store_true")
    ap.add_argument("--zrzuty", default="")
    ap.add_argument("--wyj", default="")
    a = ap.parse_args()
    wynik = {}
    with sync_playwright() as p:
        b = p.chromium.launch()
        for wariant in a.warianty.split(","):
            wynik[wariant] = []
            for ekran in a.ekrany.split(","):
                w, h = map(int, ekran.split("x"))
                mobilny = w < 700
                ctx = b.new_context(viewport={"width": w, "height": h}, device_scale_factor=a.dpr, is_mobile=mobilny, has_touch=mobilny)
                if a.blokuj_font:
                    ctx.route("**/*.woff2", lambda r: r.abort())
                s = ctx.new_page()
                s.goto(f"http://127.0.0.1:{a.port}/{wariant}/index.html", wait_until="networkidle")
                s.evaluate("document.fonts.ready")
                s.evaluate("dispatchEvent(new Event('wheel'))")
                s.add_style_tag(content=".przewin svg{animation:none!important}")
                s.wait_for_timeout(500)
                g = s.evaluate(GEOM)
                dpr = a.dpr
                if a.zrzuty:
                    Path(a.zrzuty).mkdir(parents=True, exist_ok=True)
                    s.screenshot(path=str(Path(a.zrzuty) / f"slowo_{wariant}_{ekran}.png"))
                # 1. tusz slowa
                st = s.add_style_tag(content="""body *{visibility:hidden!important} html,body,.hero,.scena{background:#000!important}
                    .slowo:not(.slowo--kontur){visibility:visible!important;color:#fff!important;text-shadow:none!important}""")
                ink = png(s, dpr).mean(axis=2) > 90
                st.evaluate("e => e.remove()")
                ys, xs = np.nonzero(ink)
                yy, xx = np.mgrid[0:ink.shape[0], 0:ink.shape[1]]
                L = g["lid"]
                w_lid = ((xx / dpr - L["cx"]) ** 2 + (yy / dpr - L["cy"]) ** 2) < (L["r"] * 0.985) ** 2
                pod_wieczkiem = int((ink & w_lid).sum())
                pasek = np.zeros_like(ink)
                for lk in g["linki"]:
                    pasek[int(lk["y"] * dpr):int((lk["y"] + lk["h"]) * dpr), int(lk["x"] * dpr):int((lk["x"] + lk["w"]) * dpr)] = True
                na_pasku = int((ink & pasek).sum())
                # najnizszy piksel tuszu i jego odleglosc do okregu wieczka
                ink_dol = float(ys.max() / dpr) if len(ys) else None
                ink_gora = float(ys.min() / dpr) if len(ys) else None
                wiersz = {"ekran": ekran, "slowo": g["slowo"], "fs": round(g["fs"], 1), "ink_x": [round(xs.min() / dpr), round(xs.max() / dpr)] if len(xs) else None,
                          "ink_y": [round(ink_gora), round(ink_dol)] if len(ys) else None, "ink_px_pod_wieczkiem": pod_wieczkiem,
                          "ink_px_ogolem": int(ink.sum()), "ink_px_na_linkach_paska": na_pasku, "font": g["fam"][:40], "obrys": g["stroke"],
                          "okno": f"{w}x{h}", "ink_poza_oknem": bool(len(xs) and (xs.min() < 0 or xs.max() / dpr > w))}
                # 2. kontrast konturu na zdjeciach
                A = png(s, dpr)
                st = s.add_style_tag(content=".slowo--kontur{visibility:hidden!important}")
                B = png(s, dpr)
                st.evaluate("e => e.remove()")
                mask = np.abs(A - B).sum(axis=2) > 36
                in_kola = np.zeros_like(mask)
                for k in g["kola"]:
                    in_kola |= ((xx / dpr - k["cx"]) ** 2 + (yy / dpr - k["cy"]) ** 2) < (k["r"] * 0.96) ** 2
                m = mask & in_kola
                n = int(m.sum())
                if n:
                    Lb = lum(B[m])
                    rgb = [int(x) for x in __import__("re").findall(r"\d+", g["kolor"])[:3]]
                    Ls = float(lum(np.array(rgb, dtype=np.float64)))
                    cr = (Ls + 0.05) / (Lb + 0.05)
                    wiersz["kontur_px_na_zdjeciach"] = n
                    wiersz["kontur_kontrast_mediana"] = round(float(np.median(cr)), 2)
                    wiersz["kontur_kontrast_p10"] = round(float(np.percentile(cr, 10)), 2)
                    wiersz["kontur_udzial_ponizej_3"] = round(float((cr < 3).mean()), 3)
                    wiersz["kontur_udzial_ponizej_2"] = round(float((cr < 2).mean()), 3)
                else:
                    wiersz["kontur_px_na_zdjeciach"] = 0
                wynik[wariant].append(wiersz)
                ctx.close()
        b.close()
    for v, rows in wynik.items():
        print("==", v)
        for r in rows:
            print(" ", r["ekran"], r["slowo"], "fs", r["fs"], "tusz y", r["ink_y"], "x", r["ink_x"], "| pod wieczkiem px", r["ink_px_pod_wieczkiem"], "z", r["ink_px_ogolem"],
                  "| na linkach paska px", r["ink_px_na_linkach_paska"], "| kontur px", r.get("kontur_px_na_zdjeciach"), "kontrast med", r.get("kontur_kontrast_mediana"),
                  "p10", r.get("kontur_kontrast_p10"), "<3:", r.get("kontur_udzial_ponizej_3"), "<2:", r.get("kontur_udzial_ponizej_2"), "poza oknem", r["ink_poza_oknem"])
    if a.wyj:
        Path(a.wyj).write_text(json.dumps(wynik, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
