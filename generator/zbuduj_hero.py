#!/usr/bin/env python3
"""Generator prototypu hero (sciezka A, statyczny HTML/CSS). Nic nie publikuje, nie wola zadnych modeli.

    python zbuduj_hero.py            # wszystkie 6 wariantow + prototyp/index.html
    python zbuduj_hero.py salon_przyklad_26   # jeden nick
    python zbuduj_hero.py --spis 8      # test okladki: probny spis tresci N pozycji (normalnie pusty; wypelnia go zbuduj_strone.py)

Wejscie: szablon/hero.html, assets/css/hero.css, assets/js/*.js, assets/fonts/,
         hero/<nick>/{warstwy,tlo,lusterko}, dane klientek z beauty-site-factory/data/<nick>/.
Wyjscie: prototyp/assets (wspolne), prototyp/<nick>/ (+ img/), prototyp/<nick>-logo/ (wariant z logo na wieczku),
         prototyp/index.html, prototyp/wagi.json.
Wszystkie teksty pochodza z danych profilu (profile.json, brief_premium.json); brak danych = pomijamy element.
"""
from __future__ import annotations

import gzip
import html as H
import json
import math
import os
import re
import shutil
import sys
from pathlib import Path

from PIL import Image, ImageFont

KATALOG = Path(__file__).resolve().parent
DANE = Path(os.environ.get("BSF_DATA", str(Path(__file__).resolve().parent / "dane")))
WYJ = KATALOG / "prototyp"

# Nazwy robocze, miasto (mianownik) i miejscownik do H1. Miasto jest sprawdzane w bio / adresie.
KLIENTKI = {
    "salon_przyklad_15": {"nazwa": "Salon Przyklad", "miasto": "Kraków", "wariant_logo": True},
    "salon_przyklad_12": {"nazwa": "Studio Przyklad", "miasto": "Szczebrzeszyn", "wariant_logo": True},
    "salon_przyklad_14": {"nazwa": "Brwi Przyklad", "miasto": "Koszalin", "wariant_logo": True},
    "salon_przyklad_26": {"nazwa": "Rzesy Przyklad", "miasto": "Kraków", "wariant_logo": True},
}
# klientki dodane generatorem (generuj.py) trzymamy w pliku, nie w kodzie
REJESTR = KATALOG / "klientki.json"
if REJESTR.exists():
    KLIENTKI.update(json.loads(REJESTR.read_text(encoding="utf-8")))

MIEJSCOWNIK = {"Kraków": "Krakowie", "Szczebrzeszyn": "Szczebrzeszynie", "Koszalin": "Koszalinie", "Tychy": "Tychach",
               "Poznań": "Poznaniu", "Warszawa": "Warszawie", "Wrocław": "Wrocławiu", "Łódź": "Łodzi", "Gdańsk": "Gdańsku",
               "Gdynia": "Gdyni", "Sopot": "Sopocie", "Szczecin": "Szczecinie", "Bydgoszcz": "Bydgoszczy", "Lublin": "Lublinie",
               "Białystok": "Białymstoku", "Katowice": "Katowicach", "Kielce": "Kielcach", "Opole": "Opolu", "Rzeszów": "Rzeszowie",
               "Olsztyn": "Olsztynie", "Toruń": "Toruniu", "Radom": "Radomiu", "Sosnowiec": "Sosnowcu", "Częstochowa": "Częstochowie",
               "Gliwice": "Gliwicach", "Zabrze": "Zabrzu", "Bytom": "Bytomiu", "Rybnik": "Rybniku", "Bielsko-Biała": "Bielsku-Białej",
               "Elbląg": "Elblągu", "Płock": "Płocku", "Wałbrzych": "Wałbrzychu", "Tarnów": "Tarnowie", "Chorzów": "Chorzowie",
               "Kalisz": "Kaliszu", "Legnica": "Legnicy", "Słupsk": "Słupsku", "Zielona Góra": "Zielonej Górze",
               "Gorzów Wielkopolski": "Gorzowie Wielkopolskim", "Nowy Sącz": "Nowym Sączu", "Otwock": "Otwocku", "Łęczna": "Łęcznej",
               "Kraśnik": "Kraśniku", "Lębork": "Lęborku", "Piaseczno": "Piasecznie", "Pruszków": "Pruszkowie", "Zamość": "Zamościu",
               "Siedlce": "Siedlcach", "Konin": "Koninie", "Leszno": "Lesznie", "Gniezno": "Gnieźnie", "Piła": "Pile",
               "Inowrocław": "Inowrocławiu", "Grudziądz": "Grudziądzu", "Jaworzno": "Jaworznie", "Mysłowice": "Mysłowicach",
               "Ostrów Wielkopolski": "Ostrowie Wielkopolskim", "Stargard": "Stargardzie", "Świnoujście": "Świnoujściu",
               "Kołobrzeg": "Kołobrzegu", "Zakopane": "Zakopanem", "Wieliczka": "Wieliczce", "Skawina": "Skawinie"}


def miejscownik(miasto: str) -> str | None:
    """'w Krakowie': slownik, potem tylko bezpieczne koncowki; nic pewnego = None (H1 bez miasta)."""
    if miasto in MIEJSCOWNIK:
        return MIEJSCOWNIK[miasto]
    for koniec, zamiana in (("ów", "owie"), ("ń", "niu"), ("in", "inie"), ("yn", "ynie"), ("ice", "icach"), ("sk", "sku"),
                            ("ck", "cku"), ("wa", "wie"), ("ia", "ii")):
        if " " not in miasto and miasto.endswith(koniec):
            return miasto[: len(miasto) - len(koniec)] + zamiana
    return None

