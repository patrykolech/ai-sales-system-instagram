#!/usr/bin/env python3
"""QA: waga na kablu (po kompresji serwera) i LCP/FCP/CLS w Chromium, z ograniczeniem sieci i procesora.

    python testy/qa_wagi_lcp.py --port 8794 --warianty salon_przyklad_15,salon_przyklad_26 --siec fast3g --cpu 4 --powtorzen 3
    python testy/qa_wagi_lcp.py --port 8793 --siec brak --cpu 1          # serwer bez kompresji (python -m http.server)

Waga to `encodedDataLength` z CDP (bajty faktycznie przeslane, z naglowkami), a nie rozmiar pliku na dysku.
Klasyfikacja plikow (definicje z briefu, sekcja 8 i 15):
  paczka1  = wieczko, zawias zamkniety, kola S*, awatar (obrazy stanu zamknietego)
  paczka2  = rama lusterka, podstawa, zawias otwarty, zdjecie, lusterko
  kod      = HTML + CSS + JS + kroje (bez tego strona nie ruszy, wiec to tez liczy sie do pierwszego ekranu)
"""
from __future__ import annotations

import argparse
import json
import statistics
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

KAT = Path(__file__).resolve().parent.parent
FAST3G = dict(latency=562.5, downloadThroughput=1.6 * 1024 * 1024 / 8 * 0.9, uploadThroughput=750 * 1024 / 8 * 0.9)

P1_IMG = ("wieczko", "zawias-zamkniety", "/tlo/S", "avatar")
P2_IMG = ("rama-lusterka", "podstawa", "/warstwy/zawias.webp", "zdjecie.webp", "lusterko.webp")


def klasa(url: str, typ: str) -> str:
    u = url.split("?")[0]
    if u.endswith("/") or u.endswith("index.html"):
        return "html"
    if u.endswith(".css"):
        return "css"
    if u.endswith(".js"):
        return "js"
    if u.endswith(".woff2"):
        return "krój"
    if any(k in u for k in P2_IMG):
        return "paczka2"
    if any(k in u for k in P1_IMG):
        return "paczka1"
    return "inne"


INIT = """
window.__qa = {lcp: [], cls: 0, paint: {}, longtasks: 0};
new PerformanceObserver(l => { for (const e of l.getEntries()) window.__qa.lcp.push({t: Math.round(e.startTime), size: e.size, url: e.url || '', el: e.element ? e.element.tagName + '.' + (e.element.className||'') : ''}); }).observe({type: 'largest-contentful-paint', buffered: true});
new PerformanceObserver(l => { for (const e of l.getEntries()) if (!e.hadRecentInput) window.__qa.cls += e.value; }).observe({type: 'layout-shift', buffered: true});
new PerformanceObserver(l => { for (const e of l.getEntries()) window.__qa.paint[e.name] = Math.round(e.startTime); }).observe({type: 'paint', buffered: true});
new PerformanceObserver(l => { window.__qa.longtasks += l.getEntries().length; }).observe({type: 'longtask', buffered: true});
"""


