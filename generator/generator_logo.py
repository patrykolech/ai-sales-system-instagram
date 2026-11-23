#!/usr/bin/env python3
"""Logo dla kazdej klientki przez routemux: odtworzone ze zdjec albo wygenerowane od zera.

Decyzja wlasciciela: logo ma byc zawsze. Jesli jest widoczne na awatarze lub okladkach relacji,
model rysuje je od nowa w wysokiej rozdzielczosci. Jesli go nie ma, powstaje nowe z nazwy.

Uzycie:
    python generator_logo.py --profil salon_przyklad_14 --nazwa "Brwi Przyklad" --typ brows
    python generator_logo.py --nazwa "Studio Lucja" --branza "rzesy i brwi" --styl monogram

--profil szuka logo w danych z Instagrama. --nick czyta wyniki starego generatora z output_v3.

Model rysuje logo czarne na bialym tle. Reszta jest lokalna i darmowa: przyciecie,
przezroczystosc i wersje kolorystyczne. Tani model wizyjny czyta napis z gotowego
obrazu i odrzuca logo z literowka, bo modele obrazow potrafia przekrecic nazwe.
"""
from __future__ import annotations

import argparse
import base64
import glob
import hashlib
import io
import json
import os
import re
import sys
import unicodedata
import urllib.error
import urllib.request
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageOps

KATALOG = Path(__file__).resolve().parent
PROJEKT = KATALOG.parent
DANE = Path(os.environ.get("BSF_DATA", str(Path(__file__).resolve().parent / "dane")))
PLIK_KLUCZA = PROJEKT / "klucz_routemux.txt"
API = "https://api.routemux.com/v1"
MODEL_OBRAZU = "openai/gpt-image-2.5-flare"
MODEL_KONTROLI = "google/gemini-3.5-flash-lite"
# Obrazy najpierw przez Kuai (2026-11-15: ten sam gpt-image za 0,05 CNY zamiast ok. 0,019 USD), RouteMux zostaje zapasem.
# Klucz: KUAI_OBRAZY_KEY w .env automatu (serwer) albo klucz_kuai_obrazy.txt obok klucz_routemux.txt (PC).
API_KUAI = "https://kuaiapi.net/v1"
PLIK_KLUCZA_KUAI = PROJEKT / "klucz_kuai_obrazy.txt"
# Trzeci zapas (16.11): BestAIPrice, ten sam gpt-image-2.5-flare, odpowiedz b64. BESTAIPRICE_KEY albo klucz_bestaiprice.txt.
API_BAP = "https://bestaiprice.com/gateway/v1"
PLIK_KLUCZA_BAP = PROJEKT / "klucz_bestaiprice.txt"
UA = "Mozilla/5.0 (generator-logo)"          # Cloudflare przed czescia bramek odrzuca zapytania bez przegladarkowego UA

# Bryf z skilla design (scripts/logo/search.py) proponuje dla beauty pismo odreczne,
# roz i zloto. Tak wygladaloby kazde logo w branzy, wiec trzymamy sie jednego koloru
# i ksztaltow, ktore da sie tez wytloczyc na wieczku puderniczki.
STYLE = {
    "monogram": "a refined monogram of the initials {inicjaly} in a high-contrast didone serif, "
                "enclosed in one thin perfect circle, with the full name \"{nazwa}\" set small in "
                "widely spaced serif capitals directly below the circle",
    "wordmark": "a pure typographic wordmark: the name \"{nazwa}\" set in an elegant high-contrast "
                "editorial serif with one subtle custom letter detail, no symbol, on one or two lines",
    "symbol": "a single minimal continuous-line symbol inspired by {motyw}, drawn with one even thin "
              "stroke and no fills, centred above the name \"{nazwa}\" in a clean refined serif",
    "stempel": "a circular seal: the name \"{nazwa}\" curved cleanly around the inside of a thin ring, "
               "with one tiny minimal {motyw} line symbol in the centre",
}
MOTYWY = {
    "lashes": "a single eyelash curve", "brows": "an arched eyebrow stroke", "nails": "an almond nail shape",
    "hair": "a flowing strand of hair", "makeup": "a lipstick silhouette", "skin": "a drop of serum",
    "pmu": "a fine brow stroke",
}

PROMPT = """Professional logo design for a beauty studio named "{nazwa}" ({branza}).
Design: {styl}.
The name must be spelled exactly, letter by letter: {litery}. Keep every Polish diacritic mark.
Style: minimalist, luxury, refined, timeless, thin elegant lines, generous spacing, vector flat design.
Colors: solid pure black only, on a pure white background.
Requirements: one logo, centred, with wide empty margins, crisp edges, no gradient, no shadow, no texture.
NOT: photorealistic, 3D, mockup, photograph, clip art, multiple logos, tagline, any words other than the name, watermark."""

