"""Plynnosc scen po hero: telefon 390x844 (DPR 3, dotyk), CPU 4x (CDP), zywe gesty przewijania (Input.synthesizeScrollGesture).
Mierzone od konca toru hero do stopki: odstepy klatek rAF, long-animation-frame (LoAF) i longtask > 50 ms.

    python testy/strona_v2_plynnosc.py [wariant ...] [--lite] [--d]
"""
import sys, subprocess, time, json
from pathlib import Path
from playwright.sync_api import sync_playwright

K = Path(__file__).resolve().parent.parent
arg = [a for a in sys.argv[1:] if not a.startswith("--")]
fl = [a for a in sys.argv[1:] if a.startswith("--")]
WARIANTY = arg or ["salon_przyklad_26-logo", "salon_przyklad_14-logo", "salon_przyklad_15-logo", "salon_przyklad_12-logo"]
LITE = "--lite" in fl
DESK = "--d" in fl

ZAPIS = """
window.__pom = { klatki: [], loaf: [], lt: [], start: performance.now() };
function sekcja() { var e = document.elementFromPoint(innerWidth / 2, innerHeight / 2); var s = e && e.closest('section, footer'); return s ? (s.id || s.className) : '?'; }
(function petla(t0) { requestAnimationFrame(function (t) { if (window.__pom.ost) window.__pom.klatki.push([t - window.__pom.ost, scrollY, Math.round(t - window.__pom.start)]); window.__pom.ost = t; petla(); }); })();
try { new PerformanceObserver(function (l) { l.getEntries().forEach(function (e) { if (e.duration > 50) window.__pom.loaf.push([Math.round(e.duration), Math.round(e.blockingDuration || 0), scrollY,
  (e.scripts || []).map(function (s) { return (s.sourceURL || '').split('/').pop() + ':' + (s.invokerType || '') + ':' + (s.invoker || '').slice(0, 60) + ':' + Math.round(s.duration) + 'ms/styl' + Math.round(s.forcedStyleAndLayoutDuration || 0); }).join(' | '), Math.round(e.renderStart ? e.startTime + e.duration - e.renderStart : 0), Math.round(e.styleAndLayoutStart ? e.startTime + e.duration - e.styleAndLayoutStart : 0), sekcja()]); }); })
  .observe({ type: 'long-animation-frame', buffered: false }); } catch (e) {}
try { new PerformanceObserver(function (l) { l.getEntries().forEach(function (e) { window.__pom.lt.push([Math.round(e.duration), scrollY]); }); }).observe({ type: 'longtask', buffered: false }); } catch (e) {}
"""

srv = subprocess.Popen([sys.executable, "-m", "http.server", "8793", "--bind", "127.0.0.1", "--directory", str(K / "prototyp_strona")],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(1.2)
wyniki = []
try:
    with sync_playwright() as p:
        b = p.chromium.launch()
        for w in WARIANTY:
            if DESK:
                ctx = b.new_context(viewport={"width": 1440, "height": 900}, device_scale_factor=1)
            else:
                ctx = b.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=3, is_mobile=True, has_touch=True,
                                    user_agent="Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Mobile Safari/537.36")
            s = ctx.new_page()
            cdp = ctx.new_cdp_session(s)
            bledy = []
            s.on("pageerror", lambda e: bledy.append(str(e)))
            s.on("console", lambda m: bledy.append(m.text) if m.type == "error" else None)
            s.goto(f"http://127.0.0.1:8793/{w}/index.html" + ("?lite=1" if LITE else ""), wait_until="networkidle")
            s.wait_for_timeout(1500)
            # za hero bez pomiaru (hero ma wlasne testy), potem doczytanie obrazow nizej
            y0 = s.evaluate("document.querySelector('[data-scene=lustro]').getBoundingClientRect().bottom + scrollY - innerHeight * 0.3")
            s.evaluate(f"window.scrollTo(0, {y0})")
            s.wait_for_timeout(1500)
            cdp.send("Emulation.setCPUThrottlingRate", {"rate": 4})
            s.evaluate(ZAPIS)
            s.wait_for_timeout(500)
            H = s.evaluate("document.documentElement.scrollHeight - innerHeight")
            t0 = time.time()
            ost, stoi = -1, 0
            while time.time() - t0 < 150 and stoi < 3:
                # gestureSourceType zostaje domyslny: "touch" w tej wersji Chromium nie przewija (sprawdzone), domyslny = dotyk przy has_touch
                if DESK:
                    cdp.send("Input.synthesizeScrollGesture", {"x": 720, "y": 450, "yDistance": -700, "speed": 1600, "preventFling": True})
                else:
                    cdp.send("Input.synthesizeScrollGesture", {"x": 195, "y": 640, "yDistance": -520, "speed": 1400, "preventFling": True})
                s.wait_for_timeout(60)
                yy = s.evaluate("scrollY")
                if yy >= H - 2:
                    break
                stoi = stoi + 1 if yy == ost else 0
                ost = yy
            s.wait_for_timeout(800)
            cdp.send("Emulation.setCPUThrottlingRate", {"rate": 1})
            pom = s.evaluate("window.__pom")
            kl = [k[0] for k in pom["klatki"]]
            kl_s = sorted(kl)
            p95 = kl_s[int(len(kl_s) * 0.95)] if kl_s else 0
            wynik = {"wariant": w, "tryb": "desktop" if DESK else ("telefon lite" if LITE else "telefon"), "klatek": len(kl),
                     "mediana_ms": round(kl_s[len(kl_s) // 2], 1) if kl_s else 0, "p95_ms": round(p95, 1),
                     "klatki_ponad_50ms": sum(1 for k in kl if k > 50), "klatki_ponad_33ms": sum(1 for k in kl if k > 33.4),
                     "najdluzsza_ms": round(max(kl), 1) if kl else 0,
                     "loaf_ponad_50": len(pom["loaf"]), "longtask": len(pom["lt"]), "loaf": pom["loaf"][:12],
                     "dlugie_klatki_ms_y_t": [[round(k[0]), round(k[1]), k[2]] for k in pom["klatki"] if k[0] > 50][:12],
                     "przewinieto_px": round(ost), "bledy": bledy[:3]}
            wyniki.append(wynik)
            print(json.dumps(wynik, ensure_ascii=False))
            ctx.close()
        b.close()
finally:
    srv.terminate()
nazwa = "plynnosc" + ("_lite" if LITE else "") + ("_desktop" if DESK else "") + ".json"
(K / "testy" / "strona_v2" / nazwa).write_text(json.dumps(wyniki, ensure_ascii=False, indent=1), encoding="utf-8")

