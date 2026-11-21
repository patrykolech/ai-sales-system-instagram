#!/usr/bin/env python3
"""QA: (1) pusta rama przy zablokowanej paczce 2 i na Fast 3G, (2) stan koncowy = czyste zdjecie (porownanie pikseli),
(3) prazki w tle (poswiata), (4) przewijanie przed zaladowaniem JS na wolnym lacu.

    python testy/qa_rama_zdjecie.py --port 8790 --zrzuty KAT --wyj docs/qa/rama_zdjecie.json
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

FAST3G = dict(latency=562.5, downloadThroughput=1.6 * 1024 * 1024 / 8 * 0.9, uploadThroughput=750 * 1024 / 8 * 0.9)
P2 = re.compile(r"/(podstawa|rama-lusterka|zawias|zdjecie|lusterko)(-zamkniety)?\.webp")


def img(s, clip=None):
    return Image.open(io.BytesIO(s.screenshot())).convert("RGB")


def przewin(s, p):
    s.evaluate("(p) => { const t = ScrollTrigger.getAll()[0]; scrollTo(0, t.start + p * (t.end - t.start)); }", p)
    s.wait_for_timeout(350)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8790)
    ap.add_argument("--wariant", default="salon_przyklad_15-logo")
    ap.add_argument("--zrzuty", default="")
    ap.add_argument("--wyj", default="")
    a = ap.parse_args()
    out = Path(a.zrzuty) if a.zrzuty else None
    if out:
        out.mkdir(parents=True, exist_ok=True)
    url = f"http://127.0.0.1:{a.port}/{a.wariant}/index.html"
    wyn = {}
    with sync_playwright() as p:
        b = p.chromium.launch()
        # (1a) paczka 2 zablokowana na stale: pusta rama?
        ctx = b.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=1, is_mobile=True, has_touch=True)
        ctx.route(P2, lambda r: None)                                  # zadanie wisi: tak wyglada lacze, ktore nie dowozi
        s = ctx.new_page()
        s.goto(url, wait_until="domcontentloaded")
        s.wait_for_timeout(3000)
        s.evaluate("dispatchEvent(new Event('wheel'))")
        ok = s.evaluate("document.documentElement.hasAttribute('data-animator')")
        kl = []
        for pr in (0.4, 0.62, 0.8, 1.0):
            przewin(s, pr)
            im = img(s)
            kl.append(im)
        wyn["paczka2_zablokowana"] = {"animator_dziala": ok}
        if out:
            sh = Image.new("RGB", (390 * 4 + 12, 844), "white")
            for i, im in enumerate(kl):
                sh.paste(im, (i * 394, 0))
            sh.resize((sh.width // 2, sh.height // 2), Image.LANCZOS).save(out / "pusta_rama_p2_zablokowane.jpg", quality=84)
        ctx.close()
        # (1b)+(4) Fast 3G + CPU 4x: scroll po 2,4 s (po LCP, przed JS) i po 7 s
        ctx = b.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=1, is_mobile=True, has_touch=True)
        s = ctx.new_page()
        cdp = ctx.new_cdp_session(s)
        cdp.send("Network.enable")
        cdp.send("Network.setCacheDisabled", {"cacheDisabled": True})
        cdp.send("Network.emulateNetworkConditions", {"offline": False, **FAST3G})
        cdp.send("Emulation.setCPUThrottlingRate", {"rate": 4})
        t0 = {}
        s.goto(url, wait_until="commit")
        s.wait_for_timeout(2400)
        stan = lambda: s.evaluate("""() => ({gsap: !!window.gsap, st: !!window.ScrollTrigger, animator: document.documentElement.getAttribute('data-animator'),
            zdjecie: (i => i ? {complete: i.complete, nw: i.naturalWidth} : null)(document.querySelector('.zdjecie-img')),
            rama: (i => i ? i.complete : null)(document.querySelector('.rama-plaska img.warstwa')),
            lusterko: (i => i ? i.complete : null)(document.querySelector('.rama-plaska .lustro img')), y: Math.round(scrollY), sh: document.documentElement.scrollHeight})""")
        wyn["fast3g_2_4s"] = stan()
        s.evaluate("scrollTo(0, 760)")
        s.wait_for_timeout(400)
        k1 = img(s)
        wyn["fast3g_po_scrollu_przed_JS"] = stan()
        s.wait_for_timeout(5500)
        k2 = img(s)
        wyn["fast3g_po_7_9s"] = stan()
        s.wait_for_timeout(2500)
        k3 = img(s)
        wyn["fast3g_po_10s"] = stan()
        cdp.send("Emulation.setCPUThrottlingRate", {"rate": 1})
        if out:
            sh = Image.new("RGB", (390 * 3 + 8, 844), "white")
            for i, im in enumerate((k1, k2, k3)):
                sh.paste(im, (i * 394, 0))
            sh.resize((sh.width // 2, sh.height // 2), Image.LANCZOS).save(out / "fast3g_scroll_przed_JS.jpg", quality=84)
        ctx.close()
        # (2) czyste zdjecie: porownanie pikseli w stanie koncowym (390x844, DPR 1)
        for (w, h, mob) in ((390, 844, True), (1440, 900, False)):
            ctx = b.new_context(viewport={"width": w, "height": h}, device_scale_factor=1, is_mobile=mob, has_touch=mob)
            s = ctx.new_page()
            s.goto(url, wait_until="networkidle")
            s.evaluate("document.fonts.ready")
            if w < 1100:
                s.evaluate("dispatchEvent(new Event('wheel'))")
                s.wait_for_timeout(400)
            else:
                s.wait_for_timeout(4200)
            przewin(s, 1.0)
            s.wait_for_timeout(900)
            g = s.evaluate("""() => { const i = document.querySelector('.zdjecie-img'), z = document.querySelector('.zdjecie'), r = i.getBoundingClientRect(), q = z.getBoundingClientRect();
                const num = s => { const e = document.querySelector(s); return e ? +getComputedStyle(e).opacity : null; };
                return {src: i.currentSrc, ix: r.left, iy: r.top, iw: r.width, ih: r.height, cx: q.left + q.width / 2, cy: q.top + q.height / 2, cr: q.width / 2,
                  hi: num('.lusterko-hi'), przy: num('.przyciemnienie'), pos: num('.poswiata'), luk: num('.luk'), zdj: num('.zdjecie'),
                  filtr: getComputedStyle(i).filter, mix: getComputedStyle(i).mixBlendMode, ophi: num('.zdjecie-wew')}; }""")
            shot = np.asarray(img(s)).astype(np.float64)
            src = Path(__file__).resolve().parent.parent / "prototyp" / a.wariant.replace("-logo", "") / g["src"].split(a.wariant)[-1].split("/", 2)[-1] if False else None
            # zrodlo: ten sam plik, ktory laduje strona
            rel = re.sub(r"^https?://[^/]+/", "", g["src"])
            zr = Image.open(Path(__file__).resolve().parent.parent / "prototyp" / rel).convert("RGB")
            iw, ih = max(int(round(g["iw"])), 1), max(int(round(g["ih"])), 1)
            ex = np.asarray(zr.resize((iw, ih), Image.LANCZOS)).astype(np.float64)
            canvas = np.full(shot.shape, np.nan)
            x0, y0 = int(round(g["ix"])), int(round(g["iy"]))
            xs0, ys0 = max(x0, 0), max(y0, 0)
            xs1, ys1 = min(x0 + iw, shot.shape[1]), min(y0 + ih, shot.shape[0])
            canvas[ys0:ys1, xs0:xs1] = ex[ys0 - y0:ys1 - y0, xs0 - x0:xs1 - x0]
            yy, xx = np.mgrid[0:shot.shape[0], 0:shot.shape[1]]
            w_kole = ((xx - g["cx"]) ** 2 + (yy - g["cy"]) ** 2) < (g["cr"] - 5) ** 2
            maska = w_kole & ~np.isnan(canvas[..., 0])
            d = shot - canvas
            dd = np.abs(d[maska])
            wyn[f"zdjecie_czyste_{w}x{h}"] = {
                "px": int(maska.sum()), "src": rel, "nakladki_krycie": {k: g[k] for k in ("hi", "przy", "pos", "luk", "zdj")}, "filtr": g["filtr"], "mix": g["mix"],
                "srednia_roznica": round(float(dd.mean()), 2), "p99_roznica": round(float(np.percentile(dd, 99)), 1),
                "przesuniecie_jasnosci_rgb": [round(float(d[maska][:, c].mean()), 2) for c in range(3)],
                "udzial_pikseli_roznica_ponad_12": round(float((dd.max(axis=1) > 12).mean()), 4)}
            if out:
                s.screenshot(path=str(out / f"koncowa_{w}x{h}.png"))
            ctx.close()
        # (3) poswiata: prazki / schodki w tle, ekran w stanie zamknietym
        for (w, h, mob, dpr) in ((1440, 900, False, 1), (390, 844, True, 3)):
            ctx = b.new_context(viewport={"width": w, "height": h}, device_scale_factor=dpr, is_mobile=mob, has_touch=mob)
            s = ctx.new_page()
            s.goto(url, wait_until="networkidle")
            s.evaluate("document.fonts.ready")
            s.add_style_tag(content="body *{visibility:hidden!important} .hero,.scena,.poswiata{visibility:visible!important}")
            s.wait_for_timeout(400)
            im = np.asarray(img(s)).astype(np.float64).mean(axis=2)
            # profil w pionie przy lewej krawedzi (bez tekstu, wylaczone) i poziomo na srodku: dlugosci "schodkow"
            def runs(v):
                r = np.round(v).astype(int); L = []; c = 1
                for i in range(1, len(r)):
                    if r[i] == r[i - 1]: c += 1
                    else: L.append(c); c = 1
                L.append(c); return L
            kol = im[:, int(im.shape[1] * 0.1)]
            wie = im[int(im.shape[0] * 0.5), :]
            rk, rw = runs(kol), runs(wie)
            lo, hi = np.percentile(im, 1), np.percentile(im, 99)
            wyn[f"poswiata_{w}x{h}_dpr{dpr}"] = {"zakres_jasnosci": [round(float(lo), 1), round(float(hi), 1)], "max_dlugosc_schodka_px_pion": int(max(rk)), "max_dlugosc_schodka_px_poziom": int(max(rw)),
                                                  "liczba_poziomow_pion": len(rk), "liczba_poziomow_poziom": len(rw), "udzial_dlugich_schodkow_gt_24px_pion": round(sum(x for x in rk if x > 24) / len(kol), 3)}
            if out:
                amp = np.clip((im - lo) / max(hi - lo, 1) * 255 * 3, 0, 255).astype("uint8")
                Image.fromarray(amp).resize((im.shape[1] // (2 if dpr == 3 else 1) // 2, im.shape[0] // (2 if dpr == 3 else 1) // 2)).save(out / f"poswiata_wzmocniona_{w}x{h}.png")
            ctx.close()
        b.close()
    if a.wyj:
        Path(a.wyj).write_text(json.dumps(wyn, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(wyn, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
