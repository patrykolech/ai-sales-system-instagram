import subprocess, sys, time
from pathlib import Path
from playwright.sync_api import sync_playwright
K = Path(__file__).resolve().parent.parent
srv = subprocess.Popen([sys.executable, "-m", "http.server", "8792", "--directory", str(K / "prototyp_strona")], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(1.2)
try:
    with sync_playwright() as p:
        b = p.chromium.launch()
        for w, h, tag in ((390, 844, "m"), (1440, 900, "d")):
            pg = b.new_page(viewport={"width": w, "height": h})
            pg.goto("http://127.0.0.1:8792/salon_przyklad_15-logo/index.html", wait_until="networkidle")
            pg.evaluate("document.documentElement.scrollTo(0, document.documentElement.scrollHeight)")
            # dojscie bez wyzwolenia: najpierw zatrzymaj tuz przed progiem
            pg.evaluate("window.scrollTo(0, document.querySelector('#kontakt').getBoundingClientRect().top + scrollY - %d)" % (h - 160))
            pg.wait_for_timeout(500)
            pg.screenshot(path=str(K / "testy/strona" / f"kp_{tag}_0.png"))
            pg.evaluate("window.scrollTo(0, document.querySelector('#kontakt').getBoundingClientRect().top + scrollY - 40)")
            pg.wait_for_timeout(350)
            pg.screenshot(path=str(K / "testy/strona" / f"kp_{tag}_1.png"))
            pg.wait_for_timeout(1500)
            pg.screenshot(path=str(K / "testy/strona" / f"kp_{tag}_2.png"))
            print(tag, pg.evaluate("document.querySelector('.kp').className"))
        b.close()
finally:
    srv.terminate()
