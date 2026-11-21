#!/usr/bin/env python3
"""Generator calej strony konceptu "Moment w lustrze": hero (z zbuduj_hero.py, bez zmian) + sekcje po hero (v3).
Sciezka A, statyczny HTML/CSS/JS. Nic nie publikuje. Jedyne wywolanie sieci: tekst O mnie (o_mnie.py, tani model tekstowy,
pamiec w dobor/<nick>/o_mnie.json, budzet 0,05 USD, stop przy saldzie < 1,6 USD); bez sieci zostaje wersja z bio.

    python zbuduj_strone.py                     # wszystkie klientki z rejestru -> prototyp_strona/<wariant>/index.html + indeks
    python zbuduj_strone.py salon_przyklad_26 ...     # wybrane klientki
    python zbuduj_strone.py --bez-modelu ...    # bez zapytan o tekst O mnie (tylko pamiec)

v3 (2026-11-10): kolory z palety klientki (hero/<nick>/paleta_strony.json) jako powierzchnie sekcji w rytmie (wzor.py: papier,
mrok, akcent, papier2, przelamanie; kolejne sekcje nigdy na tym samym tle, kontrast WCAG liczony w Pythonie), tla z faktura
(ziarno, monogram klientki, prazki, kropki), przejscia (kolo lusterka, kartka magazynu, plynna zmiana koloru, slowo konturem),
spis tresci ({{SPIS}} w hero + staly spis po hero), numery sekcji zgodne ze spisem, O mnie z modelu, standardowe pytania
w Dobrze wiedziec, karty postow z Instagrama, stopka z winieta. Zero ramek w ksztalcie luku.

Hero jest importowane: zbuduj_hero.zbuduj() z podmienionym WYJ, a szablon hero.html jest tylko przerabiany w pamieci.
"""
from __future__ import annotations

import html as H
import inspect
import json
import os
import re
import sys
import urllib.parse
from pathlib import Path

from PIL import Image, ImageOps

import dobierz_zdjecie as D
import zbuduj_hero as Z
import wzor as WZ
import o_mnie as OM
import cennik_wzor as CW
from zbuduj_hero import DANE, KLIENTKI, cena, esc, zdanie, bez_ogonkow, CHEVRON

KATALOG = Path(__file__).resolve().parent
WYJ = KATALOG / "prototyp_strona"
FRAG = KATALOG / "szablon" / "sekcje"
Z.WYJ = WYJ                                     # hero zapisuje do nowego folderu; prototyp/ zostaje nietkniety

EMOJI = re.compile("[\U0001F000-\U0001FAFF←-⇿⌀-⏿①-➿⤀-⥿⬀-⯿︀-️‍⃣⁠]")
BEZ_MODELU = False
PRODUKCJA = os.environ.get("LUSTRO_PRODUKCJA") == "1"     # automat na serwerze: strona idzie do klientki

# Decyzje reczne po obejrzeniu danych (powod w komentarzu). Klucz: nick.
OPINIE_ODRZUCONE = {"salon_przyklad_12": ["Wiki"]}            # imie wlascicielki w tresci opinii
FAQ_ODRZUCONE = {"salon_przyklad_14": ["Czy nitkowanie to boli?"]}   # blad jezykowy ("lekka odruch") i twierdzenie o bolu bez zrodla
PRACE_ODRZUCONE = {
    "salon_przyklad_26": {"post-88.jpg": "szare pasy na brzegach (zrzut ekranu)", "post-51.jpg": "dwa oka jedno nad drugim (kolaz)"},
    "salon_przyklad_14": {"post-11.jpg": "naklejka z napisem na zdjeciu",
                         "post-39.jpg": "napis 'Korean lash lift' i serca na zdjeciu (v2: widac go w lusterkach i w O nas)"},
    "salon_przyklad_15": {"post-43.jpg": "cala sylwetka w body, nie praca", "post-23.jpg": "fryzura, nie makijaz", "post-21.jpg": "teczowe tlo (mocne barwy)"},
    "salon_przyklad_12": {"post-03.jpg": "dwie osoby, niejasne autorstwo"},
}
GRUPY_PODMIANA = {"henna pudrowa / farbka z geometrią + masaż": ("Henna pudrowa i farbka", "Z geometrią i masażem")}  # sklejony naglowek z OCR
GRUPY_POZA_PASKIEM = re.compile(r"^(dodatk|inne|extra|dopłat)", re.I)                   # to nie usluga, tylko doplaty

STRZALKA = ('<svg viewBox="0 0 16 16" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.5" '
            'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M8 2.5v11M3.5 9l4.5 4.5L12.5 9"/></svg>')
ISKRA = '<svg class="iskra" viewBox="0 0 24 24" aria-hidden="true" focusable="false"><use href="#iskra"/></svg>'
SYMBOLE = ('<svg class="symbole" width="0" height="0" aria-hidden="true" focusable="false">'
           '<symbol id="iskra" viewBox="0 0 24 24"><path fill="currentColor" d="M12 1.5c.7 5.6 4.9 9.8 10.5 10.5'
           '-5.6.7-9.8 4.9-10.5 10.5C11.3 16.9 7.1 12.7 1.5 12 7.1 11.3 11.3 7.1 12 1.5z"/></symbol></svg>')
PLUS = '<span class="faq-znak" aria-hidden="true"><i></i><i></i></span>'
IG_ZNAK = ('<svg class="post-ig" viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="1.5" '
           'aria-hidden="true"><rect x="3" y="3" width="18" height="18" rx="5"/><circle cx="12" cy="12" r="4.2"/><circle cx="17.3" cy="6.7" r="1" fill="currentColor" stroke="none"/></svg>')

# Galeria luster: miejsca lusterek. (ksztalt, desktop x% y% szer[jw], telefon x% y% szer%, obrot, glebia).
# Ksztalty luster: kolo, owal, prostokat lustra toaletki (lekko zaokraglone rogi). Bez luku (zakaz wlasciciela).
MIEJSCA = {
    "a": ("prost", (7.5, 9, 16), (3, 1.5, 36), -4, "przod"),
    "e": ("prost", (78, 46, 14.5), (60, 62, 34), 3, "przod"),
    "c": ("owal", (70, 5, 14), (62, 0, 33), 5, "tyl"),
    "b": ("kolo", (26, 63, 12.5), (5, 72, 30), 0, "tyl"),
    "f": ("kolo", (2.5, 57, 9), (2, 45, 16), 0, "tyl"),
    "g": ("owal", (51, 70, 8.5), (42, 87, 17), -6, "przod"),
    "d": ("kolo", (56.5, 12, 7.2), (45, 21, 14), 0, "tyl"),
}
UKLADY = {3: "a e b", 4: "a c e b", 5: "a c e b d", 6: "a c e b d f", 7: "a c e b d f g"}
KOLEJNOSC_ROZMIARU = "a e c b f g d"             # najwieksze miejsca dostaja najostrzejsze pliki

# Usluga -> pasujace zdjecie: (wzorzec nazwy grupy, rodzaje kadru z przegladu, wzorzec podpisu posta)
KLUCZE_USLUG = [
    (r"brw|henn|nitk|regulac", {"brew"}, r"brw|henn|nitk"),
    (r"rzęs|rzes|lash|lifting", {"oko"}, r"rzęs|rzes|lash"),
    (r"makija|mua|wizaż|wizaz", {"twarz", "oko"}, r"makija"),
    (r"paznok|manicure|pedicure|hybryd|żel", set(), r"paznok|hybry|manicure|pedicure"),
    (r"\bust|lip", set(), r"\busta|\bust\b|lip"),
    (r"włos|wlos|fryz|strzy|koloryzacja włos", set(), r"włos|wlos|fryz"),
]


def tekst(t: str) -> str:
    return re.sub(r"\s+", " ", EMOJI.sub("", t)).strip()


def plik_html(nazwa: str, **kw) -> str:
    t = (FRAG / nazwa).read_text(encoding="utf-8")
    for k, v in kw.items():
        t = t.replace("{{" + k + "}}", str(v))
    ost = re.findall(r"\{\{[A-Z_0-9]+\}\}", t)
    if ost:
        raise SystemExit(f"{nazwa}: niepodmienione {ost}")
    return t


def dwie(n: int) -> str:
    return f"{n:02d}"


def img_tag(src: str, w: int, h: int, alt: str = "", klasa: str = "", styl: str = "") -> str:
    k = f' class="{klasa}"' if klasa else ""
    s = f' style="{styl}"' if styl else ""
    return f'<img{k} src="{src}" width="{w}" height="{h}" alt="{H.escape(alt)}" loading="lazy" decoding="async"{s}>'


def zapisz_webp(im: Image.Image, p: Path, limit_kb: int, jakosci=(74, 70, 66, 62, 58, 54)) -> int:
    p.parent.mkdir(parents=True, exist_ok=True)
    for q in jakosci:
        im.save(p, "WEBP", quality=q, method=6)
        if p.stat().st_size <= limit_kb * 1024:
            break
    return q


# ---------------------------------------------------------------- liczba (ja / my)
def liczba_mnoga(prof: dict) -> bool:
    """Bio w pierwszej osobie liczby mnogiej ("Uzywamy", "pracujemy") = salon: 'Nasze prace', 'O nas'."""
    return bool(re.search(r"\b\w+(amy|emy|imy)\b", prof.get("biography") or "", re.I))


# ---------------------------------------------------------------- uslugi i ceny
def cena_wiersza(prices: list[str]) -> str:
    c = cena(" / ".join(prices))
    if re.fullmatch(r"\+\s*0\s*(zł)?", c):                    # QA P3-9: "+0 zł" -> bez doplaty
        return "bez dopłaty"
    return c


def grupa_tytul(t: str) -> tuple[str, str]:
    z = zdanie(t)
    if z.lower() in GRUPY_PODMIANA:
        return GRUPY_PODMIANA[z.lower()]
    if " / " in z:                                           # sklejka z OCR
        z = z.replace(" / ", " i ")
    return z, ""


