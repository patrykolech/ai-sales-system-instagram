#!/usr/bin/env python3
"""Cennik orientacyjny: zeby sekcja "Uslugi i ceny" zawsze miala ceny i kilka pozycji, takze gdy profil cen nie podaje.

Zasady (wlasciciel 2026-11-11: "zeby zawsze dawalo jakies ceny do cennika nawet jak nie ma, wiecej pozycji"):
- ceny z jej cennika (pricing_mode exact) zostaja nietkniete; gdy pozycji jest mniej niz MIN_POZYCJI, dochodzi grupa
  "Pozostałe usługi" z typowymi zabiegami jej branzy, ktorych jeszcze nie ma w cenniku, opisana "ceny orientacyjne";
- uslugi z profilu bez cen dostaja cene "od X zł" ze wzoru (dopasowanie po slowach kluczowych), a gdy jest ich malo,
  dochodza typowe zabiegi; cala sekcja ma wtedy note "Ceny orientacyjne";
- profil bez uslug: pelny wzor dla typu.
Ceny to typowe ceny "od" w Polsce (2026) dla miasta sredniej wielkosci, z mnoznikiem dla duzych miast.
Kazda dopisana pozycja i cena jest wyraznie opisana jako orientacyjna, na stronie nie udaje cennika klientki.
"""
from __future__ import annotations

import re
import unicodedata

MIN_POZYCJI = 6
DOCELOWO = 8
OPIS_ORIENT = "Ceny orientacyjne"

# (wzorzec w nazwie uslugi, nazwa do cennika, cena od w zl)
WZOR = {
    "rzesy": [
        ("Przedłużanie rzęs", [
            (r"1\s*[:/]\s*1|klasycz", "Rzęsy metodą 1:1", 140),
            (r"2\s*[--]?\s*3\s*d|lekk\w* obj", "Objętość 2-3D", 160),
            (r"4\s*[--]?\s*[56]\s*d|objęto|volume|wolum", "Objętość 4-6D", 180),
            (r"mega|7\s*d|8\s*d", "Mega volume", 220),
            (r"uzupe|dopeł", "Uzupełnienie do 3 tygodni", 110),
            (r"zdjęci|ściągn|usunięci", "Zdjęcie stylizacji", 40),
        ]),
        ("Lifting i laminacja", [
            (r"lifting|laminacj\w* rzęs", "Lifting i laminacja rzęs", 120),
            (r"henn\w* rzęs|koloryzacj\w* rzęs", "Henna rzęs", 30),
        ]),
        ("Brwi", [
            (r"regulacj", "Regulacja brwi", 30),
            (r"henn\w* pudr|henn\w* brwi", "Henna pudrowa brwi", 60),
            (r"laminacj\w* brwi", "Laminacja brwi", 110),
        ]),
    ],
    "brwi": [
        ("Stylizacja brwi", [
            (r"regulacj", "Regulacja brwi", 30),
            (r"henn\w* klas", "Henna klasyczna", 40),
            (r"henn\w* pudr", "Henna pudrowa", 60),
            (r"architekt|stylizacj\w* brwi", "Architektura brwi z henną", 90),
        ]),
        ("Laminacja", [
            (r"laminacj\w* brwi", "Laminacja brwi", 110),
            (r"laminacj.*koloryz|pakiet|komplet", "Laminacja z koloryzacją i regulacją", 140),
        ]),
        ("Rzęsy", [
            (r"henn\w* rzęs", "Henna rzęs", 30),
            (r"lifting|laminacj\w* rzęs", "Lifting rzęs", 120),
        ]),
    ],
    "pmu": [
        ("Makijaż permanentny", [
            (r"brw|pudr|ombre|shading", "Brwi metodą pudrową", 700),
            (r"ust|lip|warg", "Usta - efekt akwareli", 800),
            (r"kresk|eyeliner|powiek", "Kreska górna", 600),
            (r"międzyrzęs|zagęszcz", "Zagęszczenie linii rzęs", 450),
        ]),
        ("Korekty i konsultacje", [
            (r"dopigment|korekt", "Dopigmentowanie do 8 tygodni", 250),
            (r"odświe|refresh", "Odświeżenie makijażu", 450),
            (r"konsultac", "Konsultacja", 0),
        ]),
    ],
    "makijaz": [
        ("Makijaż", [
            (r"dzienn", "Makijaż dzienny", 150),
            (r"wieczor|okolicz", "Makijaż wieczorowy", 200),
            (r"sesj|foto", "Makijaż do sesji zdjęciowej", 220),
        ]),
        ("Ślub", [
            (r"ślub|panny młod", "Makijaż ślubny", 350),
            (r"prób", "Próba makijażu ślubnego", 200),
            (r"świadk|mam\w* |goś", "Makijaż dla gości i mam", 200),
        ]),
        ("Lekcje i dodatki", [
            (r"lekcj|naucz|szkolen", "Lekcja makijażu", 300),
            (r"rzęs\w* na pask|kępk", "Rzęsy na pasku lub kępki", 20),
        ]),
    ],
    "paznokcie": [
        ("Manicure", [
            (r"hybryd", "Manicure hybrydowy", 120),
            (r"żel|zel|przedłu", "Przedłużanie paznokci żelem", 180),
            (r"uzupe", "Uzupełnienie żelu", 150),
            (r"klasycz|tradycyj", "Manicure klasyczny", 70),
        ]),
        ("Pedicure", [
            (r"pedicure.*hybryd|hybryd.*stop", "Pedicure hybrydowy", 140),
            (r"pedicure", "Pedicure leczniczy", 160),
        ]),
        ("Dodatki", [
            (r"zdjęci|ściągn|usunięci", "Zdjęcie hybrydy lub żelu", 40),
            (r"zdobien|ozdob|art", "Zdobienia", 10),
        ]),
    ],
}
WZOR["ogolny"] = WZOR["rzesy"]

