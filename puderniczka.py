#!/usr/bin/env python3
"""Warstwy puderniczki: baza wspolna dla wszystkich i wersja pod konkretna klientke.

    python puderniczka.py baza
    python puderniczka.py paleta salon_przyklad_15 salon_przyklad_12
    python puderniczka.py klientka salon_przyklad_15 --nazwa "Salon Przyklad"
    python puderniczka.py klientka salon_przyklad_15 --nazwa "Salon Przyklad" --logo logo/salon_przyklad-monogram/logo-czarne.png

Baza powstaje raz z dwoch obrazow AI. Klientka to 0 USD: lokalny kolor z jej feedu i grawer.
Domyslnie na wieczku jest sama nazwa. Logo tylko z parametrem --logo (decyzja wlasciciela, sekcja 16 briefu).
"""
from __future__ import annotations

import argparse
import glob
import io
import json
import math
import os
import random
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageOps

from kolor import kontrast, oklch2hex, rgb2oklab
from skladanie import FOLIA, graweruj, graweruj_logo, maska_zieleni, pierscien

KATALOG = Path(__file__).resolve().parent
OBRAZY = KATALOG / "obrazy"
BAZA = KATALOG / "baza"
DANE = Path(os.environ.get("BSF_DATA", str(Path(__file__).resolve().parent / "dane")))
BOK = 1000
PROMIEN_LAKIERU = 0.945  # do tego promienia siega lakier, dalej jest zloty rant
PROMIEN_PIERSCIENIA = 0.80 * PROMIEN_LAKIERU  # 80% lakieru, sekcja 5 briefu
METAL = "#c8b48c"
METAL_CIEN = "#7a6844"
# budzety warstw w KB, sekcja 14 briefu
BUDZET = {"wieczko": 50, "rama": 60, "podstawa": 75, "zawias": 8}
# polysk mnozy roznice jasnosci wzgledem sredniego lakieru: ciemniejszy lakier przy tym samym odblasku wyglada plasko
POLYSK = 1.35