PROMPT_ODTWORZENIA = """This is a small, low-quality image of a beauty studio's existing logo; it may be light on a dark background.
Redraw exactly this logo as a clean, sharp master file, like a careful vector trace. Copy the design, do not reinterpret it:
the same typefaces (a serif stays serif, a handwritten script stays the same kind of script, a sans-serif stays sans-serif),
the same letter case and letter spacing, the same arrangement of the words, the same symbol if there is one, thin lines and
frames as equally thin outlines (never filled boxes), and every smaller line of text (for example a tagline) exactly as shown.
The main name reads, letter by letter: {litery}.
Colors: solid pure black only, on a pure white background (whatever is light on a dark original becomes black). No photo,
no texture, no gradient, no shadow, no background fill. One logo, centred, with wide empty margins, crisp edges."""


def klucz() -> str:
    if (os.environ.get("ROUTEMUX_API_KEY") or "").strip():         # serwer: klucz z .env automatu
        return os.environ["ROUTEMUX_API_KEY"].strip()
    if PLIK_KLUCZA.exists():
        tresc = PLIK_KLUCZA.read_text(encoding="utf-8-sig").strip()
        if tresc:
            return tresc.splitlines()[0].strip()
    return (os.environ.get("ROUTEMUX_API_KEY") or "").strip()


def klucz_kuai() -> str:
    if (os.environ.get("KUAI_OBRAZY_KEY") or "").strip():
        return os.environ["KUAI_OBRAZY_KEY"].strip()
    if PLIK_KLUCZA_KUAI.exists():
        tresc = PLIK_KLUCZA_KUAI.read_text(encoding="utf-8-sig").strip()
        if tresc:
            return tresc.splitlines()[0].strip()
    return ""


def klucz_bap() -> str:
    if (os.environ.get("BESTAIPRICE_KEY") or "").strip():
        return os.environ["BESTAIPRICE_KEY"].strip()
    if PLIK_KLUCZA_BAP.exists():
        tresc = PLIK_KLUCZA_BAP.read_text(encoding="utf-8-sig").strip()
        if tresc:
            return tresc.splitlines()[0].strip()
    return ""


def dostawcy_obrazow(model: str) -> list[tuple[str, str, str, str]]:
    """(nazwa, adres API, klucz, model) w kolejnosci prob. Kuai i BestAIPrice nazywaja modele bez "openai/"."""
    lista = []
    goly = model.split("/", 1)[1] if model.startswith("openai/") else ""
    if klucz_kuai() and goly:
        lista.append(("Kuai", API_KUAI, klucz_kuai(), goly))
    if klucz():
        lista.append(("RouteMux", API, klucz(), model))
    if klucz_bap() and goly:
        lista.append(("BestAIPrice", API_BAP, klucz_bap(), goly))
    return lista


def _obraz_z_odpowiedzi(d: dict) -> bytes:
    el = d["data"][0]
    if el.get("b64_json"):
        return splaszcz(base64.b64decode(el["b64_json"]))
    with urllib.request.urlopen(urllib.request.Request(el["url"], headers={"User-Agent": UA}), timeout=120) as odp:
        return splaszcz(odp.read())


def _po_kolei(model: str, wyslij) -> bytes:
    """wyslij(api, klucz, model) -> odpowiedz JSON. Blad u jednego dostawcy = nastepny; ostatni blad idzie wyzej."""
    dostawcy = dostawcy_obrazow(model)
    if not dostawcy:
        raise ValueError("brak klucza do modelu obrazu")
    for i, (nazwa, api, kl, m) in enumerate(dostawcy):
        try:
            return _obraz_z_odpowiedzi(wyslij(api, kl, m))
        except (urllib.error.URLError, TimeoutError, OSError, KeyError, ValueError, IndexError) as e:
            if i == len(dostawcy) - 1:
                raise
            kod = getattr(e, "code", "") or type(e).__name__
            print(f"   obraz przez {nazwa}: {kod} -> {dostawcy[i + 1][0]}")
    raise AssertionError("nieosiagalne")


def zapytanie(sciezka: str, dane: dict, limit: int = 240) -> dict:
    """RouteMux. Wizja (/chat/completions: szukanie logo, odczyt napisu) idzie najpierw przez ByteCatCode (agenci.py),
    bo 11.11 o 01:56 takie zapytanie do RouteMux zawislo na 30 min; RouteMux zostaje zapasem i jedynym od obrazow."""
    if sciezka == "/chat/completions":
        odp = _wizja_bytecat(dane)
        if odp is not None:
            return odp
    return _zapytanie_routemux(sciezka, dane, limit)


