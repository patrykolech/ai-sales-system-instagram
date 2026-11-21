#!/usr/bin/env python3
"""Pakiet do finish review: .impeccable/review/{desktop.png, mobile.png, detect.json} + klatki sekwencji.

    python testy/qa_pakiet_review.py --port 8790

Zrzuty pokazuja stan, ktory zobaczy uzytkownik: wszystkie obrazy i kroje zaladowane i zdekodowane, animator wlaczony (GSAP),
podpowiedz (uchylenie wieczka) skonczona, wieczko w spoczynku. Skrypt sam sprawdza, ze zrzut nie jest pusty
(czcionki "loaded", wszystkie <img> w scenie complete, widoczne wieczko, kola, H1 i przycisk).
"""
from __future__ import annotations

import argparse
import io
import json
from pathlib import Path

import numpy as np
from PIL import Image
from playwright.sync_api import sync_playwright

KAT = Path(__file__).resolve().parent.parent
OUT = KAT / ".impeccable" / "review"

KONTROLA = """() => {
  const vis = e => { if (!e) return false; const c = getComputedStyle(e), r = e.getBoundingClientRect(); return c.display !== 'none' && c.visibility !== 'hidden' && +c.opacity > 0.9 && r.width > 0 && r.bottom > 0 && r.top < innerHeight; };
  const imgs = [...document.querySelectorAll('.scena img')];
  return {fonty: [...document.fonts].map(f => f.family + ':' + f.status), img_razem: imgs.length, img_gotowe: imgs.filter(i => i.complete && i.naturalWidth > 0).length,
          animator: document.documentElement.getAttribute('data-animator'), wieczko: vis(document.querySelector('.panel-przod img')), h1: vis(document.querySelector('h1')),
          przycisk: vis(document.querySelector('.przewin')), kola_widoczne: [...document.querySelectorAll('.kolo')].filter(vis).length,
          slowo: vis(document.querySelector('.slowo')), kat_wieczka: document.querySelector('.panel').style.transform || 'brak'};
}"""


def przewin(s, p):
    s.evaluate("(p) => { const t = ScrollTrigger.getAll()[0]; scrollTo(0, t.start + p * (t.end - t.start)); }", p)
    s.wait_for_timeout(700)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8790)
    ap.add_argument("--glowny", default="salon_przyklad_15-logo")
    ap.add_argument("--dodatkowy", default="salon_przyklad_14-logo")
    a = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    raport = {}
    with sync_playwright() as p:
        b = p.chromium.launch()
        for wariant, przyrostek in ((a.glowny, ""), (a.dodatkowy, "-" + a.dodatkowy.split(".")[0])):
            for nazwa, (w, h, mob) in (("desktop", (1440, 900, False)), ("mobile", (390, 844, True))):
                ctx = b.new_context(viewport={"width": w, "height": h}, device_scale_factor=1, is_mobile=mob, has_touch=mob)
                s = ctx.new_page()
                kons = []
                s.on("console", lambda m: kons.append(f"{m.type}: {m.text}") if m.type in ("error", "warning") else None)
                s.goto(f"http://127.0.0.1:{a.port}/{wariant}/index.html", wait_until="networkidle")
                s.evaluate("document.fonts.ready")
                s.evaluate("Promise.all([...document.querySelectorAll('.scena img')].map(i => i.decode ? i.decode().catch(() => {}) : null))")
                s.add_style_tag(content=".przewin svg{animation:none!important}")
                # poczekaj, az podpowiedz (uchylenie wieczka 1,6 s + 1,45 s) sie skonczy; wieczko w spoczynku
                s.wait_for_timeout(4300)
                k = s.evaluate(KONTROLA)
                plik = OUT / f"{nazwa}{przyrostek}.png"
                png = s.screenshot()
                plik.write_bytes(png)
                im = np.asarray(Image.open(io.BytesIO(png)).convert("L")).astype(float)
                k["odchylenie_jasnosci"] = round(float(im.std()), 1)
                k["zapisano"] = str(plik.relative_to(KAT))
                k["konsola"] = kons
                raport[f"{nazwa}{przyrostek}"] = k
                if not przyrostek:
                    for etykieta, pr in (("otwarta", 0.40), ("koncowa", 1.0)):
                        przewin(s, pr)
                        (OUT / f"{nazwa}-{etykieta}.png").write_bytes(s.screenshot())
                ctx.close()
        b.close()
    # detect.json: wynik detect --json (URL) zebrany ze wszystkich stron i widokow
    det = {}
    for f in sorted((KAT / "docs" / "qa" / "detect").glob("*.json")):
        det[f.stem] = json.loads(f.read_text(encoding="utf-8-sig"))
    lacznie = sum(len(v) for v in det.values())
    (OUT / "detect.json").write_text(json.dumps({
        "narzedzie": "impeccable detect --json <URL> --viewport WxH (renderowana strona, tryb URL)", "stron": len({k.rsplit('_', 1)[0] for k in det}),
        "widokow": sorted({k.rsplit('_', 1)[1] for k in det}), "znalezisk_lacznie": lacznie, "znaleziska": [x for v in det.values() for x in v],
        "per_strona_widok": {k: len(v) for k, v in det.items()}}, ensure_ascii=False, indent=1), encoding="utf-8")
    (OUT / "kontrola_pakietu.json").write_text(json.dumps(raport, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(raport, ensure_ascii=False, indent=1))
    print("detect znalezisk:", lacznie)


if __name__ == "__main__":
    main()