def _pierwszy_plan(obraz: Image.Image) -> np.ndarray:
    """Tlo jest jednolite: rant rozni sie od niego wyraznie, a srodek wypelniamy po konturze."""
    a = np.asarray(obraz.convert("RGB")).astype(np.float32)
    rogi = np.concatenate([a[:24, :24], a[:24, -24:], a[-24:, :24], a[-24:, -24:]]).reshape(-1, 3)
    roznica = np.linalg.norm(a - np.median(rogi, axis=0), axis=2)
    surowa = cv2.morphologyEx((roznica > 22).astype(np.uint8), cv2.MORPH_CLOSE, np.ones((9, 9), np.uint8))
    kontury, _ = cv2.findContours(surowa, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    plan = np.zeros(surowa.shape, np.uint8)
    pole_min = surowa.size * 0.002
    cv2.drawContours(plan, [k for k in kontury if cv2.contourArea(k) > pole_min], -1, 1, cv2.FILLED)
    return plan.astype(bool)


def _kolo_alfa() -> Image.Image:
    skala = 3
    duza = Image.new("L", (BOK * skala, BOK * skala), 0)
    ImageDraw.Draw(duza).ellipse((6, 6, BOK * skala - 6, BOK * skala - 6), fill=255)
    return duza.resize((BOK, BOK), Image.LANCZOS)


def _wytnij_kolo(obraz: Image.Image, plan: np.ndarray, y0: int, y1: int) -> tuple[Image.Image, tuple]:
    wiersze = plan[y0:y1]
    szer = wiersze.sum(axis=1)
    # cieciwa 0.34 srednicy odcina zawias. Do szczytu kola brakuje wtedy 0.0595 promienia.
    pelne = np.where(szer > szer.max() * 0.34)[0] + y0
    gora, dol = int(pelne.min()), int(pelne.max())
    kolumny = np.where(plan[gora:dol].any(axis=0))[0]
    lewo, prawo = int(kolumny.min()), int(kolumny.max())
    brak = int(round((prawo - lewo) / 2 * 0.0595))
    gora -= brak
    # dol liczymy ze srednicy, bo pod przedmiotem lezy cien, ktory maska bierze za krawedz
    pudelko = (lewo, gora, prawo + 1, gora + prawo - lewo + 1)
    return obraz.convert("RGB").crop(pudelko).resize((BOK, BOK), Image.LANCZOS), pudelko


def _alfa_walca(szer: int, wys: int, promien: int = 5) -> Image.Image:
    skala = 4
    duza = Image.new("L", (szer * skala, wys * skala), 0)
    ImageDraw.Draw(duza).rounded_rectangle((0, 0, szer * skala - 1, wys * skala - 1), promien * skala, fill=255)
    return duza.resize((szer, wys), Image.LANCZOS)


def _okrag_wkladu(obraz: Image.Image) -> dict:
    """Wklad nie lezy idealnie na srodku warstwy. Barwienie musi konczyc sie na jego krawedzi, a nie na kole wokol srodka."""
    a = np.asarray(obraz.convert("RGB")).astype(np.float32)
    jasnosc, cieplo = a.mean(axis=2), a[..., 0] - a[..., 2]
    n = a.shape[0]
    punkty = []
    for kat in np.radians(np.arange(0, 360, 1.5)):
        rr = np.arange(0.80, 0.945, 0.5 / (n / 2))
        xs, ys = (n / 2 + np.cos(kat) * rr * n / 2).astype(int), (n / 2 + np.sin(kat) * rr * n / 2).astype(int)
        jadro = [1, 1, 0, -1, -1]
        g = np.abs(np.convolve(jasnosc[ys, xs], jadro, "same")) + np.abs(np.convolve(cieplo[ys, xs], jadro, "same"))
        g[:3], g[-3:] = 0, 0
        i = int(np.argmax(g))
        if g[i] > 12:
            punkty.append((xs[i], ys[i]))
    p = np.array(punkty, dtype=np.float64)
    for _ in range(6):
        s = np.linalg.lstsq(np.c_[2 * p[:, 0], 2 * p[:, 1], np.ones(len(p))], (p ** 2).sum(1), rcond=None)[0]
        cx, cy = s[0], s[1]
        r = math.sqrt(s[2] + cx ** 2 + cy ** 2)
        blad = np.abs(np.hypot(p[:, 0] - cx, p[:, 1] - cy) - r)
        p = p[blad <= max(2.5, np.percentile(blad, 70))]
    return {"srodek": [round(cx / n, 4), round(cy / n, 4)], "promien": round(r / (n / 2), 4)}


def zapisz_webp(obraz: Image.Image, sciezka: Path, budzet_kb: float, q_start: int = 88, q_min: int = 58, alfa_q: int = 90) -> dict:
    """Najwyzsza jakosc mieszczaca sie w budzecie. Rozmiar zmniejsza dopiero, gdy nawet q_min nie wystarcza."""
    im, bok = obraz, obraz.width
    while True:
        for q in range(q_start, q_min - 1, -2):
            b = io.BytesIO()
            im.save(b, "WEBP", quality=q, method=6, alpha_quality=alfa_q, exact=False)
            if b.tell() <= budzet_kb * 1024:
                sciezka.write_bytes(b.getvalue())
                return {"plik": sciezka.name, "q": q, "bok": im.width, "kb": round(b.tell() / 1024, 1), "budzet_kb": budzet_kb}
        bok = int(bok * 0.94)
        if bok < obraz.width * 0.7:
            raise ValueError(f"{sciezka.name}: nie miesci sie w {budzet_kb} KB nawet po zmniejszeniu")
        im = obraz.resize((bok, int(obraz.height * bok / obraz.width)), Image.LANCZOS)


def baza() -> None:
    BAZA.mkdir(exist_ok=True)
    kolo = _kolo_alfa()

    zamknieta = Image.open(OBRAZY / "E1_perla_zamknieta.png")
    plan = _pierwszy_plan(zamknieta)
    wieczko, pudelko_w = _wytnij_kolo(zamknieta, plan, 0, zamknieta.height)
    wieczko.putalpha(kolo)
    wieczko.save(BAZA / "wieczko.png")
    # zamkniete wieczko ma wlasny zawias na gorze: czysciej wyciac go stad niz z otwartej wersji
    wiersze_z = np.where(plan[:pudelko_w[1] + 12].any(axis=1))[0]
    zy0, zy1 = int(wiersze_z.min()), pudelko_w[1] + 12
    kolumny_z = np.where(plan[zy0:pudelko_w[1] - 2].any(axis=0))[0]
    zx0, zx1 = int(kolumny_z.min()), int(kolumny_z.max()) + 1
    zawias_z = zamknieta.convert("RGB").crop((zx0, zy0, zx1, zy1))
    alfa_z = (plan[zy0:zy1, zx0:zx1] * 255).astype(np.uint8)
    alfa_z[:3] = 0  # gorny wiersz to strzepki tla
    jasnosc = np.asarray(zawias_z.convert("L")).astype(np.float32)
    # szczeliny miedzy walcami: jasne tlo u gory szczeliny ma przepuszczac kolor sceny
    wiersze_srodka = jasnosc[20:36]
    szczeliny = np.where(wiersze_srodka.mean(axis=0) < 120)[0]
    for x in szczeliny:
        alfa_z[:16, max(x - 1, 0):x + 2] = 0
    zawias_z.putalpha(Image.fromarray(alfa_z, "L").filter(ImageFilter.GaussianBlur(0.5)))
    zawias_z.save(BAZA / "zawias-zamkniety.png")
    zapisz_webp(zawias_z, BAZA / "zawias-zamkniety.webp", BUDZET["zawias"], q_start=90)
    srednica_w = pudelko_w[2] - pudelko_w[0]
    zawias_zamkniety = {"szer": round((zx1 - zx0) / srednica_w, 4), "wys": round((zy1 - zy0) / srednica_w, 4),
                        "nachodzi": round(12 / srednica_w, 4)}

    otwarta = Image.open(OBRAZY / "E2_perla_otwarta.png")
    plan = _pierwszy_plan(otwarta)
    szer = plan.sum(axis=1).astype(np.float32)
    srodek = otwarta.height // 2
    okno = np.arange(srodek - 120, srodek + 120)
    szyja = int(okno[np.argmin(szer[okno])])

    gora, pudelko_g = _wytnij_kolo(otwarta, plan, 0, szyja)
    dol, pudelko_d = _wytnij_kolo(otwarta, plan, szyja, otwarta.height)

    zielen = maska_zieleni(gora)
    otwor = np.asarray(zielen.point(lambda v: 255 if v > 128 else 0))
    ys, xs = np.where(otwor > 0)
    promien_otworu = float((xs.max() - xs.min() + ys.max() - ys.min()) / 4 / (BOK / 2))
    srodek_otworu = (float((xs.max() + xs.min()) / 2 / BOK), float((ys.max() + ys.min()) / 2 / BOK))

    # rama lusterka to sam pierscien: zdjecie lezy pod spodem jako osobna warstwa
    alfa = Image.fromarray(np.minimum(np.asarray(kolo), 255 - np.asarray(zielen)).astype(np.uint8), "L")
    rama = gora.copy()
    rama.putalpha(alfa)
    rama.save(BAZA / "rama-lusterka.png")
    dol.putalpha(kolo)
    dol.save(BAZA / "podstawa.png")
    wklady = {"puder": _okrag_wkladu(dol)}
    # wymienne wklady: ta sama puderniczka, inna zawartosc podstawy zaleznie od uslugi
    for typ in ("brwi", "rzesy", "paznokcie"):
        plik = OBRAZY / f"E3_wklad_{typ}.png"
        if not plik.exists():
            continue
        wariant = Image.open(plik)
        plan_w = _pierwszy_plan(wariant)
        szer_w = plan_w.sum(axis=1).astype(np.float32)
        okno_w = np.arange(wariant.height // 2 - 120, wariant.height // 2 + 120)
        szyja_w = int(okno_w[np.argmin(szer_w[okno_w])])
        podstawa_w, _ = _wytnij_kolo(wariant, plan_w, szyja_w, wariant.height)
        podstawa_w.putalpha(kolo)
        podstawa_w.save(BAZA / f"podstawa-{typ}.png")
        wklady[typ] = _okrag_wkladu(podstawa_w)

    # zawias to walec w szyi miedzy kolami: szukamy go po metalu, a nie po bialej ramie
    a = np.asarray(otwarta.convert("RGB")).astype(np.float32)
    srodek_x = (pudelko_g[0] + pudelko_g[2]) // 2
    metal = (a[..., 2] < 200) & (a[..., 0] - a[..., 2] > 12) & plan
    y_s = np.where(metal[:, srodek_x - 4:srodek_x + 4].any(axis=1))[0]
    y_s = y_s[(y_s > szyja - 70) & (y_s < szyja + 70)]
    y0, y1 = int(y_s.min()) - 1, int(y_s.max()) + 2
    x_s = np.where(metal[szyja - 4:szyja + 4].any(axis=0))[0]
    x0, x1 = int(x_s.min()) - 1, int(x_s.max()) + 2
    # W tym wycinku obok walca leza rama, zielone lusterko i puder. Na zabarwionym lakierze bylyby widoczna
    # plama, wiec zostaje sam walec. Wiersze i kolumny zmierzone na E2_perla_otwarta.png.
    x0, x1 = x0 + 2, x1 - 2
    y0, y1 = y0 + 25, y0 + 62
    zawias = otwarta.convert("RGB").crop((x0, y0, x1, y1))
    zawias.putalpha(_alfa_walca(x1 - x0, y1 - y0))
    zawias.save(BAZA / "zawias.png")
    zapisz_webp(zawias, BAZA / "zawias.webp", BUDZET["zawias"], q_start=90)

    srednica = pudelko_g[2] - pudelko_g[0]
    uklad = {"promien_otworu": round(promien_otworu, 4), "srodek_otworu": [round(v, 4) for v in srodek_otworu],
             "promien_lakieru": PROMIEN_LAKIERU, "zawias_szer": round((x1 - x0) / srednica, 4),
             "zawias_wys": round((y1 - y0) / srednica, 4), "zawias_zamkniety": zawias_zamkniety, "wklady": wklady}
    (BAZA / "uklad.json").write_text(json.dumps(uklad, indent=2), encoding="utf-8")
    print("baza gotowa:", uklad)


# rodzina: nasycenie tla, nasycenie i jasnosc lakieru, opcjonalnie staly odcien lakieru (sekcja 4 briefu)
RODZINY = {
    "grafit": {"c_tla": 0.008, "c_lakieru": 0.010, "l_lakieru": 0.875, "h_lakieru": 80.0},
    "popiel": {"c_tla": 0.016, "c_lakieru": 0.028, "l_lakieru": 0.84},
    "kamien": {"c_tla": 0.012, "c_lakieru": 0.016, "l_lakieru": 0.85},
    # Decyzja wlasciciela po obejrzeniu szesciu rodzin: niebieski, mietowy i turkusowy lakier wygladaja jak plastikowa zabawka.
    # Te trzy rodziny maja lakier neutralny, a kolor z feedu idzie tylko na tlo i puder. Odstepstwo od sekcji 4: docs/03-media.md.
    "stal": {"c_tla": 0.028, "c_lakieru": 0.010, "l_lakieru": 0.875, "h_lakieru": 80.0, "c_pudru": 0.030},  # perla
    "szalwia": {"c_tla": 0.026, "c_lakieru": 0.016, "l_lakieru": 0.85, "h_lakieru": 90.0, "c_pudru": 0.034},  # kamien
    "morska": {"c_tla": 0.024, "c_lakieru": 0.010, "l_lakieru": 0.875, "h_lakieru": 80.0, "c_pudru": 0.030},  # perla
}
PROG_RODZINY = {"szalwia": 0.05, "morska": 0.05, "stal": 0.05, "popiel": 0.08}  # popiel lapie skore w cieniu
BOK_MINI = 48
_yy, _xx = np.mgrid[0:BOK_MINI, 0:BOK_MINI]
_D_MINI = np.hypot((_xx - BOK_MINI / 2 + 0.5) / (BOK_MINI / 2), (_yy - BOK_MINI / 2 + 0.5) / (BOK_MINI / 2))
PIERSCIEN_TLA = _D_MINI > 0.72  # poza 72% promienia jest tlo, a nie twarz
KOLO_OKLADKI = _D_MINI < 0.95


def _miniatura(sciezka: str) -> np.ndarray:
    im = Image.open(sciezka)
    im.draft("RGB", (96, 96))
    return np.asarray(ImageOps.fit(im.convert("RGB"), (BOK_MINI, BOK_MINI)), dtype=np.float32) / 255


def _zbierz_piksele(nick: str) -> tuple:
    """Do 30 losowych postow (ziarno = nick), tylko pierscien tla, oraz do 12 okladek w calym kole."""
    posty = sorted(glob.glob(str(DANE / nick / "post-*.jpg")))
    random.Random(nick).shuffle(posty)
    tla, okladki = [], []
    for sciezka in posty[:30]:
        try:
            tla.append(_miniatura(sciezka)[PIERSCIEN_TLA])
        except OSError:
            continue
    for sciezka in sorted(glob.glob(str(DANE / nick / "covers" / "cover-*.jpg")))[:12]:
        try:
            okladki.append(_miniatura(sciezka)[KOLO_OKLADKI])
        except OSError:
            continue
    return (np.concatenate(tla) if tla else None), (np.concatenate(okladki) if okladki else None)


def _analiza(piksele: np.ndarray) -> dict:
    lab = rgb2oklab(piksele)
    l, a, b = lab[..., 0], lab[..., 1], lab[..., 2]
    c = np.hypot(a, b)
    h = (np.degrees(np.arctan2(b, a)) + 360) % 360
    uzyteczne = (l > 0.18) & (l < 0.97)
    skora = uzyteczne & (h >= 25) & (h < 95) & (c >= 0.03)
    krzykliwe = uzyteczne & (c > 0.13)
    neutralne = uzyteczne & (c < 0.018) & ~krzykliwe
    glosujace = uzyteczne & ~skora & ~krzykliwe & ~neutralne
    return {"a": a, "b": b, "c": c, "h": h, "neutralne": neutralne, "glosujace": glosujace,
            "pole": max(int(uzyteczne.sum()), 1), "skora": skora}


def _glosy(analiza: dict) -> tuple:
    """Udzial rodzin w uzytecznych pikselach i ich odcien: srednia kolowa wazona nasyceniem."""
    h, c = analiza["h"], analiza["c"]
    # wrzos glosuje na stal tylko jako chlodna szarosc sciany. Mocny fiolet nie glosuje.
    zakresy = {"szalwia": (h >= 95) & (h < 175), "morska": (h >= 175) & (h < 235),
               "stal": ((h >= 235) & (h < 285)) | ((h >= 285) & (h < 335) & (c <= 0.05)),
               "popiel": (h >= 335) | (h < 25)}
    udzialy, odcienie = {}, {}
    for rodzina, zakres in zakresy.items():
        wybrane = analiza["glosujace"] & zakres
        udzialy[rodzina] = float(wybrane.sum() / analiza["pole"])
        if wybrane.any():
            radiany, waga = np.radians(h[wybrane]), c[wybrane]
            odcienie[rodzina] = math.degrees(math.atan2((np.sin(radiany) * waga).sum(), (np.cos(radiany) * waga).sum())) % 360
    return udzialy, odcienie


def _zacisnij_odcien(rodzina: str, h: float) -> float:
    """Poza tymi zakresami stal jest juz lawenda, popiel magenta albo braz, a kamien brazem."""
    if rodzina == "stal":
        return min(max(h, 235.0), 258.0)
    if rodzina == "popiel":
        return max(h, 352.0) if h >= 335 else min(h, 8.0)
    if rodzina == "kamien":
        return min(max(h, 72.0), 100.0)
    if rodzina == "grafit":
        return 250.0
    return h


def tokeny(rodzina: str, h: float) -> dict:
    """Jasnosc jest stala, a nasycenie z tabeli, wiec kontrast jest gwarantowany konstrukcyjnie."""
    r = RODZINY[rodzina]
    c, cl = r["c_tla"], r["c_lakieru"]
    hl = r.get("h_lakieru", h)
    # puder idzie za lakierem, chyba ze rodzina ma neutralny lakier: wtedy niesie odcien z feedu
    puder = oklch2hex(0.945, 0.42 * r["c_pudru"], h) if "c_pudru" in r else oklch2hex(0.945, 0.42 * cl, hl)
    return {
        "--tlo": oklch2hex(0.285, c, h), "--tlo-jasne": oklch2hex(0.40, 1.1 * c, h), "--tlo-ciemne": oklch2hex(0.215, c, h),
        "--lakier": oklch2hex(r["l_lakieru"], cl, hl), "--puder": puder,
        "--atrament": oklch2hex(0.26, c, h), "--szept": oklch2hex(0.47, c, h), "--szept-jasny": oklch2hex(0.82, 0.8 * c, h),
        "--jasny": oklch2hex(0.965, 0.25 * cl, hl), "--metal": METAL, "--metal-cien": METAL_CIEN, "--folia": FOLIA,
    }


def kontrasty(t: dict) -> dict:
    pary = {"jasny/tlo": ("--jasny", "--tlo"), "jasny/tlo-jasne": ("--jasny", "--tlo-jasne"), "szept-jasny/tlo": ("--szept-jasny", "--tlo"),
            "atrament/puder": ("--atrament", "--puder"), "szept/puder": ("--szept", "--puder"), "atrament/lakier": ("--atrament", "--lakier"),
            "lakier/tlo": ("--lakier", "--tlo"), "metal/tlo": ("--metal", "--tlo"), "metal-cien/puder": ("--metal-cien", "--puder"),
            "folia/lakier": ("--folia", "--lakier")}
    return {nazwa: round(kontrast(t[a], t[b]), 2) for nazwa, (a, b) in pary.items()}


def paleta_rodziny(rodzina: str, h: float, zrodlo: str = "wzorzec") -> dict:
    t = tokeny(rodzina, h)
    return {"rodzina": rodzina, "odcien": h, "odcien_lakieru": RODZINY[rodzina].get("h_lakieru", h), "zrodlo": zrodlo,
            "tokeny": t, "kontrast": kontrasty(t)}


def kolor_z_feedu(nick: str) -> dict:
    """Rodzina i tokeny z tla zdjec i okladek, nie ze skory. Regula: sekcja 4 briefu."""
    tla, okladki = _zbierz_piksele(nick)
    if tla is None:
        raise ValueError("brak zdjec: " + nick)
    analiza = _analiza(tla)
    glosy_tla, odcienie_tla = _glosy(analiza)
    glosy_okl, odcienie_okl = _glosy(_analiza(okladki)) if okladki is not None and len(okladki) > 200 else ({}, {})
    # okladki maja rowna wage, bo to kolor wybrany przez nia, a nie sciana w gabinecie
    razem = {k: glosy_tla.get(k, 0.0) + glosy_okl.get(k, 0.0) for k in glosy_tla}
    ranking = sorted(razem.items(), key=lambda p: -p[1])
    pierwsza, udzial = ranking[0]
    if udzial >= PROG_RODZINY[pierwsza] and udzial >= ranking[1][1] * 1.25:
        rodzina = pierwsza
        z_okladek = glosy_okl.get(rodzina, 0.0) > glosy_tla.get(rodzina, 0.0)
        h = (odcienie_okl if z_okladek else odcienie_tla).get(rodzina)
        if h is None:
            h = odcienie_tla.get(rodzina, odcienie_okl.get(rodzina))
        zrodlo = "okladki" if z_okladek else "tla_zdjec"
    else:
        neutralne = analiza["neutralne"]
        sr_b = float(analiza["b"][neutralne].mean()) if neutralne.any() else 0.004
        sr_a = float(analiza["a"][neutralne].mean()) if neutralne.any() else 0.0
        rodzina = "kamien" if sr_b > 0.0035 else "grafit"
        h = math.degrees(math.atan2(sr_b, sr_a)) % 360
        zrodlo = "neutralne"
    surowy = h
    h = round(_zacisnij_odcien(rodzina, h), 1)
    wynik = paleta_rodziny(rodzina, h, zrodlo)
    wynik.update({"odcien_surowy": round(surowy, 1), "udzialy": {k: round(v, 4) for k, v in razem.items()},
                  "udzial_neutralnych": round(float(analiza["neutralne"].sum() / analiza["pole"]), 3),
                  "udzial_skory": round(float(analiza["skora"].sum() / analiza["pole"]), 3)})
    return wynik


def zabarw(warstwa: Image.Image, kolor: str, promien: float, wewnetrzny: float = 0.0, polysk: float = POLYSK,
           srodek_wew: tuple = (0.5, 0.5)) -> Image.Image:
    """Mnozy lakier przez kolor: odblaski zostaja, a zloty rant, puder i otwor sa nietkniete.

    Na dole baza ma blady polksiezyc poza promieniem lakieru. Na perle go nie widac, ale na stali i szalwii
    bylby biala kreska, wiec blade piksele rantu tez dostaja kolor. Zloto poznajemy po roznicy czerwieni i blekitu.
    """
    r, g, b = (int(kolor[i:i + 2], 16) / 255 for i in (1, 3, 5))
    a = np.asarray(warstwa).astype(np.float32) / 255
    wys, szer = a.shape[:2]
    yy, xx = np.mgrid[0:wys, 0:szer].astype(np.float32)
    d = np.hypot(xx - szer / 2, yy - wys / 2) / (szer / 2)
    d_wew = np.hypot(xx - szer * srodek_wew[0], yy - wys * srodek_wew[1]) / (szer / 2)
    wnetrze = np.clip((promien - d) / 0.006, 0, 1) * np.clip((d_wew - wewnetrzny) / 0.006, 0, 1)
    odniesienie = np.median(a[..., :3][(wnetrze > 0.99) & (a[..., 3] > 0.99)], axis=0)
    zlotosc = np.clip(((a[..., 0] - a[..., 2]) - 0.05) / 0.10, 0, 1)
    rant = np.clip((d - promien) / 0.006, 0, 1) * (1 - zlotosc)
    maska = np.clip(wnetrze + rant, 0, 1)
    wzgledny = a[..., :3] / odniesienie
    nowy = (1 + (wzgledny - 1) * polysk) * np.array([r, g, b])
    a[..., :3] = a[..., :3] * (1 - maska[..., None]) + np.clip(nowy, 0, 1) * maska[..., None]
    return Image.fromarray((a * 255 + 0.5).astype(np.uint8), "RGBA")


def _logo_okragle(logo: Image.Image) -> bool:
    """Czy logo samo ma okragla oprawe: wtedy pierscien wieczka bylby drugi, wiec odpada."""
    alfa = np.asarray(logo.convert("RGBA").getchannel("A"))
    kontury, _ = cv2.findContours((alfa > 60).astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not kontury:
        return False
    k = max(kontury, key=cv2.contourArea)
    pole, obwod = cv2.contourArea(k), cv2.arcLength(k, True)
    return obwod > 0 and pole > alfa.size * 0.2 and 4 * math.pi * pole / obwod ** 2 > 0.8


def _wieczko(baza_lakieru: Image.Image, nazwa: str, nick: str | None, sciezka_logo: str | None) -> tuple:
    alfa = baza_lakieru.getchannel("A")
    rgb = baza_lakieru.convert("RGB")
    srodek = BOK // 2
    opis = {}
    if sciezka_logo:
        logo = Image.open(sciezka_logo)
        if logo.width < 400:
            raise ValueError("logo ponizej 400 px szerokosci: " + sciezka_logo)
        okragle = _logo_okragle(logo)
        if not okragle:
            rgb = pierscien(rgb, srodek, srodek, srodek, PROMIEN_PIERSCIENIA * srodek)
        wynik = graweruj_logo(rgb, srodek, srodek, srodek, logo)
        opis = {"rodzaj": "logo", "logo": str(Path(sciezka_logo).relative_to(KATALOG)).replace("\\", "/"), "pierscien": not okragle}
    else:
        rgb = pierscien(rgb, srodek, srodek, srodek, PROMIEN_PIERSCIENIA * srodek)
        wynik, opis = graweruj(rgb, srodek, srodek, srodek, nazwa, nick=nick)
        opis["pierscien"] = True
    wynik.putalpha(alfa)
    return wynik, opis


def wklad_dla(typ: str) -> str:
    return {"brwi": "brwi", "pmu": "brwi", "rzesy": "rzesy", "paznokcie": "paznokcie"}.get(typ, "")


def warstwy(paleta: dict, wyjscie: Path, nazwa: str, nick: str | None, typ: str = "", sciezka_logo: str | None = None) -> dict:
    """Barwione warstwy jednej palety. Wspolne dla klientki i dla plansz kontrolnych rodzin."""
    wyjscie.mkdir(parents=True, exist_ok=True)
    lakier = paleta["tokeny"]["--lakier"]
    baza_lakieru = zabarw(Image.open(BAZA / "wieczko.png"), lakier, PROMIEN_LAKIERU)
    uklad = json.loads((BAZA / "uklad.json").read_text(encoding="utf-8"))
    wieczko, opis = _wieczko(baza_lakieru, nazwa, nick, None)
    pliki = {"wieczko": zapisz_webp(wieczko, wyjscie / "wieczko.webp", BUDZET["wieczko"])}
    opisy = {"wieczko": opis}
    if sciezka_logo:
        wieczko_l, opis_l = _wieczko(baza_lakieru, nazwa, nick, sciezka_logo)
        pliki["wieczko-logo"] = zapisz_webp(wieczko_l, wyjscie / "wieczko-logo.webp", BUDZET["wieczko"])
        opisy["wieczko-logo"] = opis_l
    rama = zabarw(Image.open(BAZA / "rama-lusterka.png"), lakier, PROMIEN_LAKIERU, uklad["promien_otworu"] + 0.004,
                  srodek_wew=tuple(uklad["srodek_otworu"]))
    pliki["rama"] = zapisz_webp(rama, wyjscie / "rama-lusterka.webp", BUDZET["rama"])
    wklad = wklad_dla(typ)
    plik_podstawy = BAZA / f"podstawa-{wklad}.png" if wklad else BAZA / "podstawa.png"
    okrag = uklad["wklady"][wklad or "puder"]
    podstawa = zabarw(Image.open(plik_podstawy), lakier, PROMIEN_LAKIERU, okrag["promien"] + 0.004, srodek_wew=tuple(okrag["srodek"]))
    pliki["podstawa"] = zapisz_webp(podstawa, wyjscie / "podstawa.webp", BUDZET["podstawa"])
    for nazwa_zawiasu in ("zawias", "zawias-zamkniety"):
        cel = wyjscie / f"{nazwa_zawiasu}.webp"
        cel.write_bytes((BAZA / f"{nazwa_zawiasu}.webp").read_bytes())
        pliki[nazwa_zawiasu] = {"plik": cel.name, "kb": round(cel.stat().st_size / 1024, 1), "budzet_kb": BUDZET["zawias"]}
    return {"pliki": pliki, "wieczka": opisy, "wklad": wklad or "puder", "plik_wkladu": plik_podstawy.name, "uklad": uklad}


def _oklch_hex(x: str) -> tuple[float, float, float]:
    lab = rgb2oklab(np.array([int(x[i:i + 2], 16) / 255 for i in (1, 3, 5)], dtype=np.float64)[None, :])[0]
    return float(lab[0]), float(math.hypot(lab[1], lab[2])), (math.degrees(math.atan2(lab[2], lab[1])) + 360) % 360


def lakier_z_palety(kolory: dict) -> tuple[str, str]:
    """Lakier wieczka z palety strony (paleta_beauty): odcien w polowie drogi miedzy papier2 a akcentem, nasycenie papieru2,
    stala jasnosc 0,85. Chlodne odcienie (zielen, blekit, fiolet) daja perle, bo kolorowy lakier wyglada jak plastik
    (decyzja wlasciciela przy rodzinach stal/szalwia/morska). Zwraca (hex, opis)."""
    L2, C2, h2 = _oklch_hex(kolory["papier2"])
    ha = _oklch_hex(kolory["akcent"])[2]
    d = ((ha - h2 + 180) % 360) - 180
    h = (h2 + 0.5 * d) % 360
    if not (h >= 330 or h <= 100):
        return oklch2hex(0.875, 0.010, 80.0), "perla (chlodna paleta)"
    return oklch2hex(0.85, min(max(C2, 0.018), 0.034), h), f"papier2 h{h2:.0f} + akcent h{ha:.0f}"


def dostroj_do_palety(nick: str, nazwa: str | None = None, wymus: bool = False) -> dict | None:
    """Barwi wieczko, rame i podstawe klientki na lakier z palety strony (hero/<nick>/paleta_strony.json), bez AI.
    Wynik zapamietany w warstwy/paleta.json ("dostrojone"), wiec ponowna budowa niczego nie liczy. Brak palety strony = None."""
    folder = KATALOG / "hero" / nick
    plik_strony, plik_palety, plik_opisu = folder / "paleta_strony.json", folder / "warstwy" / "paleta.json", folder / "warstwy" / "warstwy.json"
    if not (plik_strony.exists() and plik_palety.exists() and plik_opisu.exists()):
        return None
    strona = json.loads(plik_strony.read_text(encoding="utf-8"))
    paleta = json.loads(plik_palety.read_text(encoding="utf-8"))
    lakier, skad = lakier_z_palety(strona["kolory"])
    znacznik = {"rodzina": strona["rodzina"], "lakier": lakier}
    if not wymus and paleta.get("dostrojone") == znacznik:
        return paleta
    opis = json.loads(plik_opisu.read_text(encoding="utf-8"))
    linie = (opis.get("wieczka", {}).get("wieczko") or {}).get("linie") or [nick]
    logo = (opis.get("wieczka", {}).get("wieczko-logo") or {}).get("logo")
    paleta.setdefault("lakier_z_feedu", paleta["tokeny"]["--lakier"])
    paleta["tokeny"]["--lakier"] = lakier
    paleta["dostrojone"] = znacznik
    paleta["dostrojone_opis"] = f"lakier z palety strony {strona.get('nazwa_rodziny', strona['rodzina'])}: {skad}"
    nowy = warstwy(paleta, folder / "warstwy", nazwa or " ".join(linie), nick, opis.get("typ", ""),
                   str(KATALOG / logo) if logo else None)
    nowy["typ"] = opis.get("typ", "")
    plik_opisu.write_text(json.dumps(nowy, ensure_ascii=False, indent=2), encoding="utf-8")
    plik_palety.write_text(json.dumps(paleta, ensure_ascii=False, indent=2), encoding="utf-8")
    return paleta


def klientka(nick: str, wyjscie: Path, nazwa: str | None = None, sciezka_logo: str | None = None, typ: str | None = None) -> dict:
    from dobierz_zdjecie import typ_uslugi

    wyjscie.mkdir(parents=True, exist_ok=True)
    profil = json.loads((DANE / nick / "profile.json").read_text(encoding="utf-8"))
    typ = typ or typ_uslugi(profil)[0]
    paleta = kolor_z_feedu(nick)
    opis = warstwy(paleta, wyjscie, nazwa or nick, nick, typ, sciezka_logo)
    opis["typ"] = typ
    (wyjscie / "paleta.json").write_text(json.dumps(paleta, ensure_ascii=False, indent=2), encoding="utf-8")
    (wyjscie / "warstwy.json").write_text(json.dumps(opis, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"paleta": paleta, **opis}


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("tryb", choices=["baza", "paleta", "klientka", "dostroj"])
    p.add_argument("nicki", nargs="*")
    p.add_argument("--logo")
    p.add_argument("--nazwa")
    p.add_argument("--wymus", action="store_true")
    a = p.parse_args()
    if a.tryb == "baza":
        baza()
    elif a.tryb == "dostroj":                      # wieczko w kolorze palety strony: python puderniczka.py dostroj <nick...>
        for nick in a.nicki:
            w = dostroj_do_palety(nick, a.nazwa, a.wymus)
            print(f"{nick:30} " + (f"{w['tokeny']['--lakier']} (z feedu {w.get('lakier_z_feedu')}) {w.get('dostrojone_opis')}" if w else "brak paleta_strony.json"))
    elif a.tryb == "paleta":
        for nick in a.nicki:
            w = kolor_z_feedu(nick)
            print(f"{nick:30} {w['rodzina']:8} h={w['odcien']:<6} surowy={w['odcien_surowy']:<6} {w['zrodlo']:10} {w['tokeny']['--tlo']} {w['tokeny']['--lakier']}")
    else:
        for nick in a.nicki:
            w = klientka(nick, KATALOG / "hero" / nick / "warstwy", a.nazwa, a.logo)
            print(json.dumps(w, ensure_ascii=False, indent=2))
