"""Szybki test dymny: ladowanie, konsola, tryb animatora, kilka klatek 390x844 jednego wariantu."""
import sys

from playwright.sync_api import sync_playwright

from animacja_lib import *

wariant = sys.argv[1] if len(sys.argv) > 1 else "salon_przyklad_15"
WYJ.mkdir(exist_ok=True)
with sync_playwright() as p:
    przegladarka, ctx = nowy_kontekst(p, 390, 844, dpr=1)
    strona, wpisy = otworz(ctx, wariant)
    print("animator:", strona.evaluate("document.documentElement.getAttribute('data-animator')"),
          "| js:", strona.evaluate("document.documentElement.classList.contains('js')"))
    print("zakres:", strona.evaluate(ZAKRES))
    for pr in (0, 0.04, 0.1, 0.18, 0.25, 0.3, 0.4, 0.55, 0.7, 0.85, 1.0):
        przewin_do(strona, pr)
        strona.screenshot(path=str(WYJ / f"_smoke_{wariant}_{int(pr*100):03d}.png"))
        print(pr, postep(strona))
    print("konsola:", wpisy)
    przegladarka.close()
