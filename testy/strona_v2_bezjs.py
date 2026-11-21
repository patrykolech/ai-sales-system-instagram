"""Zrzuty calych sekcji v2 bez JS i przy ograniczonym ruchu (z JS): telefon 390x844 i komputer 1440x900, od paska pod hero do stopki.
Zapis: testy/strona_v2/<wariant>_<m|d>_<bezjs|spokoj>.jpg oraz kontrola: poziomy scroll, ukryte elementy, bledy konsoli.

    python testy/strona_v2_bezjs.py [wariant ...]
"""
import io, sys, subprocess, time, json
from pathlib import Path
from playwright.sync_api import sync_playwright
from PIL import Image

Image.MAX_IMAGE_PIXELS = None
K = Path(__file__).resolve().parent.parent
OUT = K / "testy" / "strona_v2"
OUT.mkdir(parents=True, exist_ok=True)
WARIANTY = sys.argv[1:] or ["salon_przyklad_26-logo", "salon_przyklad_14-logo", "salon_przyklad_15-logo", "salon_przyklad_12-logo"]
UKRYTE = """[...document.querySelectorAll('main > section:not(#hero) *, footer *')].filter(e => {
  const cs = getComputedStyle(e); const r = e.getBoundingClientRect();
  return r.width > 0 && r.height > 0 && (cs.visibility === 'hidden' || parseFloat(cs.opacity) < 0.05) && !e.closest('[aria-hidden=true]') && !e.closest('dialog') && !e.matches('.dok');
}).slice(0, 8).map(e => e.tagName + '.' + e.className)"""

srv = subprocess.Popen([sys.executable, "-m", "http.server", "8793", "--bind", "127.0.0.1", "--directory", str(K / "prototyp_strona")],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(1.2)
try:
    with sync_playwright() as p:
        b = p.chromium.launch()
        for w in WARIANTY:
            for nazwa, sz, wy in (("m", 390, 844), ("d", 1440, 900)):
                for tryb in ("bezjs", "spokoj"):
                    ctx = b.new_context(viewport={"width": sz, "height": wy}, device_scale_factor=1, java_script_enabled=(tryb != "bezjs"),
                                        reduced_motion="reduce" if tryb == "spokoj" else "no-preference")
                    s = ctx.new_page()
                    bledy = []
                    s.on("pageerror", lambda e: bledy.append(str(e)))
                    s.on("console", lambda m: bledy.append(m.text) if m.type in ("error", "warning") else None)
                    s.goto(f"http://127.0.0.1:8793/{w}/index.html", wait_until="networkidle")
                    H = s.evaluate("document.documentElement.scrollHeight")
                    for y in range(0, H, 700):                     # leniwe obrazy
                        s.evaluate(f"window.scrollTo(0,{y})"); s.wait_for_timeout(40)
                    s.wait_for_timeout(1200)
                    s.evaluate("window.scrollTo(0,0)"); s.wait_for_timeout(300)
                    gora = s.evaluate("document.querySelector('.pasek-uslug').getBoundingClientRect().top + scrollY")
                    sw = s.evaluate("[document.documentElement.scrollWidth, document.documentElement.clientWidth]")
                    ukryte = s.evaluate(UKRYTE)
                    png = s.screenshot(full_page=True)
                    im = Image.open(io.BytesIO(png)).convert("RGB")
                    im = im.crop((0, int(gora), im.width, im.height))
                    skala = 390 / im.width if nazwa == "m" else 720 / im.width
                    im = im.resize((int(im.width * skala), int(im.height * skala)))
                    cel = OUT / f"{w}_{nazwa}_{tryb}.jpg"
                    im.save(cel, quality=80)
                    print(w, nazwa, tryb, "szerokosc", sw, "ukryte", ukryte, "bledy", bledy[:3], "->", cel.name, im.size)
                    ctx.close()
        b.close()
finally:
    srv.terminate()