# Ognisko zdjecia koncowego (ulamki zdjecia). Domyslnie srodek pola oka z lusterko.json.
# brwi_przyklad: pole oka = cale zdjecie (brew + oko, przechylenie 40), wiec ognisko recznie, tak by oko i brew
# miescily sie w widoku koncowym 390x844 i 430x932 (sprawdzane ponizej).
OGNISKO_RECZNE = {"salon_przyklad_14": (0.46, 0.52)}
# Pole samego oka (ulamki zdjecia), tylko gdy pole z lusterko.json obejmuje cala brew; do kontroli widocznosci.
OKO_RECZNE = {"salon_przyklad_14": (0.28, 0.50, 0.85, 0.80)}

# Tabele ukladu kol, sekcja 6 briefu: (left %, dy w R, r w R). Wysoki: 390x844, niski: 390x720.
WYSOKI = {"S1": (6.6, -1.164, 0.60), "S2": (87.9, 1.211, 0.53), "S3": (92.3, -0.987, 0.46), "S4": (9.7, 0.974, 0.41),
          "S5": (96.7, -0.221, 0.24), "S6": (5.3, -0.289, 0.20), "S7": (61.1, 1.175, 0.14)}
NISKI = {"S1": (7.4, -1.094, 0.56), "S2": (88.4, 1.133, 0.50), "S3": (94.8, -0.738, 0.40), "S4": (7.8, 0.782, 0.36),
         "S5": (94.7, -0.063, 0.20), "S6": (7.1, -0.279, 0.18), "S7": (64.0, 1.126, 0.12)}
R_WYSOKI, R_NISKI, SZER_REF = 140.4, 136.8, 390.0
EKRANY = {"390x844": (390, 844), "390x720": (390, 720), "360x640": (360, 640), "430x932": (430, 932)}

# Decyzja wlasciciela: cieply braz na wszystkich stronach. Kolor lakieru i jasnych sekcji dalej wynika z feedu.
TLO_DOMYSLNE = {"--tlo": "#2e211b", "--tlo-jasne": "#54403a", "--tlo-ciemne": "#1c130f"}
# Duze slowo nad puderniczka: krotkie i znane, wiec dlugosc nazwy klientki niczego nie psuje.
SLOWA = {"rzesy": "Rzęsy", "brwi": "Brwi", "pmu": "Brwi", "makijaz": "Makijaż", "paznokcie": "Paznokcie",
         "wlosy": "Włosy", "ogolny": "Uroda"}
_FONT_SLOWA = ImageFont.truetype(str(KATALOG / "baza" / "fonty" / "bodoni-moda-italic-pl.ttf"), 400)


def szerokosc_em(slowo: str) -> float:
    """Szerokosc slowa w em: CSS dobiera z niej rozmiar tak, by slowo miescilo sie na ekranie."""
    return _FONT_SLOWA.getlength(slowo) / 400


def linie_h1(tekst: str, fs: float = 37.4, szer: float = 350) -> int:
    """Ile linii zajmie H1 na telefonie 390 px (Bodoni, zawijanie po slowach). Trzy linie wchodza na kola, wiec wtedy h1--dlugi."""
    spacja, n, x = szerokosc_em(" ") * fs, 1, 0.0
    for s in tekst.split():
        w = szerokosc_em(s) * fs
        if x and x + spacja + w > szer:
            n, x = n + 1, w
        else:
            x = x + spacja + w if x else w
    return n


# ---------------------------------------------------------------- teksty
def nb(t: str) -> str:
    """Twarde spacje po jednoliterowych spojnikach i przed 'zl' (sierotki)."""
    t = re.sub(r"(?<!\w)([iwzouaIWZOUA]) ", lambda m: m.group(1) + "\u00a0", t)
    return re.sub(r" (zł)(?!\w)", "\u00a0zł", t)


def esc(t: str) -> str:
    return H.escape(nb(t), quote=True).replace("\u00a0", "&nbsp;")


def zdanie(s: str) -> str:
    """Pola z OCR zapisane wielkimi literami -> 'Zdanie'. Zwykly tekst zostaje, pierwsza litera duza."""
    t = re.sub(r"\s+", " ", s).strip().replace("*", "")
    lit = [c for c in t if c.isalpha()]
    if len(lit) > 3 and all(c.isupper() for c in lit):
        t = t.lower()
    return t[:1].upper() + t[1:]


def cena(s: str) -> str:
    t = re.sub(r"\s+", " ", s).strip()
    t = re.sub(r"\s*(ZŁ|zł|PLN|pln)(?!\w)\.?", " zł", t)
    t = re.sub(r"(?<=\d)\s*-\s*(?=\d)", "-", t)
    if re.fullmatch(r"\d[\d\s-.,/]*", t):                 # sama liczba z OCR ('1000', '200-500'): dopisz walute
        t += " zł"
    if re.fullmatch(r"0+(?:[.,]0+)?\s*zł", t):              # 'Konsultacja 0.00 zł' (QA 2026-11-11): bez ceny zerowej
        return "bezpłatnie"
    return t


def ulica(t: str) -> str:
    """'budowlanych 166' -> 'Budowlanych 166' (OCR i model gubia wielka litere)."""
    t = (t or "").strip()
    return t[:1].upper() + t[1:]


def wczytaj(nick: str):
    prof = json.loads((DANE / nick / "profile.json").read_text(encoding="utf-8"))
    brief = json.loads((DANE / nick / "brief_premium.json").read_text(encoding="utf-8"))
    return prof, brief


def bez_ogonkow(t: str) -> str:
    tr = str.maketrans("ąćęłńóśźżĄĆĘŁŃÓŚŹŻ", "acelnoszzACELNOSZZ")
    return t.translate(tr).lower()


