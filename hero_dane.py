#!/usr/bin/env python3
"""Komplet danych hero jednej klientki: warstwy, paleta, poswiata, lusterko, zdjecie i kola. Nic nie publikuje.

    python hero_dane.py salon_przyklad_15 --nazwa "Salon Przyklad" --logo logo/salon_przyklad-monogram/logo-czarne.png
    python hero_dane.py --testowe

Odpowiedzi modeli leza w dobor/<nick>/odpowiedzi.json, wiec drugie uruchomienie po poprawce kodu nic nie kosztuje.
Zdjecie odrzucone po obejrzeniu wpisz do dobor/<nick>/odrzucone.json jako {"post-12.jpg": "powod"}.
"""
from __future__ import annotations

import argparse
import base64
import io
import json
import time
from pathlib import Path

from PIL import Image

import dobierz_zdjecie as D
import puderniczka as P
import tlo as T

KATALOG = Path(__file__).resolve().parent
TESTOWE = {
    "salon_przyklad_15": {"nazwa": "Salon Przyklad", "logo": "logo/salon_przyklad-monogram/logo-czarne.png"},
    "salon_przyklad_12": {"nazwa": "Studio Przyklad", "logo": "logo/studio_przyklad-stempel/logo-czarne.png"},
    "salon_przyklad_14": {"nazwa": "Brwi Przyklad"},
    "salon_przyklad_26": {"nazwa": "Rzesy Przyklad"},
}
BUDZET_ZDJECIA_KB = 160
# ekrany z tabeli geometrii, sekcja 8: szerokosc, wysokosc zdjecia koncowego do luku
EKRANY_KONCOWE = {"390x844": (390, 561), "390x720": (390, 479), "360x640": (360, 426), "430x932": (430, 620)}


def _oko_w_kadrze_koncowym(w: int, h: int, pole: dict) -> dict:
    """Czy po skalowaniu cover zdjecie koncowe moze pokazac cale oko. Obraz wolno przesuwac tylko w granicach kadru."""
    wynik = {}
    for nazwa, (sz, wy) in EKRANY_KONCOWE.items():
        skala = max(sz / w, wy / h)
        widok_w, widok_h = sz / skala, wy / skala
        x0, y0, x1, y1 = pole["x0"] * w, pole["y0"] * h, pole["x1"] * w, pole["y1"] * h
        wynik[nazwa] = bool(x1 - x0 <= widok_w and y1 - y0 <= widok_h)
    return wynik


def zapisz_lusterko(wynik: dict, typ: str, wyj: Path) -> dict:
    """Tylko kadr i obrot. Kadr jest zapisany osobno, a rama z efektami szkla jest oddzielna warstwa nad zdjeciem."""
    wyj.mkdir(parents=True, exist_ok=True)
    prosty, kadr, pudelko = wynik["prosty"], wynik["kadr"], wynik["pudelko"]
    w, h = prosty.size
    skala = D.skala_zdjecia(w, h)
    zdjecie = prosty.resize((int(w * skala), int(h * skala)), Image.LANCZOS) if skala < 1 else prosty
    opis_zdjecia = P.zapisz_webp(zdjecie, wyj / "zdjecie.webp", BUDZET_ZDJECIA_KB, q_start=78, q_min=60)
    opis_kadru = P.zapisz_webp(kadr.resize((min(kadr.width, 936),) * 2, Image.LANCZOS) if kadr.width > 936 else kadr, wyj / "lusterko.webp", 90, q_start=82, q_min=62)
    # rozmyta miniatura inline <= 1 KB: w lusterku nigdy nie ma pustego miejsca przy wolnym laczu
    b = io.BytesIO()
    kadr.resize((24, 24), Image.LANCZOS).save(b, "WEBP", quality=40, method=6)
    pole = wynik["pole"]
    raport = {
        "typ": typ, "zrodlo": Path(wynik["plik"]).name, "obrot": wynik["obrot"], "ocena": wynik["ocena"],
        "przechylenie": wynik.get("przechylenie"), "mocne_barwy_w_calym_kadrze": wynik.get("kolor_calego"),
        "miekkie_na_koncu": wynik.get("miekkie"), "oryginal": [w, h], "zdjecie": opis_zdjecia, "zdjecie_wymiary": list(zdjecie.size), "skala_do_pliku": round(skala, 4),
        "kadr_w_oryginale": list(pudelko), "bok_kadru_w_oryginale": pudelko[2] - pudelko[0],
        "bok_kadru_w_zdjeciu": round((pudelko[2] - pudelko[0]) * skala),
        # otwor lusterka na 390x844 to 2 x 137,4 px CSS: ile razy plik jest powiekszany przy gestosci 3x
        "powiekszenie_w_lusterku_3x": round(2 * 137.4 * 3 / ((pudelko[2] - pudelko[0]) * skala), 2),
        "powiekszenie_koncowe_3x": round(3 * max(390 / zdjecie.width, 561 / zdjecie.height), 2),
        "kadr_w_ulamkach": [round(pudelko[0] / w, 4), round(pudelko[1] / h, 4), round(pudelko[2] / w, 4), round(pudelko[3] / h, 4)],
        "pole_oka_w_ulamkach": {k: round(float(v), 4) for k, v in pole.items()},
        "oko_w_kadrze_koncowym": _oko_w_kadrze_koncowym(w, h, pole),
        "kadr": opis_kadru, "miniatura_inline": "data:image/webp;base64," + base64.b64encode(b.getvalue()).decode(),
        "miniatura_bajty": b.tell(), "odrzucone_finalistki": wynik.get("odrzucone", []),
    }
    (wyj / "lusterko.json").write_text(json.dumps(raport, ensure_ascii=False, indent=2), encoding="utf-8")
    return raport


