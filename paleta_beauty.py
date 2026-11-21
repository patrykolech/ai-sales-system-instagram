#!/usr/bin/env python3
"""Paleta strony dobierana automatycznie do klientki, zawsze w granicach beauty. Bez modeli, 0 USD.

    python paleta_beauty.py salon_przyklad_26 salon_przyklad_14      # wypisz dobor
    python paleta_beauty.py --wszystkie --json palety.json    # zapisz dla wielu

1. Kolor marki z jej materialow: okladki wyroznionych relacji (projektuje je w kolorach marki, waga 3),
   awatar (waga 2), probka postow (waga 1, bez pikseli skory, bo skora dominuje w beauty i daje wszedzie
   ten sam bez/roz). Wynik: odcien, nasycenie i jasnosc feedu w OKLCH.
2. Rodzina palety z RODZINY: zaprojektowane pary kolorow pod beauty (papier, atrament, mrok, akcent
   i kolor na przelamanie). Wybor po odcieniu marki; przy prawie bezbarwnej marce decyduje jasnosc feedu.
3. Akcent przesuwany w strone odcienia marki (najwyzej o 18 stopni), jasnosc i nasycenie zostaja z rodziny,
   wiec nic nie wychodzi neonowe ani brudne. Kontrast tekstu sprawdzany (WCAG).
"""
from __future__ import annotations

import argparse
import json
import math
import os
import re
import sys
from pathlib import Path

import numpy as np
from PIL import Image

KATALOG = Path(__file__).resolve().parent
sys.path.insert(0, str(KATALOG))
from kolor import kontrast, oklch2hex, rgb2oklab, hex2rgb  # noqa: E402
from zbuduj_hero import DANE  # noqa: E402

# Rodziny: odcien kotwicy (OKLCH h), rola kazdego koloru. Projektowane recznie, sprawdzone na kontrast.
# papier/papier2 = jasne tla sekcji, atrament = tekst, mrok = ciemne sekcje i hero, akcent = kolor marki,
# przelamanie = kontra (duze plamy, numery, jeden blok na sekcje), na_akcencie = tekst na akcencie.
RODZINY = {
    "nude-atrament":   {"nazwa": "Nude i atrament", "kotwica": None, "papier": "#F3EEE7", "papier2": "#E6DCCF", "atrament": "#1A1714",
                        "mrok": "#1F1A16", "akcent": "#B07A4F", "przelamanie": "#111111", "opis": "naturalne, nude, minimal"},
    "czern-glam":      {"nazwa": "Czerń glam", "kotwica": None, "papier": "#F4F1EA", "papier2": "#E9E4DA", "atrament": "#0F0F0F",
                        "mrok": "#0F0F0F", "akcent": "#C9A46A", "przelamanie": "#F2A7B5", "opis": "ciemny feed, glam, czerń i złoto"},
    "roz-oliwka":      {"nazwa": "Puder i oliwka", "kotwica": 0, "papier": "#F7EEEA", "papier2": "#F2D9D6", "atrament": "#2E2420",
                        "mrok": "#2E2420", "akcent": "#C98A8A", "przelamanie": "#5C6B4A", "opis": "róż, pudrowe, romantyczne"},
    "wisnia-krem":     {"nazwa": "Wiśnia i krem", "kotwica": 18, "papier": "#F6EFE6", "papier2": "#EAD9CC", "atrament": "#1E1012",
                        "mrok": "#2A0E14", "akcent": "#8E1B2E", "przelamanie": "#E8C9B5", "opis": "czerwień, bordo, mocny makijaż"},
    "koral-kobalt":    {"nazwa": "Koral i kobalt", "kotwica": 40, "papier": "#F5EFE8", "papier2": "#F1DDD0", "atrament": "#161616",
                        "mrok": "#161616", "akcent": "#D9573F", "przelamanie": "#2B45D8", "opis": "koral, pomarańcz, nowoczesne"},
    "mokka-szalwia":   {"nazwa": "Mokka i szałwia", "kotwica": 60, "papier": "#EFE6DC", "papier2": "#E2D3C3", "atrament": "#2A1E17",
                        "mrok": "#2A1E17", "akcent": "#8A5A3C", "przelamanie": "#9DB0A0", "opis": "brąz, beż, karmel"},
    "szampan-czern":   {"nazwa": "Szampan i czerń", "kotwica": 90, "papier": "#F6F1E6", "papier2": "#EADFC8", "atrament": "#141210",
                        "mrok": "#141210", "akcent": "#B8923E", "przelamanie": "#7A1F2B", "opis": "złoto, żółć, luksus"},
    "szalwia-terakota": {"nazwa": "Szałwia i terakota", "kotwica": 140, "papier": "#EEF0E8", "papier2": "#DCE3D3", "atrament": "#1F261E",
                        "mrok": "#1F2A22", "akcent": "#6F8A68", "przelamanie": "#C2643F", "opis": "zieleń, eko, spa"},
    "granat-szampan":  {"nazwa": "Granat i szampan", "kotwica": 240, "papier": "#F2EEE6", "papier2": "#E0E4EC", "atrament": "#121A2B",
                        "mrok": "#121A2B", "akcent": "#2F4673", "przelamanie": "#D9B98A", "opis": "niebieski, turkus, chłodne"},
    "lawenda-maslo":   {"nazwa": "Lawenda i masło", "kotwica": 300, "papier": "#F2EEF6", "papier2": "#E4DCEE", "atrament": "#231C2B",
                        "mrok": "#2B1F38", "akcent": "#8C7BB0", "przelamanie": "#E9D27A", "opis": "fiolet, lawenda, delikatne"},
    "sliwka-zloto":    {"nazwa": "Śliwka i złoto", "kotwica": 345, "papier": "#F5EDEF", "papier2": "#EBD7DC", "atrament": "#2B0F1A",
                        "mrok": "#2B0F1A", "akcent": "#8A3B5C", "przelamanie": "#C8A15A", "opis": "fuksja, malina, wieczorowe"},
}
MAX_PRZESUNIECIA = 18


