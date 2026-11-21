"""QA: plynnosc hero po dodaniu slowa z konturem (-webkit-text-stroke). Kopia pomiaru animatora (animacja_plynnosc.py) z parametrem css,
zeby oddzielic koszt konturu i slowa od reszty. Wynik: docs/qa/plynnosc_slowo_dpr3_cpu4x.json (nie nadpisuje testy/animacja/).

    python testy/qa_plynnosc_slowo.py --port 8790 --warianty salon_przyklad_15-logo,salon_przyklad_26-logo
"""
import argparse, json, statistics
from pathlib import Path
from playwright.sync_api import sync_playwright
import animacja_lib as L
from animacja_lib import zbieraj_konsole

ap = argparse.ArgumentParser()
ap.add_argument("--dpr", type=float, default=3)
ap.add_argument("--cpu", type=float, default=4)
ap.add_argument("--port", type=int, default=8790)
ap.add_argument("--warianty", default="salon_przyklad_15-logo,salon_przyklad_26-logo")
a = ap.parse_args()
URL = f"http://127.0.0.1:{a.port}/"
INIT = """
window.__cls = 0; window.__lt = []; window.__lcp = 0;
new PerformanceObserver(l => { for (const e of l.getEntries()) if (!e.hadRecentInput) window.__cls += e.value; }).observe({type: 'layout-shift', buffered: true});
new PerformanceObserver(l => { for (const e of l.getEntries()) window.__lt.push([e.startTime, e.duration]); }).observe({type: 'longtask', buffered: true});
new PerformanceObserver(l => { for (const e of l.getEntries()) window.__lcp = e.startTime; }).observe({type: 'largest-contentful-paint', buffered: true});
window.__fr = []; window.__rec = false;
(() => { let last = performance.now(); const f = t => { if (window.__rec) window.__fr.push([t, t - last]); last = t; requestAnimationFrame(f); }; requestAnimationFrame(f); })();
"""

NAZWY = ("Paint", "Layout", "UpdateLayoutTree", "RasterTask", "DrawFrame", "Commit", "FunctionCall", "EvaluateScript", "UpdateLayer", "CompositeLayers", "PrePaint", "Layerize")


