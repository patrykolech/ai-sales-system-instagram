#!/usr/bin/env python3
"""Tlo pierwszego ekranu: siedem okraglych lusterek z prawdziwych zdjec klientki i poswiata z tokenow.

    python tlo.py salon_przyklad_15

Poswiata jest gotowym obrazem, wiec telefon nie liczy rozmycia podczas przewijania.
Zapisuje hero/<nick>/tlo/kola.json z miejscami S1-S7. Geometria i progi: docs/01-brief.md, sekcja 6.
"""
from __future__ import annotations

import base64
import io
import json
import math
import sys
from pathlib import Path

import numpy as np
from PIL import Image

from dobierz_zdjecie import (DANE, KATALOG, MAX_PRZECHYLENIE_TWARZY, _maska_kola, ocen_kadry, ocen_profil, obroc, otworz,
                             pamiec_odpowiedzi)
from kolor import hex2rgb, mocne_barwy, oklab2rgb, rgb2oklab

# bok pliku, ognisko fx i ciecie krawedzia z tabeli 390x844, strona: -1 lewa, 1 prawa krawedz ekranu
MIEJSCA = [
    {"id": "S1", "bok": 460, "fx": 0.26, "ciecie": 0.35, "strona": -1, "prog": 4.0, "oko": True, "temat": "oko", "krycie": 1.0},
    {"id": "S2", "bok": 400, "fx": -0.11, "ciecie": 0.18, "strona": 1, "prog": 4.0, "oko": True, "temat": "twarz", "krycie": 1.0},
    {"id": "S3", "bok": 360, "fx": -0.19, "ciecie": 0.27, "strona": 1, "prog": 3.5, "oko": True, "temat": "oko", "krycie": 0.92},
    {"id": "S4", "bok": 320, "fx": 0.10, "ciecie": 0.17, "strona": -1, "prog": 3.5, "oko": True, "temat": "twarz", "krycie": 0.92},
    {"id": "S5", "bok": 200, "fx": -0.23, "ciecie": 0.31, "strona": 1, "prog": 3.0, "oko": False, "temat": "detal", "krycie": 0.84},
    {"id": "S6", "bok": 170, "fx": 0.07, "ciecie": 0.13, "strona": -1, "prog": 3.0, "oko": False, "temat": "detal", "krycie": 0.84},
    {"id": "S7", "bok": 120, "fx": 0.0, "ciecie": 0.0, "strona": 0, "prog": 3.0, "oko": False, "temat": "usta", "krycie": 0.84},
]
WYPELNIENIE = {"oko": 0.62, "twarz": 0.85, "detal": 0.80, "usta": 0.86}
MIN_WYPELNIENIE_MAKRO = 0.33
TOLERANCJA_OGNISKA = 0.15
BUDZET_KOL_KB = 75
RUNDY_KONTROLI = 5


def _px(pole: dict, w: int, h: int) -> tuple:
    return pole["x0"] * w, pole["y0"] * h, pole["x1"] * w, pole["y1"] * h


def kadr_kola(prosty: Image.Image, pole: dict, m: dict, wypelnienie: float) -> dict | None:
    """Kwadrat, w ktorym srodek tematu pada na (fx, 0), czyli w srodek czesci widocznej na ekranie.

    Gdy brzeg zdjecia nie pozwala na takie przesuniecie, bok rosnie. Gdy temat i tak wpadlby za krawedz ekranu, zwraca None.
    """
    w, h = prosty.size
    x0, y0, x1, y1 = _px(pole, w, h)
    sz, wy = x1 - x0, y1 - y0
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    widoczna = 1 - m["ciecie"]
    bok = max(sz / (wypelnienie * widoczna), wy / wypelnienie, m["bok"])
    maks = min(w, h)
    # zakres x widoczny w ukladzie kola
    lewo = -1 + 2 * m["ciecie"] if m["strona"] < 0 else -1
    prawo = 1 - 2 * m["ciecie"] if m["strona"] > 0 else 1
    for _ in range(8):
        bok = min(bok, maks)
        sx = min(max(cx - m["fx"] * bok / 2 - bok / 2, 0), w - bok)
        sy = min(max(cy - bok / 2, 0), h - bok)
        fx, fy = (cx - sx - bok / 2) / (bok / 2), (cy - sy - bok / 2) / (bok / 2)
        pol_x = sz / bok  # polowa szerokosci tematu w jednostkach promienia
        if lewo <= fx - 0.6 * pol_x and fx + 0.6 * pol_x <= prawo and math.hypot(fx, fy) <= 0.72:
            return {"pudelko": (int(sx), int(sy), int(sx + bok), int(sy + bok)), "bok": int(bok), "fx": round(fx, 3), "fy": round(fy, 3)}
        if bok >= maks:
            return None
        bok *= 1.2
    return None