def regula_ceny(r: str) -> str | None:
    if re.search(r"zmian\w* cennika|przypominam|bez zmian", r, re.I):
        return None                                          # wiadomosc sytuacyjna, nie regula
    t = cena(zdanie(r))
    t = re.sub(r"(tyg\.?)\s*-\s*", "tyg.: ", t)
    return t.replace(" / ", ", ")


def od_ceny(poz: list[tuple[str, str, str]]) -> str:
    """Najnizsza cena podstawowa grupy ('od 150 zl'); doplaty (+10 zl) i 'bez doplaty' sie nie licza."""
    liczby = []
    for n, c, _ in poz:
        if not c or c.strip().startswith("+") or c.startswith("bez") or "%" in c or re.search(r"ściągn|sciagn|zdjęci|usunięci|zmyci", n, re.I):
            continue                                          # doplaty i zdjecie stylizacji to nie cena uslugi
        liczby += [int(x) for x in re.findall(r"\d+", c) if int(x) > 0]      # 0 zl (konsultacja) to nie "od 0 zl"
    if not liczby:
        return ""
    return f"{min(liczby)} zł" if len(set(liczby)) == 1 else f"od {min(liczby)} zł"


def cennik_strony(brief: dict, typ: str, miasto: str) -> tuple[str, bool, list, str]:
    """Cennik do pokazania: jej ceny + uzupelnienie wzorem (cennik_wzor). 4. pole: '' / 'czesc' / 'wszystko' orientacyjne.
    Fakty (O mnie, copywriter) biora grupy_uslug: tylko jej prawdziwe uslugi."""
    h2, exact, grupy = grupy_uslug(brief)
    return CW.uzupelnij(h2, exact, grupy, typ, miasto)


def grupy_uslug(brief: dict) -> tuple[str, bool, list[tuple[str, str, list[tuple[str, str, str]]]]]:
    f, c = brief["facts"], brief["content"]
    grupy: list[tuple[str, str, list[tuple[str, str, str]]]] = []
    if f["pricing_mode"] == "exact" and f["pricing_groups"]:
        for g in f["pricing_groups"]:
            poz = [(zdanie(i["name"]), cena_wiersza(i["prices"]), zdanie(i["note"]) if i.get("note") else "")
                   for i in g["items"] if i.get("name")]
            if poz:
                tytul = (g.get("title") or "").strip()
                if not tytul:                                   # grupa bez naglowka z OCR: wspolny poczatek nazw albo 'Pozostałe usługi'
                    slowa = [p[0].split() for p in poz]
                    wsp = []
                    for kolumna in zip(*slowa):
                        if len({s.lower() for s in kolumna}) != 1:
                            break
                        wsp.append(kolumna[0])
                    tytul = " ".join(wsp) if len(poz) > 1 and wsp else "Pozostałe usługi"
                tyt, opis = grupa_tytul(tytul)
                grupy.append((tyt, opis, poz))
        if grupy:
            return "Usługi i ceny", True, grupy
    kat: dict[str, list] = {}
    for s in c["services"]:
        kat.setdefault(s.get("category") or "Usługi", []).append((zdanie(s["name"]), "", ""))
    return "Usługi", False, [(k, "", v) for k, v in kat.items()]


def podpisy_postow(nick: str) -> dict[str, str]:
    out = {}
    for p in (DANE / nick).glob("post-*.txt"):
        try:
            out[p.stem + ".jpg"] = p.read_text(encoding="utf-8", errors="ignore").lower()
        except OSError:
            pass
    return out


def zdjecia_grup(nick: str, grupy: list, prace: list[dict], kand: list[dict], dst: Path, img: str) -> list[dict]:
    """Do kazdej grupy uslug jedno zdjecie: najpierw praca z podpisem albo rodzajem kadru pasujacym do nazwy grupy,
    potem (max 3) kadr z pozostalych kandydatek po tych samych filtrach, na koncu kolejna praca po kolei."""
    podp = podpisy_postow(nick)
    po_zrodle = {Path(k["plik"]).name: k for k in kand}
    pula = [{"src": f'{img}prace/{p["plik"]}', "w": 720, "h": 900, "zrodlo": p["zrodlo"],
             "rodzaj": po_zrodle.get(p["zrodlo"], {}).get("rodzaj", ""), "uzyte": 0} for p in prace]
    zapisane = {p["zrodlo"] for p in prace}
    (dst / "uslugi").mkdir(parents=True, exist_ok=True)
    for stary in (dst / "uslugi").glob("*.webp"):
        stary.unlink()
    dodatkowe, wynik = 0, []

    def ocena(z: dict, rodzaje: set, wz: str) -> float:
        s = 0.0
        if wz and re.search(wz, podp.get(z["zrodlo"], "")):
            s += 2
        if rodzaje and z["rodzaj"] in rodzaje:
            s += 1
        return s - 1.5 * z["uzyte"]

    for gi, (tyt, _, _) in enumerate(grupy):
        rodzaje, wz = set(), ""
        for wzor_, r, wp in KLUCZE_USLUG:
            if re.search(wzor_, tyt.lower()):
                rodzaje, wz = r, wp
                break
        wyb = None
        if pula:
            naj = max(pula, key=lambda z: ocena(z, rodzaje, wz))
            if ocena(naj, rodzaje, wz) >= 1 or not (rodzaje or wz):
                wyb = naj
        if wyb is None and (rodzaje or wz) and dodatkowe < 3:
            for k in kand:
                n = Path(k["plik"]).name
                if n in zapisane:
                    continue
                if (wz and re.search(wz, podp.get(n, ""))) or (rodzaje and k.get("rodzaj") in rodzaje):
                    im = ImageOps.fit(D.otworz(k["plik"]), (560, 560), Image.LANCZOS, centering=(0.5, 0.42))
                    p = dst / "uslugi" / f"u{gi + 1:02d}.webp"
                    zapisz_webp(im, p, 36, (72, 66, 60, 54))
                    wyb = {"src": f"{img}uslugi/{p.name}", "w": 560, "h": 560, "zrodlo": n, "rodzaj": k.get("rodzaj", ""), "uzyte": 0}
                    zapisane.add(n)
                    pula.append(wyb)
                    dodatkowe += 1
                    break
        if wyb is None and pula and (rodzaje or wz):                  # pasujace zdjecie drugi raz lepsze niz niepasujace
            naj = max(pula, key=lambda z: (ocena(dict(z, uzyte=0), rodzaje, wz), -z["uzyte"]))
            if ocena(dict(naj, uzyte=0), rodzaje, wz) >= 1:
                wyb = naj
        if wyb is None and pula:
            wyb = min(pula, key=lambda z: z["uzyte"])
        if wyb is not None:
            wyb["uzyte"] += 1
        wynik.append(wyb)
    return wynik


def uslugi_html(brief: dict, cta_url: str, cta_et: str, zdj: list, typ: str = "", miasto: str = "") -> tuple[str, str, str, str, str]:
    """Zwraca (H2, nota, wiersze, podglad, koniec)."""
    f = brief["facts"]
    h2, exact, grupy, orient = cennik_strony(brief, typ, miasto)
    razem = sum(len(p) for _, _, p in grupy)
    rozwijane = razem > 12
    wiersze = []
    for i, (tyt, opis, poz) in enumerate(grupy):
        rows = "\n".join(
            f'     <li><span class="n">{esc(n)}{f"<small>{esc(nt)}</small>" if nt else ""}</span>'
            + (f'<span class="c">{esc(cn)}</span>' if cn else "") + "</li>" for n, cn, nt in poz)
        lista = f'    <ul class="cennik">\n{rows}\n    </ul>'
        z = zdj[i] if i < len(zdj) else None
        foto = (f'<span class="usluga-foto" aria-hidden="true"><span class="usluga-lustro">'
                f'{img_tag(z["src"], z["w"], z["h"])}</span></span>') if z else ""
        op = f'<span class="usluga-opis">{esc(opis)}</span>' if opis else ""
        od = od_ceny(poz) if exact else ""
        if rozwijane:
            od_html = f'<span class="usluga-od">{esc(od)}</span>' if od else ""
            wiersze.append(
                f'   <details class="usluga" data-usluga="{i}"{" open" if i == 0 else ""}>\n'
                f'    <summary><span class="usluga-n">{dwie(i + 1)}</span><span class="usluga-glowa"><h3>{esc(tyt)}</h3>{op}{od_html}</span>'
                f'{foto}<span class="usluga-znak">{CHEVRON}</span></summary>\n{lista}\n   </details>')
        else:
            wiersze.append(
                f'   <article class="usluga" data-usluga="{i}">\n'
                f'    <div class="usluga-wiersz"><span class="usluga-n">{dwie(i + 1)}</span><span class="usluga-glowa"><h3>{esc(tyt)}</h3>{op}</span>{foto}</div>\n'
                f'{lista}\n   </article>')
    obrazy = [z for z in zdj if z]
    podglad = ""
    if obrazy:
        im = "".join(img_tag(z["src"], z["w"], z["h"], klasa="widoczny" if k == 0 else "") for k, z in enumerate(zdj) if z)
        podglad = (f'   <figure class="uslugi-podglad" data-anim="podglad" aria-hidden="true">'
                   f'<span class="podglad-lustro">{im}</span></figure>')
    nota = {"": '  <p class="uslugi-nota">Ceny z&nbsp;Instagrama</p>',
            "czesc": '  <p class="uslugi-nota">Ceny z&nbsp;Instagrama, pozostałe usługi orientacyjnie</p>',
            "wszystko": '  <p class="uslugi-nota">Ceny orientacyjne, dokładną cenę potwierdzisz przy&nbsp;zapisie</p>'}[orient] if exact else ""
    koniec = []
    if exact:
        for r in (x for x in (regula_ceny(r) for r in f.get("pricing_rules") or []) if x):
            koniec.append(f'  <p class="uslugi-regula">{esc(r)}</p>')
        koniec.append(f'  <p class="uslugi-cta" data-dok="ukryj"><a class="przycisk" href="{H.escape(cta_url)}">{esc(cta_et)}</a></p>')
    else:
        koniec.append(f'  <p class="uslugi-brak">Cennik: <a href="{H.escape(cta_url)}">napisz na&nbsp;Instagramie</a></p>')
    return h2, nota, "\n".join(wiersze), podglad, "\n".join(koniec)


