"""Testy funkcjonalne animacji hero (headless Chromium): stan koncowy, uchylenie, dotkniecie, przerwanie, powrot,
tryby statyczne (bez JS, reduced-motion, poziomo), pasek adresu, zmiana rozmiaru, konsola.

    python testy/animacja_funkcje.py [wariant]
"""
import io
import json
import sys

from PIL import Image, ImageChops, ImageStat
from playwright.sync_api import sync_playwright

from animacja_lib import *

WAR = sys.argv[1] if len(sys.argv) > 1 else "salon_przyklad_15"
WYJ.mkdir(exist_ok=True)
wyn = {}


def roznica(a, b, box=None):
    A, B = Image.open(io.BytesIO(a)).convert("RGB"), Image.open(io.BytesIO(b)).convert("RGB")
    if box:
        A, B = A.crop(box), B.crop(box)
    d = ImageChops.difference(A, B)
    return round(sum(ImageStat.Stat(d).mean) / 3, 3), max(ImageStat.Stat(d).extrema[i][1] for i in range(3))


KAT_PANEL = """() => { const m = new DOMMatrix(getComputedStyle(document.querySelector('[data-anim=panel]')).transform);
  return Math.atan2(m.m23, m.m22) * 180 / Math.PI; }"""

with sync_playwright() as p:
    # ------------------------------------------------------------ 1. stan koncowy = czyste zdjecie
    przegladarka, ctx = nowy_kontekst(p, 390, 844, dpr=1)
    s, kons = otworz(ctx, WAR)
    przewin_do(s, 1.0, 400)
    A = s.screenshot()
    info = s.evaluate("""() => { const g = n => document.querySelector('[data-anim=' + n + ']'); const o = n => parseFloat(getComputedStyle(g(n)).opacity);
        const img = g('zdjecie-img') || document.querySelector('.zdjecie-img');
        return {hi: o('lusterko-hi'), przyc: o('przyciemnienie'), pos: o('poswiata'), luk: o('luk'), rama: getComputedStyle(g('rama-plaska')).visibility,
                panel: getComputedStyle(g('panel')).visibility, zawO: o('zawias-o'), zawZ: o('zawias-z'),
                dol_y: new DOMMatrix(getComputedStyle(g('puder-dol')).transform).f, sh: g('scena').offsetHeight,
                src: img.currentSrc.split('/').slice(-2).join('/'), nat: [img.naturalWidth, img.naturalHeight], wyswietlane: [img.getBoundingClientRect().width, img.getBoundingClientRect().height],
                kola: [...document.querySelectorAll('[data-anim=kolo]')].map(k => getComputedStyle(k).visibility + ':' + getComputedStyle(k).opacity)}; }""")
    wyn["koncowy_stan"] = info
    # (a) wszystko poza zdjeciem ukryte -> ten sam obszar zdjecia
    box = (0, 0, 390, 540)
    s.evaluate("""() => { document.querySelectorAll('[data-anim=scena] > *').forEach(e => { if (!e.matches('[data-anim=zdjecie]')) e.style.visibility = 'hidden'; });
        document.querySelector('.zdjecie').style.border = '0'; document.querySelector('[data-anim=lusterko-hi]').style.visibility = 'hidden'; }""")
    B = s.screenshot()
    wyn["koncowy_bez_nakladek_roznica_obszar_zdjecia"] = roznica(A, B, box)
    przegladarka.close()
    # (b) statyczny ?faza=koncowa
    przegladarka, ctx = nowy_kontekst(p, 390, 844, dpr=1)
    s2, _ = otworz(ctx, WAR, "?faza=koncowa")
    s2.wait_for_timeout(500)
    C = s2.screenshot()
    wyn["koncowy_vs_css_koncowa"] = roznica(A, C)
    przegladarka.close()

    # ------------------------------------------------------------ 2. uchylenie: ile razy, jak wysoko, bez powtarzania w nieskonczonosc
    przegladarka, ctx = nowy_kontekst(p, 390, 844, dpr=1)
    s = ctx.new_page()
    kons2 = zbieraj_konsole(s)
    s.goto(URL + WAR + "/index.html", wait_until="domcontentloaded")
    s.evaluate("""() => { window.__t = []; const t0 = performance.now(); const f = () => { const e = document.querySelector('[data-anim=panel]');
        if (e) { const m = new DOMMatrix(getComputedStyle(e).transform); window.__t.push([Math.round(performance.now() - t0), Math.abs(Math.round(Math.atan2(m.m23, m.m22) * 1800 / Math.PI) / 10), scrollY]); }
        requestAnimationFrame(f); }; f(); }""")
    s.wait_for_timeout(21000)
    tr = s.evaluate("window.__t")
    seg, cur = [], None
    for t, ang, _ in tr:
        if ang > 3 and cur is None: cur = [t, t, ang]
        elif ang > 3: cur[1] = t; cur[2] = max(cur[2], ang)
        elif cur: seg.append(cur); cur = None
    wyn["uchylenie_segmenty_[start_ms,koniec_ms,max_stopni]"] = seg
    wyn["uchylenie_po_20s"] = tr[-1]
    przegladarka.close()

    # ------------------------------------------------------------ 2b. przewiniecie w trakcie uchylenia: bez przeskoku
    przegladarka, ctx = nowy_kontekst(p, 390, 844, dpr=1)
    s = ctx.new_page()
    s.goto(URL + WAR + "/index.html", wait_until="domcontentloaded")
    s.evaluate("""() => { window.__t = []; const t0 = performance.now(); const f = () => { const e = document.querySelector('[data-anim=panel]');
        if (e) { const m = new DOMMatrix(getComputedStyle(e).transform); window.__t.push([Math.round(performance.now() - t0), Math.abs(Math.atan2(m.m23, m.m22) * 180 / Math.PI), scrollY]); }
        requestAnimationFrame(f); }; f(); }""")
    s.wait_for_function("window.__t.some(r => r[1] > 15)", timeout=15000)
    s.evaluate("window.scrollTo(0, 40)")          # palec w trakcie uchylenia
    s.wait_for_timeout(900)
    tr = s.evaluate("window.__t")
    i0 = next(i for i, r in enumerate(tr) if r[2] > 0)
    po = tr[i0 - 1:i0 + 30]
    skoki = [round(abs(po[i + 1][1] - po[i][1]), 2) for i in range(len(po) - 1)]
    wyn["uchylenie_przerwane_przewinieciem"] = {"kat_przed": round(tr[i0 - 1][1], 1), "kat_po_200ms": round(po[min(len(po) - 1, 12)][1], 1),
                                                "max_skok_na_klatke_st": max(skoki), "scrub_oczekiwany_st": round(40 / 1519 * 100 / 8 * 25, 1)}
    przegladarka.close()

    # ------------------------------------------------------------ 3. dotkniecie: puderniczka i przycisk
    def sondaz(s, ms=4200, krok=100):
        out = []
        for _ in range(ms // krok):
            out.append(round(s.evaluate("ScrollTrigger.getAll()[0].progress"), 3))
            s.wait_for_timeout(krok)
        return out

    for nazwa, akcja in (("dotkniecie_puderniczki", lambda s: s.touchscreen.tap(195, 359)),
                         ("dotkniecie_przycisku", lambda s: s.locator("a.przewin").tap())):
        przegladarka, ctx = nowy_kontekst(p, 390, 844, dpr=1)
        s, _ = otworz(ctx, WAR)
        s.wait_for_timeout(300)
        akcja(s)
        pr = sondaz(s)
        t40 = next((i for i, v in enumerate(pr) if v >= 0.39), None)
        t100 = next((i for i, v in enumerate(pr) if v >= 0.995), None)
        wyn[nazwa] = {"dojscie_do_40%_po_ms": None if t40 is None else t40 * 100, "dojscie_do_100%_po_ms": None if t100 is None else t100 * 100,
                      "plateau_przy_40%": [round(v, 2) for v in pr[10:20]], "kolejnosc_monotoniczna": all(b >= a - 1e-6 for a, b in zip(pr, pr[1:]))}
        przegladarka.close()

    # ------------------------------------------------------------ 3b. przerwanie dotykiem w trakcie
    przegladarka, ctx = nowy_kontekst(p, 390, 844, dpr=1)
    s, _ = otworz(ctx, WAR)
    s.locator("a.przewin").tap()
    s.wait_for_timeout(450)
    s.touchscreen.tap(30, 700)          # dotkniecie ekranu
    y1 = s.evaluate("scrollY"); s.wait_for_timeout(700); y2 = s.evaluate("scrollY")
    wyn["przerwanie_dotykiem"] = {"y_przy_dotyku": y1, "y_700ms_pozniej": y2, "stoi": abs(y2 - y1) < 3}
    przegladarka.close()

    # ------------------------------------------------------------ 3c. klawiatura: Tab do przycisku, Enter -> sekwencja i fokus na CTA
    przegladarka, ctx = nowy_kontekst(p, 1440, 900, dpr=1, dotyk=False)
    s, _ = otworz(ctx, WAR)
    for _ in range(6):
        s.keyboard.press("Tab")
        if s.evaluate("document.activeElement && document.activeElement.classList.contains('przewin')"):
            break
    ok_fokus = s.evaluate("document.activeElement.className")
    s.keyboard.press("Enter")
    s.wait_for_timeout(3800)
    wyn["klawiatura_enter"] = {"fokus_przed": ok_fokus, "postep_po_3,8s": round(s.evaluate("ScrollTrigger.getAll()[0].progress"), 3),
                               "fokus_po": s.evaluate("document.activeElement.className + '|' + document.activeElement.textContent.trim()")}
    przegladarka.close()

    # ------------------------------------------------------------ 4. powrot w gore i zatrzymanie w polowie
    przegladarka, ctx = nowy_kontekst(p, 390, 844, dpr=1)
    s, _ = otworz(ctx, WAR)
    s.add_style_tag(content=".przewin svg{animation:none!important}")       # bez podskoku strzalki: porownujemy tylko scene
    s.evaluate("dispatchEvent(new Event('wheel'))")                           # konczy podpowiedz (uchylenie), jak pierwszy ruch uzytkownika
    s.wait_for_timeout(400)
    przed = s.screenshot()
    zaw = []
    for pr in (0.2, 0.5, 0.35, 0.6, 0.15, 0.0):
        przewin_do(s, pr, 200)
        zaw.append(round(s.evaluate("ScrollTrigger.getAll()[0].animation.progress()"), 3))
    po = s.screenshot()
    wyn["powrot_w_gore"] = {"postepy_osi": zaw, "roznica_poczatek_vs_po_powrocie": roznica(przed, po)}
    # drobne kroki w gore i w dol z rozna predkoscia
    ostatni, maks_skok = None, 0
    for pr in [i / 100 for i in range(0, 101, 2)] + [i / 100 for i in range(100, -1, -2)]:
        s.evaluate("(p) => { const t = ScrollTrigger.getAll()[0]; scrollTo(0, t.start + p * (t.end - t.start)); }", pr)
        s.evaluate("() => new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)))")
        v = s.evaluate("ScrollTrigger.getAll()[0].animation.progress()")
        if ostatni is not None: maks_skok = max(maks_skok, abs(v - ostatni))
        ostatni = v
    wyn["krok_2pct_max_zmiana_osi"] = round(maks_skok, 4)
    przegladarka.close()

    # ------------------------------------------------------------ 5. tryby statyczne
    for nazwa, kw, vp in (("bez_JS", dict(java_script_enabled=False), (390, 844)),
                          ("reduced_motion", dict(reduced_motion="reduce"), (390, 844)),
                          ("poziomo_844x390", dict(), (844, 390)),
                          ("reduced_motion_desktop", dict(reduced_motion="reduce"), (1440, 900))):
        przegladarka = p.chromium.launch()
        ctx = przegladarka.new_context(viewport={"width": vp[0], "height": vp[1]}, is_mobile=vp[0] < 700, has_touch=vp[0] < 700, **kw)
        s = ctx.new_page()
        k = zbieraj_konsole(s)
        s.goto(URL + WAR + "/index.html", wait_until="networkidle")
        s.wait_for_timeout(1200)
        st = s.evaluate("""() => ({js: document.documentElement.classList.contains('js'), animator: document.documentElement.getAttribute('data-animator'),
            sticky: getComputedStyle(document.querySelector('[data-anim=scena]')).position, scrollW: document.documentElement.scrollWidth, clientW: document.documentElement.clientWidth,
            przewin_display: getComputedStyle(document.querySelector('a.przewin')).display, st: typeof ScrollTrigger === 'undefined' ? 'brak' : ScrollTrigger.getAll().length})""") if kw.get("java_script_enabled", True) else \
            {"js": "n/d (bez JS)", "uwaga": "html.js dodaje skrypt inline"}
        s.screenshot(path=str(WYJ / f"stan_{nazwa}_{WAR}.png"), full_page=True)
        wyn[f"tryb_{nazwa}"] = {**st, "konsola": k}
        przegladarka.close()

    # ------------------------------------------------------------ 6. pasek adresu: zmiana wysokosci okna przy stalym svh, rebuild tylko przy zmianie szerokosci / svh
    przegladarka, ctx = nowy_kontekst(p, 390, 844, dpr=1)
    s, _ = otworz(ctx, WAR)
    s.add_style_tag(content=":root{--vh1:8.44px !important}")      # svh nie zmienia sie z paskiem adresu: symulujemy stala
    s.wait_for_timeout(200)
    s.evaluate("window.__ref = 0; ScrollTrigger.addEventListener('refresh', () => window.__ref++)")
    przewin_do(s, 0.5, 300)
    A = s.screenshot()
    st0 = s.evaluate("(() => { const t = ScrollTrigger.getAll()[0]; return [t.start, t.end, scrollY, t.animation.progress()]; })()")
    s.set_viewport_size({"width": 390, "height": 900})               # pasek adresu sie chowa
    s.wait_for_timeout(900)
    B = s.screenshot()
    st1 = s.evaluate("(() => { const t = ScrollTrigger.getAll()[0]; return [t.start, t.end, scrollY, t.animation.progress()]; })()")
    s.set_viewport_size({"width": 390, "height": 844})
    s.wait_for_timeout(900)
    st2 = s.evaluate("(() => { const t = ScrollTrigger.getAll()[0]; return [t.start, t.end, scrollY, t.animation.progress(), window.__ref]; })()")
    wyn["pasek_adresu_844_900_844"] = {"przed": st0, "po_900": st1, "po_powrocie": st2, "roznica_obszaru_sceny_844px": roznica(A, B, (0, 0, 390, 844)),
                                       "odswiezen_ScrollTrigger": s.evaluate("window.__ref")}
    przegladarka.close()

    # ------------------------------------------------------------ 7. zmiana rozmiaru i orientacji
    przegladarka, ctx = nowy_kontekst(p, 390, 844, dpr=1)
    s, kons7 = otworz(ctx, WAR)
    przewin_do(s, 0.5, 300)
    s.set_viewport_size({"width": 844, "height": 390}); s.wait_for_timeout(900)
    poziomo = s.evaluate("({js: document.documentElement.classList.contains('js'), an: document.documentElement.getAttribute('data-animator'), pos: getComputedStyle(document.querySelector('[data-anim=scena]')).position, sw: document.documentElement.scrollWidth})")
    s.set_viewport_size({"width": 390, "height": 844}); s.wait_for_timeout(900)
    wr = s.evaluate("({js: document.documentElement.classList.contains('js'), an: document.documentElement.getAttribute('data-animator'), st: ScrollTrigger.getAll().length, p: ScrollTrigger.getAll()[0] && ScrollTrigger.getAll()[0].animation.progress()})")
    przewin_do(s, 0.5, 300)
    s.screenshot(path=str(WYJ / f"po_obrocie_{WAR}.png"))
    wyn["obrot_390x844_844x390_390x844"] = {"poziomo": poziomo, "po_powrocie": wr, "konsola": kons7}
    przegladarka.close()

    przegladarka, ctx = nowy_kontekst(p, 1440, 900, dpr=1, dotyk=False)
    s, kons8 = otworz(ctx, WAR)
    przewin_do(s, 0.6, 400)
    pr0 = s.evaluate("ScrollTrigger.getAll()[0].animation.progress()")
    s.set_viewport_size({"width": 1200, "height": 800}); s.wait_for_timeout(900)
    pr1 = s.evaluate("ScrollTrigger.getAll()[0].animation.progress()")
    s.set_viewport_size({"width": 1000, "height": 800}); s.wait_for_timeout(900)
    pr2 = s.evaluate("({p: ScrollTrigger.getAll()[0].animation.progress(), lenis: document.documentElement.classList.contains('lenis'), an: document.documentElement.getAttribute('data-animator')})")
    wyn["resize_desktop_1440_1200_1000"] = {"postep": [round(pr0, 3), round(pr1, 3), pr2], "konsola": kons8}
    przegladarka.close()

wyn["konsola_glowna_sciezka"] = kons + kons2
print(json.dumps(wyn, ensure_ascii=False, indent=1))
(WYJ / f"funkcje_{WAR}.json").write_text(json.dumps(wyn, ensure_ascii=False, indent=1), encoding="utf-8")
