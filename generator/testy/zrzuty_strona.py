"""Zrzuty calych stron (prototyp_strona) na porcie 8792: 390x844 i 1440x900 z JS, bez JS, oraz kontakt po zamknieciu puderniczki."""
import sys, subprocess, time, json
from pathlib import Path
from playwright.sync_api import sync_playwright
K = Path(__file__).resolve().parent.parent
OUT = K / "testy" / "strona"; OUT.mkdir(exist_ok=True)
nicki = sys.argv[1:] or ["salon_przyklad_26-logo", "salon_przyklad_14", "salon_przyklad_15-logo", "salon_przyklad_12"]
srv = subprocess.Popen([sys.executable, "-m", "http.server", "8792", "--directory", str(K / "prototyp_strona")], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(1.5)
try:
    with sync_playwright() as p:
        b = p.chromium.launch()
        for n in nicki:
            for nazwa, w, h in (("m", 390, 844), ("d", 1440, 900)):
                for js in (False, True):
                    ctx = b.new_context(viewport={"width": w, "height": h}, device_scale_factor=1, java_script_enabled=js)
                    pg = ctx.new_page()
                    bledy = []
                    pg.on("console", lambda m: bledy.append(m.text) if m.type == "error" else None)
                    pg.on("pageerror", lambda e: bledy.append(str(e)))
                    pg.goto(f"http://127.0.0.1:8792/{n}/index.html", wait_until="networkidle")
                    if js:
                        # przewin do konca po kolei, zeby leniwe obrazy sie zaladowaly
                        H = pg.evaluate("document.documentElement.scrollHeight")
                        for y in range(0, H, 500):
                            pg.evaluate(f"window.scrollTo(0,{y})"); pg.wait_for_timeout(60)
                        pg.wait_for_timeout(1500)
                        pg.evaluate("window.scrollTo(0,0)")
                        pg.wait_for_timeout(300)
                    # zrzut od sekcji Uslugi w dol (hero ma wlasne testy)
                    sz = pg.evaluate("[document.documentElement.scrollWidth, document.documentElement.clientWidth]")
                    print(n, nazwa, "js" if js else "bezjs", "scrollWidth/clientWidth", sz, "bledy", bledy)
                    pg.screenshot(path=str(OUT / f"{n}_{nazwa}_{'js' if js else 'bezjs'}.png"), full_page=True)
                    if js:
                        pg.evaluate("document.querySelector('#kontakt').scrollIntoView({block:'center'})")
                        pg.wait_for_timeout(1800)
                        pg.screenshot(path=str(OUT / f"{n}_{nazwa}_kontakt.png"))
                    ctx.close()
        b.close()
finally:
    srv.terminate()