def pasek_html(brief: dict, nick: str, miasto_ok: str, typ: str = "", miasto: str = "") -> str:
    _, exact, grupy, _ = cennik_strony(brief, typ, miasto)
    poz = []
    if exact:
        for tyt, opis, p in grupy:
            if GRUPY_POZA_PASKIEM.search(tyt) or opis == CW.OPIS_ORIENT:
                continue                                          # dopisana grupa wzoru nie idzie do paska
            poz.append((tyt, od_ceny(p)))
    else:
        for _, _, p in grupy:
            poz += [(n, "") for n, _, _ in p]
    if miasto_ok:
        poz.append((miasto_ok, ""))
    li = []
    for n, c in poz:
        cena_ = f'<span class="pc">{esc(c)}</span>' if c else ""
        li.append(f'   <li><span class="pn">{esc(n)}</span>{cena_}{ISKRA}</li>')
    li.append(f'   <li><span class="pn pn--nick">@{H.escape(nick)}</span>{ISKRA}</li>')
    return "\n".join(li)


# ---------------------------------------------------------------- prace
def uzyte_w_hero(nick: str) -> set[str]:
    kola = json.loads((KATALOG / "hero" / nick / "tlo" / "kola.json").read_text(encoding="utf-8"))
    lus = json.loads((KATALOG / "hero" / nick / "lusterko" / "lusterko.json").read_text(encoding="utf-8"))
    return {w["zrodlo"] for w in kola["wpisy"] if w.get("zrodlo")} | {lus["zrodlo"]}


def kandydaci_prac(nick: str) -> list[dict]:
    """Filtry z dobierz_zdjecie.py: wlasne podpisy (bez szkolen i cudzych), ostrosc, duplikaty, mocne barwy; potem zapisany
    przeglad arkuszy (bez tekstu, kolazy, zabiegu w trakcie). Zadnych wywolan sieci: brak odpowiedzi w pamieci = tylko filtry lokalne."""
    D.klucz = lambda: (_ for _ in ()).throw(RuntimeError("offline"))
    D._tryb["bytecat"] = False                      # offline znaczy offline: bez zapasu wizji przez ByteCatCode
    D.pamiec_odpowiedzi(KATALOG / "dobor" / nick / "odpowiedzi.json")
    prof = json.loads((DANE / nick / "profile.json").read_text(encoding="utf-8"))
    typ, _ = D.typ_uslugi(prof)
    kand = D.kandydaci(DANE / nick)
    try:
        wynik = [k for k in D.przeglad(kand, typ) if not k.get("obrocone")]
        zrodlo = "przeglad"
    except Exception:
        wynik, zrodlo = [dict(k, arkusz=3.0) for k in kand], "tylko filtry lokalne"
    odrzucone = D.wczytaj_odrzucone(nick)
    uz = uzyte_w_hero(nick) | set(PRACE_ODRZUCONE.get(nick, {}))
    wynik = [k for k in wynik if Path(k["plik"]).name not in odrzucone and Path(k["plik"]).name not in uz]
    wynik.sort(key=lambda k: (-k["arkusz"], -k["ostrosc"]))
    for k in wynik:
        k["zrodlo_doboru"] = zrodlo
    return wynik


def ma_pasy(sciezka: str) -> bool:
    """Czarne (albo jednolite) pasy u gory i u dolu, np. kadr z filmu albo zrzut ekranu: w ramkach wyglada jak blad."""
    import numpy as np
    a = np.asarray(D.otworz(sciezka).convert("L").resize((90, 120)), dtype=np.float32)
    def pas(w):
        return w.mean() < 28 and w.std() < 10
    return pas(a[:8]) and pas(a[-8:]) or pas(a[:, :6]) and pas(a[:, -6:])


def zapisz_prace(nick: str, kand: list[dict], dst: Path) -> list[dict]:
    kand = [k for k in kand if not ma_pasy(k["plik"])]
    n_dostepnych = len(kand)
    # wszystkie dobre zdjecia do 9 (bylo 9/5/3 progami: przy 5 dostepnych galeria pokazywala 3, salon_e 11.11)
    n = min(9, n_dostepnych) if n_dostepnych >= 3 else 0
    wyb = kand[:n]
    (dst / "prace").mkdir(parents=True, exist_ok=True)
    for stary in (dst / "prace").glob("*.webp"):
        stary.unlink()
    wynik = []
    for i, k in enumerate(wyb, 1):
        im = ImageOps.fit(D.otworz(k["plik"]), (720, 900), Image.LANCZOS, centering=(0.5, 0.38))
        p = dst / "prace" / f"p{i:02d}.webp"
        q = zapisz_webp(im, p, 70)
        wynik.append({"plik": p.name, "zrodlo": Path(k["plik"]).name, "kb": round(p.stat().st_size / 1024, 1), "q": q})
    return wynik


def pliki_hero(dst: Path, img: str) -> list[dict]:
    """Kola S1-S4 z hero (>= 320 px), juz pobrane przez scene hero: zapas dla galerii i siatki, bez nowych bajtow."""
    out = []
    for p in sorted((dst / "tlo").glob("S*.webp")):
        w, h = Image.open(p).size
        if w >= 320:
            out.append({"src": f"{img}tlo/{p.name}", "w": w, "h": h})
    return out


def numer(nr: str) -> str:
    return f'<p class="nr" aria-hidden="true"><span class="nr-cyfra">{nr}</span><span class="nr-linia"></span></p>' if nr else ""


def galeria_html(nick: str, mn: bool, prace: list[dict], zapas: list[dict], img: str, ctx: dict) -> str:
    pula = [{"src": f'{img}prace/{p["plik"]}', "w": 720, "h": 900} for p in prace] + zapas
    n = min(7, len(pula))
    miejsca = UKLADY[n].split()
    po_rozmiarze = [m for m in KOLEJNOSC_ROZMIARU.split() if m in miejsca]
    przydzial = dict(zip(po_rozmiarze, pula[:n]))
    li = []
    for m in miejsca:
        ks, (x, y, w), (mx, my, mw), rot, gl = MIEJSCA[m]
        z = przydzial[m]
        styl = f"--x:{x};--y:{y};--w:{w};--mx:{mx};--my:{my};--mw:{mw};--rot:{rot}deg"
        li.append(f'   <li class="gl-lustro gl-lustro--{m} ksztalt-{ks}" data-anim="gl-lustro" data-glebia="{gl}" style="{styl}">'
                  f'{img_tag(z["src"], z["w"], z["h"])}</li>')
    pierwsze = "Nasze" if mn else "Moje"
    h2 = f'<span class="maska maska--1"><span>{pierwsze}</span></span> <span class="maska maska--2"><span>prace</span></span>'
    podpis = f'{len(prace)} {"prace" if 2 <= len(prace) % 10 <= 4 and not 12 <= len(prace) % 100 <= 14 else "prac"} z&nbsp;profilu <a href="https://instagram.com/{H.escape(nick)}">@{H.escape(nick)}</a>'
    return plik_html("galeria.html", H2_LINIE=h2, N=n, LUSTRA="\n".join(li), PODPIS=podpis, STRZALKA=STRZALKA, **ctx)


def wstega_html(nick: str, prace: list[dict], img: str, ctx: dict, po_wstedze: str) -> str:
    n = len(prace)
    li = []
    for i, p in enumerate(prace, 1):
        src = f'{img}prace/{p["plik"]}'
        li.append(f'    <li class="praca"><a class="praca-link" href="{src}" data-lb aria-label="Powiększ pracę {i} z {n}">'
                  f'<span class="praca-rama">{img_tag(src, 720, 900, alt=f"Praca {i} z profilu @{nick}")}</span>'
                  f'<span class="praca-n" aria-hidden="true">{dwie(i)}</span></a></li>')
    ctx = {k: v for k, v in ctx.items() if k != "NR"}
    return plik_html("wstega.html", N2=dwie(n), NICK=H.escape(nick), PRACE="\n".join(li), STRZALKA=STRZALKA, PO_WSTEDZE=po_wstedze, **ctx)


# ---------------------------------------------------------------- opinie, faq, o mnie
def opinie_z_danych(nick: str, f: dict) -> list[str]:
    if f.get("reviews_mode") != "real":
        return []
    wyb = []
    for r in f.get("reviews_text") or []:
        t = tekst(r.get("tekst", ""))
        if not 25 <= len(t) <= 260:
            continue
        if "@" in t or re.search(r"\d{1,2}[./]\d{1,2}\b|\d{1,2}:\d{2}", t) or "!!!" in t:
            continue
        lit = [c for c in t if c.isalpha()]
        if lit and sum(c.isupper() for c in lit) / len(lit) > 0.5:
            continue
        if any(s in t for s in OPINIE_ODRZUCONE.get(nick, [])):
            continue
        wyb.append(t)
    return wyb[:3]


OCENA_FRAZY = re.compile(r"piękn|przepiękn|super|świetn|cudown|idealn|naturaln|przyjemn|talent|zachwyc|trzyma|polec|najlepsz|"
                         r"efekt|zadowol|mistrz|rewelac|ekstra|perfekc|delikatn|precyz", re.I)


