#!/usr/bin/env python3
"""Zrzuty prototypu hero w headless Chromium (Playwright). Serwer lokalny na porcie 8791 uruchom osobno:

    python -m http.server 8791 --directory prototyp

    python testy/zrzuty_hero.py                      # wszystkie warianty, 4 ekrany, stan zamkniety + bez JS
    python testy/zrzuty_hero.py --warianty salon_przyklad_26 --ekrany 390x844 --stany zamknieta,otwarta,koncowa,bezjs
Zrzuty trafiaja do testy/budowa/. Do kontroli programowej: poziomy scroll, bledy konsoli, brakujace pliki.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from playwright.sync_api import sync_playwright

KAT = Path(__file__).resolve().parent.parent
WYJ = KAT / "testy" / "budowa"
WARIANTY = ["salon_przyklad_15", "salon_przyklad_15-logo", "salon_przyklad_12", "salon_przyklad_12-logo",
            "salon_przyklad_14", "salon_przyklad_26"]
EKRANY = ["390x844", "390x720", "360x640", "1440x900"]
URL = "http://127.0.0.1:8791/"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--warianty", default=",".join(WARIANTY))
    ap.add_argument("--ekrany", default=",".join(EKRANY))
    ap.add_argument("--stany", default="zamknieta,bezjs")
    ap.add_argument("--dpr", type=float, default=1.0)
    ap.add_argument("--pelna", action="store_true", help="bezjs: caly dokument")
    a = ap.parse_args()
    WYJ.mkdir(parents=True, exist_ok=True)
    raport = []
    with sync_playwright() as p:
        przegladarka = p.chromium.launch()
        for wariant in a.warianty.split(","):
            for ekran in a.ekrany.split(","):
                w, h = (int(x) for x in ekran.split("x"))
                for stan in a.stany.split(","):
                    bezjs = stan == "bezjs"
                    ctx = przegladarka.new_context(viewport={"width": w, "height": h}, device_scale_factor=a.dpr,
                                                   java_script_enabled=not bezjs, is_mobile=w < 700, has_touch=w < 700)
                    strona = ctx.new_page()
                    bledy, zle = [], []
                    strona.on("console", lambda m, b=bledy: b.append(m.text) if m.type in ("error", "warning") else None)
                    strona.on("pageerror", lambda e, b=bledy: b.append(str(e)))
                    strona.on("response", lambda r, z=zle: z.append(f"{r.status} {r.url}") if r.status >= 400 else None)
                    adres = f"{URL}{wariant}/index.html" + ("" if bezjs or stan == "zamknieta" else f"?faza={stan}")
                    if stan == "zamknieta":
                        adres += "?faza=zamknieta"
                    strona.goto(adres, wait_until="networkidle")
                    strona.evaluate("document.fonts.ready")
                    strona.wait_for_timeout(1300 if stan != "zamknieta" else 400)
                    nazwa = f"{wariant}__{ekran}__{stan}.png"
                    strona.screenshot(path=str(WYJ / nazwa), full_page=bezjs and a.pelna)
                    if not bezjs:
                        wyn = strona.evaluate("""() => ({sw: document.documentElement.scrollWidth, cw: document.documentElement.clientWidth,
                            faza: document.querySelector('[data-anim=scena]').getAttribute('data-faza')})""")
                    else:
                        wyn = strona.evaluate("() => ({sw: document.documentElement.scrollWidth, cw: document.documentElement.clientWidth})")
                    raport.append({"plik": nazwa, "poziomy_scroll": wyn["sw"] > wyn["cw"], **wyn, "konsola": bledy[:4], "http": zle[:4]})
                    ctx.close()
        przegladarka.close()
    (WYJ / "raport.json").write_text(json.dumps(raport, ensure_ascii=False, indent=1), encoding="utf-8")
    zle = [r for r in raport if r["poziomy_scroll"] or r["konsola"] or r["http"]]
    print(f"zrzutow: {len(raport)}; z problemem: {len(zle)}")
    for r in zle:
        print(r)


if __name__ == "__main__":
    main()