def _kadr_dla(k: dict, m: dict, prosty: Image.Image, luzno: bool = False) -> dict | None:
    """Temat wg miejsca: twarz, oko albo usta. Zapasowo pole oka, bo to ono jest zawsze oceniane."""
    pole = k["pole"]
    temat = "oko"
    if m["temat"] == "twarz" and k.get("twarz") and k.get("przechylenie", 0) <= MAX_PRZECHYLENIE_TWARZY:
        pole, temat = k["twarz"], "twarz"
    elif m["temat"] == "usta" and k.get("usta"):
        pole, temat = k["usta"], "usta"
    elif m["temat"] == "detal":
        temat = "detal"
    wynik = kadr_kola(prosty, pole, m, WYPELNIENIE[temat])
    # duze oko na calym zdjeciu nie ma miejsca na przesuniecie do ogniska: ciasniejszy kadr je daje, a oko dalej miesci sie w czesci widocznej
    if m["ciecie"] >= 0.25:
        for dodatek in (0.12, 0.24):
            if wynik is not None and abs(wynik["fx"] - m["fx"]) <= TOLERANCJA_OGNISKA:
                break
            ciasniej = kadr_kola(prosty, pole, m, WYPELNIENIE[temat] + dodatek)
            wynik = ciasniej or wynik
    # usta ucięte brzegiem zdjecia wygladaja jak przypadek, a przy tak malym kole nie ma czego ratowac
    if wynik is not None and temat == "usta" and abs(wynik["fx"] - m["fx"]) > 0.12:
        wynik = None
    if wynik is None and temat != "oko":
        pole, temat = k["pole"], "oko"
        wynik = kadr_kola(prosty, pole, m, WYPELNIENIE[temat])
    if wynik is None:
        return None
    # male oko w duzym kadrze to nie makro: bok pliku wymusil cala twarz, a miejsce S1 i S3 ma pokazac prace z bliska
    if m["temat"] == "oko":
        sz = (pole["x1"] - pole["x0"]) * prosty.width
        if sz / (wynik["bok"] * (1 - m["ciecie"])) < MIN_WYPELNIENIE_MAKRO:
            return None
    # duze oko na calym zdjeciu nie da sie przesunac do ogniska i krawedz ekranu by je ucinala: niech trafi do mniej cietego miejsca
    if not luzno and m["ciecie"] >= 0.25 and abs(wynik["fx"] - m["fx"]) > TOLERANCJA_OGNISKA:
        return None
    return {**wynik, "temat": temat}


def _przypisz(ranking: list, pomin: set, wczesniejsze: dict, luzno: bool = False, zablokowane: dict | None = None) -> dict:
    """Kolejne miejsca dostaja najlepsze pasujace zdjecia. Miejsce bez kandydatki konczy uklad, bo kolejnosc jest stala.

    luzno: przy ubogim profilu miejsca S1-S4 przyjmuja tez ocene 3 zamiast dziury. Taki wpis jest oznaczony w kola.json.
    """
    przydzial: dict = {}
    uzyte: set = set()
    zablokowane = zablokowane or {}
    for m in MIEJSCA:
        stare = wczesniejsze.get(m["id"])
        if stare and Path(stare["k"]["plik"]).name not in pomin and Path(stare["k"]["plik"]).name not in uzyte:
            przydzial[m["id"]] = stare
            uzyte.add(Path(stare["k"]["plik"]).name)
            continue
        znaleziony = None
        prog = min(m["prog"], 3.0) if luzno else m["prog"]
        # napis gdziekolwiek na poscie odpada tez z kol: model nie zauwazyl szyldu w tle przycietego kadru (kucharska, post-03)
        # luzno (za malo czystych): tez posty z napisem gdzies, np. znak wodny na kazdym poscie (salon_b: 11 z 11);
        # sam wycinek kola i tak przechodzi kontrole ocen_kadry, w ktorej napis, naklejka albo logo = 'bad'
        pasujace = [k for k in ranking if Path(k["plik"]).name not in uzyte and Path(k["plik"]).name not in pomin and k["ocena"] >= prog
                    and (luzno or not k.get("tekst_gdzies")) and Path(k["plik"]).name not in zablokowane.get(m["id"], ())]
        # S2 i S4 wola twarz, S1 i S3 makro: rozne ujecia zamiast siedmiu takich samych oczu
        if m["temat"] == "twarz":
            pasujace.sort(key=lambda k: (0 if k.get("twarz") else 1, -k["ocena"]))
        elif m["temat"] == "oko":
            pasujace.sort(key=lambda k: (-k["ocena"], 1 if k.get("twarz") else 0, -(k["pole"]["x1"] - k["pole"]["x0"])))
        for k in pasujace:
            prosty = obroc(otworz(k["plik"]), k.get("obrot", 0))
            kadr = _kadr_dla(k, m, prosty, luzno)
            if kadr is None:
                continue
            obraz = prosty.crop(kadr["pudelko"])
            if mocne_barwy(obraz)["odrzuc"]:
                continue
            znaleziony = {"k": k, "m": m, "kadr": kadr, "obraz": obraz}
            break
        if znaleziony is None:
            break
        przydzial[m["id"]] = znaleziony
        uzyte.add(Path(znaleziony["k"]["plik"]).name)
    return przydzial


