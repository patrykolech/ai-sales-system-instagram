"""Kontrola prototyp_strona: sciezki assetow, id, JSON-LD, poziomy scroll bez JS (1440/768/375), cele dotyku, kontrast tokenow, wagi."""
import json, re, subprocess, sys, time, gzip
from pathlib import Path
from urllib.parse import urlparse
from playwright.sync_api import sync_playwright
K = Path(__file__).resolve().parent.parent
W = K / "prototyp_strona"
raport = json.loads((W / "raport.json").read_text(encoding="utf-8"))

def lum(h):
    h = h.lstrip("#"); c = [int(h[i:i+2], 16) / 255 for i in (0, 2, 4)]
    c = [x / 12.92 if x <= .03928 else ((x + .055) / 1.055) ** 2.4 for x in c]
    return .2126 * c[0] + .7152 * c[1] + .0722 * c[2]
def kontrast(a, b):
    la, lb = sorted((lum(a), lum(b)), reverse=True); return (la + .05) / (lb + .05)

srv = subprocess.Popen([sys.executable, "-m", "http.server", "8792", "--directory", str(W)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(1.2)
try:
    with sync_playwright() as p:
        b = p.chromium.launch()
        for w in raport:
            f = w["folder"]; html = (W / f / "index.html").read_text(encoding="utf-8")
            out = {"folder": f}
            # sciezki
            brak = []
            for u in re.findall(r'(?:src|href)="([^"#?][^"]*)"', html):
                if re.match(r"(https?:|mailto:|tel:|data:)", u): continue
                if not (W / f / u).resolve().exists(): brak.append(u)
            out["brak_plikow"] = sorted(set(brak))
            ids = re.findall(r'\bid="([^"]+)"', html); out["dup_id"] = sorted({i for i in ids if ids.count(i) > 1})
            ld = re.search(r'<script type="application/ld\+json">(.*?)</script>', html, re.S)
            try: json.loads(ld.group(1)); out["jsonld"] = "ok"
            except Exception as e: out["jsonld"] = f"BLAD {e}"
            out["h1"] = len(re.findall(r"<h1[ >]", html))
            out["fffd"] = html.count("\ufffd")
            # kontrast tokenow
            tok = dict(re.findall(r"(--[a-z-]+):(#[0-9a-fA-F]{6})", html))
            k = {}
            for a, bg in (("--atrament", "--puder"), ("--szept", "--puder"), ("--jasny", "--tlo"), ("--szept-jasny", "--tlo"), ("--szept-jasny", "--tlo-ciemne"),
                          ("--atrament", "--lakier"), ("--metal-cien", "--puder")):
                if a in tok and bg in tok: k[f"{a} na {bg}"] = round(kontrast(tok[a], tok[bg]), 2)
            k["guzik-tekst na guzik"] = round(kontrast("#2e211b", "#ead9cc"), 2); k["atrament na metal (mark.todo)"] = round(kontrast(tok["--atrament"], "#c8b48c"), 2)
            out["kontrast"] = k
            # poziomy scroll bez JS
            sc = {}
            for wd in (1440, 768, 375):
                ctx = b.new_context(viewport={"width": wd, "height": 900}, java_script_enabled=False); pg = ctx.new_page()
                pg.goto(f"http://127.0.0.1:8792/{f}/index.html", wait_until="load")
                sc[wd] = pg.evaluate("document.documentElement.scrollWidth - document.documentElement.clientWidth") if False else None
                ctx.close()
            # z JS (JS potrzebny do evaluate): bez JS sprawdzamy przez emulacje w osobnym kontekscie z JS, ale bez skryptow strony
            for wd in (1440, 768, 375):
                ctx = b.new_context(viewport={"width": wd, "height": 900}); pg = ctx.new_page()
                pg.route("**/*.js", lambda r: r.abort())
                pg.goto(f"http://127.0.0.1:8792/{f}/index.html", wait_until="load")
                sc[wd] = pg.evaluate("document.documentElement.scrollWidth - document.documentElement.clientWidth")
                if wd == 375:
                    cele = pg.evaluate("""[...document.querySelectorAll('.sekcja a.przycisk, .uslugi a.przycisk, .kontakt a.przycisk, summary, .kontakt-fakty a, .stopka a, .prace-ig a, .pasek a')]
                        .map(e => {const r = e.getBoundingClientRect(); return {t: (e.textContent||'').trim().slice(0,28), h: Math.round(r.height), w: Math.round(r.width)}}).filter(x => x.h < 44)""")
                    out["cele_ponizej_44"] = cele
                    out["polskie_znaki"] = all(c in pg.content() for c in "ąęłńóśźż")
                ctx.close()
            out["scroll_x_bez_js"] = sc
            out["html_kb"] = round(len(html.encode()) / 1024, 1)
            print(json.dumps(out, ensure_ascii=False))
        b.close()
finally:
    srv.terminate()
