#!/usr/bin/env python3
"""QA runda 2: stan bez JS (noscript) i prefers-reduced-motion. Kompletnosc tresci, obrazy zaladowane (naturalWidth), konsola, poziomy scroll.

    python testy/qa_stany_statyczne.py --port 8796 --zrzuty KAT --wyj docs/qa/r2_stany_statyczne.json
"""
import argparse, json
from pathlib import Path
from playwright.sync_api import sync_playwright

SPR = """() => {
  const vis = e => { if (!e) return false; const c = getComputedStyle(e), b = e.getBoundingClientRect(); return c.display !== 'none' && c.visibility !== 'hidden' && +c.opacity > 0.05 && b.width > 2 && b.height > 2; };
  const q = s => document.querySelector(s);
  const imgs = [...document.querySelectorAll('img')].filter(i => vis(i)).map(i => ({src: (i.currentSrc || i.getAttribute('src') || i.dataset.src || '').split('/').slice(-2).join('/'), ok: i.complete && i.naturalWidth > 0, alt: i.alt}));
  return {html_js: document.documentElement.classList.contains('js'), h1: q('h1') && q('h1').textContent.trim(), h1_vis: vis(q('h1')),
    cta_statyczny: vis(q('.cta-statyczny')), cta_koniec: vis(q('.cta-koniec')), przewin: vis(q('.przewin')), zdanie: vis(q('.zdanie')), linia: vis(q('.linia')),
    slowo_vis: vis(q('.slowo')), kola_vis: [...document.querySelectorAll('.kolo')].filter(vis).length,
    zdjecie_img: q('.zdjecie-img') ? {src: q('.zdjecie-img').getAttribute('src'), vis: vis(q('.zdjecie-img')), ok: q('.zdjecie-img').complete && q('.zdjecie-img').naturalWidth > 0} : null,
    nieladowane_widoczne: imgs.filter(i => !i.ok).map(i => i.src), uslugi_h2: vis(q('.uslugi h2')), ceny: document.querySelectorAll('.cennik li, .cennik tr, .cennik .n').length,
    poziomy_scroll: document.documentElement.scrollWidth > innerWidth + 1, wys: document.documentElement.scrollHeight, vw: innerWidth};
}"""

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8796)
    ap.add_argument("--warianty", default="salon_przyklad_15-logo,salon_przyklad_14-logo,salon_przyklad_26-logo")
    ap.add_argument("--zrzuty", default="")
    ap.add_argument("--wyj", default="")
    a = ap.parse_args()
    wynik = {}
    with sync_playwright() as p:
        b = p.chromium.launch()
        for w in a.warianty.split(","):
            wynik[w] = {}
            for tryb in ("bez_JS", "reduced_motion"):
                for ekran in ("390x844", "1440x900"):
                    W, H = map(int, ekran.split("x"))
                    kw = dict(viewport={"width": W, "height": H}, device_scale_factor=1, is_mobile=W < 700, has_touch=W < 700)
                    if tryb == "bez_JS": kw["java_script_enabled"] = False
                    else: kw["reduced_motion"] = "reduce"
                    ctx = b.new_context(**kw)
                    s = ctx.new_page()
                    bl = []
                    s.on("console", lambda m: bl.append(m.type + ": " + m.text) if m.type in ("error", "warning") else None)
                    s.on("pageerror", lambda e: bl.append("pageerror: " + str(e)))
                    s.on("requestfailed", lambda r: bl.append("failed: " + r.url))
                    s.goto(f"http://127.0.0.1:{a.port}/{w}/index.html", wait_until="load")
                    s.wait_for_timeout(1200)
                    top = s.evaluate(SPR) if tryb != "bez_JS" else None
                    # bez JS evaluate nie dziala: przez zrzut i DOM z content()
                    if tryb == "bez_JS":
                        ctx.close()
                        ctx = b.new_context(**{**kw, "java_script_enabled": True})
                        s2 = ctx.new_page()
                        # w trybie bez JS emulujemy: blokujemy skrypty sieciowe i inline przez route + CSP? prostsze: zrzut z wylaczonym JS wyzej
                        ctx.close()
                        ctx = b.new_context(**kw)
                        s = ctx.new_page()
                        s.goto(f"http://127.0.0.1:{a.port}/{w}/index.html", wait_until="load")
                        s.wait_for_timeout(1200)
                        if a.zrzuty:
                            Path(a.zrzuty).mkdir(parents=True, exist_ok=True)
                            s.screenshot(path=f"{a.zrzuty}/bezJS_{w}_{ekran}_gora.png")
                            s.screenshot(path=f"{a.zrzuty}/bezJS_{w}_{ekran}_calosc.png", full_page=True)
                        # metryki z DOM przez locator (bez evaluate): widocznosc i naturalWidth
                        def vis(sel):
                            l = s.locator(sel).first
                            return l.count() > 0 and l.is_visible()
                        wiersz = {"h1": s.locator("h1").first.inner_text(), "h1_vis": vis("h1"), "cta_statyczny": vis(".cta-statyczny"), "cta_koniec": vis(".cta-koniec"), "przewin": vis(".przewin"),
                                  "zdanie": vis(".zdanie"), "linia": vis(".linia"), "slowo": vis(".slowo"), "kola": s.locator(".kolo:visible").count(),
                                  "zdjecie_img_vis": vis(".zdjecie-img"), "uslugi_h2": vis(".uslugi h2"), "html_js": "js" in (s.locator("html").get_attribute("class") or ""),
                                  "zdjecie_img_zaladowane": None, "bledy": bl}
                        try:
                            n = s.locator(".zdjecie-img").first
                            box = n.bounding_box()
                            wiersz["zdjecie_img_box"] = box and [round(box["width"]), round(box["height"])]
                        except Exception as e:
                            wiersz["zdjecie_img_box"] = str(e)[:80]
                        wynik[w][f"{tryb}_{ekran}"] = wiersz
                    else:
                        top["bledy"] = bl
                        if a.zrzuty:
                            Path(a.zrzuty).mkdir(parents=True, exist_ok=True)
                            s.screenshot(path=f"{a.zrzuty}/RM_{w}_{ekran}_gora.png")
                            s.screenshot(path=f"{a.zrzuty}/RM_{w}_{ekran}_calosc.png", full_page=True)
                        wynik[w][f"{tryb}_{ekran}"] = top
                    ctx.close()
        b.close()
    for w, v in wynik.items():
        print("==", w)
        for k, x in v.items():
            print(" ", k, json.dumps(x, ensure_ascii=False)[:600])
    if a.wyj: Path(a.wyj).write_text(json.dumps(wynik, ensure_ascii=False, indent=1), encoding="utf-8")

main()
