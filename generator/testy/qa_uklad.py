#!/usr/bin/env python3
"""QA: uklad pierwszego ekranu (stan zamkniety) na ekranach z tabel briefu (sekcje 6 i 15 pkt 2) i nakladanie elementow.

    python testy/qa_uklad.py --port 8790 --warianty salon_przyklad_15-logo,salon_przyklad_14-logo [--blokuj-font] [--zrzuty KAT]

Mierzy w prawdziwej przegladarce (Chromium, DPR 1): czy H1, przycisk, pasek, slowo i wieczko mieszcza sie w oknie bez przewijania,
ile linii ma H1, czy H1 / przycisk / pasek nachodza na kola lub wieczko, czy slowo miesci sie w szerokosci, gdzie konczy sie wzgledem wieczka.
--blokuj-font: blokuje plik kroju (sprawdza zapasowe fonty).
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

from playwright.sync_api import sync_playwright

KAT = Path(__file__).resolve().parent.parent
EKRANY = ["390x844", "390x720", "360x640", "430x932", "412x892", "375x812", "360x780", "412x787", "390x753", "414x736", "375x600"]

POMIAR = """
() => {
  const r2 = e => { const r = e.getBoundingClientRect(); return {x: r.left, y: r.top, w: r.width, h: r.height, r: r.right, b: r.bottom}; };
  const tekst = e => { const g = document.createRange(); g.selectNodeContents(e); const rs = [...g.getClientRects()].filter(r => r.width > 1);
    const tops = [...new Set(rs.map(r => Math.round(r.top / 4)))];
    return {linii: tops.length, x: Math.min(...rs.map(r => r.left)), y: Math.min(...rs.map(r => r.top)), r: Math.max(...rs.map(r => r.right)), b: Math.max(...rs.map(r => r.bottom))}; };
  const widoczny = e => { const c = getComputedStyle(e); return c.display !== 'none' && c.visibility !== 'hidden' && +c.opacity > 0.05; };
  const lid = document.querySelector('.panel-przod img.warstwa'); const L = r2(lid);
  const kola = [...document.querySelectorAll('.kolo')].filter(widoczny).map(k => { const r = r2(k); return {m: k.dataset.miejsce, cx: r.x + r.w / 2, cy: r.y + r.h / 2, r: r.w / 2}; });
  const h1 = document.querySelector('h1'), pr = document.querySelector('.przewin'), bar = document.querySelector('.pasek'),
        sl = document.querySelector('.slowo'), sk = document.querySelector('.slowo--kontur');
  const cs = getComputedStyle(h1);
  return {
    vw: innerWidth, vh: innerHeight, sw: document.documentElement.scrollWidth,
    animator: document.documentElement.getAttribute('data-animator'),
    font_h1: cs.fontFamily, fs_h1: cs.fontSize, lh_h1: cs.lineHeight,
    fonts: [...document.fonts].map(f => f.family + ':' + f.status),
    h1: {...tekst(h1), box: r2(h1)}, przewin: r2(pr), pasek: r2(bar), lid: L,
    lid_c: {cx: L.x + L.w / 2, cy: L.y + L.h / 2, r: L.w / 2},
    slowo: sl ? {...tekst(sl), fs: parseFloat(getComputedStyle(sl).fontSize), fam: getComputedStyle(sl).fontFamily, box: r2(sl)} : null,
    kola, tekst_slowa: sl ? sl.textContent : null,
    cta_pasek: r2(document.querySelector('.pasek__cta')), profil: r2(document.querySelector('.pasek__profil'))
  };
}
"""


def kolo_prostokat(c, r):
    """Czy okrag (cx, cy, r) nachodzi na prostokat r (x, y, r, b)?"""
    nx = min(max(c["cx"], r["x"]), r["r"])
    ny = min(max(c["cy"], r["y"]), r["b"])
    return math.hypot(c["cx"] - nx, c["cy"] - ny) < c["r"]


def analiza(m):
    w, h = m["vw"], m["vh"]
    pro = lambda e: {"x": e["x"], "y": e["y"], "r": e["r"] if "r" in e else e["x"] + e["w"], "b": e["b"] if "b" in e else e["y"] + e["h"]}
    h1 = {"x": m["h1"]["x"], "y": m["h1"]["y"], "r": m["h1"]["r"], "b": m["h1"]["b"]}
    pr = pro(m["przewin"])
    bledy = []
    for nazwa, e in (("h1", h1), ("przewin", pr)):
        if e["x"] < -0.5 or e["r"] > w + 0.5 or e["y"] < 0 or e["b"] > h + 0.5:
            bledy.append(f"{nazwa} poza oknem ({e['x']:.0f},{e['y']:.0f})-({e['r']:.0f},{e['b']:.0f}) okno {w}x{h}")
    if m["sw"] > w:
        bledy.append(f"poziomy scroll: scrollWidth {m['sw']} > {w}")
    nach = []
    elementy = {"h1": h1, "przewin": pr, "pasek-profil": pro(m["profil"]), "pasek-cta": pro(m["cta_pasek"])}
    for nazwa, e in elementy.items():
        if kolo_prostokat(m["lid_c"], e):
            nach.append(f"{nazwa} nachodzi na wieczko")
        for k in m["kola"]:
            if kolo_prostokat(k, e):
                nach.append(f"{nazwa} nachodzi na kolo {k['m']}")
    s = m["slowo"]
    if s:
        if s["x"] < -0.5 or s["r"] > w + 0.5:
            bledy.append(f"slowo poza szerokoscia: {s['x']:.0f}..{s['r']:.0f} / {w}")
        if s["y"] < m["pasek"]["b"] - 4:
            bledy.append(f"slowo nachodzi na pasek: gora {s['y']:.0f} < dol paska {m['pasek']['b']:.0f}")
    odst_slowo_wieczko = None
    if s:
        top_lid = m["lid_c"]["cy"] - m["lid_c"]["r"]
        odst_slowo_wieczko = round(top_lid - s["b"], 1)       # > 0: slowo konczy sie nad wieczkiem; < 0: zachodzi pod wieczko
    odst_h1_wieczko = round(math.hypot(0, 0), 1)
    # najmniejszy odstep H1 i przycisku do wieczka / kol
    def odstep(e):
        wart = []
        for c in [m["lid_c"]] + m["kola"]:
            nx = min(max(c["cx"], e["x"]), e["r"]); ny = min(max(c["cy"], e["y"]), e["b"])
            wart.append(math.hypot(c["cx"] - nx, c["cy"] - ny) - c["r"])
        return round(min(wart), 1)
    return {"ekran": f"{w}x{h}", "linii_h1": m["h1"]["linii"], "fs_h1": m["fs_h1"], "h1_y": round(h1["y"]), "h1_b": round(h1["b"]),
            "przewin_y": round(pr["y"]), "przewin_b": round(pr["b"]), "lid_dol": round(m["lid_c"]["cy"] + m["lid_c"]["r"]),
            "odstep_h1_od_kol_px": odstep(h1), "odstep_przycisk_od_kol_px": odstep(pr),
            "slowo_fs": round(s["fs"], 1) if s else None, "slowo_szer": round(s["r"] - s["x"]) if s else None,
            "slowo_dol_nad_wieczkiem_px": odst_slowo_wieczko, "liczba_kol": len(m["kola"]),
            "bledy": bledy, "nachodzenie": nach, "fonty": m["fonts"], "font_h1": m["font_h1"]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8790)
    ap.add_argument("--warianty", default="salon_przyklad_15-logo,salon_przyklad_26-logo,salon_przyklad_14-logo,salon_przyklad_12-logo")
    ap.add_argument("--ekrany", default=",".join(EKRANY))
    ap.add_argument("--blokuj-font", action="store_true")
    ap.add_argument("--zrzuty", default="")
    ap.add_argument("--wyj", default="")
    a = ap.parse_args()
    wynik = {}
    with sync_playwright() as p:
        przegladarka = p.chromium.launch()
        for wariant in a.warianty.split(","):
            wynik[wariant] = []
            for ekran in a.ekrany.split(","):
                w, h = map(int, ekran.split("x"))
                ctx = przegladarka.new_context(viewport={"width": w, "height": h}, device_scale_factor=1, is_mobile=True, has_touch=True)
                if a.blokuj_font:
                    ctx.route("**/*.woff2", lambda r: r.abort())
                s = ctx.new_page()
                kons = []
                s.on("console", lambda m: kons.append(f"{m.type}: {m.text}") if m.type in ("error", "warning") else None)
                s.goto(f"http://127.0.0.1:{a.port}/{wariant}/index.html", wait_until="networkidle")
                s.evaluate("document.fonts.ready")
                s.evaluate("dispatchEvent(new Event('wheel'))")
                s.add_style_tag(content=".przewin svg{animation:none!important}")
                s.wait_for_timeout(500)
                m = s.evaluate(POMIAR)
                r = analiza(m)
                r["konsola"] = kons
                wynik[wariant].append(r)
                if a.zrzuty:
                    Path(a.zrzuty).mkdir(parents=True, exist_ok=True)
                    s.screenshot(path=str(Path(a.zrzuty) / f"{wariant}__{ekran}.png"))
                ctx.close()
        przegladarka.close()
    for wariant, lista in wynik.items():
        print("==", wariant)
        for r in lista:
            print(f"  {r['ekran']:8} H1 {r['linii_h1']} lin {r['fs_h1']:>6} y{r['h1_y']}-{r['h1_b']} przycisk y{r['przewin_y']}-{r['przewin_b']} "
                  f"odstep H1-kola {r['odstep_h1_od_kol_px']:>6} przycisk-kola {r['odstep_przycisk_od_kol_px']:>6} slowo fs {r['slowo_fs']} szer {r['slowo_szer']} "
                  f"slowo->wieczko {r['slowo_dol_nad_wieczkiem_px']} kol {r['liczba_kol']}  {'; '.join(r['bledy'] + r['nachodzenie'])}")
    if a.wyj:
        Path(a.wyj).write_text(json.dumps(wynik, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