def fragment(t: str) -> str | None:
    """Dosłowna fraza z prawdziwej opinii do ozdobnego paska: 2-6 słów, ze słowem oceny (piękny, trzyma się, talent...).
    Spójnik na początku (a, i, że, tak) odpada. Opinia bez takiej frazy nie daje fragmentu."""
    najlepsza = None
    for cz in re.split(r"[,.!?;:--]|\s-\s", t.strip().strip('"„”')):
        cz = re.sub(r"^(a|i|że|ze|tak|no|bo|ale|oraz)\s+", "", cz.strip(), flags=re.I)
        slowa = cz.split()
        if not 2 <= len(slowa) <= 6 or not OCENA_FRAZY.search(cz):
            continue
        if najlepsza is None or len(slowa) < len(najlepsza.split()):
            najlepsza = cz
    if not najlepsza:
        return None
    return najlepsza[:1].upper() + najlepsza[1:]


# Standardowe pytania (zadanie 6): ogolne wskazowki bez liczb, czasu i obietnic, ktore zaleza od salonu.
# Tematy: przygotowanie, przebieg, pielegnacja po, przeciwwskazania; umawianie dochodzi zawsze z danych (Booksy / Instagram).
FAQ_STANDARD = {
    "rzesy": [
        ("przygotowanie", "Jak przygotować się do stylizacji rzęs?",
         "Przyjdź bez makijażu oczu i bez tuszu na rzęsach. Jeśli nosisz soczewki kontaktowe, zdejmij je przed zabiegiem albo zabierz pojemnik."),
        ("przebieg", "Jak wygląda zabieg?",
         "Na początku ustalamy efekt, który Ci odpowiada. Podczas stylizacji leżysz wygodnie z zamkniętymi oczami."),
        ("pielegnacja", "Jak dbać o rzęsy po zabiegu?",
         "Zaraz po wizycie unikaj moczenia rzęs, pary i sauny. Na co dzień czesz je delikatnie i nie używaj przy oczach kosmetyków z olejkami."),
        ("przeciwwskazania", "Kiedy lepiej przełożyć wizytę?",
         "Gdy masz infekcję lub podrażnienie oka, stan zapalny powiek albo jesteś tuż po zabiegu okulistycznym. W razie wątpliwości napisz przed wizytą."),
    ],
    "brwi": [
        ("przygotowanie", "Jak przygotować się do stylizacji brwi?",
         "Nie reguluj brwi samodzielnie przed wizytą, żeby było z czego zbudować kształt. Przyjdź bez makijażu brwi."),
        ("przebieg", "Jak wygląda zabieg?",
         "Najpierw ustalamy kształt dopasowany do Twojej twarzy, potem wykonujemy wybraną usługę, na przykład regulację, koloryzację albo laminację."),
        ("pielegnacja", "Jak dbać o brwi po zabiegu?",
         "Zaraz po wizycie nie mocz brwi i nie nakładaj na nie makijażu. Po laminacji pomaga codzienne czesanie i odżywka do brwi."),
        ("przeciwwskazania", "Kiedy lepiej przełożyć wizytę?",
         "Przy podrażnieniu, rankach lub stanie zapalnym skóry w okolicy brwi. Jeśli kiedyś reagowałaś uczuleniem na hennę lub farbkę, powiedz o tym przed zabiegiem."),
    ],
    "pmu": [
        ("przygotowanie", "Jak przygotować się do makijażu permanentnego?",
         "Nie reguluj brwi przed wizytą i przyjdź bez makijażu w miejscu zabiegu. Leki, ciążę i alergie zgłoś przy zapisie."),
        ("przebieg", "Jak wygląda zabieg?",
         "Zaczynamy od rysunku kształtu, który akceptujesz, zanim zacznie się pigmentacja. Pigment wprowadzany jest stopniowo."),
        ("pielegnacja", "Jak dbać o skórę po zabiegu?",
         "Utrzymuj skórę w miejscu zabiegu czystą, nie drap jej i nie wystawiaj na słońce ani do sauny, dopóki się nie zagoi. O szczegółowe zalecenia zapytaj na wizycie."),
        ("przeciwwskazania", "Kiedy nie wykonuje się makijażu permanentnego?",
         "Przeciwwskazaniem bywają między innymi ciąża i karmienie piersią, choroby skóry w miejscu zabiegu, skłonność do bliznowców i niektóre leki. Zapytaj przed zapisem, jeśli masz wątpliwości."),
    ],
    "makijaz": [
        ("przygotowanie", "Jak przygotować się do makijażu?",
         "Przyjdź z czystą, nawilżoną twarzą, bez makijażu. Jeśli masz zdjęcie inspiracji albo strój na okazję, pokaż je na początku wizyty."),
        ("przebieg", "Jak wygląda wizyta?",
         "Zaczynamy od rozmowy o okazji i efekcie, jaki chcesz uzyskać, potem przygotowanie skóry i makijaż."),
        ("pielegnacja", "Jak przedłużyć trwałość makijażu?",
         "Staraj się nie dotykać twarzy. Do poprawek w ciągu dnia przydadzą się bibułki matujące i pomadka."),
        ("przeciwwskazania", "Kiedy lepiej przełożyć wizytę?",
         "Gdy masz podrażnioną skórę, infekcję oka albo świeży zabieg na twarzy. Uczulenia na kosmetyki zgłoś przy zapisie."),
    ],
}
TEMATY_FAQ = {"przygotowanie": r"przygot|przed wizyt|przed zabieg", "przebieg": r"wygląda|przebieg|ile trwa|jak długo trwa",
              "pielegnacja": r"pielęgn|po zabieg|dbać|trwał", "przeciwwskazania": r"przeciwwsk|ciąż|alerg|uczul|nie można",
              "umawianie": r"umówi|zapis|rezerw|termin"}


def faq_z_danych(nick: str, c: dict) -> list[tuple[str, str]]:
    poz = []
    for q in c.get("faq") or []:
        a, p = tekst(q.get("a", "")), tekst(q.get("q", ""))
        if not a or not p or p in FAQ_ODRZUCONE.get(nick, []):
            continue
        if re.match(r"(Tak|Nie)\b", a):
            continue                                          # odpowiedz-twierdzenie o jej praktyce
        if re.search(r"\d\s*(godz|tygod|minut|dni|miesi)", a):
            continue                                          # liczby o czasie bez zrodla
        poz.append((p, a))
    return poz[:4]


def faq_pozycje(nick: str, c: dict, typ: str, booking: str, booking_label: str) -> tuple[list[tuple[str, str]], bool]:
    """Pytania z profilu; gdy mniej niz 3: standardowe dla typu uslugi (bez tematow, ktore profil juz ma) + umawianie.
    Zwraca (pozycje, czy_standardowe)."""
    z_profilu = faq_z_danych(nick, c)
    if len(z_profilu) >= 3:
        return z_profilu, False
    zestaw = FAQ_STANDARD.get(typ)                 # rzesy, brwi, pmu, makijaz; inne uslugi: tylko pytania z profilu
    if zestaw is None:
        return z_profilu if len(z_profilu) >= 2 else [], False
    ma = {t for t, w in TEMATY_FAQ.items() for q, _ in z_profilu if re.search(w, q, re.I)}
    out = list(z_profilu)
    for temat, q, a in zestaw:
        if temat not in ma:
            out.append((q, a))
    if "umawianie" not in ma:
        if booking:
            gdzie = booking_label or ("Booksy" if "booksy" in booking.lower() else "rezerwację online")
            out.append(("Jak się umówić?", f"Termin zarezerwujesz online przez {gdzie}. Pytania możesz też wysłać w wiadomości na Instagramie @{nick}."))
        else:
            out.append(("Jak się umówić?", f"Napisz wiadomość na Instagramie @{nick}: podaj usługę i dni, które Ci pasują."))
    return out[:6], True


def linie_bio(prof: dict, nazwa: str) -> tuple[list[str], str]:
    """Czysty tekst z bio: bez emoji, bez wezwan do dzialania, bez nazwy (jest juz w hero). Zwraca (linie, miejsce z pinezki)."""
    linie, miejsce = [], ""
    for l in (prof.get("biography") or "").splitlines():
        if "📍" in l:
            l, _, po_pinezce = l.partition("📍")
            miejsce = ", ".join(x for x in (tekst(y) for y in re.split(r"\|", EMOJI.sub("", po_pinezce))) if x)
        frag = [tekst(x) for x in re.split(r"\|", EMOJI.sub("", l))]
        frag = [x for x in frag if x]
        czyste = []
        for x in frag:
            if re.search(r"umów|booksy|link|rezerw|zapisy|\d[.,]\d\s*w\s*opini", x, re.I):
                continue
            if bez_ogonkow(x) in bez_ogonkow(nazwa) or bez_ogonkow(nazwa) in bez_ogonkow(x) and len(x) < len(nazwa) + 4:
                continue
            x = re.sub(r"(?<!\w)[A-ZĄĆĘŁŃÓŚŹŻ]{4,}(?!\w)", lambda m: m.group().lower(), x)
            czyste.append(x[:1].upper() + x[1:])
        if czyste:
            linie.append(". ".join(x.rstrip(".") for x in czyste) + ".")
    return linie, miejsce


def adres_z_danych(f: dict, miejsce_bio: str) -> str:
    u, m = f["address_street"], f["address_city"]
    if u["value"] and u["confidence"] >= 0.9 and m["value"] and m["confidence"] >= 0.9:
        mc = m["value"].title() if m["value"].isupper() else m["value"]
        return f'{Z.ulica(u["value"])}, {mc}'
    mm = re.match(r"^(.*\d+[a-z]?)\s+([A-ZŁŚŻŹĆ][\wąćęłńóśźż-]+)$", miejsce_bio)
    return f"{mm.group(1)}, {mm.group(2)}" if mm else miejsce_bio


def podpis_wiarygodny(sig: str, prof: dict, nick: str) -> bool:
    zr = bez_ogonkow(" ".join([prof.get("biography") or "", prof.get("full_name") or "", nick]))
    zr = re.sub(r"[^a-z]", "", zr)
    return bool(sig.strip()) and all(re.sub(r"[^a-z]", "", bez_ogonkow(w)) in zr for w in sig.split())