def h1_z_danych(brief: dict, prof: dict, miasto: str) -> str:
    """H1 = hero_kicker po sprawdzeniu, ze miasto wystepuje w bio lub adresie. 'Usluga - Miasto' -> 'Usluga w Miescie'."""
    kicker = brief["content"]["hero_kicker"].strip()
    f = brief["facts"]
    zrodlo = bez_ogonkow(" ".join([prof.get("biography") or "", prof.get("full_name") or "", prof.get("username") or "",
                                   f["address_city"]["value"], f["address_street"]["value"]]))
    m = [c.strip() for c in re.split(r"\s+[--]\s*(?:w\s+)?", kicker, maxsplit=1)]
    usluga = re.sub(r"\s+w\s+[A-ZŁŚŻŹĆ][\w-]*(\s+[A-ZŁŚŻŹĆ][\w-]*)?$", "", m[0]).strip()   # 'X w Tychach' -> 'X'
    loc = miejscownik(miasto) if miasto else None
    if not miasto or bez_ogonkow(miasto)[:6] not in zrodlo or not loc:
        return usluga                                 # bez pewnego miasta: same uslugi
    przyimek = "we" if re.match(r"[WwFf][^aeiouyąęó]", loc) else "w"     # we Wrocławiu, we Włocławku
    return f"{usluga} {przyimek} {loc}"               # miasto zawsze z bio/adresu, nie dzielnica z modelu


def linia_faktow(nazwa: str, brief: dict, miasto: str) -> str:
    """Nazwa, adres, miasto -> Nazwa, miasto -> Nazwa. Adres tylko przy confidence >= 0,9."""
    f = brief["facts"]
    ul, mc = f["address_street"], f["address_city"]
    czesci = [nazwa]
    if ul["value"] and ul["confidence"] >= 0.9 and mc["value"] and mc["confidence"] >= 0.9:
        czesci += [ulica(ul["value"]), mc["value"].title() if mc["value"].isupper() else mc["value"]]
    elif bez_ogonkow(miasto) not in bez_ogonkow(nazwa):
        czesci.append(miasto)
    return ", ".join(czesci)


# ---------------------------------------------------------------- cennik
CHEVRON = ('<svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" '
           'stroke-linejoin="round" aria-hidden="true"><path d="M3.5 6l4.5 4.5L12.5 6"/></svg>')


def wiersze(pozycje: list[tuple[str, str]]) -> str:
    out = []
    for nazwa, c in pozycje:
        out.append(f'   <li><span class="n">{esc(nazwa)}</span>' + (f'<span class="c">{esc(c)}</span>' if c else "") + "</li>")
    return '  <ul class="cennik">\n' + "\n".join(out) + "\n  </ul>"


def cennik_html(brief: dict, cta_url: str) -> tuple[str, str]:
    """Zwraca (naglowek H2, HTML). exact: grupy z cenami; draft: same nazwy uslug i linia o cenniku."""
    f, c = brief["facts"], brief["content"]
    grupy: list[tuple[str, list[tuple[str, str]]]] = []
    if f["pricing_mode"] == "exact" and f["pricing_groups"]:
        for g in f["pricing_groups"]:
            poz = [(zdanie(i["name"]), cena(" / ".join(i["prices"]))) for i in g["items"] if i.get("name")]
            if poz:
                grupy.append((zdanie(g["title"]), poz))
        h2 = "Usługi i ceny"
        nota = '  <p class="uslugi-nota">Ceny z&nbsp;Instagrama</p>'
        koniec = ""
    else:
        po_kategorii: dict[str, list] = {}
        for s in c["services"]:
            po_kategorii.setdefault(s.get("category") or "Usługi", []).append((zdanie(s["name"]), ""))
        grupy = list(po_kategorii.items())
        h2 = "Usługi"
        nota = ""
        koniec = f'  <p class="uslugi-brak">Cennik: <a href="{H.escape(cta_url)}">napisz na&nbsp;Instagramie</a></p>'
    razem = sum(len(p) for _, p in grupy)
    czesci = [nota] if nota else []
    for i, (tytul, poz) in enumerate(grupy):
        if razem > 12:
            czesci.append(f'  <details class="grupa" data-anim="grupa"{" open" if i == 0 else ""}>\n'
                          f'   <summary><h3>{esc(tytul)}</h3>{CHEVRON}</summary>\n{wiersze(poz)}\n  </details>')
        else:
            czesci.append(f'  <div class="grupa" data-anim="grupa">\n   <h3>{esc(tytul)}</h3>\n{wiersze(poz)}\n  </div>')
    if koniec:
        czesci.append(koniec)
    return h2, "\n".join(czesci)


# ---------------------------------------------------------------- kola, tokeny, kontrola
def rgb_trojka(hex_: str) -> str:
    h = hex_.lstrip("#")
    return " ".join(str(int(h[i:i + 2], 16)) for i in (0, 2, 4))


def kola_html(katalog_tlo: Path, img: str, kola: dict) -> str:
    out = []
    for w in kola["wpisy"]:
        m = w["miejsce"]
        lw, dyw, rw = WYSOKI[m]
        ln, dyn, rn = NISKI[m]
        dxw = (lw / 100 - 0.5) * SZER_REF / R_WYSOKI
        dxn = (ln / 100 - 0.5) * SZER_REF / R_NISKI
        dlug = math.hypot(dxw, dyw)
        ox, oy = dxw / dlug * (1.2 + rw), dyw / dlug * (1.2 + rw)
        styl = (f"--lw:{lw};--dyw:{dyw};--rw:{rw};--ln:{ln};--dyn:{dyn};--rn:{rn};--dxw:{dxw:.3f};--dxn:{dxn:.3f};"
                f"--ox:{ox:.3f};--oy:{oy:.3f};--krycie:{w['krycie']}")
        puste = w.get("puste") or not w.get("plik")
        if puste:
            out.append(f'    <div class="kolo kolo--puste kolo--{m.lower()}" data-anim="kolo" data-miejsce="{m}" style="{styl}"></div>')
            continue
        px = Image.open(katalog_tlo / w["plik"]).size
        out.append(f'    <div class="kolo kolo--{m.lower()}" data-anim="kolo" data-miejsce="{m}" style="{styl}">'
                   f'<img src="{img}tlo/{w["plik"]}" width="{px[0]}" height="{px[1]}" alt="" decoding="async"></div>')
    return "\n".join(out)


