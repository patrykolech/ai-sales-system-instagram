"""Kolor w OKLCH: przeliczenia, kontrast i lokalny filtr mocnych barw. Bez modeli, 0 USD.

Filtr i reguly palety sa opisane w docs/01-brief.md, sekcje 4 i 6.
"""
from __future__ import annotations

import math

import numpy as np
from PIL import Image, ImageOps

# udzial pikseli w srodkowym kole, powyzej ktorego zdjecie odpada (sekcja 6)
PROG_CZERWIEN = 0.01
PROG_FIOLET = 0.01
PROG_ZIELEN = 0.03


def srgb2lin(c):
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def lin2srgb(c):
    c = np.clip(c, 0, 1)
    return np.where(c <= 0.0031308, 12.92 * c, 1.055 * c ** (1 / 2.4) - 0.055)


def rgb2oklab(rgb: np.ndarray) -> np.ndarray:
    """rgb w zakresie 0-1, ostatnia os to kanaly."""
    lin = srgb2lin(rgb)
    r, g, b = lin[..., 0], lin[..., 1], lin[..., 2]
    l = np.cbrt(0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b)
    m = np.cbrt(0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b)
    s = np.cbrt(0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b)
    return np.stack([0.2104542553 * l + 0.7936177850 * m - 0.0040720468 * s,
                     1.9779984951 * l - 2.4285922050 * m + 0.4505937099 * s,
                     0.0259040371 * l + 0.7827717662 * m - 0.8086757660 * s], -1)


def oklab2rgb(lab: np.ndarray) -> np.ndarray:
    L, a, b = lab[..., 0], lab[..., 1], lab[..., 2]
    l = (L + 0.3963377774 * a + 0.2158037573 * b) ** 3
    m = (L - 0.1055613458 * a - 0.0638541728 * b) ** 3
    s = (L - 0.0894841775 * a - 1.2914855480 * b) ** 3
    return lin2srgb(np.stack([4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s,
                              -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s,
                              -0.0041960863 * l - 0.7034186147 * m + 1.7076147010 * s], -1))


def oklch2hex(L: float, C: float, h: float) -> str:
    a, b = C * math.cos(math.radians(h)), C * math.sin(math.radians(h))
    rgb = oklab2rgb(np.array([L, a, b]))
    return "#%02x%02x%02x" % tuple(int(round(float(v) * 255)) for v in rgb)


def hex2rgb(kolor: str) -> np.ndarray:
    return np.array([int(kolor[i:i + 2], 16) / 255 for i in (1, 3, 5)], dtype=np.float64)


def luminancja(kolor) -> float:
    c = srgb2lin(hex2rgb(kolor) if isinstance(kolor, str) else np.asarray(kolor, dtype=np.float64))
    return float(0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2])


def kontrast(a, b) -> float:
    x, y = sorted((luminancja(a), luminancja(b)), reverse=True)
    return (x + 0.05) / (y + 0.05)


def mocne_barwy(obraz: Image.Image, srodkowe_kolo: bool = True) -> dict:
    """Udzial mocnych barw. Zdjecia z nimi odpadaja, zanim zaplacimy za model."""
    a = np.asarray(ImageOps.fit(obraz.convert("RGB"), (160, 160)), dtype=np.float32) / 255
    if srodkowe_kolo:
        yy, xx = np.mgrid[0:160, 0:160]
        maska = np.hypot(xx - 79.5, yy - 79.5) <= 80
    else:
        maska = np.ones((160, 160), bool)
    lab = rgb2oklab(a)
    c = np.hypot(lab[..., 1], lab[..., 2])
    h = (np.degrees(np.arctan2(lab[..., 2], lab[..., 1])) + 360) % 360
    pole = maska.sum()
    czerwien = float((((c > 0.13) & (h >= 5) & (h < 38)) & maska).sum() / pole)
    fiolet = float((((c > 0.09) & (h >= 285) & (h < 350)) & maska).sum() / pole)
    zielen = float((((c > 0.09) & (h >= 100) & (h < 285)) & maska).sum() / pole)
    return {"czerwien": round(czerwien, 4), "fiolet": round(fiolet, 4), "zielen": round(zielen, 4),
            "odrzuc": czerwien > PROG_CZERWIEN or fiolet > PROG_FIOLET or zielen > PROG_ZIELEN}