def miasto_potwierdzone(miasto: str, prof: dict, f: dict) -> str:
    zr = bez_ogonkow(" ".join([prof.get("biography") or "", prof.get("full_name") or "",
                                f["address_city"]["value"], f["address_street"]["value"]]))
    return miasto if miasto and bez_ogonkow(miasto)[:6] in zr else ""


def nick_wbr(nick: str) -> str:
    """@salon_przyklad_15: miejsce na zlamanie po kropce i podkresleniu (duzy krój na telefonie)."""
    return re.sub(r"([._])", r"\1<wbr>", H.escape(nick))


def fakty_o_mnie(nick: str) -> dict:
    """Fakty do tekstu O mnie: tylko dane profilu i pola briefu z confidence >= 0,9."""
    kl = KLIENTKI[nick]
    prof = json.loads((DANE / nick / "profile.json").read_text(encoding="utf-8"))
    brief = json.loads((DANE / nick / "brief_premium.json").read_text(encoding="utf-8"))
    f, c = brief["facts"], brief["content"]
    # bio bez czasow zabiegow, ocen i wezwan (model przerabial "1h 30 min" na slowa i przypinal do innej uslugi)
    czesci = [tekst(x) for l in (prof.get("biography") or "").splitlines() for x in re.split(r"\||•|·", EMOJI.sub("", l))]
    czesci = [x for x in czesci if x and not re.search(r"\d\s*(h|min|godz)|\d[.,]\d|opini|umów|booksy|link|zapis", x, re.I)]
    bio = " | ".join(czesci)
    bio = re.sub(r"(?<!\w)[A-ZĄĆĘŁŃÓŚŹŻ]{4,}(?!\w)", lambda m: m.group().lower(), bio)
    pelna = tekst(prof.get("full_name") or "")
    pelna = re.sub(r"(?<!\w)[A-ZĄĆĘŁŃÓŚŹŻ]{4,}(?!\w)", lambda m: m.group().lower(), pelna)
    _, exact, grupy = grupy_uslug(brief)
    uslugi = [g[0] for g in grupy if not GRUPY_POZA_PASKIEM.search(g[0])] if exact else \
        list(dict.fromkeys(zdanie(s.get("category") or s["name"]) for s in c["services"]))[:8]
    fakty = {"nazwa": kl["nazwa"], "Instagram": "@" + nick, "bio": bio, "nazwa konta na Instagramie": pelna,
             "miasto": miasto_potwierdzone(kl["miasto"], prof, f), "usługi z cennika": ", ".join(u.lower() for u in uslugi)}
    if f["address_city"]["value"] and f["address_city"]["confidence"] >= 0.9 and not fakty["miasto"]:
        fakty["miasto"] = f["address_city"]["value"]                 # ulica zostaje w kontakcie, w tekscie O mnie brzmiala jak formularz
    if f["booking_url"]["value"] and f["booking_url"]["confidence"] >= 0.9:
        fakty["rezerwacja"] = "online (" + ("Booksy" if "booksy" in f["booking_url"]["value"] else "link w profilu") + ")"
    tr = c.get("training") or {}
    if f.get("training_found") and (tr.get("body") or tr.get("points")):
        fakty["szkolenia"] = "prowadzi szkolenia"
    return fakty


# ---------------------------------------------------------------- posty z Instagrama
def podpis_posta(nick: str, plik: str) -> str:
    """Fragment podpisu, gdy czysty: pierwsze zdanie(a) do ~110 znakow, bez emoji, hasztagow, oznaczen, linkow, cen i telefonow."""
    p = DANE / nick / plik.replace(".jpg", ".txt")
    if not p.exists():
        return ""
    t = p.read_text(encoding="utf-8-sig", errors="replace")
    t = re.split(r"\s#|\n#|^#", t, maxsplit=1)[0]
    t = re.sub(r"\[[^\]]{0,40}\]", " ", t)                    # znaczniki scrapera, np. "[okładka reela]"
    t = tekst(t.replace("\n", " "))
    if not t or re.search(r"https?:|www\.|@|\d{3}[\s-]?\d{3}|zł|pln|\bcena\b|promoc|rabat", t, re.I):
        return ""
    lit = [ch for ch in t if ch.isalpha()]
    if len(lit) < 18 or sum(ch.isupper() for ch in lit) / len(lit) > 0.3:
        return ""
    zdania = re.findall(r"[^.!?…]+[.!?…]*", t)
    out = ""
    for z in zdania:
        if len(out) + len(z) > 110:
            break
        out += z
    out = out.strip()
    if len(out) < 18:
        cz = t[:105].rsplit(" ", 1)[0].rstrip(",;:--")
        out = cz + "…" if len(cz) >= 18 else ""
    return out


def posty_ig(nick: str, kand: list[dict], prace: list[dict], dst: Path, img: str) -> list[dict]:
    """3-6 ostatnich postow po filtrach jakosci (numer posta = kolejnosc w profilu, post-01 najnowszy). Zdjecie juz zapisane
    w pracach jest uzywane ponownie (bez nowych bajtow); pozostale jako 480x600 do 34 KB w img/posty/."""
    po_nr = sorted((k for k in kand if not ma_pasy(k["plik"])), key=lambda k: int(re.search(r"(\d+)", Path(k["plik"]).stem).group(1)))
    prace_po_zrodle = {p["zrodlo"]: p["plik"] for p in prace}
    (dst / "posty").mkdir(parents=True, exist_ok=True)
    for stary in (dst / "posty").glob("*.webp"):
        stary.unlink()
    out = []
    for k in po_nr[:6]:
        nazwa = Path(k["plik"]).name
        if nazwa in prace_po_zrodle:
            src, w, h = f"{img}prace/{prace_po_zrodle[nazwa]}", 720, 900
        else:
            im = ImageOps.fit(D.otworz(k["plik"]), (480, 600), Image.LANCZOS, centering=(0.5, 0.4))
            p = dst / "posty" / f"{Path(nazwa).stem}.webp"
            zapisz_webp(im, p, 34, (66, 60, 55, 50))
            src, w, h = f"{img}posty/{p.name}", 480, 600
        out.append({"src": src, "w": w, "h": h, "zrodlo": nazwa, "podpis": podpis_posta(nick, nazwa)})
    return out if len(out) >= 3 else []


def posty_html(nick: str, posty: list[dict], ig_url: str, img_av: str) -> str:
    li = []
    for i, p in enumerate(posty, 1):
        podp = (f'<span class="post-podpis"><b>{H.escape(nick)}</b> {esc(p["podpis"])}</span>') if p["podpis"] else ""
        li.append(f'   <li class="post"><a class="post-karta" href="{H.escape(ig_url)}" aria-label="Post {i} z {len(posty)} na profilu @{H.escape(nick)}">'
                  f'<span class="post-glowa"><img class="post-av" src="{img_av}" width="32" height="32" alt="" loading="lazy" decoding="async">'
                  f'<span class="post-nick">{H.escape(nick)}</span>{IG_ZNAK}</span>'
                  f'<span class="post-foto">{img_tag(p["src"], p["w"], p["h"], alt=f"Post z profilu @{nick}")}</span>{podp}</a></li>')
    return "\n".join(li)


# ---------------------------------------------------------------- spis, przejscia
def spis_hero(pozycje: list[tuple[str, str, str]]) -> str:
    """Markup {{SPIS}} w koncu hero: dokladnie w ustalonej postaci."""
    return ('<nav class="spis" aria-label="Spis treści">' +
            "".join(f'<a class="spis__poz" href="#{H.escape(i)}"><span class="spis__nr">{nr}</span>'
                    f'<span class="spis__tyt">{esc(t)}</span></a>' for nr, i, t in pozycje) + "</nav>")


def skroty(pozycje: list[tuple[str, str, str]], wciecie: str = "  ") -> str:
    return "\n".join(f'{wciecie}<a class="skrot" href="#{H.escape(i)}" data-skrot="{H.escape(i)}"><span class="skrot-nr">{nr}</span>'
                     f'<span class="skrot-tyt">{esc(t)}</span></a>' for nr, i, t in pozycje)


def przejscie_html(typ: str | None, przed_bg: str) -> tuple[str, str]:
    """(atrybut sekcji, warstwa przejscia). Warstwa jest ozdobna (aria-hidden) i dziala tylko z ruchem (CSS: html.sk-ruch)."""
    if not typ:
        return "", ""
    atr = f' data-przejscie="{typ}"'
    if typ == "kolo":
        return atr, (f' <div class="przejscie przejscie--kolo" data-anim="przejscie" aria-hidden="true" style="--przed:{przed_bg}">'
                     f'<span class="przejscie-rama"></span><span class="przejscie-kolo faktura"></span></div>')
    if typ == "plynnie":
        return atr, f' <div class="przejscie przejscie--plynnie" data-anim="przejscie" aria-hidden="true" style="--przed:{przed_bg}"></div>'
    return atr, ""                                          # kartka: sama sekcja (CSS sticky poprzedniej + cien)


def przerywnik_html(slowo: str) -> str:
    s = H.escape(slowo)
    tor = ISKRA.join(f"<span>{s}</span>" for _ in range(4))
    return f' <div class="przerywnik" data-anim="przerywnik" aria-hidden="true"><p class="przerywnik-tor">{tor}</p></div>'