def wybierz_kola(profil: dict, wyj: Path, pomin: set) -> list:
    """Przydzial, wspolna kontrola gotowych kadrow na jednym arkuszu i zapis. Odpadle miejsca dostaja nastepne zdjecia."""
    wyj.mkdir(parents=True, exist_ok=True)
    ranking = profil["ranking"]
    odpadle = set(pomin)
    zablokowane: dict = {}
    przydzial: dict = {}
    sprawdzone: dict = {}
    powody: list = []
    luzno = False
    for runda in range(RUNDY_KONTROLI):
        przydzial = _przypisz(ranking, odpadle, przydzial, luzno, zablokowane)
        if len(przydzial) < 7 and not luzno:
            # same scisle progi zostawilyby dziury: sprawdz, czy luzniej da sie je wypelnic
            luzno = True
            przydzial = _przypisz(ranking, odpadle, przydzial, luzno, zablokowane)
        nowe = [p for p in przydzial.values() if (p["m"]["id"], p["k"]["plik"]) not in sprawdzone]
        if not nowe:
            break
        tafle = [_maska_kola(p["obraz"], 300, p["m"]["ciecie"], p["m"]["strona"]) for p in nowe]
        oceny = ocen_kadry(tafle)
        for i, p in enumerate(nowe, 1):
            o = oceny.get(i) or {}
            nazwa = Path(p["k"]["plik"]).name
            sprawdzone[(p["m"]["id"], p["k"]["plik"])] = o
            ocena = float(o.get("a", 3))
            p["ocena_kadru"] = ocena
            p["ponizej_progu"] = ocena < p["m"]["prog"]
            # przechylenie liczy sie raz, na pelnym kole: przy czesci zaslonietej krawedzia ekranu odczyt modelu skacze o kilkadziesiat stopni
            if o.get("bad") or o.get("upside_down") or (p["m"]["oko"] and not o.get("eye", True)) or ocena < 3:
                odpadle.add(nazwa)
                powody.append({"miejsce": p["m"]["id"], "zrodlo": nazwa, "odpowiedz": o})
                przydzial.pop(p["m"]["id"], None)
            elif p["ponizej_progu"] and not luzno:
                # kadr jest uczciwy, ale za slaby na to miejsce: moze zagrac nizej
                zablokowane.setdefault(p["m"]["id"], set()).add(nazwa)
                przydzial.pop(p["m"]["id"], None)
    # ostatnia runda mogla zostawic niesprawdzone zastepstwa: lepiej mniej kol niz kadr bez kontroli
    przydzial = {mid: p for mid, p in przydzial.items() if (p["m"]["id"], p["k"]["plik"]) in sprawdzone}
    ciagle = {}
    for m in MIEJSCA:
        if m["id"] not in przydzial:
            break
        ciagle[m["id"]] = przydzial[m["id"]]
    return _zapisz_kola(ciagle, wyj, powody)


