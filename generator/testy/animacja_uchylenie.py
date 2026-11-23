"""Klatki uchylenia wieczka po 1,6 s (390x844, DPR 2): przed, szczyt (22 st.), po powrocie."""
from PIL import Image
from playwright.sync_api import sync_playwright
from animacja_lib import *
with sync_playwright() as p:
    for war in ("salon_przyklad_15", "salon_przyklad_26"):
        b, ctx = nowy_kontekst(p, 390, 844, dpr=2)
        s = ctx.new_page(); s.goto(URL + war + "/index.html", wait_until="domcontentloaded")
        s.wait_for_function("document.documentElement.getAttribute('data-animator') === 'gsap'")
        s.wait_for_timeout(300); s.screenshot(path=str(WYJ / "_u0.png"))
        s.wait_for_function("(() => { const m = new DOMMatrix(getComputedStyle(document.querySelector('[data-anim=panel]')).transform); return Math.abs(Math.atan2(m.m23, m.m22) * 180 / Math.PI) > 20.5; })()", timeout=8000)
        s.screenshot(path=str(WYJ / "_u1.png"))
        s.wait_for_timeout(2200); s.screenshot(path=str(WYJ / "_u2.png"))
        ims = [Image.open(WYJ / f"_u{i}.png").convert("RGB") for i in range(3)]
        m = Image.new("RGB", (ims[0].width * 3 + 12, ims[0].height), (60, 60, 60))
        for i, im in enumerate(ims): m.paste(im, (i * (im.width + 6), 0))
        m = m.resize((m.width // 2, m.height // 2), Image.LANCZOS); m.save(WYJ / f"uchylenie_{war}.jpg", quality=88)
        b.close()
for f in WYJ.glob("_u?.png"): f.unlink()