def _szukaj_logo(dane: dict, limit: int = 90) -> dict:
    """Szukanie logo: tylko ByteCatCode (jedno zapytanie, max 60 s), gdy jest klucz. Brak odpowiedzi = brak logo, bez
    RouteMux (tam zawislo 11.11). Bez klucza ByteCatCode (PC bez agentow) - RouteMux jak dawniej."""
    try:
        import agenci
        ma_bytecat = agenci.dostepne()
    except Exception:  # noqa: BLE001
        ma_bytecat = False
    if not ma_bytecat:
        return _zapytanie_routemux("/chat/completions", dane, limit)
    odp = _wizja_bytecat(dane)
    if odp is None:
        raise RuntimeError("szukanie logo: ByteCatCode bez odpowiedzi")
    return odp


def _wizja_bytecat(dane: dict) -> dict | None:
    try:
        import agenci
        if not agenci.dostepne():
            return None
        tekst, obrazy = "", []
        for m in dane.get("messages", []):
            for c in m.get("content", []) if isinstance(m.get("content"), list) else []:
                if c.get("type") == "text":
                    tekst += c["text"]
                elif c.get("type") == "image_url":
                    surowe = base64.b64decode(c["image_url"]["url"].split(",", 1)[1])
                    obrazy.append(agenci._jpeg(Image.open(io.BytesIO(surowe)).convert("RGB")))
        t = agenci._jeden(agenci.ASTRA, tekst, obrazy, max(int(dane.get("max_tokens", 500)), 800), "", 0.0, 60, proby=1)
        return {"choices": [{"message": {"content": t}}]}
    except Exception as e:  # ByteCatCode nie odpowiada: RouteMux
        print(f"   wizja logo przez ByteCatCode: {type(e).__name__}: {str(e)[:100]} -> RouteMux")
        return None


def _zapytanie_routemux(sciezka: str, dane: dict, limit: int = 240) -> dict:
    req = urllib.request.Request(API + sciezka, data=json.dumps(dane).encode(), headers={
        "Authorization": "Bearer " + klucz(),
        "Content-Type": "application/json",
        "User-Agent": UA,
    })
    with urllib.request.urlopen(req, timeout=limit) as odp:
        return json.load(odp)


def inicjaly(nazwa: str) -> str:
    pomin = {"salon", "studio", "by", "beauty", "gabinet", "i", "and", "the"}
    slowa = [s for s in re.findall(r"[^\W\d_]+", nazwa)]
    glowne = [s for s in slowa if s.lower() not in pomin] or slowa
    return "".join(s[0].upper() for s in glowne[:2])


def wybierz_styl(nazwa: str) -> str:
    """Staly wybor z nazwy: ponowne uruchomienie daje ten sam styl, a klientki sie roznia."""
    nazwy = list(STYLE)
    return nazwy[int(hashlib.sha256(nazwa.encode()).hexdigest(), 16) % len(nazwy)]


def zbuduj_prompt(nazwa: str, branza: str, styl: str, typ: str) -> str:
    motyw = MOTYWY.get(typ, "a soft abstract curve")
    opis = STYLE[styl].format(nazwa=nazwa, inicjaly=inicjaly(nazwa), motyw=motyw)
    litery = " ".join("/" if z == " " else z for z in nazwa)
    return PROMPT.format(nazwa=nazwa, branza=branza, styl=opis, litery=litery)


def splaszcz(obraz: bytes) -> bytes:
    """Model zwraca czasem przezroczysty PNG: bez bialego tla wyglada jak czarne na czarnym."""
    im = Image.open(io.BytesIO(obraz)).convert("RGBA")
    tlo = Image.new("RGBA", im.size, (255, 255, 255, 255))
    tlo.alpha_composite(im)
    bufor = io.BytesIO()
    tlo.convert("RGB").save(bufor, "PNG")
    return bufor.getvalue()


def generuj_obraz(prompt: str, model: str) -> bytes:
    def wyslij(api: str, kl: str, m: str) -> dict:
        req = urllib.request.Request(api + "/images/generations", data=json.dumps(
            {"model": m, "prompt": prompt, "n": 1, "size": "1024x1024"}).encode(), headers={
            "Authorization": "Bearer " + kl, "Content-Type": "application/json", "User-Agent": UA})
        with urllib.request.urlopen(req, timeout=240) as odp:
            return json.load(odp)
    return _po_kolei(model, wyslij)


def edytuj_obraz(prompt: str, obraz: bytes, model: str) -> bytes:
    """Rysowanie na podstawie wzoru: /images/edits przyjmuje tylko multipart."""
    def wyslij(api: str, kl: str, m: str) -> dict:
        granica = "----logo" + hashlib.sha256(obraz).hexdigest()[:16]
        czesci = []
        for pole, wartosc in (("model", m), ("prompt", prompt), ("size", "1024x1024"), ("n", "1")):
            czesci.append(f'--{granica}\r\nContent-Disposition: form-data; name="{pole}"\r\n\r\n{wartosc}\r\n'.encode())
        czesci.append(f'--{granica}\r\nContent-Disposition: form-data; name="image"; filename="logo.png"\r\n'
                      "Content-Type: image/png\r\n\r\n".encode() + obraz + b"\r\n")
        czesci.append(f"--{granica}--\r\n".encode())
        req = urllib.request.Request(api + "/images/edits", data=b"".join(czesci), headers={
            "Authorization": "Bearer " + kl,
            "Content-Type": "multipart/form-data; boundary=" + granica,
            "User-Agent": UA,
        })
        with urllib.request.urlopen(req, timeout=240) as odp:
            return json.load(odp)
    return _po_kolei(model, wyslij)