def pomiar(p, wariant, query, tempo, dpr, cpu, tracing=True, css=""):
    przegladarka = p.chromium.launch()
    ctx = przegladarka.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=dpr, is_mobile=True, has_touch=True)
    strona = ctx.new_page()
    kons = zbieraj_konsole(strona)
    strona.add_init_script(INIT)
    strona.goto(f"{URL}{wariant}/index.html{query}", wait_until="networkidle")
    strona.evaluate("document.fonts.ready")
    strona.evaluate("dispatchEvent(new Event('wheel'))")             # bez podpowiedzi w trakcie pomiaru
    strona.add_style_tag(content=".przewin svg{animation:none!important}" + css)
    strona.wait_for_timeout(600)
    cdp = ctx.new_cdp_session(strona)
    cdp.send("Performance.enable")
    sonda = "() => { const t = performance.now(); let x = 0; for (let i = 0; i < 4e6; i++) x += Math.sqrt(i); return performance.now() - t; }"
    sonda1 = strona.evaluate(sonda)
    cdp.send("Emulation.setCPUThrottlingRate", {"rate": cpu})
    sondaN = strona.evaluate(sonda)
    m0 = {x["name"]: x["value"] for x in cdp.send("Performance.getMetrics")["metrics"]}
    t0 = strona.evaluate("performance.now()")
    strona.evaluate("window.__fr = []; window.__rec = true")
    if tracing:
        przegladarka.start_tracing(page=strona, categories=["devtools.timeline", "disabled-by-default-devtools.timeline", "cc", "gpu", "viz"])
    dyst, kroki = 1519, 4
    po_dol = None
    for kierunek in (-1, 1):                                          # w dol (yDistance < 0), potem w gore
        for _ in range(kroki):
            cdp.send("Input.synthesizeScrollGesture", {"x": 195, "y": 640 if kierunek < 0 else 200, "yDistance": kierunek * dyst / kroki, "speed": tempo,
                                                       "preventFling": True})
            strona.wait_for_timeout(60)
        if kierunek < 0:
            po_dol = strona.evaluate("[Math.round(scrollY), (typeof ScrollTrigger === 'undefined' || !ScrollTrigger.getAll()[0]) ? null : +ScrollTrigger.getAll()[0].animation.progress().toFixed(3)]")
    sciezka = None
    if tracing:
        sciezka = przegladarka.stop_tracing()
    strona.evaluate("window.__rec = false")
    t1 = strona.evaluate("performance.now()")
    m1 = {x["name"]: x["value"] for x in cdp.send("Performance.getMetrics")["metrics"]}
    cdp.send("Emulation.setCPUThrottlingRate", {"rate": 1})
    fr = strona.evaluate("window.__fr")
    dt = [d for _, d in fr if d > 0]
    lt = [(s, d) for s, d in strona.evaluate("window.__lt") if t0 <= s <= t1]
    zdarz = {n: 0 for n in NAZWY}
    if tracing and sciezka:
        for e in json.loads(sciezka).get("traceEvents", []):
            if e.get("name") in zdarz and e.get("ph") in ("X", "B", "I"):
                zdarz[e["name"]] += 1
    wyn = {
        "sonda_cpu_ms_bez_i_z_dlawieniem": [round(sonda1), round(sondaN)], "scrollY_i_os_po_przewinieciu_w_dol": po_dol,
        "klatek": len(dt), "czas_s": round((t1 - t0) / 1000, 2),
        "klatka_mediana_ms": round(statistics.median(dt), 1), "klatka_p95_ms": round(sorted(dt)[int(len(dt) * .95) - 1], 1), "klatka_max_ms": round(max(dt), 1),
        "klatek_>20ms": sum(d > 20 for d in dt), "klatek_>33ms": sum(d > 33.4 for d in dt), "klatek_>50ms": sum(d > 50 for d in dt),
        "dlugie_zadania_>50ms": len(lt), "dlugie_zadania_suma_ms": round(sum(d for _, d in lt)), "najdluzsze_ms": round(max([d for _, d in lt], default=0)),
        "ScriptDuration_s": round(m1["ScriptDuration"] - m0["ScriptDuration"], 3), "LayoutDuration_s": round(m1["LayoutDuration"] - m0["LayoutDuration"], 3),
        "RecalcStyleDuration_s": round(m1["RecalcStyleDuration"] - m0["RecalcStyleDuration"], 3), "TaskDuration_s": round(m1["TaskDuration"] - m0["TaskDuration"], 3),
        "LayoutCount": int(m1["LayoutCount"] - m0["LayoutCount"]), "RecalcStyleCount": int(m1["RecalcStyleCount"] - m0["RecalcStyleCount"]),
        "trace": {k: v for k, v in zdarz.items() if v},
        "CLS_od_ladowania": round(strona.evaluate("window.__cls"), 4), "LCP_ms": round(strona.evaluate("window.__lcp")),
        "konsola": kons,
    }
    przegladarka.close()
    return wyn



BEZ_KONTURU = ".slowo--kontur{-webkit-text-stroke:0!important}"
BEZ_SLOWA = ".slowo{display:none!important}"
wynik = {}
with sync_playwright() as p:
    for w in a.warianty.split(","):
        wynik[w] = {}
        for tempo in (800, 2500):
            wynik[w][f"animacja_{tempo}px_s"] = pomiar(p, w, "", tempo, a.dpr, a.cpu)
        wynik[w]["bez_konturu_800px_s"] = pomiar(p, w, "", 800, a.dpr, a.cpu, css=BEZ_KONTURU)
        wynik[w]["bez_slowa_800px_s"] = pomiar(p, w, "", 800, a.dpr, a.cpu, css=BEZ_SLOWA)
        wynik[w]["baza_bez_GSAP_800px_s"] = pomiar(p, w, "?faza=zamknieta", 800, a.dpr, a.cpu)
out = Path(__file__).resolve().parent.parent / "docs" / "qa" / f"plynnosc_slowo_dpr{int(a.dpr)}_cpu{int(a.cpu)}x.json"
out.write_text(json.dumps(wynik, ensure_ascii=False, indent=1), encoding="utf-8")
for w, r in wynik.items():
    for k, v in r.items():
        print(w, k, "mediana", v["klatka_mediana_ms"], "p95", v["klatka_p95_ms"], "max", v["klatka_max_ms"], ">20ms", v["klatek_>20ms"], ">33ms", v["klatek_>33ms"], ">50ms", v["klatek_>50ms"], "klatek", v["klatek"], "dlugie", v["dlugie_zadania_>50ms"], "CLS", v["CLS_od_ladowania"], "konsola", v["konsola"][:2])
