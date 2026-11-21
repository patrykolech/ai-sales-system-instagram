"""Lokalne skladanie grafik puderniczki: bez kosztu i bez modeli AI.

Prawdziwe zdjecie klientki trafia do lusterka bez zadnej przerobki przez AI,
a nazwa jest nakladana na puste wieczko. Dzieki temu baza grafik powstaje raz,
a kazda klientka kosztuje 0 USD za obrazy.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

FONT_NAZWY = str(Path(__file__).resolve().parent / "baza" / "fonty" / "Belleza-Regular.ttf")
FOLIA = "#6f5c38"  # stala folia: na kazdym lakierze z sekcji 4 ma co najmniej 3,9:1
FOLIA_RGB = tuple(int(FOLIA[i:i + 2], 16) for i in (1, 3, 5))
# Pole na wieczku w ulamkach srednicy pliku (sekcja 5 briefu)
POLE_NAZWY = 0.66
POLE_LOGO = 0.61
# Rozmiar czcionki jako ulamek srednicy pliku. 47 px CSS przy R = 140,4 to 167 px w pliku 1000 px,
# a 24 px CSS to dolna granica folii, bo 3,9:1 wystarcza tylko dla duzego tekstu.
ROZMIAR_MAX = 0.167
ROZMIAR_MIN = 0.0855
# rogi bloku tekstu nie wchodza w pierscien (0,756 promienia pliku) i zostaje oddech
PROMIEN_POLA_TEKSTU = 0.69


def maska_zieleni(img: Image.Image) -> Image.Image:
    """Maska lusterka: piksele kluczowane na czysta zielen z promptu."""
    a = np.asarray(img.convert("RGB")).astype(np.int16)
    r, g, b = a[..., 0], a[..., 1], a[..., 2]
    m = (g > 150) & (g - r > 70) & (g - b > 70)
    maska = Image.fromarray((m * 255).astype(np.uint8), "L")
    # lekko poszerzona, zeby nie zostala zielona obwodka, potem wygladzona
    return maska.filter(ImageFilter.MaxFilter(5)).filter(ImageFilter.GaussianBlur(1.2))


def kadr_kwadratowy(zdjecie: Image.Image, bok: int, obrot: int = 0, fokus=(0.5, 0.5), zoom: float = 1.0) -> Image.Image:
    """Obraca zdjecie o obrot stopni w prawo i wycina kwadrat wokol fokusa.

    fokus podajemy we wspolrzednych oryginalu (0-1), zanim zdjecie zostanie obrocone.
    """
    fx, fy = fokus
    fx, fy = {0: (fx, fy), 90: (1 - fy, fx), 180: (1 - fx, 1 - fy), 270: (fy, 1 - fx)}[obrot]
    im = zdjecie.convert("RGB").rotate(-obrot, expand=True) if obrot else zdjecie.convert("RGB")
    w, h = im.size
    s = min(w, h) / max(zoom, 1.0)
    x = min(max(fx * w - s / 2, 0), w - s)
    y = min(max(fy * h - s / 2, 0), h - s)
    return im.crop((int(x), int(y), int(x + s), int(y + s))).resize((bok, bok), Image.LANCZOS)


def wstaw_do_lustra(puderniczka: Image.Image, zdjecie: Image.Image, odblask: float = 0.10,
                    obrot: int = 0, fokus=(0.5, 0.5), zoom: float = 1.0) -> Image.Image:
    """Wstawia zdjecie w lusterko: kadr, cien krawedzi i delikatny odblask szkla.

    Tylko do plansz probnych. W scenie hero oprawa jest osobna warstwa nad zdjeciem, bo tu efekty zmieniaja jasnosc pracy klientki.
    """
    baza = puderniczka.convert("RGB")
    maska = maska_zieleni(baza)
    x0, y0, x1, y1 = maska.point(lambda v: 255 if v > 128 else 0).getbbox()
    bok = max(x1 - x0, y1 - y0) + 8
    kadr = kadr_kwadratowy(zdjecie, bok, obrot, fokus, zoom)

    warstwa = Image.new("RGB", baza.size)
    warstwa.paste(kadr, (x0 - 4, y0 - 4))

    a = np.asarray(warstwa).astype(np.float32) / 255
    h, w = a.shape[:2]
    mm = np.asarray(maska).astype(np.float32) / 255

    # cien od oprawki: szklo lezy glebiej niz obudowa
    sr = np.asarray(maska.filter(ImageFilter.GaussianBlur(bok * 0.022))).astype(np.float32) / 255
    a *= (0.62 + 0.38 * np.clip((sr - 0.5) * 2, 0, 1))[..., None]

    # ukosny pas odblasku
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    d = ((xx - x0) + (yy - y0) * 0.55) / bok
    pas = np.exp(-((d - 0.42) / 0.10) ** 2) + 0.5 * np.exp(-((d - 0.68) / 0.04) ** 2)
    a = np.clip(a + (pas * odblask)[..., None], 0, 1)

    wynik = np.asarray(baza).astype(np.float32) / 255
    wynik = wynik * (1 - mm[..., None]) + a * mm[..., None]
    return Image.fromarray((wynik * 255).astype(np.uint8), "RGB")


def _uloz_tekst(tekst: str, sciezka_fontu: str, szer_max: int, rozmiar_max: int, promien_pola: float | None = None):
    """Dobiera rozmiar i podzial na linie (najwyzej dwie). Bierze uklad z najwieksza czcionka.

    Przy remisie wybiera dwie linie o podobnej dlugosci, bo jedna dluga linia wyglada na opaske.
    promien_pola pilnuje, zeby rogi bloku tekstu nie wchodzily w pierscien.
    """
    slowa = tekst.split()
    warianty = [[tekst]]
    for i in range(1, len(slowa)):
        warianty.append([" ".join(slowa[:i]), " ".join(slowa[i:])])
    najlepszy = None
    for linie in warianty:
        for rozmiar in range(rozmiar_max, 18, -2):
            font = ImageFont.truetype(sciezka_fontu, rozmiar)
            szer = max(font.getlength(l) for l in linie)
            wys = rozmiar * (1.04 * (len(linie) - 1) + 0.72)
            if szer <= szer_max and (promien_pola is None or np.hypot(szer / 2, wys / 2) <= promien_pola):
                if najlepszy is None or rozmiar > najlepszy[1]:
                    najlepszy = (linie, rozmiar, font)
                break
    return najlepszy


def nazwa_na_wieczko(nazwa: str, nick: str | None, r: int, sciezka_fontu: str = FONT_NAZWY) -> tuple:
    """Kolejno: nazwa w jednej lub dwoch liniach, @nick, inicjaly. Pod 24 px CSS folia jest za slaba."""
    szer = int(2 * r * POLE_NAZWY)
    rozmiar_max, rozmiar_min = int(2 * r * ROZMIAR_MAX), int(2 * r * ROZMIAR_MIN)
    pole = r * PROMIEN_POLA_TEKSTU
    uklad = _uloz_tekst(nazwa, sciezka_fontu, szer, rozmiar_max, pole)
    if uklad and uklad[1] >= rozmiar_min:
        return uklad + ("nazwa",)
    if nick:
        uklad = _uloz_tekst("@" + nick.lstrip("@"), sciezka_fontu, szer, rozmiar_max, pole)
        if uklad and uklad[1] >= rozmiar_min:
            return uklad + ("nick",)
    inicjaly = "".join(s[0] for s in nazwa.split()[:2]).upper() or (nick or "?")[:2].upper()
    return _uloz_tekst(inicjaly, sciezka_fontu, szer, rozmiar_max, pole) + ("inicjaly",)


def graweruj(img: Image.Image, cx: int, cy: int, r: int, tekst: str, sciezka_fontu: str | None = None,
             tryb: str = "folia", kolor=FOLIA_RGB, nick: str | None = None) -> tuple:
    """Naklada nazwe na wieczko. Zwraca obraz i rodzaj napisu: nazwa, nick albo inicjaly."""
    linie, rozmiar, font, rodzaj = nazwa_na_wieczko(tekst, nick, r, sciezka_fontu or FONT_NAZWY)
    maska = Image.new("L", img.size, 0)
    d = ImageDraw.Draw(maska)
    odstep = rozmiar * 1.04
    # srodek liczony z wysokosci wielkiej litery, zeby ogonki i kreski nie przesuwaly nazwy miedzy klientkami
    wys_wielkiej = -font.getbbox("H", anchor="ls")[1]
    linia_bazowa = cy - (odstep * (len(linie) - 1) + wys_wielkiej) / 2 + wys_wielkiej
    for l in linie:
        d.text((cx, linia_bazowa), l, font=font, fill=255, anchor="ms")
        linia_bazowa += odstep
    return tlocz(img, maska, r, tryb, kolor), {"linie": linie, "rozmiar": rozmiar, "rodzaj": rodzaj}


def pierscien(img: Image.Image, cx: int, cy: int, r: int, promien: float, grubosc: float = 3.5) -> Image.Image:
    """Cienki grawerowany pierscien. Daje nazwie oprawe, ale nie udaje znaku."""
    skala = 4
    duza = Image.new("L", (img.width * skala, img.height * skala), 0)
    d = ImageDraw.Draw(duza)
    zew, wew = (promien + grubosc / 2) * skala, (promien - grubosc / 2) * skala
    d.ellipse((cx * skala - zew, cy * skala - zew, cx * skala + zew, cy * skala + zew), fill=255)
    d.ellipse((cx * skala - wew, cy * skala - wew, cx * skala + wew, cy * skala + wew), fill=0)
    return tlocz(img, duza.resize(img.size, Image.LANCZOS), r, "grawer", FOLIA_RGB)


def graweruj_logo(img: Image.Image, cx: int, cy: int, r: int, logo: Image.Image,
                  tryb: str = "folia", kolor=FOLIA_RGB, pole: float = POLE_LOGO) -> Image.Image:
    """To samo tloczenie, ale z przezroczystego logo. Dluzszy bok miesci sie w polu wieczka."""
    alfa = logo.convert("RGBA").getchannel("A")
    pudelko = alfa.point(lambda v: 255 if v > 40 else 0).getbbox()
    alfa = alfa.crop(pudelko)
    bok = 2 * r * pole
    skala = min(bok / alfa.width, bok / alfa.height)
    w, h = int(alfa.width * skala), int(alfa.height * skala)
    alfa = alfa.resize((w, h), Image.LANCZOS)
    maska = Image.new("L", img.size, 0)
    maska.paste(alfa, (cx - w // 2, cy - h // 2))
    return tlocz(img, maska, r, tryb, kolor)


def tlocz(img: Image.Image, maska: Image.Image, r: int, tryb: str, kolor) -> Image.Image:
    baza = img.convert("RGB")
    a = np.asarray(baza).astype(np.float32) / 255
    m = np.asarray(maska.filter(ImageFilter.GaussianBlur(0.5))).astype(np.float32) / 255
    lum = np.clip(a.mean(axis=2, keepdims=True) / max(a.mean(), 1e-3), 0.7, 1.3)

    def przesun(dx, dy, blur):
        return np.asarray(ImageChops_offset(maska, dx, dy).filter(ImageFilter.GaussianBlur(blur))).astype(np.float32) / 255

    if tryb == "folia":
        cien = przesun(1, 2, 1.4)
        a *= (1 - 0.45 * cien)[..., None]
        h, w = a.shape[:2]
        yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
        fala = 0.90 + 0.14 * np.sin((xx + yy * 0.6) / (r * 0.16))
        folia = np.array(kolor, dtype=np.float32) / 255 * fala[..., None] * lum
        a = a * (1 - m[..., None]) + np.clip(folia, 0, 1) * m[..., None]
    else:
        ciemny = przesun(0, 0, 0.4)
        a *= (1 - 0.46 * ciemny)[..., None]
        wewn = np.clip(przesun(-1, -2, 1.2) - 0.0, 0, 1) * m
        a *= (1 - 0.22 * wewn)[..., None]
        krawedz = np.clip(przesun(1, 2, 0.8) - m, 0, 1)
        a = np.clip(a + (0.42 * krawedz)[..., None], 0, 1)
    return Image.fromarray((np.clip(a, 0, 1) * 255).astype(np.uint8), "RGB")


def ImageChops_offset(maska: Image.Image, dx: int, dy: int) -> Image.Image:
    return ImageChops.offset(maska, dx, dy)