def _oklch(img: Image.Image, bok: int = 72) -> np.ndarray:
    im = img.convert("RGB")
    im.thumbnail((bok, bok))
    lab = rgb2oklab(np.asarray(im, dtype=np.float64).reshape(-1, 3) / 255)
    C = np.hypot(lab[:, 1], lab[:, 2])
    h = (np.degrees(np.arctan2(lab[:, 2], lab[:, 1])) + 360) % 360
    return np.stack([lab[:, 0], C, h], 1)


def _skora(p: np.ndarray) -> np.ndarray:
    """Piksele w zakresie skory (cieplo, srednie nasycenie, jasne): wyrzucamy je z postow."""
    L, C, h = p[:, 0], p[:, 1], p[:, 2]
    return (h > 15) & (h < 85) & (C > 0.02) & (C < 0.13) & (L > 0.42) & (L < 0.93)


def kolor_marki(nick: str, ile_postow: int = 40) -> dict:
    folder = DANE / nick
    zrodla: list[tuple[np.ndarray, float, str]] = []
    for p in sorted((folder / "covers").glob("cover-*.jpg")):
        zrodla.append((_oklch(Image.open(p)), 3.0, "okladki"))
    for p in list((folder / "highlights").glob("*/*.jpg"))[:12]:
        zrodla.append((_oklch(Image.open(p)), 1.5, "relacje"))
    av = folder / "covers" / "profile-pic.jpg"
    if av.exists():
        zrodla.append((_oklch(Image.open(av)), 2.0, "awatar"))
    posty = sorted(folder.glob("post-*.jpg"))[:ile_postow]
    for p in posty:
        px = _oklch(Image.open(p), 48)
        zrodla.append((px[~_skora(px)], 1.0, "posty"))
    wszystkie_L, kolorowe = [], []
    for px, waga, _ in zrodla:
        if len(px) == 0:
            continue
        wszystkie_L.append((float(np.median(px[:, 0])), waga))
        k = px[px[:, 1] > 0.045]
        if len(k):
            kolorowe.append((k, waga / max(1, len(px)) * 100))
    jasnosc = sum(l * w for l, w in wszystkie_L) / max(1e-9, sum(w for _, w in wszystkie_L))
    # histogram odcieni wazony nasyceniem i waga zrodla, wygladzony
    hist = np.zeros(360)
    masa_kolor = 0.0
    for k, w in kolorowe:
        np.add.at(hist, k[:, 2].astype(int) % 360, k[:, 1] * w)
        masa_kolor += float(k[:, 1].sum() * w)
    jadro = np.exp(-0.5 * (np.arange(-20, 21) / 8) ** 2)
    gl = np.convolve(np.concatenate([hist[-20:], hist, hist[:20]]), jadro, "same")[20:380]
    h = int(np.argmax(gl)) if gl.max() > 0 else 0
    sasiedzi = [k[np.abs(((k[:, 2] - h + 180) % 360) - 180) < 20] for k, _ in kolorowe]
    sasiedzi = np.concatenate([s for s in sasiedzi if len(s)]) if any(len(s) for s in sasiedzi) else np.zeros((0, 3))
    C = float(np.median(sasiedzi[:, 1])) if len(sasiedzi) else 0.0
    L = float(np.median(sasiedzi[:, 0])) if len(sasiedzi) else jasnosc
    udzial = masa_kolor / max(1e-9, sum(w for _, w in wszystkie_L) * 100 * 0.05)
    return {"h": h, "C": round(C, 3), "L": round(L, 3), "jasnosc_feedu": round(jasnosc, 3), "sila_koloru": round(udzial, 3),
            "zrodla": sorted({z for _, _, z in zrodla}), "probka": oklch2hex(L, min(C, 0.16), h)}


