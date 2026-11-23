"""Testy dodatkowe: Lenis i dotkniecie na desktopie, UA Instagrama (lite), bezpieczniki (brak ScrollTrigger, brak haka), przeladowanie w polowie,
tablet, link pomijajacy, podglad ?faza=."""
import json
import sys

from playwright.sync_api import sync_playwright

from animacja_lib import *

WAR = sys.argv[1] if len(sys.argv) > 1 else "salon_przyklad_15"
w = {}
STAN = """() => ({js: document.documentElement.classList.contains('js'), an: document.documentElement.getAttribute('data-animator'), lite: document.documentElement.classList.contains('lite'),
    lenis: document.documentElement.classList.contains('lenis'), st: typeof ScrollTrigger === 'undefined' ? null : ScrollTrigger.getAll().length,
    sticky: getComputedStyle(document.querySelector('[data-anim=scena]')).position, sw: document.documentElement.scrollWidth, cw: document.documentElement.clientWidth})"""

with sync_playwright() as p:
    # desktop: klik w puderniczke przez Lenis
    b, ctx = nowy_kontekst(p, 1440, 900, dpr=1, dotyk=False)
    s, k = otworz(ctx, WAR)
    s.mouse.click(936, 450)
    ser = []
    for _ in range(36):
        ser.append(round(s.evaluate("ScrollTrigger.getAll()[0].progress"), 3)); s.wait_for_timeout(100)
    w["desktop_klik_w_puderniczke_Lenis"] = {"stan": s.evaluate(STAN), "40%_po_ms": next((i * 100 for i, v in enumerate(ser) if v >= .39), None),
                                              "100%_po_ms": next((i * 100 for i, v in enumerate(ser) if v >= .995), None), "monotonicznie": all(b_ >= a_ - 1e-6 for a_, b_ in zip(ser, ser[1:])), "konsola": k}
    # kolko myszy w trakcie auto-przewijania przerywa
    s.evaluate("scrollTo(0,0)"); s.wait_for_timeout(600)
    s.mouse.click(936, 450); s.wait_for_timeout(500)
    s.mouse.wheel(0, 100); y1 = s.evaluate("scrollY"); s.wait_for_timeout(900); y2 = s.evaluate("scrollY")
    w["desktop_kolko_przerywa_auto"] = {"y_chwile_po_kole": y1, "y_900ms_pozniej": y2, "delta_px": round(y2 - y1, 1)}
    b.close()

    # UA Instagrama -> lite, bez Lenis (takze na desktopie)
    b = p.chromium.launch()
    ctx = b.new_context(viewport={"width": 1440, "height": 900}, user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/21F90 Instagram 330.0.0.12.113 (iPhone15,2; iOS 17_5; pl_PL)")
    s = ctx.new_page(); k = zbieraj_konsole(s); s.goto(URL + WAR + "/index.html", wait_until="networkidle"); s.wait_for_timeout(500)
    przewin_do(s, 0.5, 300)
    w["ua_instagram_lite"] = {**s.evaluate(STAN), "postep": round(s.evaluate("ScrollTrigger.getAll()[0].animation.progress()"), 3), "konsola": k}
    b.close()

    # bezpiecznik 1: ScrollTrigger sie nie zaladowal
    b = p.chromium.launch(); ctx = b.new_context(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True)
    s = ctx.new_page(); k = zbieraj_konsole(s)
    s.route("**/ScrollTrigger.min.js", lambda r: r.abort())
    s.goto(URL + WAR + "/index.html", wait_until="networkidle"); s.wait_for_timeout(500)
    w["bezpiecznik_brak_ScrollTrigger"] = {**s.evaluate(STAN), "konsola": [x for x in k if "ERR_FAILED" not in x]}
    s.screenshot(path=str(WYJ / "bezpiecznik_brak_ST.png"), full_page=False)
    b.close()
    # bezpiecznik 2: brak jednego haka w HTML -> wyjatek w budowie
    b = p.chromium.launch(); ctx = b.new_context(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True)
    s = ctx.new_page(); k = zbieraj_konsole(s)
    def zepsuj(route):
        r = route.fetch(); body = r.text().replace('data-anim="luk"', 'data-anim="luk-x"'); route.fulfill(response=r, body=body)
    s.route("**/index.html", zepsuj)
    s.goto(URL + WAR + "/index.html", wait_until="networkidle"); s.wait_for_timeout(800)
    w["bezpiecznik_blad_w_budowie"] = {**s.evaluate(STAN), "konsola": k}
    s.screenshot(path=str(WYJ / "bezpiecznik_blad_budowy.png"), full_page=False)
    b.close()

    # przeladowanie w polowie
    b, ctx = nowy_kontekst(p, 390, 844, dpr=1)
    s, k = otworz(ctx, WAR)
    przewin_do(s, 0.5, 300)
    s.reload(wait_until="networkidle"); s.wait_for_timeout(900)
    w["przeladowanie_w_polowie"] = {"scrollY": s.evaluate("scrollY"), "postep_osi": round(s.evaluate("ScrollTrigger.getAll()[0].animation.progress()"), 3), "stan": s.evaluate(STAN)}
    s.screenshot(path=str(WYJ / f"po_reload_polowa_{WAR}.png"))
    # link pomijajacy
    w["link_pomijajacy_href"] = s.evaluate("document.querySelector('.pomin').getAttribute('href')")
    b.close()

    # tablet 820x1180 i 768x1024: klatki + brak poziomego scrolla
    for vp in ((820, 1180), (768, 1024)):
        b, ctx = nowy_kontekst(p, vp[0], vp[1], dpr=1, dotyk=True)
        s, k = otworz(ctx, WAR)
        for pr in (0, 0.18, 0.3, 0.55, 1.0):
            przewin_do(s, pr, 260); s.screenshot(path=str(WYJ / "klatki" / f"{WAR}__{vp[0]}x{vp[1]}__{int(pr*100):03d}.jpg"), type="jpeg", quality=88)
        w[f"tablet_{vp[0]}x{vp[1]}"] = {**s.evaluate(STAN), "konsola": k}
        b.close()

    # podglad ?faza= nadal dziala i animator go nie rusza
    b, ctx = nowy_kontekst(p, 390, 844, dpr=1)
    s, k = otworz(ctx, WAR, "?faza=otwarta"); s.wait_for_timeout(400)
    w["podglad_faza_otwarta"] = {**s.evaluate(STAN), "faza": s.evaluate("document.querySelector('[data-anim=scena]').getAttribute('data-faza')"), "konsola": k}
    b.close()

print(json.dumps(w, ensure_ascii=False, indent=1))
(WYJ / "dodatki.json").write_text(json.dumps(w, ensure_ascii=False, indent=1), encoding="utf-8")
