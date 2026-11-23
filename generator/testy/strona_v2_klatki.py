"""Klatki przewijania sekcji v2 (prototyp_strona) na porcie 8793: telefon 390x844 i komputer 1440x900, prawdziwe kolko myszy.
Zapisuje arkusz klatek testy/strona_v2/<wariant>_<m|d>salon_przyklad_25 i liste bledow konsoli.

    python testy/strona_v2_klatki.py [wariant ...] [--m|--d] [--lite] [--bezjs] [--spokoj]
"""
import sys, subprocess, time, json
from pathlib import Path
from playwright.sync_api import sync_playwright
from PIL import Image

K = Path(__file__).resolve().parent.parent
OUT = K / "testy" / "strona_v2"
OUT.mkdir(parents=True, exist_ok=True)
arg = [a for a in sys.argv[1:] if not a.startswith("--")]
fl = [a for a in sys.argv[1:] if a.startswith("--")]
warianty = arg or ["salon_przyklad_26-logo"]
ekrany = [("m", 390, 844, 2), ("d", 1440, 900, 1)]
if "--m" in fl: ekrany = ekrany[:1]
if "--d" in fl: ekrany = ekrany[1:]
lite, bezjs, spokoj = "--lite" in fl, "--bezjs" in fl, "--spokoj" in fl
dop = ("_lite" if lite else "") + ("_bezjs" if bezjs else "") + ("_spokoj" if spokoj else "")

srv = subprocess.Popen([sys.executable, "-m", "http.server", "8793", "--bind", "127.0.0.1", "--directory", str(K / "prototyp_strona")],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(1.2)
try:
    with sync_playwright() as p:
        b = p.chromium.launch()
        for w in warianty:
            for nazwa, sz, wy, dpr in ekrany:
                ctx = b.new_context(viewport={"width": sz, "height": wy}, device_scale_factor=dpr, java_script_enabled=not bezjs,
                                    reduced_motion="reduce" if spokoj else "no-preference", has_touch=(nazwa == "m"),
                                    is_mobile=(nazwa == "m"))
                s = ctx.new_page()
                bledy = []
                s.on("pageerror", lambda e: bledy.append("pageerror: " + str(e)))
                s.on("console", lambda m: bledy.append(m.type + ": " + m.text) if m.type in ("error", "warning") else None)
                s.goto(f"http://127.0.0.1:8793/{w}/index.html" + ("?lite=1" if lite else ""), wait_until="networkidle")
                s.wait_for_timeout(1500)
                s.mouse.move(sz // 2, wy // 2)
                start = s.evaluate("(document.querySelector('.pasek-uslug')||document.body).getBoundingClientRect().top + scrollY - innerHeight*0.6")
                if bezjs or spokoj:
                    s.evaluate(f"window.scrollTo(0,{start})")
                else:
                    y = 0
                    while y < start:
                        s.mouse.wheel(0, 120); y += 120; time.sleep(0.012)
                s.wait_for_timeout(900)
                klatki, i, ost = [], 0, -1
                krok = int(wy * 0.55)
                while i < 90:
                    f = OUT / f"_k_{w}_{nazwa}{dop}_{i:03d}.png"
                    s.screenshot(path=str(f))
                    klatki.append(f)
                    i += 1
                    if bezjs or spokoj:
                        s.evaluate(f"window.scrollBy(0,{krok})")
                    else:
                        for _ in range(krok // 40):
                            s.mouse.wheel(0, 40); time.sleep(0.016)
                    s.wait_for_timeout(700)
                    yy = s.evaluate("scrollY")
                    if yy == ost:
                        break
                    ost = yy
                stan = s.evaluate("window.__SEKCJE__ ? JSON.stringify(window.__SEKCJE__.stan()) : 'brak'") if not bezjs else "bezjs"
                sw = s.evaluate("[document.documentElement.scrollWidth, document.documentElement.clientWidth]")
                ctx.close()
                # arkusz
                kol = 8 if nazwa == "m" else 4
                szer = 230 if nazwa == "m" else 460
                ims = [Image.open(f).convert("RGB") for f in klatki]
                ims = [im.resize((szer, int(im.height * szer / im.width))) for im in ims]
                h = ims[0].height
                wier = (len(ims) + kol - 1) // kol
                ark = Image.new("RGB", (kol * szer + (kol - 1) * 6, wier * h + (wier - 1) * 6), (255, 255, 255))
                for k, im in enumerate(ims):
                    ark.paste(im, ((k % kol) * (szer + 6), (k // kol) * (h + 6)))
                cel = OUT / f"{w}_{nazwa}{dop}salon_przyklad_25"
                ark.save(cel, quality=82)
                for f in klatki:
                    f.unlink()
                print(w, nazwa, dop or "js", "klatek", len(klatki), "szerokosc", sw, "bledy", bledy[:4], "\n   stan", stan[:400], "\n  ", cel)
        b.close()
finally:
    srv.terminate()
