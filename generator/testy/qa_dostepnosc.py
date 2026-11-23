#!/usr/bin/env python3
"""QA: dostepnosc i stany hero. Klawiatura, fokus, cele dotyku, drzewo dostepnosci, kontrast w przegladarce, alt, polskie znaki,
ograniczony ruch, brak JS.

    python testy/qa_dostepnosc.py --port 8790 [--zrzuty KAT] --wyj docs/qa/dostepnosc.json
"""
from __future__ import annotations

import argparse
import io
import json
import re
from pathlib import Path

import numpy as np
from PIL import Image
from playwright.sync_api import sync_playwright

W = ["salon_przyklad_15-logo", "salon_przyklad_14-logo", "salon_przyklad_12-logo", "salon_przyklad_26-logo"]


def lum(c):
    c = np.asarray(c, dtype=np.float64) / 255.0
    c = np.where(c <= 0.03928, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)
    return 0.2126 * c[..., 0] + 0.7152 * c[..., 1] + 0.0722 * c[..., 2]


def kontrast(l1, l2):
    a, b = max(l1, l2), min(l1, l2)
    return (a + 0.05) / (b + 0.05)


def otworz(b, port, v, w=390, h=844, dpr=1, mob=True, **kw):
    ctx = b.new_context(viewport={"width": w, "height": h}, device_scale_factor=dpr, is_mobile=mob, has_touch=mob, **kw)
    s = ctx.new_page()
    kons = []
    s.on("console", lambda m: kons.append(f"{m.type}: {m.text}") if m.type in ("error", "warning") else None)
    s.on("pageerror", lambda e: kons.append(f"pageerror: {e}"))
    s.on("requestfailed", lambda r: kons.append(f"requestfailed: {r.url}"))
    s.on("response", lambda r: kons.append(f"http {r.status}: {r.url}") if r.status >= 400 else None)
    s.goto(f"http://127.0.0.1:{port}/{v}/index.html", wait_until="networkidle")
    s.evaluate("document.fonts.ready")
    return ctx, s, kons


OPIS = """
e => { const r = e.getBoundingClientRect(), c = getComputedStyle(e);
  return {tag: e.tagName.toLowerCase(), cls: (e.className || '').toString().slice(0, 30), txt: (e.getAttribute('aria-label') || e.innerText || e.alt || '').trim().slice(0, 40),
    x: Math.round(r.left), y: Math.round(r.top), w: Math.round(r.width), h: Math.round(r.height), vis: c.visibility, op: +(+c.opacity).toFixed(2),
    outline: c.outlineStyle + ' ' + c.outlineWidth + ' ' + c.outlineColor, wokno: r.bottom > 0 && r.top < innerHeight}; }
"""

KONTRAST_JS = """
(sel) => [...document.querySelectorAll(sel)].map(e => { const g = document.createRange(); g.selectNodeContents(e);
  const rs = [...g.getClientRects()].filter(r => r.width > 1);
  if (!rs.length) return null; const c = getComputedStyle(e);
  const x = Math.min(...rs.map(r => r.left)), y = Math.min(...rs.map(r => r.top)), r = Math.max(...rs.map(r => r.right)), b = Math.max(...rs.map(r => r.bottom));
  return {sel, txt: e.textContent.trim().slice(0, 30), color: c.color, fs: parseFloat(c.fontSize), fw: c.fontWeight, op: +c.opacity, x, y, r, b}; }).filter(Boolean)
"""


