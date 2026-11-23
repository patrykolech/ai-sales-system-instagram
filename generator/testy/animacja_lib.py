"""Wspolne funkcje testow animacji hero (Playwright, headless Chromium). Serwer: python -m http.server 8792 --directory prototyp"""
from __future__ import annotations

from pathlib import Path

from playwright.sync_api import sync_playwright

KAT = Path(__file__).resolve().parent.parent
WYJ = KAT / "testy" / "animacja"
URL = "http://127.0.0.1:8792/"
WARIANTY = ["salon_przyklad_15", "salon_przyklad_15-logo", "salon_przyklad_12", "salon_przyklad_12-logo",
            "salon_przyklad_14", "salon_przyklad_26"]
GLOWNE = ["salon_przyklad_15", "salon_przyklad_26", "salon_przyklad_14"]


def nowy_kontekst(p, w, h, dpr=1.0, dotyk=None, **kw):
    """Chromium headless; dotyk domyslnie dla szerokosci < 700 (telefon)."""
    dotyk = (w < 700) if dotyk is None else dotyk
    przegladarka = p.chromium.launch()
    ctx = przegladarka.new_context(viewport={"width": w, "height": h}, device_scale_factor=dpr,
                                   is_mobile=dotyk, has_touch=dotyk, **kw)
    return przegladarka, ctx


def zbieraj_konsole(strona):
    wpisy = []
    strona.on("console", lambda m: wpisy.append(f"{m.type}: {m.text}") if m.type in ("error", "warning") else None)
    strona.on("pageerror", lambda e: wpisy.append(f"pageerror: {e}"))
    strona.on("response", lambda r: wpisy.append(f"http {r.status} {r.url}") if r.status >= 400 else None)
    return wpisy


def otworz(ctx, wariant, query=""):
    strona = ctx.new_page()
    wpisy = zbieraj_konsole(strona)
    strona.goto(f"{URL}{wariant}/index.html{query}", wait_until="networkidle")
    strona.evaluate("document.fonts.ready")
    return strona, wpisy


ZAKRES = "(() => { const s = ScrollTrigger.getAll()[0]; return {a: s.start, b: s.end}; })()"


def przewin_do(strona, p, czekaj=260):
    """Ustaw przewiniecie na p (0-1) toru sceny i poczekaj na scrub."""
    strona.evaluate("""(p) => { const s = ScrollTrigger.getAll()[0]; window.scrollTo(0, s.start + p * (s.end - s.start)); }""", p)
    strona.evaluate("() => new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)))")
    strona.wait_for_timeout(czekaj)


def postep(strona):
    return strona.evaluate("() => { const s = ScrollTrigger.getAll()[0]; return {sp: s.progress, tl: s.animation.progress(), y: scrollY}; }")
