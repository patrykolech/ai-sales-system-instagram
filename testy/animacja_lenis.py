"""Czy Lenis poprawia wrazenie na desktopie? Seria impulsow kolka myszy (headless, CPU 4x): ile klatek rusza scrolla i jak duzy jest skok na klatke.
Porownanie: Lenis (domyslnie) vs ?lenis=0 (natywne przewijanie + scrub 0,4 s). To pomiar liczbowy, nie ocena na oko."""
import json, statistics
from playwright.sync_api import sync_playwright
from animacja_lib import *

def seria(p, q):
    b, ctx = nowy_kontekst(p, 1440, 900, dpr=1, dotyk=False)
    s, k = otworz(ctx, "salon_przyklad_15", q)
    s.mouse.click(40, 880)                    # konczy podpowiedz; (syntetyczny Event('wheel') bez deltaY psuje Lenis, wiec nie uzywamy)
    s.wait_for_timeout(500)
    cdp = ctx.new_cdp_session(s)
    cdp.send("Emulation.setCPUThrottlingRate", {"rate": 4})
    s.evaluate("""() => { window.__s = []; window.__prog = []; window.__rec = true; let last = performance.now();
        const f = t => { if (window.__rec) { window.__s.push([t - last, scrollY]); window.__prog.push(ScrollTrigger.getAll()[0].animation.progress()); } last = t; requestAnimationFrame(f); }; requestAnimationFrame(f); }""")
    s.mouse.move(700, 450)
    for _ in range(14):                       # 14 zapadek kolka co 70 ms
        s.mouse.wheel(0, 100); s.wait_for_timeout(70)
    s.wait_for_timeout(1500)
    s.evaluate("window.__rec = false")
    d = s.evaluate("window.__s"); pr = s.evaluate("window.__prog")
    y = [r[1] for r in d]
    dy = [abs(b_ - a_) for a_, b_ in zip(y, y[1:])]
    ruch = [v for v in dy if v > 0.01]
    dp = [abs(b_ - a_) for a_, b_ in zip(pr, pr[1:])]
    out = {"klatek_ze_scrollem": len(ruch), "max_skok_px": round(max(dy), 1), "mediana_skoku_px_gdy_rusza": round(statistics.median(ruch), 1) if ruch else 0,
           "max_skok_osi_%": round(max(dp) * 100, 2), "koncowe_y": y[-1], "czas_klatki_max_ms": round(max(r[0] for r in d), 1),
           "klatek_>20ms": sum(r[0] > 20 for r in d), "lenis": s.evaluate("document.documentElement.classList.contains('lenis')"), "konsola": k}
    b.close()
    return out

with sync_playwright() as p:
    wyn = {"Lenis": seria(p, ""), "natywne+scrub0.4": seria(p, "?lenis=0")}
print(json.dumps(wyn, ensure_ascii=False, indent=1))
(WYJ / "lenis.json").write_text(json.dumps(wyn, ensure_ascii=False, indent=1), encoding="utf-8")