MNOZNIK_MIASTA = {"warszawa": 1.2, "kraków": 1.1, "wrocław": 1.1, "gdańsk": 1.1, "poznań": 1.1, "gdynia": 1.05, "sopot": 1.15,
                  "katowice": 1.05, "łódź": 1.0}


def _bez(t: str) -> str:
    t = unicodedata.normalize("NFKD", (t or "").lower().replace("ł", "l"))
    return "".join(z for z in t if not unicodedata.combining(z))


def _cena(zl: int, miasto: str) -> str:
    if zl == 0:
        return "bezpłatnie"
    m = MNOZNIK_MIASTA.get((miasto or "").strip().lower(), 1.0)
    return f"od {int(round(zl * m / 10.0)) * 10} zł"


def _pasuje(wzor: str, tekst: str) -> bool:
    return bool(re.search(wzor, tekst, re.I) or re.search(_bez(wzor), _bez(tekst), re.I))


def cena_z_wzoru(nazwa: str, typ: str, miasto: str) -> str:
    """Cena 'od' dla jej uslugi bez ceny: pierwszy pasujacy wzor jej typu, potem pozostalych typow."""
    kolejnosc = [typ] + [t for t in WZOR if t != typ]
    for t in kolejnosc:
        for _, poz in WZOR.get(t, []):
            for wzor, _, zl in poz:
                if _pasuje(wzor, nazwa):
                    return _cena(zl, miasto)
    return ""


def uzupelnij(h2: str, exact: bool, grupy: list, typ: str, miasto: str) -> tuple[str, bool, list, str]:
    """(h2, ceny_sa, grupy, orient): orient = '' (same jej ceny), 'czesc' (dopisane pozycje), 'wszystko' (ceny ze wzoru).
    grupy: [(tytul, opis, [(nazwa, cena, notka)])] jak w zbuduj_strone.grupy_uslug."""
    typ = typ if typ in WZOR else "ogolny"
    jej = " | ".join(n for _, _, p in grupy for n, _, _ in p) + " | " + " | ".join(t for t, _, _ in grupy)
    if exact:
        razem = sum(len(p) for _, _, p in grupy)
        if razem >= MIN_POZYCJI:
            return h2, True, grupy, ""
        dodane = _brakujace(jej, typ, miasto, DOCELOWO - razem)
        if not dodane:
            return h2, True, grupy, ""
        return "Usługi i ceny", True, grupy + [("Pozostałe usługi", OPIS_ORIENT, dodane)], "czesc"
    # profil bez cen: jej uslugi z cenami ze wzoru, reszta typowa
    nowe = []
    for tyt, opis, poz in grupy:
        p2 = [(n, cena_z_wzoru(n, typ, miasto) or cena_z_wzoru(tyt, typ, miasto), nt) for n, _, nt in poz]
        nowe.append((tyt, opis, p2))
    razem = sum(len(p) for _, _, p in nowe)
    if razem < MIN_POZYCJI:
        if not nowe:
            for tyt, poz in WZOR[typ]:
                nowe.append((tyt, "", [(nz, _cena(zl, miasto), "") for _, nz, zl in poz]))
        else:
            dodane = _brakujace(jej, typ, miasto, DOCELOWO - razem)
            if dodane:
                nowe.append(("Pozostałe usługi", "", dodane))
    # pozycje bez dopasowanej ceny: najnizsza cena "od" w tej grupie, a gdy jej brak - pierwsza usluga typu
    domyslna = _cena(WZOR[typ][0][1][0][2], miasto)
    nowe = [(t, o, [(n, c or (min((x for _, x, _ in p if x.startswith("od ")), key=lambda s: int(re.sub(r"\D", "", s)), default="")
                               or domyslna), nt) for n, c, nt in p]) for t, o, p in nowe]
    return "Usługi i ceny", True, nowe, "wszystko"


def _brakujace(jej: str, typ: str, miasto: str, ile: int) -> list:
    """Typowe zabiegi jej typu, ktorych nazwy nie ma w jej cenniku (po wzorcu), najwazniejsze najpierw."""
    out = []
    for _, poz in WZOR[typ]:
        for wzor, nazwa, zl in poz:
            if len(out) >= max(0, ile):
                return out
            if _pasuje(wzor, jej) or zl == 0:
                continue
            out.append((nazwa, _cena(zl, miasto), ""))
    return out