def kontrasty(s, selektory, dpr=1):
    rects = []
    for sel in selektory:
        rects += s.evaluate(KONTRAST_JS, sel)
    st = s.add_style_tag(content="*{color:transparent!important;-webkit-text-fill-color:transparent!important;text-shadow:none!important;text-decoration-color:transparent!important} svg,svg *{visibility:hidden!important}")
    img = np.asarray(Image.open(io.BytesIO(s.screenshot())).convert("RGB")).astype(np.float64)
    st.evaluate("e => e.remove()")
    wynik = []
    for e in rects:
        x0, x1 = max(int(e["x"] * dpr), 0), min(int(e["r"] * dpr) + 1, img.shape[1])
        y0, y1 = max(int(e["y"] * dpr), 0), min(int(e["b"] * dpr) + 1, img.shape[0])
        if x1 <= x0 or y1 <= y0:
            continue
        reg = img[y0:y1, x0:x1].reshape(-1, 3)
        fg = np.array([int(v) for v in re.findall(r"\d+", e["color"])[:3]], dtype=np.float64)
        lf = float(lum(fg))
        lb = lum(reg)
        # najgorsze tlo: dla jasnego tekstu najjasniejsze 5% pikseli, dla ciemnego najciemniejsze 5%
        lw = float(np.percentile(lb, 95) if lf > np.median(lb) else np.percentile(lb, 5))
        wynik.append({"sel": e["sel"], "txt": e["txt"], "fs": e["fs"], "fw": e["fw"], "kontrast_najgorszy": round(kontrast(lf, lw), 2),
                      "kontrast_mediana": round(kontrast(lf, float(np.median(lb))), 2)})
    return wynik


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8790)
    ap.add_argument("--zrzuty", default="")
    ap.add_argument("--wyj", default="")
    a = ap.parse_args()
    wyn = {}
    with sync_playwright() as p:
        b = p.chromium.launch()
        # --- 1. klawiatura, fokus, Enter na "Przewin" (telefon 390x844) ---
        for v in W:
            ctx, s, kons = otworz(b, a.port, v)
            s.evaluate("dispatchEvent(new Event('wheel'))")
            s.add_style_tag(content=".przewin svg{animation:none!important}")
            s.wait_for_timeout(400)
            kol = []
            for i in range(9):
                s.keyboard.press("Tab")
                s.wait_for_timeout(80)
                kol.append(s.evaluate("() => { const e = document.activeElement; return e && e !== document.body ? (" + OPIS + ")(e) : null; }"))
            url0 = s.url
            ctx.close()
            # osobna, swieza strona: Tab az do "Przewin", Enter, czekaj na koniec sekwencji
            ctx, s, kons2 = otworz(b, a.port, v)
            s.evaluate("dispatchEvent(new Event('wheel'))")
            s.wait_for_timeout(400)
            for i in range(8):
                s.keyboard.press("Tab")
                if s.evaluate("document.activeElement && document.activeElement.classList.contains('przewin')"):
                    break
            s.keyboard.press("Enter")
            s.wait_for_timeout(4500)
            po = s.evaluate("() => { const e = document.activeElement; const t = ScrollTrigger.getAll()[0]; return {akt: e ? (e.className || e.tagName) : null, "
                            "p: +t.progress.toFixed(3), y: Math.round(scrollY), url: location.href, wId: e ? (e.textContent || '').trim().slice(0, 30) : null}; }")
            s.keyboard.press("Tab"); s.wait_for_timeout(150)
            nast = s.evaluate("() => { const e = document.activeElement; return e ? (e.className || e.tagName).toString().slice(0, 30) + ' | ' + (e.textContent || '').trim().slice(0, 24) : null; }")
            s.keyboard.press("Shift+Tab"); s.keyboard.press("Shift+Tab"); s.wait_for_timeout(150)
            wstecz = s.evaluate("() => { const e = document.activeElement; return e ? (e.className || e.tagName).toString().slice(0, 30) + ' | ' + (e.textContent || '').trim().slice(0, 24) : null; }")
            kons += kons2
            wyn.setdefault("klawiatura", {})[v] = {"kolejnosc_tab": [(k["tag"], k["cls"], k["txt"], k["vis"], k["op"], k["outline"]) if k else None for k in kol],
                                                    "url_przed": url0, "po_enter_na_przewin": po, "tab_po_koncu": nast, "shift_tab_2x": wstecz, "konsola": kons}
            ctx.close()
        # --- 2. cele dotyku, p = 0 i koniec ---
        ctx, s, kons = otworz(b, a.port, "salon_przyklad_15-logo")
        s.evaluate("dispatchEvent(new Event('wheel'))"); s.wait_for_timeout(300)
        cele0 = s.evaluate("() => [...document.querySelectorAll('a, button, summary')].filter(e => getComputedStyle(e).visibility !== 'hidden' && getComputedStyle(e).display !== 'none').map(e => (" + OPIS + ")(e))")
        s.evaluate("(() => { const t = ScrollTrigger.getAll()[0]; scrollTo(0, t.end); })()"); s.wait_for_timeout(900)
        cele1 = s.evaluate("() => [...document.querySelectorAll('a, button, summary')].filter(e => getComputedStyle(e).visibility !== 'hidden' && getComputedStyle(e).display !== 'none').map(e => (" + OPIS + ")(e))")
        wyn["cele_dotyku"] = {"p0": cele0, "koniec": cele1}
        # --- 3. drzewo dostepnosci w 3 stanach ---
        ar = {}
        s.evaluate("scrollTo(0,0)"); s.wait_for_timeout(700)
        ar["p0"] = s.locator("body").aria_snapshot()
        s.evaluate("(() => { const t = ScrollTrigger.getAll()[0]; scrollTo(0, t.start + 0.5 * (t.end - t.start)); })()"); s.wait_for_timeout(700)
        ar["p50"] = s.locator("body").aria_snapshot()
        s.evaluate("(() => { const t = ScrollTrigger.getAll()[0]; scrollTo(0, t.end); })()"); s.wait_for_timeout(700)
        ar["p100"] = s.locator("body").aria_snapshot()
        wyn["aria"] = ar
        ctx.close()
        # --- 4. kontrast w przegladarce (p=0, koniec, usługi, stopka) ---
        for v in ("salon_przyklad_15-logo", "salon_przyklad_14-logo"):
            ctx, s, kons = otworz(b, a.port, v)
            s.evaluate("dispatchEvent(new Event('wheel'))"); s.add_style_tag(content=".przewin svg{animation:none!important}"); s.wait_for_timeout(400)
            k0 = kontrasty(s, [".pasek__profil span", ".pasek__cta", "h1", ".przewin"])
            s.evaluate("(() => { const t = ScrollTrigger.getAll()[0]; scrollTo(0, t.end); })()"); s.wait_for_timeout(1000)
            k1 = kontrasty(s, [".zdanie", ".linia", ".cta-koniec"])
            s.evaluate("document.querySelector('#uslugi').scrollIntoView()"); s.wait_for_timeout(500)
            k2 = kontrasty(s, [".uslugi h2", ".uslugi-nota", ".grupa h3", ".grupa summary", ".cennik .n", ".cennik .c", ".uslugi-brak a", ".uslugi-brak"])
            s.evaluate("document.querySelector('.stopka').scrollIntoView()"); s.wait_for_timeout(300)
            k3 = kontrasty(s, [".stopka p", "mark.todo"])
            wyn.setdefault("kontrast", {})[v] = {"p0": k0, "koniec": k1, "uslugi": k2, "stopka": k3}
            ctx.close()
        # --- 5. fokus na jasnym tle (kucharska: link w uslugach; brwi_przyklad: summary) ---
        fj = {}
        for v, sel in (("salon_przyklad_12-logo", ".uslugi-brak a"), ("salon_przyklad_14-logo", ".uslugi summary")):
            ctx, s, kons = otworz(b, a.port, v)
            s.evaluate("dispatchEvent(new Event('wheel'))"); s.wait_for_timeout(300)
            s.evaluate("document.querySelector('#uslugi').scrollIntoView()"); s.wait_for_timeout(300)
            s.evaluate("(sel) => document.querySelector(sel).focus()", sel)
            s.keyboard.press("Shift+Tab"); s.keyboard.press("Tab"); s.wait_for_timeout(150)
            info = s.evaluate("(sel) => { const e = document.querySelector(sel); const c = getComputedStyle(e); const r = e.getBoundingClientRect();"
                              " return {focus: document.activeElement === e, outline: c.outlineStyle + ' ' + c.outlineWidth + ' ' + c.outlineColor, offset: c.outlineOffset,"
                              " tlo: getComputedStyle(document.querySelector('.uslugi')).backgroundColor, x: r.left, y: r.top, w: r.width, h: r.height}; }", sel)
            if a.zrzuty:
                Path(a.zrzuty).mkdir(parents=True, exist_ok=True)
                s.screenshot(path=str(Path(a.zrzuty) / f"fokus_jasne_{v}.png"))
            oc = [int(x) for x in re.findall(r"\d+", info["outline"].split("rgb")[-1])[:3]] if "rgb" in info["outline"] else None
            tl = [int(x) for x in re.findall(r"\d+", info["tlo"])[:3]]
            if oc:
                info["kontrast_obrysu_do_tla"] = round(kontrast(float(lum(oc)), float(lum(tl))), 2)
            fj[v] = info
            ctx.close()
        wyn["fokus_na_jasnym"] = fj
        # --- 6. alt, naglowki, jezyk, tytul ---
        ctx, s, kons = otworz(b, a.port, "salon_przyklad_15-logo")
        wyn["semantyka"] = s.evaluate("""() => ({
          lang: document.documentElement.lang, title: document.title, desc: document.querySelector('meta[name=description]').content,
          h: [...document.querySelectorAll('h1,h2,h3,h4')].map(h => h.tagName + ': ' + h.textContent.trim().slice(0, 50)),
          landmarki: [...document.querySelectorAll('main,nav,footer,header,[role]')].map(e => e.tagName.toLowerCase() + (e.getAttribute('aria-label') ? '[' + e.getAttribute('aria-label') + ']' : '')),
          img: [...document.images].map(i => ({src: i.getAttribute('src').split('/').slice(-2).join('/'), alt: i.getAttribute('alt'), ah: i.closest('[aria-hidden=true]') !== null, w: i.width, h: i.height})),
          aria_hidden: [...document.querySelectorAll('[aria-hidden=true]')].map(e => (e.className || e.tagName).toString().slice(0, 24)),
          zly_znak: /[\\uFFFD]|Ä|Å‚|Ã/.test(document.body.innerText + document.title),
          kotwice: [...document.querySelectorAll('a[href^="#"]')].map(a => [a.getAttribute('href'), !!document.querySelector(a.getAttribute('href'))]),
          linki: [...document.querySelectorAll('a[href]')].map(a => a.getAttribute('href')).filter(h => !h.startsWith('#')),
          tytul_ma_nbsp: document.title.includes('\\u00a0'), desc_ma_nbsp: document.querySelector('meta[name=description]').content.includes('\\u00a0')
        })""")
        ctx.close()
        # --- 7. ograniczony ruch i brak JS ---
        stany = {}
        for nazwa, kw in (("reduced_motion", {"reduced_motion": "reduce"}), ("bez_JS", {"java_script_enabled": False})):
            for (w, h, mob) in ((390, 844, True), (1440, 900, False)):
                for v in ("salon_przyklad_15-logo", "salon_przyklad_14-logo"):
                    ctx, s, kons = otworz(b, a.port, v, w, h, 1, mob, **kw)
                    s.wait_for_timeout(600)
                    inf = s.evaluate("""() => { const vis = e => { if (!e) return false; const c = getComputedStyle(e), r = e.getBoundingClientRect(); return c.display !== 'none' && c.visibility !== 'hidden' && +c.opacity > 0.9 && r.width > 0; };
                      const q = s => document.querySelector(s);
                      return {js: document.documentElement.classList.contains('js'), animator: document.documentElement.getAttribute('data-animator'), sw: document.documentElement.scrollWidth, vw: innerWidth,
                        h1: vis(q('h1')), zdanie: vis(q('.zdanie')), linia: vis(q('.linia')), cta_koniec: vis(q('.cta-koniec')), cta_statyczny: vis(q('.cta-statyczny')), przewin: vis(q('.przewin')),
                        zdjecie: vis(q('.zdjecie')), puder: vis(q('.panel-przod, .rama-plaska')), lid_alt: !!q('.panel-przod img') && !!q('.panel-przod img').alt,
                        uslugi_h2: vis(q('.uslugi h2')), ceny: document.querySelectorAll('.cennik .c').length, pasek: vis(q('.pasek')), slowo: vis(q('.slowo')), kola: [...document.querySelectorAll('.kolo')].filter(vis).length,
                        h1_txt: q('h1').textContent.trim(), skrypty_pasuja: !!window.gsap, docH: document.documentElement.scrollHeight}; }""")
                    inf["konsola"] = kons
                    stany[f"{nazwa}_{w}x{h}_{v}"] = inf
                    if a.zrzuty and v == "salon_przyklad_15-logo":
                        s.screenshot(path=str(Path(a.zrzuty) / f"stan_{nazwa}_{w}x{h}.png"), full_page=(w == 390))
                    ctx.close()
        wyn["stany"] = stany
        b.close()
    if a.wyj:
        Path(a.wyj).write_text(json.dumps(wyn, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({k: v for k, v in wyn.items() if k in ("klawiatura",)}, ensure_ascii=False, indent=1)[:6000])


if __name__ == "__main__":
    main()