def _napis_klientki(napis: str, nick: str) -> bool:
    """Okladki relacji pokazuja tez marki produktow, wiec napis musi pasowac do nicku albo nazwy konta."""
    def proste(t: str) -> str:
        t = unicodedata.normalize("NFKD", t.replace("ł", "l").replace("Ł", "L"))
        return "".join(z for z in t.casefold() if z.isalnum() and not unicodedata.combining(z))

    plik = DANE / nick / "profile.json"
    profil = json.loads(plik.read_text(encoding="utf-8")) if plik.exists() else {}
    tozsamosc = proste(nick + " " + str(profil.get("full_name", "")))
    slowa = [proste(s) for s in re.findall(r"[^\W\d_]+", napis)]
    if any(len(s) >= 3 and s in tozsamosc for s in slowa):
        return True
    # sam monogram: litery musza byc inicjalami slow z nazwy konta
    litery = proste(napis)
    inicjaly_konta = {proste(s)[0] for s in re.findall(r"[^\W\d_]+", f"{nick} {profil.get('full_name', '')}")}
    return 1 <= len(litery) <= 3 and set(litery) <= inicjaly_konta


def znajdz_logo(nick: str) -> dict | None:
    """Szuka logo na awatarze i okladkach relacji. Zwraca wyciety wzor i napis albo None."""
    pliki = sorted(glob.glob(str(DANE / nick / "covers" / "*.jpg")), key=lambda p: "profile-pic" not in p)[:12]
    if not pliki:
        return None
    bok = 256
    wiersze = (len(pliki) + 3) // 4
    arkusz = Image.new("RGB", (4 * bok, wiersze * bok), "white")
    obrazy = []
    for i, p in enumerate(pliki):
        im = Image.open(p).convert("RGB")
        obrazy.append(im)
        arkusz.paste(im.resize((bok - 4, bok - 4), Image.LANCZOS), ((i % 4) * bok + 2, (i // 4) * bok + 2))
        ImageDraw.Draw(arkusz).text(((i % 4) * bok + 8, (i // 4) * bok + 6), str(i + 1), fill="red")
    bufor = io.BytesIO()
    arkusz.save(bufor, "PNG")
    d = _szukaj_logo({
        "model": MODEL_KONTROLI,
        "max_tokens": 500,
        "messages": [{"role": "user", "content": [
            {"type": "text", "text": "Numbered tiles from the Instagram profile of a beauty studio: profile picture and story "
                                     "covers. Does any tile show the studio's own LOGO or brand mark, not a plain sentence, not a "
                                     "generic icon of an eye or heart and not a photo of a person? Pick the clearest tile. Reply with "
                                     "JSON only: {\"logo\": true or false, \"tile\": number, \"text\": exact letters in the logo, keeping "
                                     "diacritics, \"x0\": 0-1, \"y0\": 0-1, \"x1\": 0-1, \"y1\": 0-1 box of the logo inside that tile}"},
            {"type": "image_url", "image_url": {"url": "data:image/png;base64," + base64.b64encode(bufor.getvalue()).decode()}},
        ]}],
    }, limit=90)
    tresc = d["choices"][0]["message"]["content"]
    if isinstance(tresc, list):
        tresc = "".join(c.get("text", "") for c in tresc)
    o = json.loads(re.search(r"\{.*\}", tresc, re.S).group(0))
    nr = int(o.get("tile") or 0)
    if not o.get("logo") or not 1 <= nr <= len(obrazy) or not str(o.get("text", "")).strip():
        return None
    if not _napis_klientki(str(o["text"]), nick):
        print(f"{nick}: odrzucam {o['text']!r}, napis nie pasuje do profilu, to moze byc marka produktu")
        return None
    if _sam_opis(str(o["text"])):
        # okladka relacji "Brwi" / "Cennik" to nie logo (salon_f 11.11: z okladki "Brwi" wyszla nieczytelna plama)
        print(f"{nick}: odrzucam {o['text']!r}, to nazwa uslugi albo relacji, nie logo marki")
        return None
    im = obrazy[nr - 1]
    # model czasem podaje piksele albo zle pole: wtedy bierzemy caly kafel. Tak samo, gdy wycinek jest pusty
    # (salon_d 2026-11-11: pole trafilo w ciemny pas tla, model obrazu dostal sam napis i zaprojektowal nowe logo)
    pudelko = [float(o.get(k, d)) for k, d in (("x0", 0), ("y0", 0), ("x1", 1), ("y1", 1))]
    x0, x1 = sorted((pudelko[0], pudelko[2]))
    y0, y1 = sorted((pudelko[1], pudelko[3]))
    if min(pudelko) < 0 or max(pudelko) > 1 or x1 - x0 < 0.1 or y1 - y0 < 0.05:
        x0, y0, x1, y1 = 0.0, 0.0, 1.0, 1.0
    m = 0.15 * max(x1 - x0, y1 - y0)
    wycinek = im.crop((int(max(x0 - m, 0) * im.width), int(max(y0 - m, 0) * im.height),
                       int(min(x1 + m, 1) * im.width), int(min(y1 + m, 1) * im.height)))
    if not ma_rysunek(wycinek):
        wycinek = im
    tlo_ = tuple(int(v) for v in np.median(np.asarray(wycinek.convert("RGB")).reshape(-1, 3), axis=0))
    wzor = ImageOps.pad(wycinek, (1024, 1024), Image.LANCZOS, color=tlo_)    # tlo jak w oryginale, bez bialych pasow
    bufor = io.BytesIO()
    wzor.save(bufor, "PNG")
    b2 = io.BytesIO()
    wycinek.save(b2, "PNG")
    return {"wzor": bufor.getvalue(), "wycinek": b2.getvalue(), "tekst": str(o["text"]).strip(), "zrodlo": Path(pliki[nr - 1]).name}


def logo_tekstowe(nazwa: str) -> bytes:
    """Napis marki fontem szablonu (Belleza, rozstrzelony, wersaliki), czern na bieli; dluga nazwa w dwoch liniach."""
    from PIL import ImageFont
    font_ = str(KATALOG / "baza" / "fonty" / "Belleza-Regular.ttf")
    slowa = nazwa.upper().split()
    linie = [" ".join(slowa)] if len(nazwa) <= 16 or len(slowa) == 1 else \
        [" ".join(slowa[:(len(slowa) + 1) // 2]), " ".join(slowa[(len(slowa) + 1) // 2:])]
    font = ImageFont.truetype(font_, 150)
    rozstaw = 18
    szer = [sum(font.getlength(z) for z in l) + rozstaw * (len(l) - 1) for l in linie]
    w, h = int(max(szer)) + 240, 230 * len(linie) + 160
    im = Image.new("RGB", (w, h), "white")
    d = ImageDraw.Draw(im)
    for i, (l, s) in enumerate(zip(linie, szer)):
        x = (w - s) / 2
        for z in l:
            d.text((x, 80 + i * 230), z, font=font, fill="black")
            x += font.getlength(z) + rozstaw
    b = io.BytesIO()
    im.save(b, "PNG")
    return b.getvalue()


OPIS_RELACJI = {"brwi", "brew", "rzesy", "rzes", "lashes", "lash", "brows", "makeup", "makijaz", "pmu", "paznokcie", "nails",
                "cennik", "ceny", "opinie", "opinia", "efekty", "efekt", "kontakt", "mnie", "o", "szkolenia", "szkolenie",
                "promocje", "promo", "terminy", "wolne", "info", "studio", "salon", "beauty", "laminacja", "henna",
                "stylizacja", "przedluzanie", "volume", "klasyka", "metamorfozy", "pielegnacja", "faq", "i", "&", "and"}


def _sam_opis(napis: str) -> bool:
    slowa = [unicodedata.normalize("NFKD", s.lower().replace("ł", "l")).encode("ascii", "ignore").decode()
             for s in re.findall(r"[^\W\d_]+", napis)]
    return bool(slowa) and all(s in OPIS_RELACJI for s in slowa)


def ma_rysunek(im: Image.Image) -> bool:
    """Czy w wycinku jest cokolwiek poza tlem: >= 2 % pikseli odstaje od mediany o 40 poziomow jasnosci."""
    g = np.asarray(im.convert("L"), dtype=np.float32)
    return float((np.abs(g - np.median(g)) > 40).mean()) >= 0.02


def wytnij_lokalnie(wycinek_png: bytes) -> bytes | None:
    """Logo prosto z jej grafiki, bez rysowania od nowa: czern na bieli (jasny napis na ciemnym tle sie odwraca),
    powiekszone i podciagniete kontrastem. Miekkie przy malym awatarze, ale wierne. None, gdy nic nie widac."""
    im = Image.open(io.BytesIO(wycinek_png)).convert("L")
    g = np.asarray(im, dtype=np.float32)
    brzeg = np.concatenate([g[0], g[-1], g[:, 0], g[:, -1]])
    tlo_ = float(np.median(brzeg))
    tusz = (g - tlo_) if tlo_ < 128 else (tlo_ - g)
    lo, hi = np.percentile(tusz, 50), np.percentile(tusz, 99.5)
    if hi - lo < 25:
        return None
    v = np.clip((tusz - lo) / (hi - lo), 0, 1) ** 0.8
    szare = Image.fromarray((255 * (1 - v)).astype(np.uint8))
    skala = max(1.0, 900 / max(szare.size))
    szare = szare.resize((int(szare.width * skala), int(szare.height * skala)), Image.LANCZOS)
    plotno = Image.new("L", (szare.width + 200, szare.height + 200), 255)
    plotno.paste(szare, (100, 100))
    b = io.BytesIO()
    plotno.convert("RGB").save(b, "PNG")
    return b.getvalue()


def wiernosc(wzor: bytes, obraz: bytes) -> dict | None:
    """Agent (agenci.py, Claude przez ByteCatCode) porownuje przerysowanie z oryginalem. None = bez agenta (brak klucza)."""
    try:
        import agenci
        if not agenci.dostepne():
            return None
        pytanie = ("Obraz 1: oryginalne logo studia z jej Instagrama (male, slabej jakosci, moze byc jasne na ciemnym tle). "
                   "Obraz 2: przerysowanie na czarno na bialym. Ocen wiernosc kopii: kroje pisma (szeryfowy, pisany odrecznie, "
                   "bezszeryfowy) dla kazdego slowa, uklad slow, elementy (ramka, linie, symbol, drugi mniejszy napis), proporcje. "
                   "Kolor, tlo i ostrosc nie maja znaczenia. Odpowiedz wylacznie JSON: "
                   '{"ocena": 1-5, "roznice": "max 20 slow"} (5 = ta sama grafika, 3 = podobna, ale inny kroj albo brak elementu, '
                   "1 = inne logo)")
        o, model = agenci.zapytaj("qa_sprawdzenie", pytanie, [Image.open(io.BytesIO(wzor)), Image.open(io.BytesIO(obraz))],
                                  max_tokens=300, temperatura=0.0,
                                  sprawdz=lambda x: None if isinstance(x, dict) and isinstance(x.get("ocena"), (int, float)) else "zly format")
        return {"ocena": float(o["ocena"]), "roznice": str(o.get("roznice", ""))[:160], "model": model}
    except Exception as e:  # agent nie odpowiada: nie blokujemy logo
        print(f"   wiernosc logo: {type(e).__name__}: {str(e)[:100]}")
        return None


def _porownawczy(t: str) -> str:
    """Bez wielkosci liter i spacji, ale z zachowaniem polskich znakow."""
    t = unicodedata.normalize("NFC", t).casefold()
    return "".join(z for z in t if z.isalnum())


def sprawdz_logo(obraz: bytes, nazwa: str) -> dict:
    """Model wizyjny czyta napis, a o zgodnosci decyduje kod, nie opinia modelu."""
    png = base64.b64encode(obraz).decode()
    d = zapytanie("/chat/completions", {
        "model": MODEL_KONTROLI,
        "max_tokens": 400,
        "messages": [{"role": "user", "content": [
            {"type": "text", "text": "Read this logo exactly as drawn. Do not correct spelling and keep "
                                     "diacritics exactly as they appear. Reply with JSON only: {\"text\": all words "
                                     "visible as one string, \"logo_count\": number of separate logos, \"only_black_on_white\": "
                                     "true or false, \"damaged_letters\": true if any letter is malformed}"},
            {"type": "image_url", "image_url": {"url": "data:image/png;base64," + png}},
        ]}],
    }, limit=90)
    tresc = d["choices"][0]["message"]["content"]
    if isinstance(tresc, list):
        tresc = "".join(c.get("text", "") for c in tresc)
    wynik = json.loads(re.search(r"\{.*\}", tresc, re.S).group(0))
    odczyt, wzor = _porownawczy(str(wynik.get("text", ""))), _porownawczy(nazwa)
    # monogram (np. "MA" nad "Mon Ami studio") model czytajacy czesto pomija: odczyt zawarty w nazwie i >= 80 % jej dlugosci
    wynik["napis_zgodny"] = odczyt == wzor or wzor in odczyt or (bool(odczyt) and odczyt in wzor and len(odczyt) >= 0.8 * len(wzor))
    wynik["ok"] = bool(wynik["napis_zgodny"] and wynik.get("logo_count", 1) == 1
                       and wynik.get("only_black_on_white", True) and not wynik.get("damaged_letters", False))
    return wynik


def zapisz_warianty(obraz: bytes, katalog: Path, kolory: dict) -> dict:
    """Przycina logo i robi przezroczyste wersje w dowolnym kolorze, lokalnie i bez kosztu."""
    szare = np.asarray(Image.open(io.BytesIO(obraz)).convert("L")).astype(np.float32) / 255
    alfa = np.clip((0.97 - szare) / 0.87, 0, 1)
    ys, xs = np.where(alfa > 0.15)
    margines = int(max(alfa.shape) * 0.03)
    y0, y1 = max(ys.min() - margines, 0), min(ys.max() + margines, alfa.shape[0])
    x0, x1 = max(xs.min() - margines, 0), min(xs.max() + margines, alfa.shape[1])
    alfa = alfa[y0:y1, x0:x1]
    pliki = {}
    for nazwa_koloru, (r, g, b) in kolory.items():
        rgba = np.zeros((*alfa.shape, 4), dtype=np.uint8)
        rgba[..., 0], rgba[..., 1], rgba[..., 2] = r, g, b
        rgba[..., 3] = (alfa * 255).astype(np.uint8)
        plik = katalog / f"logo-{nazwa_koloru}.png"
        Image.fromarray(rgba, "RGBA").save(plik, optimize=True)
        pliki[nazwa_koloru] = plik.name
    return pliki


def dane_klientki(nick: str) -> tuple[str, str, str, str]:
    """Zwraca nazwe, branze, typ uslugi i status logo z wynikow generatora."""
    folder = PROJEKT / "output_v3" / nick
    fakty = json.loads((folder / "facts.json").read_text(encoding="utf-8"))
    marka = json.loads((folder / "brand.json").read_text(encoding="utf-8"))
    uslugi = fakty.get("services") or []
    branza = ", ".join(dict.fromkeys(u["name"] for u in uslugi[:3])) or "beauty studio"
    typ = uslugi[0].get("type", "") if uslugi else ""
    return fakty.get("name") or nick, branza, typ, marka.get("status", "")


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--profil", help="nick z danych Instagrama: najpierw szuka tam logo do odtworzenia")
    p.add_argument("--nick", help="profil z output_v3")
    p.add_argument("--nazwa", help="nazwa salonu, gdy nie ma profilu; przy --profil uzywana, gdy logo trzeba stworzyc")
    p.add_argument("--branza", default="beauty studio")
    p.add_argument("--typ", default="", help="lashes, brows, nails, hair, makeup, skin, pmu")
    p.add_argument("--styl", choices=list(STYLE), help="domyslnie wybierany stale z nazwy")
    p.add_argument("--model", default=MODEL_OBRAZU)
    p.add_argument("--proby", type=int, default=2, help="ile platnych prob, gdy kontrola odrzuci logo")
    p.add_argument("--wymus", action="store_true", help="generuj mimo znalezionego logo klientki")
    p.add_argument("--z-pliku", help="sprawdz i przetworz gotowy obraz zamiast placic za nowy")
    p.add_argument("--wyjscie", default=str(KATALOG / "logo"))
    a = p.parse_args()

    if not klucz() and not klucz_kuai() and not klucz_bap():
        print(f"Brak klucza: zapisz go w {PLIK_KLUCZA.name} / {PLIK_KLUCZA_KUAI.name} albo ustaw ROUTEMUX_API_KEY / KUAI_OBRAZY_KEY.")
        return 2
    try:                    # szukanie logo nie moze trwac: bez odpowiedzi = brak logo, od razu tworzymy nowe
        znalezione = znajdz_logo(a.profil) if a.profil else None
    except Exception as e:  # noqa: BLE001
        print(f"{a.profil}: szukanie logo nieudane ({type(e).__name__}), tworze nowe")
        znalezione = None
    if a.profil:
        print(f"{a.profil}: " + (f"logo na {znalezione['zrodlo']}, napis {znalezione['tekst']!r}" if znalezione else "brak logo w materialach"))
    if znalezione:
        nazwa, branza, typ = znalezione["tekst"], a.branza, a.typ
        slug = a.profil
    elif a.profil and a.nazwa:
        nazwa, branza, typ = a.nazwa, a.branza, a.typ
        slug = a.profil
    elif a.nick:
        nazwa, branza, typ, status = dane_klientki(a.nick)
        if status != "typographic_fallback" and not a.wymus:
            print(f"{a.nick}: klientka ma wlasne logo (status {status}), nic nie generuje.")
            return 0
        slug = a.nick
    elif a.nazwa:
        nazwa, branza, typ = a.nazwa, a.branza, a.typ
        slug = re.sub(r"[^\w-]+", "_", unicodedata.normalize("NFKD", nazwa).encode("ascii", "ignore").decode()).lower()
    else:
        p.error("podaj --nick albo --nazwa")

    styl = "odtworzone" if znalezione else (a.styl or wybierz_styl(nazwa))
    litery = " ".join("/" if z == " " else z for z in nazwa)
    prompt = PROMPT_ODTWORZENIA.format(litery=litery) if znalezione else zbuduj_prompt(nazwa, branza, styl, typ)
    wyjscie = Path(a.wyjscie) / f"{slug}-{styl}"
    wyjscie.mkdir(parents=True, exist_ok=True)
    if znalezione:
        (wyjscie / "wzor.png").write_bytes(znalezione["wzor"])

    proby = []
    for nr in range(1, a.proby + 1):
        try:
            if a.z_pliku:
                obraz = splaszcz(Path(a.z_pliku).read_bytes())
            elif znalezione:
                obraz = edytuj_obraz(prompt, znalezione["wzor"], a.model)
            else:
                obraz = generuj_obraz(prompt, a.model)
        except urllib.error.HTTPError as e:
            print(f"{nazwa} [{styl}] proba {nr}: blad HTTP {e.code}")
            proby.append({"proba": nr, "blad": e.code})
            continue
        except (urllib.error.URLError, TimeoutError, OSError, KeyError, ValueError) as e:   # zerwane albo zawieszone polaczenie
            print(f"{nazwa} [{styl}] proba {nr}: {type(e).__name__} {str(e)[:80]}")
            proby.append({"proba": nr, "blad": type(e).__name__})
            continue
        (wyjscie / f"surowe-{nr}.png").write_bytes(obraz)
        ocena = sprawdz_logo(obraz, nazwa)
        if ocena["ok"] and znalezione and not a.z_pliku:
            w = wiernosc(znalezione["wzor"], obraz)
            if w:
                ocena["wiernosc"] = w
                ocena["ok"] = w["ocena"] >= 4                      # inny kroj albo zgubiony element = nowe logo, nie jej
        proby.append({"proba": nr, **ocena})
        print(f"{nazwa} [{styl}] proba {nr}: {'OK' if ocena['ok'] else 'ODRZUCONE'}, odczytano: {ocena.get('text')!r}"
              + (f", wiernosc {ocena['wiernosc']['ocena']:.0f}/5 ({ocena['wiernosc']['roznice']})" if ocena.get("wiernosc") else ""))
        if ocena["ok"]:
            kolory = {"czarne": (20, 18, 16), "kremowe": (246, 239, 228), "folia": (111, 92, 56)}
            pliki = zapisz_warianty(obraz, wyjscie, kolory)
            raport = {"status": "odtworzone_z_profilu" if znalezione else "generated_ai", "name": nazwa, "styl": styl, "model": a.model,
                      "zrodlo": znalezione["zrodlo"] if znalezione else "",
                      "prompt": prompt, "pliki": pliki, "proby": proby}
            (wyjscie / "logo.json").write_text(json.dumps(raport, ensure_ascii=False, indent=2), encoding="utf-8")
            return 0
    if znalezione and znalezione.get("wycinek"):
        # zadne przerysowanie nie bylo wierne: jej wlasna grafika, wycieta i oczyszczona lokalnie (bez kosztu)
        wyciete = wytnij_lokalnie(znalezione["wycinek"])
        if wyciete:
            # wycinek z malego obrazka bywa nieczytelny: bierzemy go tylko, gdy model odczyta z niego napis
            try:
                czytelne = sprawdz_logo(wyciete, nazwa)
                if not czytelne.get("napis_zgodny") or czytelne.get("damaged_letters"):
                    print(f"{nazwa}: wycinek nieczytelny ({czytelne.get('text')!r}), nowe logo z nazwy")
                    wyciete = None
            except Exception:  # noqa: BLE001
                wyciete = None
        if wyciete:
            (wyjscie / "wyciete.png").write_bytes(wyciete)
            kolory = {"czarne": (20, 18, 16), "kremowe": (246, 239, 228), "folia": (111, 92, 56)}
            pliki = zapisz_warianty(wyciete, wyjscie, kolory)
            (wyjscie / "logo.json").write_text(json.dumps(
                {"status": "wyciete_z_profilu", "name": nazwa, "styl": styl, "zrodlo": znalezione["zrodlo"], "pliki": pliki,
                 "proby": proby}, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"{nazwa}: przerysowania niewierne, logo wyciete prosto z {znalezione['zrodlo']}")
            return 0
    if not a.z_pliku:
        # nic nie wyszlo (brak logo, nieczytelny wycinek, RouteMux bez rady): logo tekstowe lokalnie, bez modelu.
        # Wczesniej tylko przy braku logo w materialach - salon_a 11-11 poszla przez to do fabryki
        tekstowe = logo_tekstowe(a.nazwa or nazwa)          # nazwa marki ze strony, nie ucinek odczytu z awatara ("Roks")
        (wyjscie / "tekstowe.png").write_bytes(tekstowe)
        kolory = {"czarne": (20, 18, 16), "kremowe": (246, 239, 228), "folia": (111, 92, 56)}
        pliki = zapisz_warianty(tekstowe, wyjscie, kolory)
        (wyjscie / "logo.json").write_text(json.dumps(
            {"status": "tekstowe_lokalne", "name": nazwa, "styl": styl, "pliki": pliki, "proby": proby},
            ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"{nazwa}: logo tekstowe zlozone lokalnie (Belleza)")
        return 0
    (wyjscie / "logo.json").write_text(json.dumps(
        {"status": "needs_review", "name": nazwa, "styl": styl, "model": a.model, "proby": proby},
        ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"{nazwa}: zadna proba nie przeszla kontroli, zostaje logo tekstowe.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