def _zapisz_kola(przydzial: dict, wyj: Path, powody: list) -> list:
    wpisy = []
    for stary in list(wyj.glob("S*.webp")) + list(wyj.glob("kolo-*.webp")):
        stary.unlink()
    for q in range(82, 45, -4):
        pliki, razem = {}, 0
        for mid, p in przydzial.items():
            bok = min(p["m"]["bok"], p["kadr"]["bok"])
            b = io.BytesIO()
            p["obraz"].resize((bok, bok), Image.LANCZOS).save(b, "WEBP", quality=q, method=6)
            pliki[mid] = (b.getvalue(), bok)
            razem += b.tell()
        if razem <= BUDZET_KOL_KB * 1024:
            break
    for mid, p in przydzial.items():
        dane, bok = pliki[mid]
        (wyj / f"{mid}.webp").write_bytes(dane)
        k, m, kadr = p["k"], p["m"], p["kadr"]
        wpisy.append({"miejsce": mid, "plik": f"{mid}.webp", "zrodlo": Path(k["plik"]).name, "obrot": k.get("obrot", 0),
                      "pudelko": list(kadr["pudelko"]), "bok_zrodla": kadr["bok"], "bok_pliku": bok, "powiekszone": bok > kadr["bok"],
                      "temat": kadr["temat"], "ognisko": {"cel_fx": m["fx"], "fx": kadr["fx"], "fy": kadr["fy"]}, "ciecie": m["ciecie"],
                      "ocena": p.get("ocena_kadru", k["ocena"]), "ponizej_progu": bool(p.get("ponizej_progu")), "prog": m["prog"],
                      "krycie": m["krycie"], "kb": round(len(dane) / 1024, 1), "q": q})
    # stany przy malej liczbie zdjec, sekcja 6: do czterech narozniki zostaja jako puste lusterka
    n = len(wpisy)
    puste = [m["id"] for m in MIEJSCA[n:4]]
    uklad = {"zdjec": n, "puste": puste, "razem_kb": round(sum(w["kb"] for w in wpisy), 1), "q": q, "wpisy": wpisy, "odpadle_w_kontroli": powody}
    (wyj / "kola.json").write_text(json.dumps(uklad, ensure_ascii=False, indent=2), encoding="utf-8")
    return wpisy


def poswiata(paleta: dict, wyj: Path) -> dict:
    """Poswiata z tokenow, bez mozaiki zdjec: mozaika niesie skore i robi braz. 98x211, do wstawienia inline."""
    W, H = 98, 211
    t = paleta["tokeny"]
    jasne, tlo, ciemne = (rgb2oklab(hex2rgb(t[k])) for k in ("--tlo-jasne", "--tlo", "--tlo-ciemne"))
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float64)
    # elipsa za puderniczka: srodek na 42,5% wysokosci. Bez plaskiego srodka, bo jego krawedz wyglada jak plama.
    d = np.hypot((xx + 0.5 - W / 2) / W, (yy + 0.5 - H * 0.425) / (W * 1.08))
    t_pol = d / float(np.hypot(0.5, 0.575 * H / (W * 1.08)))
    # jasne na srodku, tlo w polowie drogi do naroznika, ciemne w narozniku
    u = np.clip(t_pol / 0.5, 0, 1)
    v = np.clip((t_pol - 0.5) / 0.5, 0, 1)
    u, v = u * u * (3 - 2 * u), v * v * (3 - 2 * v)
    lab = jasne * (1 - u)[..., None] + tlo * (u * (1 - v))[..., None] + ciemne * v[..., None]
    rgb = oklab2rgb(lab)
    # szum trojkatny do 0,8% przeciw paskom. Rozklad normalny dawal pojedyncze ciemne kropki po powiekszeniu.
    los = np.random.default_rng(7)
    szum = (los.random((H, W, 1)) - los.random((H, W, 1))) * 0.008
    obraz = Image.fromarray((np.clip(rgb + szum, 0, 1) * 255 + 0.5).astype(np.uint8), "RGB")
    wyj.mkdir(parents=True, exist_ok=True)
    for q in range(100, 20, -2):  # szum ma przetrwac kompresje: im blizej 2 KB, tym mniej paskow
        b = io.BytesIO()
        obraz.save(b, "WEBP", quality=q, method=6)
        if b.tell() <= 2048:
            break
    (wyj / "poswiata.webp").write_bytes(b.getvalue())
    uri = "data:image/webp;base64," + base64.b64encode(b.getvalue()).decode()
    (wyj / "poswiata.txt").write_text(uri, encoding="utf-8")
    return {"plik": "poswiata.webp", "wymiary": [W, H], "bajty": b.tell(), "q": q, "inline": "poswiata.txt"}


if __name__ == "__main__":
    nick = sys.argv[1]
    cel = KATALOG / "hero" / nick / "tlo"
    paleta = json.loads((KATALOG / "hero" / nick / "warstwy" / "paleta.json").read_text(encoding="utf-8"))
    print(poswiata(paleta, cel))
    pamiec_odpowiedzi(KATALOG / "dobor" / nick / "odpowiedzi.json")
    print(nick, "dane z", DANE)
    profil = ocen_profil(nick)
    raport = json.loads((KATALOG / "hero" / nick / "lusterko" / "lusterko.json").read_text(encoding="utf-8"))
    print(wybierz_kola(profil, cel, {raport["zrodlo"]}))