def klientka(nick: str, nazwa: str, logo: str | None) -> dict:
    wyj = KATALOG / "hero" / nick
    dobor = KATALOG / "dobor" / nick
    D.pamiec_odpowiedzi(dobor / "odpowiedzi.json")
    D.wyzeruj_licznik()
    start = time.time()
    saldo_przed = D.saldo()
    warstwy = P.klientka(nick, wyj / "warstwy", nazwa, str(KATALOG / logo) if logo else None)
    profil = D.ocen_profil(nick)
    lusterko = D.dobierz_lusterko_z_zapasem(profil)
    raport_lusterka = zapisz_lusterko(lusterko, profil["typ"], wyj / "lusterko")
    pomin = set(profil["odrzucone"]) | {Path(lusterko["plik"]).name}
    kola = T.wybierz_kola(profil, wyj / "tlo", pomin)
    poswiata = T.poswiata(warstwy["paleta"], wyj / "tlo")
    time.sleep(2)  # saldo ksieguje sie z lekkim opoznieniem
    saldo_po = D.saldo()
    koszt = {"saldo_przed": saldo_przed, "saldo_po": saldo_po, "koszt_usd": round(saldo_przed - saldo_po, 6), **{k: v for k, v in D.LICZNIK.items()}}
    wynik = {"nick": nick, "nazwa": nazwa, "typ": profil["typ"], "rodzina": warstwy["paleta"]["rodzina"], "odcien": warstwy["paleta"]["odcien"],
             "lejek": profil["raport"], "lusterko": raport_lusterka["zrodlo"], "kola": [(k["miejsce"], k["zrodlo"], k["temat"], k["ocena"]) for k in kola],
             "poswiata": poswiata, "koszt": koszt, "sek": round(time.time() - start)}
    dobor.mkdir(parents=True, exist_ok=True)
    (dobor / "przebieg.json").write_text(json.dumps(wynik, ensure_ascii=False, indent=2), encoding="utf-8")
    return wynik


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("nick", nargs="?")
    p.add_argument("--nazwa")
    p.add_argument("--logo")
    p.add_argument("--testowe", action="store_true")
    a = p.parse_args()
    zadania = TESTOWE if a.testowe else {a.nick: {"nazwa": a.nazwa or a.nick, "logo": a.logo}}
    for nick, opis in zadania.items():
        try:
            print(json.dumps(klientka(nick, opis["nazwa"], opis.get("logo")), ensure_ascii=False))
        except Exception as e:
            print(f"BLAD {nick}: {type(e).__name__}: {e}")