# ---------------------------------------------------------------- budowa
def zbuduj_strone(nick: str, logo: bool, szablon_hero: str, wspolne: dict) -> dict:
    kl = KLIENTKI[nick]
    prof = json.loads((DANE / nick / "profile.json").read_text(encoding="utf-8"))
    brief = json.loads((DANE / nick / "brief_premium.json").read_text(encoding="utf-8"))
    f, c = brief["facts"], brief["content"]
    nazwa = kl["nazwa"]
    mn = kl["mnoga"] if isinstance(kl.get("mnoga"), bool) else liczba_mnoga(prof)     # weryfikator (agenci.py) albo bio
    ta = teksty_agentow(nick)                                  # copywriter (agenci.py): O mnie, kontakt, stopka, FAQ
    if ta.get("faq") is not None:
        c = dict(c, faq=[{"q": q, "a": a} for q, a in ta["faq"]])
    ig_url = brief.get("instagram_url") or f"https://instagram.com/{nick}"
    booking = f["booking_url"]["value"]
    cta_url = booking or f"https://ig.me/m/{nick}"
    cta_et = "Umów wizytę" if booking else "Napisz na Instagramie"
    lus = json.loads((KATALOG / "hero" / nick / "lusterko" / "lusterko.json").read_text(encoding="utf-8"))
    typ = kl.get("typ") or lus.get("typ") or D.typ_uslugi(prof)[0]
    slowo = Z.SLOWA.get(lus.get("typ", ""), Z.SLOWA["ogolny"])

    folder = nick + ("-logo" if logo else "")
    img = "img/" if not logo else f"../{nick}/img/"
    plik_wieczka = "warstwy/wieczko-logo.webp" if logo else "warstwy/wieczko.webp"
    dst_img = WYJ / nick / "img"

    # --- zdjecia (raz na klientke; wariant -logo korzysta z tych samych plikow)
    if nick not in wspolne:
        Z.kopiuj_obrazy(nick)
        kand = kandydaci_prac(nick)
        prace_info = zapisz_prace(nick, kand, dst_img) if len(kand) >= 3 else []
        zapas = pliki_hero(dst_img, "img/")
        _, _, grupy, _ = cennik_strony(brief, typ, kl.get("miasto") or "")
        zdj_u = zdjecia_grup(nick, grupy, prace_info, kand, dst_img, "img/")
        posty = posty_ig(nick, kand, prace_info, dst_img, "img/")
        wspolne[nick] = {"kand": kand, "prace": prace_info, "zapas": zapas, "zdj_u": zdj_u, "posty": posty}
    w = wspolne[nick]
    kand, prace_info = w["kand"], w["prace"]
    zmien = (lambda s: s.replace("img/", img, 1)) if logo else (lambda s: s)
    zapas = [dict(z, src=zmien(z["src"])) for z in w["zapas"]]
    zdj_u = [dict(z, src=zmien(z["src"])) if z else None for z in w["zdj_u"]]
    posty = [dict(p, src=zmien(p["src"])) for p in w["posty"]]
    miasto_ok = miasto_potwierdzone(kl["miasto"], prof, f)

    # --- jakie sekcje beda (kolejnosc strony) i ich tytuly w spisie
    op = opinie_z_danych(nick, f)
    tr = c.get("training") or {}
    ma_szkolenia = bool(f.get("training_found") and (tr.get("body") or tr.get("points")))
    faq, faq_std = faq_pozycje(nick, c, typ, booking, f.get("booking_label") or "")
    linie, miejsce = linie_bio(prof, nazwa)
    fakty = fakty_o_mnie(nick)
    akapity = OM.popraw_pisownie(ta["o_mnie"], fakty) if ta.get("o_mnie") else None
    if not akapity and (not BEZ_MODELU or (KATALOG / "dobor" / nick / "o_mnie.json").exists()):
        try:
            akapity = OM.tekst_o_mnie(nick, fakty, mn) if not BEZ_MODELU else _o_mnie_z_pamieci(nick, fakty, mn)
        except Exception as e:  # nigdy nie blokuje budowy
            print(f"   {nick}: O mnie z modelu nieudane ({type(e).__name__}), zostaje bio")
    ma_o_mnie = bool(akapity or linie or miejsce)
    h2_u, nota_u, wiersze_u, podglad_u, koniec_u = uslugi_html(brief, cta_url, cta_et, zdj_u, typ, kl.get("miasto") or "")

    kolejnosc = ["pasek"] + (["prace", "z-bliska"] if prace_info else []) + ["uslugi"] + (["o-mnie"] if ma_o_mnie else []) \
        + (["opinie"] if op else []) + (["szkolenia"] if ma_szkolenia else []) + (["faq"] if faq else []) \
        + (["instagram"] if posty else []) + ["kontakt", "stopka"]
    tytuly = {"prace": ("prace", "Nasze prace" if mn else "Moje prace"), "uslugi": ("uslugi", h2_u),
              "o-mnie": ("o-mnie", "O nas" if mn else "O mnie"), "opinie": ("opinie", "Opinie"),
              "szkolenia": ("szkolenia", zdanie(tr.get("heading") or "Szkolenia")), "faq": ("dobrze-wiedziec", "Dobrze wiedzieć"),
              "instagram": ("instagram", "Instagram"), "kontakt": ("kontakt", "Kontakt")}
    spis = [(dwie(k + 1), *tytuly[s]) for k, s in enumerate(x for x in kolejnosc if x in tytuly)]
    nr_sekcji = {s: dwie(k + 1) for k, s in enumerate(x for x in kolejnosc if x in tytuly)}

    # --- kolory: powierzchnie i rytm (wzor.py), przejscia
    plik_palety = KATALOG / "hero" / nick / "paleta_strony.json"
    tokeny = json.loads(plik_palety.read_text(encoding="utf-8"))["tokeny"]
    pw = WZ.powierzchnie(tokeny)
    rytm = WZ.rytm(kolejnosc, pw)
    prz = WZ.przejscia(kolejnosc, rytm, pw)
    kafle = WZ.kafle_klientki(nick, kl, logo, {n: pw[n] for n in set(rytm.values())}, dst_img, img)
    css_pw = WZ.css_powierzchni(pw, kafle)

    def ctx(sid: str) -> dict:
        p = pw[rytm[sid]]
        poprz = kolejnosc[kolejnosc.index(sid) - 1] if kolejnosc.index(sid) else None
        atr, warstwa = przejscie_html(prz.get(sid), pw[rytm[poprz]]["bg"] if poprz else tokeny["--tlo"])
        return {"PW": f"pw-{rytm[sid]}", "NAV": "light" if p["jasna"] else "dark", "PRZ_ATR": atr, "PRZEJSCIE": warstwa,
                "NR": numer(nr_sekcji.get(sid, ""))}

    przerywnik_w = "o-mnie" if ma_o_mnie else ("opinie" if op else None)
    html_sekcji: dict[str, str] = {}
    html_sekcji["pasek"] = plik_html("pasek.html", POZYCJE=pasek_html(brief, nick, miasto_ok, typ, kl.get("miasto") or ""),
                                     **{k: v for k, v in ctx("pasek").items() if k in ("PW", "NAV")})
    if prace_info:
        html_sekcji["prace"] = galeria_html(nick, mn, prace_info, zapas, img, {k: v for k, v in ctx("prace").items() if k in ("PW", "NAV", "NR")})
        html_sekcji["z-bliska"] = wstega_html(nick, prace_info, img, ctx("z-bliska"), "uslugi")
    html_sekcji["uslugi"] = plik_html("uslugi.html", H2=esc(h2_u), NOTA=nota_u, WIERSZE=wiersze_u, PODGLAD=podglad_u,
                                      KONIEC=koniec_u, **ctx("uslugi"))

    # --- o mnie / o nas: tekst z modelu (fakty), inaczej z bio; kolaz trzech zdjec w roznych formach
    if ma_o_mnie:
        if akapity:
            akap = [f"<p>{esc(a)}</p>" for a in akapity]
        else:
            uslugi_nazwy = [x.strip() for x in fakty["usługi z cennika"].split(",") if x.strip()]
            akap = [f"<p>{esc(l)}</p>" for l in linie]
            if uslugi_nazwy:
                akap.append(f"<p>W&nbsp;ofercie: {esc(', '.join(uslugi_nazwy))}.</p>")
        if miejsce:
            akap.append(f'<p class="o-mnie-miejsce">{esc(miejsce)}</p>')
        sig = c.get("about_signature") or ""
        if sig and bez_ogonkow(sig).strip() == bez_ogonkow(nazwa).strip():
            sig = nazwa                                       # 'Zaczarowane Rzesy' -> 'Zaczarowane Rzęsy' (pisownia z nazwy)
        if not mn and podpis_wiarygodny(sig, prof, nick):
            dl_ = " podpis--dlugi" if len(sig) > 12 else ""
            akap.append(f'<p class="podpis{dl_}" data-anim="podpis"><span class="podpis-tekst">{esc(sig)}</span>'
                        f'<svg class="podpis-kreska" viewBox="0 0 240 28" preserveAspectRatio="none" aria-hidden="true" focusable="false">'
                        f'<path data-anim="podpis-kreska" d="M3 19C46 9 104 5 156 11S220 24 237 9"/></svg></p>')
        kolaz = []
        pula_om = [{"src": f'{img}prace/{p["plik"]}', "w": 720, "h": 900} for p in prace_info[::-1][:3]] or zapas[:3]
        av_src = DANE / nick / "covers" / "profile-pic.jpg"
        formy = ["prost", "owal"]
        if av_src.exists():
            Image.open(av_src).convert("RGB").resize((240, 240), Image.LANCZOS).save(dst_img / "o-mnie.webp", "WEBP", quality=80, method=6)
            pula_om = pula_om[:2] + [{"src": img + "o-mnie.webp", "w": 240, "h": 240, "av": True}]
        formy.append("kolo")
        for k, (z, ks) in enumerate(zip(pula_om, formy), 1):
            alt = "Zdjęcie profilowe" if z.get("av") else f"Praca z profilu @{nick}"
            kolaz.append(f'   <figure class="om om--{k} ksztalt-{ks}">{img_tag(z["src"], z["w"], z["h"], alt=alt)}</figure>')
        html_sekcji["o-mnie"] = plik_html("o-mnie.html", H2="O nas" if mn else "O mnie", N=len(kolaz), KOLAZ="\n".join(kolaz),
                                          TEKST="\n".join("   " + a for a in akap),
                                          PRZERYWNIK=przerywnik_html(slowo) if przerywnik_w == "o-mnie" else "", **ctx("o-mnie"))

    # --- opinie
    if op:
        fr = [x for x in (fragment(t) for t in op) if x]
        frag_html = ""
        if fr:                                                   # ozdobny pasek tylko, gdy jest dosłowna fraza z oceną
            frag_html = (' <div class="opinie-fragmenty" data-anim="petla" data-kierunek="-1" aria-hidden="true">\n'
                         '  <div class="pasek-tor">\n   <p class="pasek-grupa">'
                         + "".join(f'<span class="frag">„{esc(x)}”</span>{ISKRA}' for x in fr)
                         + '</p>\n  </div>\n </div>')
        bq = "\n".join(f'    <blockquote class="cytat"><p>{esc(t)}</p></blockquote>' for t in op)
        html_sekcji["opinie"] = plik_html("opinie.html", H2="Co piszą klientki", FRAGMENTY=frag_html, OPINIE=bq,
                                          PRZERYWNIK=przerywnik_html(slowo) if przerywnik_w == "opinie" else "", **ctx("opinie"))

    # --- szkolenia
    if ma_szkolenia:
        czesci = []
        if tr.get("body"):
            czesci.append(f'<p>{esc(tr["body"])}</p>')
        if tr.get("points"):
            czesci.append('<ol class="szkolenia-lista">' + "".join(
                f'<li><span class="usluga-n">{dwie(i)}</span><span>{esc(p)}</span></li>' for i, p in enumerate(tr["points"], 1)) + "</ol>")
        czesci.append(f'<p><a class="przycisk" href="{H.escape(cta_url)}">Zapytaj o&nbsp;szkolenie</a></p>')
        html_sekcji["szkolenia"] = plik_html("szkolenia.html", H2=esc(zdanie(tr.get("heading") or "Szkolenia")),
                                             TRESC="\n".join("   " + x for x in czesci), **ctx("szkolenia"))

    # --- dobrze wiedziec
    if faq:
        poz = []
        for q, a in faq:
            poz.append(f'   <details class="faq-poz"><summary><span>{esc(q)}</span>{PLUS}</summary>'
                       f'<div class="faq-odp"><p>{esc(a)}</p></div></details>')
        nota = ("Ogólne wskazówki dla tego rodzaju zabiegów, szczegóły ustalisz przy zapisie. "
                '<mark class="todo">[DO POTWIERDZENIA]</mark> z&nbsp;właścicielką.') if faq_std else \
            '<mark class="todo">[DO POTWIERDZENIA]</mark> Odpowiedzi do&nbsp;sprawdzenia z&nbsp;właścicielką.'
        if PRODUKCJA:                       # strona idzie do klientki: bez znacznikow roboczych
            nota = "Ogólne wskazówki dla tego rodzaju zabiegów, szczegóły ustalisz przy zapisie." if faq_std else ""
        html_sekcji["faq"] = plik_html("faq.html", H2="Dobrze wiedzieć", POZYCJE="\n".join(poz), NOTA=nota, **ctx("faq"))

    # --- wiecej na @nick: karty postow
    if posty:
        html_sekcji["instagram"] = plik_html("wiecej.html", NICK=H.escape(nick), NICK_WBR=nick_wbr(nick), IG_URL=H.escape(ig_url),
                                             N=len(posty), POSTY=posty_html(nick, posty, ig_url, img + "avatar.webp"), **ctx("instagram"))

    # --- kontakt
    adres = adres_z_danych(f, miejsce)
    fakty_k = []
    if adres:
        mapa = ""
        if re.search(r"\d", adres):
            mapa = (f' <a href="https://www.google.com/maps/search/?api=1&amp;query={urllib.parse.quote(adres)}">Zobacz na&nbsp;mapie</a>')
        fakty_k.append(("Adres", f"{esc(adres)}{mapa}"))
    tel = f["phone"]["value"]
    if tel:
        fakty_k.append(("Telefon", f'<a href="tel:{re.sub(r"[^+0-9]", "", tel)}">{esc(tel)}</a>'))
    if f["email"]["value"]:
        fakty_k.append(("E-mail", f'<a href="mailto:{H.escape(f["email"]["value"])}">{esc(f["email"]["value"])}</a>'))
    if f.get("hours_found") and f.get("hours_note"):
        fakty_k.append(("Godziny", esc(f["hours_note"])))
    fakty_k.append(("Instagram", f'<a href="{H.escape(ig_url)}">@{H.escape(nick)}</a>'))
    if booking:
        fakty_k.append(("Rezerwacja", f'<a href="{H.escape(booking)}">{esc(f.get("booking_label") or "Rezerwacja online")}</a>'))
    dl = '   <dl class="kontakt-fakty">\n' + "\n".join(f"    <div><dt>{k}</dt><dd>{v}</dd></div>" for k, v in fakty_k) + "\n   </dl>"
    ct = tekst(ta.get("kontakt") or c.get("contact_text") or "")
    etykieta = "Umów wizytę w " + f["booking_label"] if booking and f.get("booking_label") else cta_et
    html_sekcji["kontakt"] = plik_html("kontakt.html", H2="Umów wizytę", TEKST=f'   <p class="kontakt-opis">{esc(ct)}</p>' if ct else "",
                                       CTA_URL=H.escape(cta_url), CTA_ETYKIETA=esc(etykieta), FAKTY=dl, IMG=img,
                                       IMG_WIECZKO=img + plik_wieczka,
                                       KADR_PX=Image.open(KATALOG / "hero" / nick / "lusterko" / "lusterko.webp").size[0], **ctx("kontakt"))
    dodatki = plik_html("dodatki.html", CTA_URL=H.escape(cta_url), CTA_ETYKIETA=esc(cta_et), PIERWSZY=esc(spis[0][2]),
                        SKROTY=skroty(spis, "  "))

    intro = tekst(ta.get("stopka") or c.get("footer_intro") or "")
    stopka = plik_html("stopka.html", NAZWA=esc(nazwa), SZER_EM=f"{max(3.6, Z.szerokosc_em(nazwa) * 0.98):.3f}", NICK=H.escape(nick), IG_URL=H.escape(ig_url),
                       INTRO=f'    <p class="stopka-intro">{esc(intro)}</p>' if intro else "", SKROTY=skroty(spis, "    "),
                       **ctx("stopka"))

    # --- kartka: sekcja przed "kartka" przykleja sie (sticky) i przygasa, gdy nowa na nia nachodzi
    for s, t in prz.items():
        if t == "kartka":
            a = kolejnosc[kolejnosc.index(s) - 1]
            html_sekcji[a] = re.sub(r"^(\s*(?:<!--.*?-->\s*)?<(?:section|footer)\b)", r"\1 data-kartka-pod", html_sekcji[a], count=1, flags=re.S)

    # --- hero: ten sam generator co w prototypie; {{SPIS}} (jesli szablon go ma) wypelniamy spisem sekcji
    spis_html = spis_hero(spis)
    if "spis" in inspect.signature(Z.zbuduj).parameters:          # hero v3: zbuduj_hero wstawia {{SPIS}} sam
        info = Z.zbuduj(nick, logo, szablon_hero, spis=spis_html)
    else:
        info = Z.zbuduj(nick, logo, szablon_hero.replace("{{SPIS}}", "<!--SPIS-->"))
    sciezka = WYJ / folder / "index.html"
    strona = sciezka.read_text(encoding="utf-8").replace("<!--SPIS-->", spis_html)
    ma_spis = spis_html in strona
    # komputer: pod H1 trzy fakty z jej danych (lewa polowa hero byla pusta, wlasciciel 11-12)
    fakty_h = fakty_hero(brief, typ, kl.get("miasto") or "", len(prace_info), len(op))
    if fakty_h:
        strona = re.sub(r'(<h1 id="hero-h1"[^>]*>.*?</h1>)', lambda m: m.group(1) + "\n    " + fakty_h, strona, count=1, flags=re.S)

    tresc = [SYMBOLE] + [html_sekcji[s] for s in kolejnosc if s not in ("kontakt", "stopka")] + [html_sekcji["kontakt"], dodatki]
    assert "<!--SEKCJE-->" in strona and "<!--STOPKA-->" in strona
    strona = strona.replace("<!--SEKCJE-->", "\n\n".join(tresc)).replace("<!--STOPKA-->", stopka)
    strona = strona.replace("</head>", f'<style id="sekcje-powierzchnie">{css_pw}</style>\n</head>', 1)
    if PRODUKCJA:
        strona = bez_znacznikow(strona)
    sciezka.write_text(strona, encoding="utf-8")

    ids = re.findall(r'\bid="([^"]+)"', strona)
    dup = sorted({i for i in ids if ids.count(i) > 1})
    return {"folder": folder, "nick": nick, "nazwa": nazwa, "logo": logo, "h1": info["h1"], "mnoga": mn,
            "sekcje": kolejnosc, "rytm": rytm, "przejscia": prz, "spis_w_hero": ma_spis, "spis": [s[2] for s in spis],
            "prace": prace_info, "opinie": len(op), "faq": len(faq), "faq_standardowe": faq_std,
            "o_mnie": ("agent" if ta.get("o_mnie") else "model") if akapity else "bio", "teksty_agenta": sorted(k for k in ("o_mnie", "kontakt", "stopka", "faq") if ta.get(k)),
            "posty": len(posty),
            "lustra_galerii": min(7, len(prace_info) + len(zapas)) if prace_info else 0,
            "zdjecia_uslug": [z["src"] if z else None for z in zdj_u],
            "zdjec_dostepnych": len(kand), "zrodlo_doboru": kand[0]["zrodlo_doboru"] if kand else "",
            "kontrast": {n: p["kontrast"] for n, p in pw.items()},
            "duplikaty_id": dup, "html_kb": round(sciezka.stat().st_size / 1024, 1)}