def jeden_przebieg(p, port, wariant, siec, cpu, w, h, dpr, bez_cache=True):
    przegladarka = p.chromium.launch()
    ctx = przegladarka.new_context(viewport={"width": w, "height": h}, device_scale_factor=dpr, is_mobile=w < 700, has_touch=w < 700)
    strona = ctx.new_page()
    strona.add_init_script(INIT)
    cdp = ctx.new_cdp_session(strona)
    cdp.send("Network.enable")
    cdp.send("Network.setCacheDisabled", {"cacheDisabled": True})
    if siec == "fast3g":
        cdp.send("Network.emulateNetworkConditions", {"offline": False, **FAST3G})
    if cpu > 1:
        cdp.send("Emulation.setCPUThrottlingRate", {"rate": cpu})
    zad = {}
    t0 = {}

    def start(e):
        zad[e["requestId"]] = {"url": e["request"]["url"], "typ": e.get("type"), "start": e["timestamp"]}
        t0.setdefault("t", e["timestamp"])

    def odp(e):
        z = zad.get(e["requestId"])
        if z:
            z["status"] = e["response"]["status"]
            z["enc"] = e["response"]["headers"].get("content-encoding") or e["response"]["headers"].get("Content-Encoding")

    def koniec(e):
        z = zad.get(e["requestId"])
        if z:
            z["bajty"] = e["encodedDataLength"]
            z["koniec"] = e["timestamp"]

    cdp.on("Network.requestWillBeSent", start)
    cdp.on("Network.responseReceived", odp)
    cdp.on("Network.loadingFinished", koniec)
    bledy = []
    strona.on("console", lambda m: bledy.append(f"{m.type}: {m.text}") if m.type in ("error", "warning") else None)
    strona.on("pageerror", lambda e: bledy.append(f"pageerror: {e}"))
    strona.goto(f"http://127.0.0.1:{port}/{wariant}/index.html", wait_until="load", timeout=180000)
    strona.wait_for_timeout(2500 if siec == "brak" else 6000)
    qa = strona.evaluate("window.__qa")
    cdp.send("Emulation.setCPUThrottlingRate", {"rate": 1})
    przegladarka.close()
    # agregacja
    suma = {}
    pliki = []
    for z in zad.values():
        if "bajty" not in z:
            continue
        k = klasa(z["url"], z["typ"])
        suma[k] = suma.get(k, 0) + z["bajty"]
        pliki.append({"url": z["url"].split("127.0.0.1:%s/" % port)[-1], "klasa": k, "bajty": int(z["bajty"]), "enc": z.get("enc"),
                      "start_ms": round((z["start"] - t0["t"]) * 1000), "koniec_ms": round((z["koniec"] - t0["t"]) * 1000)})
    pliki.sort(key=lambda x: x["koniec_ms"])
    lcp = qa["lcp"][-1] if qa["lcp"] else None
    return {"suma_b": suma, "pliki": pliki, "lcp": lcp, "fcp": qa["paint"].get("first-contentful-paint"), "cls": round(qa["cls"], 4),
            "longtasks": qa["longtasks"], "bledy": bledy}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8794)
    ap.add_argument("--warianty", default="salon_przyklad_15,salon_przyklad_26")
    ap.add_argument("--siec", default="fast3g", choices=["fast3g", "brak"])
    ap.add_argument("--cpu", type=int, default=4)
    ap.add_argument("--powtorzen", type=int, default=3)
    ap.add_argument("--ekran", default="390x844")
    ap.add_argument("--dpr", type=float, default=3)
    ap.add_argument("--wyj", default="")
    a = ap.parse_args()
    w, h = map(int, a.ekran.split("x"))
    wynik = {}
    with sync_playwright() as p:
        for wariant in a.warianty.split(","):
            przebiegi = [jeden_przebieg(p, a.port, wariant, a.siec, a.cpu, w, h, a.dpr) for _ in range(a.powtorzen)]
            lcps = [r["lcp"]["t"] for r in przebiegi if r["lcp"]]
            fcps = [r["fcp"] for r in przebiegi if r["fcp"]]
            ref = przebiegi[0]
            kb = {k: round(v / 1024, 1) for k, v in ref["suma_b"].items()}
            kod = sum(ref["suma_b"].get(k, 0) for k in ("html", "css", "js", "krój")) / 1024
            p1 = ref["suma_b"].get("paczka1", 0) / 1024
            p2 = ref["suma_b"].get("paczka2", 0) / 1024
            wynik[wariant] = {
                "ekran": a.ekran, "dpr": a.dpr, "siec": a.siec, "cpu": a.cpu, "powtorzen": a.powtorzen,
                "lcp_ms": lcps, "lcp_mediana_ms": statistics.median(lcps) if lcps else None,
                "fcp_ms": fcps, "fcp_mediana_ms": statistics.median(fcps) if fcps else None,
                "cls": max(r["cls"] for r in przebiegi), "longtasks": max(r["longtasks"] for r in przebiegi),
                "element_lcp": ref["lcp"],
                "kb_na_kablu": kb, "paczka1_obrazy_kb": round(p1, 1), "kod_html_css_js_kroje_kb": round(kod, 1),
                "paczka1_scisle_kb": round(p1 + kod, 1), "paczka2_kb": round(p2, 1),
                "calosc_kb": round(sum(ref["suma_b"].values()) / 1024, 1),
                "pliki": ref["pliki"], "bledy": sorted({b for r in przebiegi for b in r["bledy"]}),
            }
            print(wariant, "LCP", lcps, "FCP", fcps, "CLS", wynik[wariant]["cls"], "P1 scisle", wynik[wariant]["paczka1_scisle_kb"],
                  "P1 obrazy", wynik[wariant]["paczka1_obrazy_kb"], "kod", wynik[wariant]["kod_html_css_js_kroje_kb"],
                  "P2", wynik[wariant]["paczka2_kb"], "calosc", wynik[wariant]["calosc_kb"], flush=True)
    if a.wyj:
        Path(a.wyj).parent.mkdir(parents=True, exist_ok=True)
        Path(a.wyj).write_text(json.dumps(wynik, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