def _luminancja(hex_: str) -> float:
    c = [int(hex_.lstrip("#")[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    c = [x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4 for x in c]
    return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]


def kontrast(a: str, b: str) -> float:
    la, lb = sorted((_luminancja(a), _luminancja(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def tokeny_hero(t: dict) -> dict:
    """Role kolorow hero liczone z palety strony (paleta_beauty): akcent czytelny na mroku i tokeny okladki.
    Stare palety (bez --przelamanie) dostaja zastepstwa, wiec szablon dziala tez dla nich."""
    tlo = t["--tlo"]
    papier = t.get("--papier", t.get("--jasny"))
    kandydaci = [t.get(k) for k in ("--przelamanie", "--akcent", "--guzik", "--papier2")] + [papier]
    akcent_mrok = next(k for k in kandydaci if k and kontrast(k, tlo) >= 4.5)
    przel = t.get("--przelamanie") or t.get("--lakier")
    na_przel = t.get("--na-przelamaniu") or (t["--atrament"] if kontrast(t["--atrament"], przel) >= kontrast(papier, przel) else papier)
    return {"--papier": papier, "--akcent-mrok": akcent_mrok, "--przelamanie": przel, "--na-przelamaniu": na_przel,
            "--guzik": t.get("--guzik") or t.get("--lakier"), "--guzik-tekst": t.get("--guzik-tekst") or t["--atrament"]}


def kontrola_kontrastu(t: dict) -> dict:
    """Pary tekstu hero (WCAG): tekst >= 4,5, ksztalt przycisku na tle >= 3."""
    pary = {"papier/tlo": ("--papier", "--tlo", 4.5), "papier/tlo-jasne": ("--papier", "--tlo-jasne", 4.5),
            "akcent-mrok/tlo": ("--akcent-mrok", "--tlo", 4.5), "guzik-tekst/guzik": ("--guzik-tekst", "--guzik", 4.5),
            "guzik/tlo": ("--guzik", "--tlo", 3.0), "na-przelamaniu/przelamanie": ("--na-przelamaniu", "--przelamanie", 4.5),
            "szept-jasny/tlo": ("--szept-jasny", "--tlo", 4.5)}
    return {n: (round(kontrast(t[a], t[b]), 2), prog) for n, (a, b, prog) in pary.items() if a in t and b in t}


def inicjaly(nazwa: str) -> str:
    slowa = [s for s in re.split(r"[\s&+]+", nazwa) if s and s[0].isalpha() and len(s) > 1]
    return "".join(s[0].upper() for s in slowa[:2]) or nazwa[:1].upper()


def wzor_tla(nazwa: str, kolor: str, krycie: float = 0.095) -> str:
    """Kafel wzoru tla: monogram klientki (inicjaly kursywa Bodoni) w ukladzie przesunietym o pol kafla, jasny na ciemnym.
    Kafel 150 px CSS w podwojnej rozdzielczosci, WebP z kanalem alfa (ok. 1-2 KB), wstawiany inline jako data URI."""
    import base64
    import io
    from PIL import ImageDraw
    bok = 300
    znak = inicjaly(nazwa)
    font = ImageFont.truetype(str(KATALOG / "baza" / "fonty" / "bodoni-moda-italic-pl.ttf"), 62 if len(znak) > 1 else 72)
    r, g, b = (int(kolor.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4))
    a = int(round(255 * krycie))
    im = Image.new("RGBA", (bok, bok), (r, g, b, 0))
    d = ImageDraw.Draw(im)
    for cx, cy in ((bok * 0.25, bok * 0.25), (bok * 0.75, bok * 0.75)):
        d.text((cx, cy), znak, font=font, fill=(r, g, b, a), anchor="mm")
    buf = io.BytesIO()
    im.save(buf, "WEBP", lossless=True, method=6)
    return "data:image/webp;base64," + base64.b64encode(buf.getvalue()).decode()


def tokeny_css(nick: str, paleta: dict, kola_dir: Path, lus: dict, fx: float, fy: float, slowo: str,
               nazwa: str | None = None) -> str:
    # paleta strony dobrana do klientki (paleta_beauty.py); bez niej stary staly braz
    plik_palety = KATALOG / "hero" / nick / "paleta_strony.json"
    strony = json.loads(plik_palety.read_text(encoding="utf-8"))["tokeny"] if plik_palety.exists() else TLO_DOMYSLNE
    t = {**paleta["tokeny"], **strony}
    t.update(tokeny_hero(t))
    dekl = [f"{k}:{v}" for k, v in t.items()]
    for k in ("--papier", "--papier2", "--akcent", "--przelamanie", "--atrament", "--na-przelamaniu", "--guzik", "--akcent-mrok"):
        if k in t:
            dekl.append(f"{k}-rgb:{rgb_trojka(t[k])}")
    dekl.append(f"--slowo-em:{szerokosc_em(slowo):.4f}")
    if nazwa:
        dekl.append(f"--winieta-em:{szerokosc_em(nazwa):.4f}")
        dekl.append(f'--wzor:url("{wzor_tla(nazwa, t["--papier"])}")')
    for k in ("--tlo", "--tlo-ciemne", "--lakier", "--jasny"):
        dekl.append(f"{k}-rgb:{rgb_trojka(t[k])}")
    kadr = lus["kadr_w_ulamkach"]
    Wp, Hp = lus["zdjecie_wymiary"]
    dekl += [f"--Wp:{Wp}", f"--Hp:{Hp}", f"--fx:{fx:.4f}", f"--fy:{fy:.4f}",
             f"--cx0:{(kadr[0] + kadr[2]) / 2:.4f}", f"--cy0:{(kadr[1] + kadr[3]) / 2:.4f}",
             f"--kx0:{kadr[0]}", f"--ky0:{kadr[1]}", f"--kx1:{kadr[2]}", f"--ky1:{kadr[3]}",
             f'--lustro-mini:url("{lus["miniatura_inline"]}")']
    return ":root{" + ";".join(dekl) + "}" + maska_slowa_css(kola_dir)


def maska_slowa_css(kola_dir: Path) -> str:
    """Kontur slowa tylko nad kolami: maska z kol (te same wzory co left/top .kolo w hero.css, osobno dla
    telefonu wysokiego, niskiego, tabletu i desktopu). Bez tego ciemna krawedz kladzie sie na cale slowo."""
    plik = kola_dir / "kola.json"
    if not plik.exists():
        return ""
    wpisy = json.loads(plik.read_text(encoding="utf-8"))["wpisy"]
    if not wpisy:
        return ""

    def zestaw(tryb: str) -> str:
        d = []
        for i, w in enumerate(wpisy, 1):
            m = w["miejsce"]
            l, dy, r = (WYSOKI if tryb in ("w", "dw") else NISKI)[m]
            if tryb in ("w", "n"):
                x = f"calc({l} * 1vw)"
            else:
                ref = R_WYSOKI if tryb == "dw" else R_NISKI
                x = f"calc(var(--cx) + {(l / 100 - 0.5) * SZER_REF / ref:.3f} * var(--R))"
            d += [f"--m{i}x:{x}", f"--m{i}y:calc(var(--cy) + {dy} * var(--R))", f"--m{i}r:calc({r} * var(--R))"]
        return ";".join(d)

    warstwy = ",".join(
        f"radial-gradient(circle var(--m{i}r) at calc(var(--m{i}x) - var(--slowo-x)) "
        f"calc(var(--m{i}y) - var(--slowo-top) + var(--slowo-pad)),#000 calc(100% - 1px),#0000 100%)"
        for i in range(1, len(wpisy) + 1))
    niskie = ";".join(f"--m{i}r:0px" for i, w in enumerate(wpisy, 1) if w["miejsce"] in ("S5", "S6", "S7"))
    sel = "html.js .slowo--kontur"
    css = (f"@media (prefers-reduced-motion:no-preference) and (min-height:501px){{"
           f"{sel}{{{zestaw('w')};-webkit-mask:{warstwy};mask:{warstwy};-webkit-mask-repeat:no-repeat;mask-repeat:no-repeat}}"
           f"@media (min-aspect-ratio:1/2){{{sel}{{{zestaw('n')}}}}}"
           f"@media (min-width:768px){{{sel}{{{zestaw('dn')}}}}}"
           f"@media (min-width:1100px){{{sel}{{{zestaw('dw')}}}}}")
    if niskie:
        css += f"@media (max-height:600px){{{sel}{{{niskie}}}}}"
    return css + "}"


def oko_widoczne(w: int, h: int, lus: dict, fx: float, fy: float, bbox, ay: float = 0.42) -> bool:
    """Replika formul CSS (scena, telefon): czy prostokat bbox (ulamki zdjecia) lezy w widocznej czesci okladki koncowej:
    w kole zdjecia, ponizej gornej krawedzi ekranu i nad pasem ze spisem (gora pasa = luk - 15,5vw - 8 px, hero.css)."""
    Wp, Hp = lus["zdjecie_wymiary"]
    arcy, rF = 0.665 * h, 0.8839 * w
    pas = arcy - 0.155 * w - 8
    cyF = arcy - rF
    sf = max(w / Wp, arcy / Hp)
    Pw, Ph = Wp * sf, Hp * sf
    clamp = lambda lo, v, hi: max(lo, min(v, hi))
    left = clamp(w - Pw, w / 2 - fx * Pw, 0)
    top = clamp(arcy - Ph, arcy * ay - fy * Ph, 0)
    x0, y0, x1, y1 = bbox
    for x, y in ((x0, y0), (x1, y0), (x0, y1), (x1, y1)):
        sx, sy = left + x * Pw, top + y * Ph
        if not (0 <= sx <= w and sy >= 0 and sy <= pas and (sx - w / 2) ** 2 + (sy - cyF) ** 2 <= rF ** 2):
            return False
    return True


# ---------------------------------------------------------------- budowa
def zrob_ziarno(nadpisz: bool = False) -> None:
    """Ziarno tla jako bitmapa (kafel 192 px pokazywany jako 96 px CSS, rzadkie drobiny 1 px), jasne i ciemne.
    Bitmapa zamiast szumu SVG (feTurbulence): filtr SVG liczy sie przy kazdym rastrze kafla warstwy i kosztowal klatki."""
    import io
    import numpy as np
    for nazwa, kolor, ziarno in (("ziarno-j.webp", 255, 7), ("ziarno-c.webp", 0, 11)):
        cel = KATALOG / "assets" / "css" / nazwa
        if cel.exists() and not nadpisz:
            continue
        rng = np.random.default_rng(ziarno)
        bok = 192
        a = np.zeros((bok, bok), np.uint8)
        m = rng.random((bok, bok)) < 0.08
        a[m] = (rng.random(int(m.sum())) * 0.22 * 255 + 0.06 * 255).astype(np.uint8) // 8 * 8
        im = Image.fromarray(np.dstack([np.full((bok, bok), kolor, np.uint8)] * 3 + [a]), "RGBA")
        b = io.BytesIO()
        im.save(b, "WEBP", lossless=True, method=6)
        cel.write_bytes(b.getvalue())


def kopiuj_wspolne() -> None:
    zrob_ziarno()
    for rel in ("assets/css", "assets/js"):
        dst = WYJ / rel
        dst.mkdir(parents=True, exist_ok=True)
        for p in (KATALOG / rel).iterdir():
            if p.is_file():
                shutil.copy2(p, dst / p.name)
    css = dst.parent / "css" / "hero.css"                             # minifikacja bez narzedzi: komentarze i odstepy
    tekst = re.sub(r"/\*.*?\*/", "", css.read_text(encoding="utf-8"), flags=re.S)
    css.write_text(re.sub(r"\s*([{};])\s*", lambda m: m.group(1), re.sub(r"\s+", " ", tekst)).strip(), encoding="utf-8")
    vendor = KATALOG / "assets" / "js" / "vendor"                      # gsap, ScrollTrigger, lenis (przypiete wersje)
    if vendor.is_dir():
        dst = WYJ / "assets" / "js" / "vendor"
        dst.mkdir(parents=True, exist_ok=True)
        for p in vendor.iterdir():
            if p.is_file():
                shutil.copy2(p, dst / p.name)
    dst = WYJ / "assets" / "fonts"
    dst.mkdir(parents=True, exist_ok=True)
    for p in (KATALOG / "assets" / "fonts").iterdir():
        if p.is_file():
            shutil.copy2(p, dst / p.name)


def kopiuj_obrazy(nick: str) -> Path:
    src, dst = KATALOG / "hero" / nick, WYJ / nick / "img"
    # wieczko, rama i podstawa w lakierze z palety strony (lokalnie, bez AI); liczone raz, potem zapamietane w paleta.json
    try:
        import puderniczka
        puderniczka.dostroj_do_palety(nick, KLIENTKI.get(nick, {}).get("nazwa"))
    except Exception as e:                                    # brak bazy warstw itp.: zostaje lakier z feedu
        print(f"{nick}: wieczko bez dostrojenia do palety ({type(e).__name__}: {e})", file=sys.stderr)
    for podkat in ("warstwy", "tlo", "lusterko"):
        (dst / podkat).mkdir(parents=True, exist_ok=True)
        for p in (src / podkat).iterdir():
            if p.suffix == ".webp":
                shutil.copy2(p, dst / podkat / p.name)
    # awatar z profilu; scraper nie zawsze go pobiera, wtedy kadr z lusterka (to samo zdjecie, ktore otwiera scene)
    zrodlo_av = DANE / nick / "covers" / "profile-pic.jpg"
    if not zrodlo_av.exists():
        zrodlo_av = src / "lusterko" / "lusterko.webp"
    av = Image.open(zrodlo_av).convert("RGB").resize((96, 96), Image.LANCZOS)
    av.save(dst / "avatar.webp", "WEBP", quality=82, method=6)
    return dst


SPIS_PROBNY = [("prace", "Moje prace"), ("uslugi", "Usługi i ceny"), ("opinie", "Opinie"), ("o-mnie", "O mnie"),
               ("szkolenia", "Szkolenia"), ("faq", "Dobrze wiedzieć"), ("instagram", "Więcej na @{nick}"), ("kontakt", "Kontakt")]


def spis_probny(nick: str, ile: int) -> str:
    """Tylko do testow samego hero (--spis N): ten sam markup, ktory wstawia zbuduj_strone.py."""
    poz = "".join(f'<a class="spis__poz" href="#{k}"><span class="spis__nr">{i:02d}</span>'
                  f'<span class="spis__tyt">{esc(t.format(nick=nick)).replace(".", ".<wbr>").replace("_", "_<wbr>")}</span></a>' for i, (k, t) in enumerate(SPIS_PROBNY[:ile], 1))
    return f'<nav class="spis" aria-label="Spis treści">{poz}</nav>'


def wydanie(h1: str, miasto: str) -> tuple[str, str]:
    """Linia pod winieta okladki: usluga (H1 bez miasta) i miasto w mianowniku; bez miasta w H1 zostaje sama usluga."""
    loc = miejscownik(miasto) if miasto else None
    if loc and re.search(rf"\s+we?\s+{re.escape(loc)}$", h1):
        return re.sub(rf"\s+we?\s+{re.escape(loc)}$", "", h1), miasto
    return h1, ""


def zbuduj(nick: str, logo: bool, szablon: str, spis: str = "") -> dict:
    """spis: markup <nav class="spis"> dla stanu koncowego (wypelnia zbuduj_strone.py); sam hero ma pusty spis."""
    kl = KLIENTKI[nick]
    prof, brief = wczytaj(nick)
    src = KATALOG / "hero" / nick
    paleta = json.loads((src / "warstwy" / "paleta.json").read_text(encoding="utf-8"))
    kola = json.loads((src / "tlo" / "kola.json").read_text(encoding="utf-8"))
    lus = json.loads((src / "lusterko" / "lusterko.json").read_text(encoding="utf-8"))
    slowo = SLOWA.get(lus.get("typ", ""), SLOWA["ogolny"])

    nazwa, miasto = kl["nazwa"], kl["miasto"]
    h1 = h1_z_danych(brief, prof, miasto)
    if len(h1) > 48:                                         # dlugi opis wchodzilby na kola: zostaje pierwsza usluga i miasto
        h1 = re.sub(r"(,| i ).*?(?= w [A-ZŁŚŻŹĆ])", "", h1, count=1)
    f = brief["facts"]
    booking = f["booking_url"]["value"]
    ig_url = brief.get("instagram_url") or f"https://instagram.com/{nick}"
    dm_url = f"https://ig.me/m/{nick}"                       # wiadomosc na Instagramie, z nicka
    cta_url = booking or dm_url
    cta_et = "Umów wizytę" if booking else "Napisz na Instagramie"

    pole = lus["pole_oka_w_ulamkach"]
    fx, fy = OGNISKO_RECZNE.get(nick, ((pole["x0"] + pole["x1"]) / 2, (pole["y0"] + pole["y1"]) / 2))
    bbox = OKO_RECZNE.get(nick, (pole["x0"], pole["y0"], pole["x1"], pole["y1"]))

    folder = nick + ("-logo" if logo else "")
    katalog_wyj = WYJ / folder
    katalog_wyj.mkdir(parents=True, exist_ok=True)
    img = "img/" if not logo else f"../{nick}/img/"
    plik_wieczka = "warstwy/wieczko-logo.webp" if logo else "warstwy/wieczko.webp"
    if logo and not (src / "warstwy" / "wieczko-logo.webp").exists():
        raise SystemExit(f"{nick}: brak wieczko-logo.webp")

    h2, uslugi = cennik_html(brief, cta_url)
    kadr_px = Image.open(src / "lusterko" / "lusterko.webp").size[0]
    tytul = f"{nazwa} | {h1}"
    opis = f"{nazwa}: {h1}. Podgląd strony przygotowany z profilu @{nick}."
    jsonld = {"@context": "https://schema.org", "@type": "BeautySalon", "name": nazwa, "description": h1,
              "sameAs": [ig_url]}
    if f["address_street"]["value"] and f["address_street"]["confidence"] >= 0.9:
        jsonld["address"] = {"@type": "PostalAddress", "streetAddress": ulica(f["address_street"]["value"]),
                             "addressLocality": f["address_city"]["value"] or miasto, "addressCountry": "PL"}
    elif miasto:
        jsonld["address"] = {"@type": "PostalAddress", "addressLocality": miasto, "addressCountry": "PL"}

    ctx = {
        "TYTUL": esc(tytul), "OPIS": esc(opis), "THEME": (json.loads((src / "paleta_strony.json").read_text(encoding="utf-8"))["tokeny"]["--tlo"]
                  if (src / "paleta_strony.json").exists() else TLO_DOMYSLNE["--tlo"]), "SLOWO": H.escape(slowo),
        "WSP": "../", "IMG": img, "IMG_WIECZKO": img + plik_wieczka,
        "TOKENY": tokeny_css(nick, paleta, src / "tlo", lus, fx, fy, slowo, nazwa),
        "JSONLD": json.dumps(jsonld, ensure_ascii=False).replace("</", "<\\/"),
        "NICK": H.escape(nick), "NAZWA": esc(nazwa), "IG_URL": H.escape(ig_url), "CTA_URL": H.escape(cta_url),
        "CTA_ETYKIETA": esc(cta_et), "H1": esc(h1), "H1_KLASA": "h1--dlugi" if len(h1) >= 36 or linie_h1(h1) > 2 else "",
        "LINIA": esc(linia_faktow(nazwa, brief, miasto)),
        "USLUGA": esc(wydanie(h1, miasto)[0]), "MIASTO": esc(wydanie(h1, miasto)[1]),
        "WINIETA_KLASA": "winieta--dluga" if szerokosc_em(nazwa) > 10.3 else "",
        "SPIS": spis,
        "KOLA": kola_html(src / "tlo", img, kola), "KADR_PX": kadr_px,
        "WP": lus["zdjecie_wymiary"][0], "HP": lus["zdjecie_wymiary"][1],
        "USLUGI_H2": h2, "USLUGI": uslugi,
    }
    out = szablon
    for k, v in ctx.items():
        out = out.replace("{{" + k + "}}", str(v))
    ostatki = re.findall(r"\{\{[A-Z_]+\}\}", out)
    if ostatki:
        raise SystemExit(f"{nick}: niepodmienione znaczniki {ostatki}")
    (katalog_wyj / "index.html").write_text(out, encoding="utf-8")

    oko = {e: oko_widoczne(w, h, lus, fx, fy, bbox) for e, (w, h) in EKRANY.items()}
    plik_palety = src / "paleta_strony.json"
    tk = {**paleta["tokeny"], **(json.loads(plik_palety.read_text(encoding="utf-8"))["tokeny"] if plik_palety.exists() else TLO_DOMYSLNE)}
    tk.update(tokeny_hero(tk))
    return {"folder": folder, "nick": nick, "nazwa": nazwa, "logo": logo, "h1": h1, "oko_widoczne": oko,
            "kontrast": kontrola_kontrastu(tk), "lakier": tk.get("--lakier"),
            "cta": [cta_et, cta_url], "linia": linia_faktow(nazwa, brief, miasto),
            "zdjec": kola["zdjec"], "kola": [w["miejsce"] for w in kola["wpisy"]], "fx_fy": [round(fx, 3), round(fy, 3)]}


def kb(p: Path) -> float:
    return p.stat().st_size / 1024


def wagi(nick: str, logo: bool) -> dict:
    """Paczka 1 (stan zamkniety): wieczko, zawias zamkniety, kola, poswiata inline, kroje. Paczka 2: reszta sceny."""
    d = WYJ / nick / "img"
    wieczko = d / "warstwy" / ("wieczko-logo.webp" if logo else "wieczko.webp")
    kola = sum(kb(p) for p in (d / "tlo").glob("S*.webp"))
    kroje = kb(WYJ / "assets/fonts/bodoni-moda-italic-pl.woff2") + kb(WYJ / "assets/fonts/hanken-grotesk-latin-ext-wght.woff2")
    p1 = kb(wieczko) + kb(d / "warstwy/zawias-zamkniety.webp") + kola + kroje
    p2 = sum(kb(d / x) for x in ("warstwy/rama-lusterka.webp", "warstwy/podstawa.webp", "warstwy/zawias.webp",
                                  "lusterko/zdjecie.webp", "lusterko/lusterko.webp"))
    html_kb = kb(WYJ / (nick + ("-logo" if logo else "")) / "index.html")
    vendor = sorted((WYJ / "assets/js/vendor").glob("*.js"))
    vendor_kb = sum(kb(p) for p in vendor)
    js_wlasny = kb(WYJ / "assets/js/hero.js") + kb(WYJ / "assets/js/main.js")
    css_js = kb(WYJ / "assets/css/hero.css") + js_wlasny + vendor_kb
    gz = lambda p: len(gzip.compress(p.read_bytes(), 9)) / 1024
    js_gz = sum(gz(p) for p in vendor) + gz(WYJ / "assets/js/hero.js") + gz(WYJ / "assets/js/main.js")
    avatar = kb(d / "avatar.webp")
    calosc = p1 + p2 + html_kb + css_js + avatar
    css_gz = gz(WYJ / "assets/css/hero.css")
    # Definicje z briefu: paczka 1 = wieczko, zawias zamkniety, kola, kroje, poswiata; paczka 2 = rama, podstawa, zawias otwarty,
    # zdjecie; skrypty w zadnej z nich. Pokazujemy tez wersje ze skryptami (po gzip, tak jak poleci z hostingu) i bez kompresji.
    return {"paczka1_kb": round(p1, 1), "paczka1_budzet_kb": 250, "paczka2_kb": round(p2, 1), "paczka2_budzet_kb": 350,
            "paczka1_z_js_gzip_kb": round(p1 + js_gz, 1), "paczka1_z_js_surowe_kb": round(p1 + vendor_kb + js_wlasny, 1),
            "scena_kb": round(p1 + p2, 1), "scena_z_js_css_gzip_kb": round(p1 + p2 + js_gz + css_gz, 1), "scena_budzet_kb": 600,
            "html_kb": round(html_kb, 1), "css_js_kb": round(css_js, 1), "vendor_js_kb": round(vendor_kb, 1),
            "wlasny_js_kb": round(js_wlasny, 1), "js_gzip_kb": round(js_gz, 1), "avatar_kb": round(avatar, 1),
            "calosc_kb": round(calosc, 1), "calosc_budzet_kb": 1536,
            "lusterko_webp_kb": round(kb(d / "lusterko/lusterko.webp"), 1)}


def indeks(warianty: list[dict]) -> None:
    pozycje = []
    for w in warianty:
        etykieta = w["nazwa"] + (" (logo na wieczku)" if w["logo"] else (" (nazwa na wieczku)" if KLIENTKI[w["nick"]]["wariant_logo"] else ""))
        pozycje.append(f'  <li><a href="{H.escape(w["folder"])}/index.html">{H.escape(etykieta)}</a>'
                       f'<span class="m">@{H.escape(w["nick"])}</span></li>')
    tresc = f"""<!doctype html>
<html lang="pl">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex, nofollow">
<title>Prototypy hero Moment w lustrze</title>
<link rel="preload" href="assets/fonts/belleza-latin-ext.woff2" as="font" type="font/woff2" crossorigin>
<style>
@font-face{{font-family:"Belleza";src:url(assets/fonts/belleza-latin-ext.woff2) format("woff2");font-display:swap}}
@font-face{{font-family:"Hanken Grotesk";src:url(assets/fonts/hanken-grotesk-latin-ext-wght.woff2) format("woff2");font-weight:400 600;font-display:swap}}
:root{{color-scheme:dark}}
*{{box-sizing:border-box}}
body{{margin:0;background:#272a2e;color:#f4f3f1;font:400 17px/26px "Hanken Grotesk",system-ui,sans-serif;padding:48px 20px}}
main{{max-width:560px;margin:0 auto}}
h1{{font:400 30px/34px Belleza,Optima,Candara,"Segoe UI",sans-serif;margin:0 0 20px}}
p{{color:#c1c4c8;margin:0 0 28px}}
ul{{list-style:none;margin:0;padding:0}}
li{{display:flex;flex-direction:column;border-bottom:1px solid #44484c}}
li a{{display:block;padding:14px 0 2px;color:#f4f3f1;font-weight:500;min-height:44px}}
.m{{color:#c1c4c8;font-size:14px;line-height:20px;padding-bottom:12px}}
a:focus-visible{{outline:2px solid #c8b48c;outline-offset:3px}}
</style>
</head>
<body>
<main>
 <h1>Prototypy hero</h1>
 <p>Pierwszy ekran i początek sekcji Usługi i ceny. Do przeglądu faz: dopisz do adresu ?faza=zamknieta, ?faza=otwarta lub ?faza=koncowa.</p>
 <ul>
{chr(10).join(pozycje)}
 </ul>
</main>
</body>
</html>
"""
    (WYJ / "index.html").write_text(tresc, encoding="utf-8")


def main() -> None:
    argv = sys.argv[1:]
    ile_spis = 0
    if "--spis" in argv:                                      # test samego hero: probny spis N pozycji (domyslnie pusty)
        i = argv.index("--spis")
        ile_spis = int(argv[i + 1])
        del argv[i:i + 2]
    wybrane = [a for a in argv if not a.startswith("-")]
    nicki = wybrane or list(KLIENTKI)
    szablon = (KATALOG / "szablon" / "hero.html").read_text(encoding="utf-8")
    WYJ.mkdir(exist_ok=True)
    kopiuj_wspolne()
    warianty = []
    for nick in nicki:
        kopiuj_obrazy(nick)
        spis = spis_probny(nick, ile_spis) if ile_spis else ""
        warianty.append(zbuduj(nick, False, szablon, spis))
        if KLIENTKI[nick]["wariant_logo"]:
            warianty.append(zbuduj(nick, True, szablon, spis))
    for w in warianty:
        w["wagi"] = wagi(w["nick"], w["logo"])
    if not wybrane:
        indeks(warianty)
    (WYJ / "wagi.json").write_text(json.dumps(warianty, ensure_ascii=False, indent=1), encoding="utf-8")
    for w in warianty:
        g = w["wagi"]
        print(f"{w['folder']:28s} H1: {w['h1']!r} | CTA: {w['cta'][0]} | kola {','.join(w['kola'])} | "
              f"P1 {g['paczka1_kb']}/250  P2 {g['paczka2_kb']}/350  scena+JS gz {g['scena_z_js_css_gzip_kb']}/600  calosc {g['calosc_kb']}/1536 KB "
              f"(JS {g['vendor_js_kb']}+{g['wlasny_js_kb']}, gzip {g['js_gzip_kb']}; P1+JS gz {g['paczka1_z_js_gzip_kb']}) | oko {w['oko_widoczne']}")
        slabe = {n: k for n, (k, prog) in w["kontrast"].items() if k < prog}
        if slabe:
            print(f"   UWAGA kontrast ponizej progu: {slabe}")


if __name__ == "__main__":
    main()