def bez_znacznikow(strona: str) -> str:
    """LUSTRO_PRODUKCJA=1 (automat na serwerze): stopka bez [DO UZUPEŁNIENIA]. Adres do prosb o usuniecie z LUSTRO_EMAIL;
    bez niego prosba idzie odpowiedzia na wiadomosc z linkiem (tak dostala strone). Zostawiony znacznik = blad budowy."""
    email = (os.environ.get("LUSTRO_EMAIL") or "").strip()
    gdzie = (f'na&nbsp;<a href="mailto:{H.escape(email)}">{H.escape(email)}</a>' if email
             else "w&nbsp;odpowiedzi na&nbsp;wiadomość z&nbsp;tym linkiem")
    strona = strona.replace('wyślij na&nbsp;<mark class="todo">[DO UZUPEŁNIENIA]</mark>', "wyślij " + gdzie)
    strona = re.sub(r'\s*<p class="faq-nota">\s*</p>', "", strona)
    if 'class="todo"' in strona:
        raise RuntimeError("tryb produkcyjny: na stronie zostal znacznik [DO ...]")
    return strona


def fakty_hero(brief: dict, typ: str, miasto: str, n_prac: int, n_opinii: int) -> str:
    """<ul class="fakty-hero">: do dwoch grup uslug z cena "od" i liczba prac albo opinii. Tylko komputer (CSS)."""
    _, ceny, grupy, _ = cennik_strony(brief, typ, miasto)
    poz = []
    if ceny:
        for tyt, opis, p in grupy:
            od = od_ceny(p)
            if od and not GRUPY_POZA_PASKIEM.search(tyt) and opis != CW.OPIS_ORIENT and len(tyt) <= 26:
                poz.append((od.replace("od ", ""), ("od · " if od.startswith("od ") else "") + tyt))
            if len(poz) == 2:
                break
    if n_prac >= 3:
        poz.append((str(n_prac), "prac z profilu"))
    elif n_opinii:
        poz.append((str(n_opinii), "opinii klientek" if n_opinii >= 5 else "opinie klientek"))
    if len(poz) < 2:
        return ""
    li = "".join(f'<li><span class="fakty-hero__w">{esc(w)}</span><span class="fakty-hero__o">{esc(o)}</span></li>' for w, o in poz[:3])
    return f'<ul class="fakty-hero" data-anim="fakty" aria-label="W skrócie">{li}</ul>'