def _roznica(a: float, b: float) -> float:
    return abs((a - b + 180) % 360 - 180)


def wybierz_rodzine(m: dict) -> str:
    if m["sila_koloru"] < 0.35 or m["C"] < 0.05:                # marka prawie bez koloru
        return "czern-glam" if m["jasnosc_feedu"] < 0.5 else "nude-atrament"
    kandydaci = [(k, r) for k, r in RODZINY.items() if r["kotwica"] is not None]
    k, _ = min(kandydaci, key=lambda kr: _roznica(m["h"], kr[1]["kotwica"]))
    if k == "roz-oliwka" and m["C"] > 0.13 and m["L"] < 0.55:  # mocny, ciemny roz to juz wisnia
        return "wisnia-krem"
    if k == "mokka-szalwia" and m["C"] < 0.07 and m["L"] > 0.7:
        return "nude-atrament"
    return k


def _hex2oklch(x: str) -> tuple[float, float, float]:
    lab = rgb2oklab(hex2rgb(x)[None, :])[0]
    return float(lab[0]), float(math.hypot(lab[1], lab[2])), (math.degrees(math.atan2(lab[2], lab[1])) + 360) % 360


def arkusz_marki(nick: str, bok: int = 150) -> Image.Image:
    """Okladki relacji, awatar i kilka postow na jednym arkuszu: tak grafik widzi kolory marki."""
    folder = DANE / nick
    pliki = sorted((folder / "covers").glob("cover-*.jpg"))[:8]
    if (folder / "covers" / "profile-pic.jpg").exists():
        pliki.insert(0, folder / "covers" / "profile-pic.jpg")
    if len(pliki) < 4:
        pliki += sorted((folder / "highlights").glob("*/*.jpg"))[:6]
    pliki += sorted(folder.glob("post-*.jpg"))[:20 - len(pliki)]
    ark = Image.new("RGB", (5 * bok, 4 * bok), "white")
    for i, p in enumerate(pliki[:20]):
        im = Image.open(p).convert("RGB")
        im.thumbnail((bok, bok))
        ark.paste(im, ((i % 5) * bok, (i // 5) * bok))
    return ark


PYTANIE = """You are an art director choosing a website colour palette for a Polish beauty professional (lashes, brows, makeup, nails).
The sheet shows her Instagram highlight covers, avatar and recent posts. Ignore skin tones, hair and makeup on faces;
look at the colours she CHOSE for her brand: cover backgrounds, graphics, logo, props, outfits, interior.
Pick exactly one palette family that fits her brand and the beauty industry:
{rodziny}
Reply with JSON only: {{"family": "<key>", "brand_hex": "#rrggbb", "accent_hex": "#rrggbb", "mood": "<2-4 words>", "why": "<max 12 words>"}}
brand_hex = her dominant brand colour, accent_hex = a second colour she uses (or the same)."""


def wybierz_modelem(nick: str) -> dict | None:
    """Art director (agenci.py, Claude Sonnet 5 przez ByteCatCode) wybiera rodzine z listy; bez ByteCatCode tani model
    z wizja przez RouteMux. Odpowiedzi zapamietane w dobor/<nick>/agenci.json albo odpowiedzi.json."""
    opis = "\n".join(f'- "{k}": {r["nazwa"]} ({r["opis"]}; paper {r["papier"]}, ink {r["atrament"]}, accent {r["akcent"]}, contrast {r["przelamanie"]})'
                     for k, r in RODZINY.items())
    try:
        import agenci
        if agenci.dostepne() and os.environ.get("LUSTRO_AGENCI", "1") != "0":
            return agenci.art_director_paleta(nick, PYTANIE.format(rodziny=opis), arkusz_marki(nick), set(RODZINY))
    except Exception as e:                                      # ByteCatCode nie odpowiada: zostaje RouteMux
        print(f"  art director palety: {type(e).__name__}: {str(e)[:120]}", file=sys.stderr)
    try:
        import dobierz_zdjecie as D
        D.pamiec_odpowiedzi(KATALOG / "dobor" / nick / "odpowiedzi.json")
        o = D.zapytaj(PYTANIE.format(rodziny=opis), arkusz_marki(nick), max_tokens=300, model=D.MODEL_ARKUSZ)
        return o if o.get("family") in RODZINY else None
    except Exception as e:                                      # brak sieci, saldo, zla odpowiedz: zostaje liczenie
        print(f"  model palety: {type(e).__name__}: {str(e)[:120]}", file=sys.stderr)
        return None


def paleta(nick: str, model: bool = True) -> dict:
    m = kolor_marki(nick)
    o = wybierz_modelem(nick) if model else None
    klucz = o["family"] if o else wybierz_rodzine(m)
    cel_h = m["h"]
    if o and re.fullmatch(r"#[0-9a-fA-F]{6}", o.get("accent_hex", "")):
        cel_h = _hex2oklch(o["accent_hex"])[2]
    r = dict(RODZINY[klucz])
    if r["kotwica"] is not None:                                # akcent w strone jej odcienia, reszta z rodziny
        L, C, h = _hex2oklch(r["akcent"])
        d = ((cel_h - h + 180) % 360) - 180
        r["akcent"] = oklch2hex(L, C, (h + max(-MAX_PRZESUNIECIA, min(MAX_PRZESUNIECIA, d))) % 360)
    kontr = {"atrament/papier": kontrast(r["atrament"], r["papier"]), "atrament/papier2": kontrast(r["atrament"], r["papier2"]),
             "papier/mrok": kontrast(r["papier"], r["mrok"]), "akcent/papier": kontrast(r["akcent"], r["papier"])}
    jasny_na_akcencie = kontrast(r["papier"], r["akcent"]) >= kontrast(r["atrament"], r["akcent"])
    r["na_akcencie"] = r["papier"] if jasny_na_akcencie else r["atrament"]
    return {"nick": nick, "rodzina": klucz, "marka": m, "model": o, "kolory": {k: r[k] for k in ("papier", "papier2", "atrament", "mrok", "akcent", "przelamanie", "na_akcencie")},
            "nazwa_rodziny": r["nazwa"], "kontrast": {k: round(v, 2) for k, v in kontr.items()}}


def _ton(x: str, dL: float, kC: float = 1.0) -> str:
    L, C, h = _hex2oklch(x)
    return oklch2hex(max(0.05, min(0.98, L + dL)), C * kC, h)


def _wyciszony(tekst: str, tlo: str, cel: float = 5.0) -> str:
    """Kolor drugiego planu: od tekstu w strone tla, dopoki kontrast z tlem >= cel."""
    Lt, Ct, ht = _hex2oklch(tekst)
    Lb = _hex2oklch(tlo)[0]
    najlepszy = tekst
    for i in range(1, 20):
        k = oklch2hex(Lt + (Lb - Lt) * i / 20, Ct * 0.8, ht)
        if kontrast(k, tlo) < cel:
            break
        najlepszy = k
    return najlepszy


def tokeny_strony(p: dict) -> dict:
    """Role palety -> zmienne CSS uzywane przez hero.css i sekcje.css (stare nazwy zostaja, dochodza nowe)."""
    k = p["kolory"]
    guzik = max((k["akcent"], k["przelamanie"], k["papier"]), key=lambda c: kontrast(c, k["mrok"]) if kontrast(c, k["mrok"]) < 12 else 0)
    t = {"--tlo": k["mrok"], "--tlo-jasne": _ton(k["mrok"], 0.11, 0.9), "--tlo-ciemne": _ton(k["mrok"], -0.05),
         "--puder": k["papier"], "--papier": k["papier"], "--papier2": k["papier2"], "--atrament": k["atrament"],
         "--jasny": k["papier"], "--szept": _wyciszony(k["atrament"], k["papier"]), "--szept-jasny": _wyciszony(k["papier"], k["mrok"], 7.0),
         "--akcent": k["akcent"], "--na-akcencie": k["na_akcencie"], "--przelamanie": k["przelamanie"],
         "--na-przelamaniu": k["papier"] if kontrast(k["papier"], k["przelamanie"]) > kontrast(k["atrament"], k["przelamanie"]) else k["atrament"],
         "--guzik": guzik, "--guzik-tekst": k["atrament"] if kontrast(k["atrament"], guzik) >= kontrast(k["papier"], guzik) else k["papier"]}
    return t


def zapisz(nick: str, rodzina: str | None = None) -> dict:
    """Paleta strony do hero/<nick>/paleta_strony.json (czyta ja zbuduj_hero.tokeny_css). rodzina = reczny wybor."""
    p = paleta(nick, model=rodzina is None)
    if rodzina:
        if rodzina not in RODZINY:
            raise SystemExit(f"nieznana rodzina {rodzina}; dostepne: {', '.join(RODZINY)}")
        r = RODZINY[rodzina]
        p.update(rodzina=rodzina, nazwa_rodziny=r["nazwa"], model={"family": rodzina, "why": "wybor reczny"})
        p["kolory"] = {x: r[x] for x in ("papier", "papier2", "atrament", "mrok", "akcent", "przelamanie")}
        p["kolory"]["na_akcencie"] = r["papier"] if kontrast(r["papier"], r["akcent"]) >= kontrast(r["atrament"], r["akcent"]) else r["atrament"]
    p["tokeny"] = tokeny_strony(p)
    cel = KATALOG / "hero" / nick / "paleta_strony.json"
    cel.parent.mkdir(parents=True, exist_ok=True)
    cel.write_text(json.dumps(p, ensure_ascii=False, indent=1), encoding="utf-8")
    return p


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("nicki", nargs="*")
    ap.add_argument("--json")
    ap.add_argument("--zapisz", action="store_true", help="zapisz hero/<nick>/paleta_strony.json")
    ap.add_argument("--rodzina", help="reczny wybor rodziny (tylko przy jednym nicku)")
    a = ap.parse_args()
    if a.zapisz:
        for n in a.nicki:
            p = zapisz(n, a.rodzina)
            print(f"{n:24s} -> {p['nazwa_rodziny']:20s} {p['tokeny']['--tlo']} {p['tokeny']['--papier']} {p['tokeny']['--akcent']} {p['tokeny']['--przelamanie']} guzik {p['tokeny']['--guzik']}")
        sys.exit(0)
    wyniki = []
    for n in a.nicki:
        p = paleta(n)
        wyniki.append(p)
        mk = p["marka"]
        o = p["model"] or {}
        print(f"{n:24s} -> {p['nazwa_rodziny']:20s} akcent {p['kolory']['akcent']} | model: {o.get('brand_hex')} {o.get('accent_hex')} "
              f"{o.get('mood')!r} {o.get('why')!r} | liczenie: h={mk['h']} C={mk['C']:.3f} -> {wybierz_rodzine(mk)}")
    if a.json:
        Path(a.json).write_text(json.dumps(wyniki, ensure_ascii=False, indent=1), encoding="utf-8")