def teksty_agentow(nick: str) -> dict:
    """hero/<nick>/teksty.json od copywritera (generuj.py -> agenci.copywriter). Brak pliku = teksty z danych i o_mnie.py."""
    p = KATALOG / "hero" / nick / "teksty.json"
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def _o_mnie_z_pamieci(nick: str, fakty: dict, mn: bool):
    """--bez-modelu: tylko pamiec (o_mnie.json), zadnych zapytan."""
    stary = OM._saldo_pozwala
    OM._saldo_pozwala = lambda: False
    try:
        return OM.tekst_o_mnie(nick, fakty, mn)
    finally:
        OM._saldo_pozwala = stary


def przerob_szablon(t: str) -> str:
    """hero.html w pamieci: Uslugi i stopka wychodza (zastepuja je sekcje), dochodzi sekcje.css, SplitText, DrawSVG i sekcje.js
    (po main.js, wiec kolejnosc skryptow hero i bezpiecznik zdejmujacy html.js zostaja bez zmian). {{SPIS}} zostaje:
    wypelnia go zbuduj_hero.zbuduj(spis=...) markupem ze spisu sekcji."""
    t, n1 = re.subn(r"<!-- =+ USLUGI I CENY.*?</main>", "<!--SEKCJE-->\n</main>", t, flags=re.S)
    t, n2 = re.subn(r'<footer class="stopka".*?</footer>', "<!--STOPKA-->", t, flags=re.S)
    css = '<link rel="stylesheet" href="{{WSP}}assets/css/hero.css">'
    js = '<script src="{{WSP}}assets/js/main.js" defer></script>'
    assert n1 == 1 and n2 == 1 and css in t and js in t, "szablon hero.html zmienil sie: dostosuj przerob_szablon"
    t = t.replace(css, css + '\n<link rel="stylesheet" href="{{WSP}}assets/css/sekcje.css">')
    return t.replace(js, js + '\n<script src="{{WSP}}assets/js/vendor/SplitText.min.js" defer></script>'
                              '\n<script src="{{WSP}}assets/js/vendor/DrawSVGPlugin.min.js" defer></script>'
                              '\n<script src="{{WSP}}assets/js/sekcje.js" defer></script>')


def minifikuj(p: Path) -> None:
    tekst_ = re.sub(r"/\*.*?\*/", "", p.read_text(encoding="utf-8"), flags=re.S)
    p.write_text(re.sub(r"\s*([{};])\s*", lambda m: m.group(1), re.sub(r"\s+", " ", tekst_)).strip(), encoding="utf-8")


def waga_wariantu(folder: str, nick: str) -> dict:
    """Wagi: (1) pliki faktycznie uzyte przez strone: html + obrazy z src/href/url() + CSS + JS (z Lenis) + kroje z CSS;
    (2) gorna granica: html + caly folder img klientki + wszystkie assets."""
    sciezka = WYJ / folder / "index.html"
    html_t = sciezka.read_text(encoding="utf-8")
    uzyte: set[Path] = set()
    for ref in re.findall(r'(?:src|href|data-src)="([^"#?]+)"', html_t) + re.findall(r'url\("?([^")]+)"?\)', html_t) \
            + re.findall(r"src=\\?\"([^\"\\]+lenis[^\"\\]*)", html_t):
        if ref.startswith(("http", "data:", "mailto:", "tel:")):
            continue
        p = (sciezka.parent / ref).resolve()
        if p.is_file():
            uzyte.add(p)
    for css in [p for p in list(uzyte) if p.suffix == ".css"]:
        for ref in re.findall(r'url\("?([^")]+)"?\)', css.read_text(encoding="utf-8")):
            if not ref.startswith(("http", "data:")):
                p = (css.parent / ref).resolve()
                if p.is_file():
                    uzyte.add(p)
    uzyte_b = sum(p.stat().st_size for p in uzyte) + sciezka.stat().st_size
    html_b = sciezka.stat().st_size
    img_b = sum(p.stat().st_size for p in (WYJ / nick / "img").rglob("*") if p.is_file())
    as_b = sum(p.stat().st_size for p in (WYJ / "assets").rglob("*") if p.is_file())
    return {"html_kb": round(html_b / 1024, 1), "uzyte_kb": round(uzyte_b / 1024, 1), "img_kb": round(img_b / 1024, 1),
            "assets_kb": round(as_b / 1024, 1), "gorna_granica_kb": round((html_b + img_b + as_b) / 1024, 1)}


def indeks(warianty: list[dict]) -> None:
    li = "\n".join(f'  <li><a href="{H.escape(w["folder"])}/index.html">{H.escape(w["nazwa"])}'
                   f'{" (logo na wieczku)" if w["logo"] else (" (nazwa na wieczku)" if KLIENTKI[w["nick"]]["wariant_logo"] else "")}</a>'
                   f'<span>@{H.escape(w["nick"])}</span></li>' for w in warianty)
    (WYJ / "index.html").write_text(f"""<!doctype html>
<html lang="pl"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex, nofollow"><title>Strony Moment w lustrze</title>
<style>@font-face{{font-family:"Hanken Grotesk";src:url(assets/fonts/hanken-grotesk-latin-ext-wght.woff2) format("woff2");font-weight:400 600;font-display:swap}}
body{{margin:0;padding:48px 20px;background:#2e211b;color:#fbf5ef;font:400 17px/26px "Hanken Grotesk",system-ui,sans-serif}}
main{{max-width:560px;margin:0 auto}}h1{{font:400 30px/34px Didot,"Times New Roman",serif;font-style:italic;margin:0 0 20px}}
ul{{list-style:none;margin:0;padding:0}}li{{display:flex;flex-direction:column;border-bottom:1px solid #54403a}}
a{{display:block;padding:14px 0 2px;color:#fbf5ef;font-weight:500;min-height:44px}}span{{color:#d9c9bd;font-size:14px;padding-bottom:12px}}</style></head>
<body><main><h1>Pełne strony</h1><ul>
{li}
</ul></main></body></html>
""", encoding="utf-8")


def main() -> None:
    global BEZ_MODELU
    BEZ_MODELU = "--bez-modelu" in sys.argv
    wybrane = [a for a in sys.argv[1:] if not a.startswith("-")]
    nicki = wybrane or list(KLIENTKI)
    szablon = przerob_szablon((KATALOG / "szablon" / "hero.html").read_text(encoding="utf-8"))
    WYJ.mkdir(exist_ok=True)
    Z.kopiuj_wspolne()
    minifikuj(WYJ / "assets" / "css" / "sekcje.css")
    warianty, wspolne = [], {}
    for nick in nicki:
        warianty.append(zbuduj_strone(nick, False, szablon, wspolne))
        if KLIENTKI[nick]["wariant_logo"]:
            warianty.append(zbuduj_strone(nick, True, szablon, wspolne))
    for w in warianty:
        w["waga"] = waga_wariantu(w["folder"], w["nick"])
    if not wybrane:
        indeks(warianty)
    raport = WYJ / "raport.json"
    stare = {}
    if wybrane and raport.exists():
        try:
            stare = {w["folder"]: w for w in json.loads(raport.read_text(encoding="utf-8"))}
        except Exception:
            stare = {}
    stare.update({w["folder"]: w for w in warianty})
    raport.write_text(json.dumps(list(stare.values()), ensure_ascii=False, indent=1), encoding="utf-8")
    for w in warianty:
        print(f"{w['folder']:30s} {','.join(w['sekcje'])} | rytm {'/'.join(w['rytm'][s][:4] for s in w['sekcje'])} | "
              f"o mnie {w['o_mnie']} faq {w['faq']}{'s' if w['faq_standardowe'] else ''} posty {w['posty']} | spis w hero {w['spis_w_hero']} | "
              f"uzyte {w['waga']['uzyte_kb']} KB (granica {w['waga']['gorna_granica_kb']}) | dup {w['duplikaty_id']}")
    print("O mnie (routemux):", json.dumps(OM.KOSZT, ensure_ascii=False))


if __name__ == "__main__":
    main()
