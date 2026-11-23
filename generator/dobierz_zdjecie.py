#!/usr/bin/env python3
"""Dobiera z calego profilu zdjecie do lusterka i kandydatki do kol.

Etapy:
1. lokalnie i za darmo: wykluczenia z podpisow, ostrosc, duplikaty, mocne barwy,
2. tani model ocenia caly profil na arkuszach po 36 miniatur. Te same oceny sluza lusterku i kolom,
3. drozszy model zaznacza oko tylko dla kilku finalistek do lusterka.

Model nie zmienia zdjecia. Kod tylko je obraca i kadruje, wiec na stronie zostaje
prawdziwa praca klientki.

    python dobierz_zdjecie.py salon_przyklad_12
"""
from __future__ import annotations

import base64
import glob
import hashlib
import io
import json
import os
import re
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageOps

from kolor import mocne_barwy

KATALOG = Path(__file__).resolve().parent
PROJEKT = KATALOG.parent
DANE = Path(os.environ.get("BSF_DATA", str(Path(__file__).resolve().parent / "dane")))
API = "https://api.routemux.com/v1/chat/completions"
SALDO = "https://api.routemux.com/v1/user/balance"
MODEL_LUSTERKO = "google/gemini-3.8-flash"  # tylko lusterko: flash-lite zle zaznaczal oko
MODEL_ARKUSZ = "google/gemini-3.5-flash-lite"  # wspolna ocena kadrow i calych postow: bez myslenia, najtanszy i najlepiej widzi napisy
MODEL_KOLO = "zhipu/glm-5.3-flash"  # arkusze i kola: pola oka trafne jak we flash, odpowiedz 5 razy tansza (pomiar w docs/03-media.md)
MIN_BOK_KADRU = 450  # ponizej tego oko w lusterku bedzie rozmyte na telefonie
MIN_SZER_LUSTERKA = 800  # zdjecie konczace scene musi miec tyle szerokosci, takze po obrocie
MAX_PRZECHYLENIE_LUSTERKA = 25  # stopnie linii kacikow oka od poziomu
MAX_PRZECHYLENIE_KOLA = 45  # makro rzes bywa ukosne, bo klientka lezy. Powyzej tego oko wyglada na lezace
MAX_PRZECHYLENIE_TWARZY = 30  # cala twarz obrocona bardziej wyglada na blad, nawet gdy obrot o 90 stopni jest poprawny
MAX_ROWNOCZESNIE = 3
MAX_KANDYDATEK = 40  # gorny limit wywolan na kandydatke u jednej klientki
# szkolenia, cudze konta i fotografowie: to nie jest praca klientki albo nie ma do tego praw
CUDZE = re.compile(r"szkole[nń]|kurs|warsztat|foto\s*[:\--@]|fot\.|photo\s*[:\--@]|ph\s*:|fotograf|pod okiem|photo\s*session|fotosesj|sesj[aięy]\s+zdj[eę]|^\s*@", re.I | re.M)

OPIS_OKA = "one clearly visible eye with lashes and brow in sharp focus, large in the frame, eye open"
OPIS_BRWI = "one clearly visible finished eyebrow with the open eye under it, in sharp focus, large in the frame"
OPIS_DLONI = "a hand with finished nails in sharp focus, large in the frame"
OPIS_WLOSOW = "a finished hairstyle, seen from behind or the side, with the hair in sharp focus and large in the frame"
OPIS_UST = "finished lips in sharp focus, large in the frame, healed and calm, no redness, no needles"
OPIS_SKORY = "healthy finished skin in sharp focus, close up, no gloves, no devices"
TEMATY = {
    OPIS_OKA: "the single sharpest, most open EYE. The box must hug only that one eye with its lashes, from the inner "
              "corner to the outer corner, and must NOT include the nose, the other eye or the whole face",
    OPIS_BRWI: "the single best finished EYEBROW together with the eye right under it. The box must hug that brow and eye "
               "and must NOT include the other eye or the whole face",
    OPIS_DLONI: "the hand with the finished nails. The box must hug only the fingers and nails",
    OPIS_WLOSOW: "the finished hair. The box must hug the hair",
    OPIS_UST: "the lips. The box must hug only the lips",
    OPIS_SKORY: "the area of skin that shows the finished result. The box must hug that area",
}
# kolejnosc ma znaczenie: nazwa konta mowi o specjalizacji wiecej niz bio z lista wszystkich uslug
USLUGI = [(r"rz[eę]s|lash", "rzesy", OPIS_OKA), (r"brw|brow|henn", "brwi", OPIS_BRWI),
          (r"pmu|permanent|linergist", "pmu", OPIS_BRWI), (r"makij|mua|makeup|wiza[zż]", "makijaz", OPIS_OKA),
          (r"paznok|nail|manicure|stylistka paz", "paznokcie", OPIS_DLONI), (r"w[lł]os|fryz|hair|barber", "wlosy", OPIS_WLOSOW),
          (r"\busta\b|\blips?\b|powi[eę]ksz", "usta", OPIS_UST), (r"kosmetolog|kosmetyk|derm|skin|pielegn|piel[eę]gn", "kosmetologia", OPIS_SKORY)]
USLUGA_PO_ANGIELSKU = {"rzesy": "eyelash extensions and lifts", "brwi": "eyebrow styling", "pmu": "permanent make-up",
                       "makijaz": "make-up artist", "paznokcie": "nails", "wlosy": "hair", "usta": "lips", "kosmetologia": "skin care",
                       "ogolny": "beauty"}
# ktore rodzaje kadrow pasuja do lusterka, od najlepszego. "twarz" to ostatnia deska: oko wykadruje kod
RODZAJE_LUSTERKA = {"rzesy": ["oko", "twarz"], "makijaz": ["oko", "twarz"], "brwi": ["brew", "oko", "twarz"], "pmu": ["brew", "oko", "twarz"],
                    "paznokcie": ["dlon"], "wlosy": ["wlosy"], "usta": ["usta", "twarz"], "kosmetologia": ["skora", "twarz"], "ogolny": ["oko", "twarz"]}

_semafor = threading.BoundedSemaphore(MAX_ROWNOCZESNIE)
_blokada = threading.Lock()
LICZNIK = {"wywolania": 0, "z_pamieci": 0, "wejscie": 0, "wyjscie": 0, "koszt": 0.0, "modele": {}}
_pamiec: dict = {}
_plik_pamieci: Path | None = None


def typ_uslugi(profil: dict) -> tuple[str, str]:
    """Typ uslugi. Najpierw nick, potem nazwa konta i bio, bo te dwa wymieniaja zwykle wszystkie uslugi."""
    for tekst in (profil.get("username", ""), profil.get("full_name", ""), profil.get("biography", "")):
        for wzor, typ, cel in USLUGI:
            if re.search(wzor, (tekst or "").lower()):
                return typ, cel
    return "ogolny", OPIS_OKA


def klucz() -> str:
    env = (os.environ.get("ROUTEMUX_API_KEY") or "").strip()      # serwer: klucz z .env automatu
    if env:
        return env
    return (PROJEKT / "klucz_routemux.txt").read_text(encoding="utf-8-sig").strip().splitlines()[0].strip()


def saldo() -> float:
    req = urllib.request.Request(SALDO, headers={"Authorization": "Bearer " + klucz(), "User-Agent": "dobor-zdjecia/1.0"})
    with urllib.request.urlopen(req, timeout=60) as odp:
        return float(json.load(odp)["balance"])


def pamiec_odpowiedzi(plik: Path | None) -> None:
    """Odpowiedzi modelu zapisane na dysku: ponowne uruchomienie po poprawce kodu nic nie kosztuje."""
    global _plik_pamieci, _pamiec
    _plik_pamieci = plik
    _pamiec = json.loads(plik.read_text(encoding="utf-8")) if plik and plik.exists() else {}


def wyzeruj_licznik() -> None:
    LICZNIK.update({"wywolania": 0, "z_pamieci": 0, "wejscie": 0, "wyjscie": 0, "koszt": 0.0, "modele": {}})


def _zapisz_uzycie(model: str, uzycie: dict) -> None:
    with _blokada:
        LICZNIK["wywolania"] += 1
        wej, wyj = int(uzycie.get("prompt_tokens") or 0), int(uzycie.get("completion_tokens") or 0)
        LICZNIK["wejscie"] += wej
        LICZNIK["wyjscie"] += wyj
        LICZNIK["koszt"] += float(uzycie.get("cost") or 0)
        m = LICZNIK["modele"].setdefault(model, {"wywolania": 0, "wejscie": 0, "wyjscie": 0})
        m["wywolania"] += 1
        m["wejscie"] += wej
        m["wyjscie"] += wyj


def _json_z_odpowiedzi(t: str) -> dict:
    """Odpowiedz bywa ucieta albo z luznym przecinkiem. Na arkuszach da sie uratowac cale wpisy listy."""
    t = re.sub(r"(\d+(?:\.\d+)?)\s*/\s*(\d+(?:\.\d+)?)", lambda m: str(float(m.group(1)) / (float(m.group(2)) or 1.0)), t)
    znalezione = re.search(r"\{.*\}", t, re.S)
    if znalezione:
        try:
            return json.loads(znalezione.group(0))
        except json.JSONDecodeError:
            pass
    wpisy = []
    for fragment in re.findall(r"\{[^{}]*\}", t):
        try:
            wpisy.append(json.loads(fragment))
        except json.JSONDecodeError:
            continue
    if not wpisy:
        raise ValueError("odpowiedz modelu bez JSON: " + t[:120])
    return {"t": wpisy, "ok": wpisy}


# ponizej: wizja przez ByteCatCode (agenci.py), RouteMux zostaje na logo. 11.11: 1,6 -> 0,3, bo dobor zdjec przez Astre
# kosztowal ok. 0,13 w panelu ByteCat na strone (ukryty prompt ~4 tys. tokenow w kazdym zapytaniu), a Gemini ok. 0,01 USD
# wlasciciel: "mozesz to wyczerpac do konca i wtedy zmienic model" - prog 0; koniec salda = HTTP 402 -> ByteCatCode
SALDO_ROUTEMUX_MIN = 0.0
_tryb = {"bytecat": None}          # None = jeszcze nie sprawdzone; LUSTRO_WIZJA=bytecat|routemux wymusza


def _wizja_przez_bytecat() -> bool:
    wymuszone = os.environ.get("LUSTRO_WIZJA", "").lower()
    if _tryb["bytecat"] is False:                    # ustawione wprost (np. zbuduj_strone offline): bez zmiany dostawcy
        return False
    if wymuszone in ("bytecat", "routemux"):
        _tryb["bytecat"] = wymuszone == "bytecat"
    if _tryb["bytecat"] is None:
        try:
            s = saldo()
            _tryb["bytecat"] = s < SALDO_ROUTEMUX_MIN
            powod = f"saldo RouteMux {s:.2f} < {SALDO_ROUTEMUX_MIN}"
        except Exception as e:  # bez sieci do RouteMux
            _tryb["bytecat"], powod = True, f"RouteMux niedostepny ({type(e).__name__})"
        if _tryb["bytecat"]:
            print(f"   wizja: {powod} -> ByteCatCode", file=sys.stderr)
    if not _tryb["bytecat"]:
        return False
    import agenci
    return agenci.dostepne()


def _zapytaj_bytecat(tekst: str, dane_obrazu: bytes, max_tokens: int, model: str) -> dict:
    import agenci
    model_bc = agenci.ZAPAS_WIZJI.get(model, agenci.ASTRA)
    odcisk = hashlib.sha1(model_bc.encode() + b"|" + tekst.encode() + b"|" + dane_obrazu).hexdigest()
    with _blokada:
        if odcisk in _pamiec:
            LICZNIK["z_pamieci"] += 1
            return json.loads(_pamiec[odcisk])
    t, model_bc = agenci.tekst_z_obrazem(tekst, dane_obrazu, model, max_tokens)
    _zapisz_uzycie(model_bc, {})
    wynik = _json_z_odpowiedzi(t)
    with _blokada:
        _pamiec[odcisk] = json.dumps(wynik, ensure_ascii=False)
        if _plik_pamieci:
            _plik_pamieci.parent.mkdir(parents=True, exist_ok=True)
            _plik_pamieci.write_text(json.dumps(_pamiec, ensure_ascii=False), encoding="utf-8")
    return wynik


def zapytaj(tekst: str, obraz: Image.Image, max_tokens: int = 800, model: str | None = None, jakosc: int = 85) -> dict:
    model = model or MODEL_KOLO
    bufor = io.BytesIO()
    obraz.convert("RGB").save(bufor, "JPEG", quality=jakosc)
    dane_obrazu = bufor.getvalue()
    # pamiec najpierw, pod obiema nazwami modelu (RouteMux i zapas ByteCatCode): zbuduj_strone jest offline i szukal tylko
    # nazwy RouteMux, wiec po doborze przez zapas galeria szla bez kontroli napisow (salon_b, 2026-11-11)
    import agenci
    for m_ in (model, agenci.ZAPAS_WIZJI.get(model, agenci.ASTRA)):
        k_ = hashlib.sha1(m_.encode() + b"|" + tekst.encode() + b"|" + dane_obrazu).hexdigest()
        with _blokada:
            if k_ in _pamiec:
                LICZNIK["z_pamieci"] += 1
                return json.loads(_pamiec[k_])
    if _wizja_przez_bytecat():
        return _zapytaj_bytecat(tekst, dane_obrazu, max_tokens, model)
    odcisk = hashlib.sha1(model.encode() + b"|" + tekst.encode() + b"|" + dane_obrazu).hexdigest()
    url = "data:image/jpeg;base64," + base64.b64encode(dane_obrazu).decode()
    tresc = {
        "model": model, "max_tokens": max_tokens, "temperature": 0,
        "messages": [{"role": "user", "content": [
            {"type": "text", "text": tekst}, {"type": "image_url", "image_url": {"url": url}},
        ]}],
    }
    # gemini-3.8 domyslnie mysli 2-3 tys. tokenow na obraz i to byl glowny koszt doboru. flash-lite tego parametru nie przyjmuje.
    # 2026-11-10: routemux odrzuca juz "none" (HTTP 400 PROVIDER_REQUEST_REJECTED); "minimal" daje te same ~60 tokenow odpowiedzi
    if model.startswith("google/gemini-3.8"):
        tresc["reasoning_effort"] = "minimal"
    req = urllib.request.Request(API, data=json.dumps(tresc).encode(), headers={
        "Authorization": "Bearer " + klucz(), "Content-Type": "application/json", "User-Agent": "dobor-zdjecia/1.0"})
    for proba in range(5):
        try:
            with _semafor, urllib.request.urlopen(req, timeout=120) as odp:
                d = json.load(odp)
            break
        except urllib.error.HTTPError as e:
            # limit routemux: przy wielu klientkach naraz to normalny stan, nie blad
            # 400 bywa przejsciowy po stronie dostawcy (PROVIDER_REQUEST_REJECTED): ten sam obraz chwile pozniej przechodzi
            if e.code == 404 and not os.environ.get("LUSTRO_WIZJA"):
                # chwilowy "MODEL_NOT_FOUND" w RouteMux (salon_a 11-12, model jest w katalogu): to jedno zapytanie przez ByteCatCode
                import agenci
                if agenci.dostepne():
                    return _zapytaj_bytecat(tekst, dane_obrazu, max_tokens, model)
            if e.code in (401, 402, 403) and not os.environ.get("LUSTRO_WIZJA"):
                # koniec salda / klucz zablokowany: reszta zapytan tego uruchomienia idzie przez ByteCatCode
                print(f"   wizja: RouteMux HTTP {e.code} -> ByteCatCode", file=sys.stderr)
                _tryb["bytecat"] = True
                import agenci
                if agenci.dostepne():
                    return _zapytaj_bytecat(tekst, dane_obrazu, max_tokens, model)
            if e.code not in (400, 429, 500, 502, 503) or proba == 4:
                raise RuntimeError(f"{model} HTTP {e.code}: {e.read().decode(errors='replace')[:300]}") from e
            time.sleep(2 ** proba * 3)
        except (TimeoutError, urllib.error.URLError):
            if proba == 4:
                raise
            time.sleep(5)
    _zapisz_uzycie(model, d.get("usage") or {})
    t = d["choices"][0]["message"].get("content")
    if isinstance(t, list):
        t = "".join(c.get("text", "") for c in t)
    if not t:
        # pusta odpowiedz (np. GLM wymyslil caly limit tokenow): ten sam obraz pytamy tanie Gemini, zamiast tracic kandydatke
        if model != MODEL_ARKUSZ:
            LICZNIK["puste_zapas"] = LICZNIK.get("puste_zapas", 0) + 1
            return zapytaj(tekst, obraz, max_tokens, MODEL_ARKUSZ, jakosc)
        raise RuntimeError(f"{model}: pusta odpowiedz ({d['choices'][0].get('finish_reason')})")
    wynik = _json_z_odpowiedzi(t)
    with _blokada:
        _pamiec[odcisk] = json.dumps(wynik, ensure_ascii=False)
        if _plik_pamieci:
            _plik_pamieci.parent.mkdir(parents=True, exist_ok=True)
            _plik_pamieci.write_text(json.dumps(_pamiec, ensure_ascii=False), encoding="utf-8")
    return wynik


def otworz(sciezka: str) -> Image.Image:
    return ImageOps.exif_transpose(Image.open(sciezka)).convert("RGB")


def ocena_lokalna(sciezka: str):
    """Ostrosc, odcisk zdjecia i mocne barwy. W OpenCV 5 nie ma juz detektora oka, wybiera model."""
    try:
        pelne = ImageOps.exif_transpose(Image.open(sciezka))
        rozmiar = pelne.size
        im = pelne.convert("RGB")
    except OSError:
        return None
    if min(rozmiar) < 500:
        return None
    im.thumbnail((640, 640))
    szare = im.convert("L")
    ostrosc = float(cv2.Laplacian(np.asarray(szare), cv2.CV_64F).var())
    mala = szare.resize((9, 8)).tobytes()
    odcisk = sum((mala[y * 9 + x] > mala[y * 9 + x + 1]) << (y * 8 + x) for y in range(8) for x in range(8))
    return {"plik": sciezka, "ostrosc": ostrosc, "odcisk": odcisk, "rozmiar": rozmiar, "barwy": mocne_barwy(im)}


def kandydaci(folder: Path, raport: dict | None = None) -> list:
    """Wszystkie posty bez duplikatow i mocnych barw. Ostrosc tylko odrzuca rozmazane, bo grafiki z napisem maja ja najwyzsza."""
    def wlasne(p: str) -> bool:
        opis = Path(p).with_suffix(".txt")
        if not opis.exists():
            return True
        tresc = opis.read_text(encoding="utf-8-sig", errors="replace")
        if CUDZE.search(tresc):
            return False
        # D1: oznaczone cudze konto w pierwszej linii to zwykle modelka, fotograf albo cudza marka
        pierwsza = next((l for l in tresc.splitlines() if l.strip()), "")
        return not [m for m in re.findall(r"@([\w.]+)", pierwsza) if m.lower().rstrip(".") != folder.name.lower()]

    wszystkie = sorted(glob.glob(str(folder / "post-*.jpg")))
    wlasne_posty = [p for p in wszystkie if wlasne(p)]
    wyniki = [w for w in (ocena_lokalna(p) for p in wlasne_posty) if w]
    if not wyniki:
        return []
    prog = float(np.percentile([w["ostrosc"] for w in wyniki], 15))
    bez_duplikatow = []
    for w in wyniki:
        if w["ostrosc"] >= prog and all((w["odcisk"] ^ b["odcisk"]).bit_count() > 8 for b in bez_duplikatow):
            bez_duplikatow.append(w)
    wybrane = [w for w in bez_duplikatow if not w["barwy"]["odrzuc"]]
    if raport is not None:
        raport.update({"postow": len(wszystkie), "po_podpisach": len(wlasne_posty), "po_ostrosci_i_duplikatach": len(bez_duplikatow),
                       "po_barwach": len(wybrane)})
    return wybrane


def _font(rozmiar: int):
    for f in ("arialbd.ttf", "DejaVuSans-Bold.ttf"):
        try:
            return ImageFont.truetype(f, rozmiar)
        except OSError:
            continue
    return ImageFont.load_default()


def arkusz(obrazy: list, etykiety: list, kolumny: int, bok: int) -> Image.Image:
    wiersze = (len(obrazy) + kolumny - 1) // kolumny
    wynik = Image.new("RGB", (kolumny * bok, wiersze * bok), "white")
    d = ImageDraw.Draw(wynik)
    for i, (im, e) in enumerate(zip(obrazy, etykiety)):
        x, y = (i % kolumny) * bok, (i // kolumny) * bok
        wynik.paste(ImageOps.fit(im, (bok - 4, bok - 4)), (x + 2, y + 2))
        d.rectangle((x + 2, y + 2, x + 48, y + 36), fill="black")
        d.text((x + 8, y + 4), str(e), fill="white", font=_font(26))
    return wynik


PROMPT_ARKUSZA = (
    "Numbered Instagram photos from a Polish beauty professional ({usluga}). I am choosing her finished work for a website. "
    "List ONLY the tiles that qualify. A tile does NOT qualify if it shows any of: text, captions, stickers or logos over the photo; "
    "a collage, a split or a before/after; a designed graphic; only products, tools, gloves or a room; only neck, chest, cleavage, "
    "shoulders or chin with no eye visible; a treatment in progress; a blurry, dark or unflattering shot; strong purple, pink, magenta, "
    "red or blue make-up or clothing. "
    "For each tile that qualifies give n = tile number, k = one of \"oko\" (a single eye, with or without brow, fills most of the tile), "
    "\"brew\" (an eyebrow is the main subject), \"twarz\" (a face with open eyes), \"usta\" (lips), \"dlon\" (hand with nails), "
    "\"wlosy\" (hair), \"skora\" (skin close-up), \"detal\" (another close-up of finished work), a = appeal from 1 to 5 where 5 is "
    "magazine quality, r = 1 if the tile is rotated sideways or upside down, otherwise 0. "
    "Reply with JSON only: {{\"ok\": [{{\"n\": 1, \"k\": \"oko\", \"a\": 4, \"r\": 0}}]}}"
)


def przeglad(kand: list, typ: str, rozmiar_arkusza: int = 36, bok: int = 220) -> list:
    """Jeden przeglad calego profilu. Zwraca kandydatki z rodzajem i ocena, najlepsze najpierw."""
    tekst = PROMPT_ARKUSZA.format(usluga=USLUGA_PO_ANGIELSKU.get(typ, "beauty"))

    def runda(pula: list) -> list:
        obrazy = [ImageOps.fit(otworz(k["plik"]), (bok, bok)) for k in pula]
        odp = zapytaj(tekst, arkusz(obrazy, list(range(1, len(obrazy) + 1)), 6, bok), max_tokens=3000)
        wynik = []
        for o in odp.get("ok", []):
            try:
                n = int(o["n"])
                if 1 <= n <= len(pula):
                    wynik.append({**pula[n - 1], "rodzaj": str(o.get("k", "detal")), "arkusz": float(o.get("a", 3)), "obrocone": bool(o.get("r"))})
            except (KeyError, TypeError, ValueError):
                continue
        return wynik

    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(MAX_ROWNOCZESNIE) as ex:
        rundy = list(ex.map(runda, [kand[i:i + rozmiar_arkusza] for i in range(0, len(kand), rozmiar_arkusza)]))
    wszystkie = [k for r in rundy for k in r]
    return sorted(wszystkie, key=lambda k: -k["arkusz"])


def prompt_kandydata(cel: str, usluga: str) -> str:
    return (f"One photo from a Polish beauty professional ({usluga}). It may become a small round crop on her website. "
            f"Find {TEMATY.get(cel, TEMATY[OPIS_OKA])}. Give boxes as fractions of image width and height. Reply with JSON only: "
            "{\"upright\": true if a person's eyebrow is above the eye, forehead on top and fingers point naturally, false if the photo is "
            "sideways or upside down, \"box\": {\"x0\": 0.0, \"y0\": 0.0, \"x1\": 1.0, \"y1\": 1.0} around that subject, "
            "\"face\": the same kind of box around the whole face if a whole face is visible, otherwise null, "
            "\"lips\": the same kind of box around the lips if they are visible, otherwise null, "
            "\"eye_open\": true if at least one open eye is clearly visible, \"text_anywhere\": true if any text, sticker or logo is on the photo, "
            "\"text_on_subject\": true if it overlaps the subject, \"collage\": true for a collage, split or designed graphic, "
            "\"only_body\": true if NO eye is visible and it shows only neck, chest, chin or shoulders, \"strong_colours\": true if make-up or clothing is strongly "
            "purple, pink, magenta, red or blue, \"tools\": true if gloves, tweezers, needles or devices are visible, "
            "\"appeal\": 1 to 5}")


def ocen_kandydata(obraz: Image.Image, cel: str, typ: str, model: str | None = None) -> dict:
    """Jedno wywolanie na kandydatke: pole tematu i wszystkie kontrole w jednej odpowiedzi."""
    maly = obraz.copy()
    maly.thumbnail((768, 768))
    return zapytaj(prompt_kandydata(cel, USLUGA_PO_ANGIELSKU.get(typ, "beauty")), maly, max_tokens=1200, model=model)


def pole_z_odpowiedzi(b) -> dict | None:
    """Modele mieszaja ulamki ze skala 0-1000, czasem w jednym polu. Zwraca ulamki albo None, gdy pole jest puste."""
    if not isinstance(b, dict):
        return None
    try:
        v = [float(b[k]) for k in ("x0", "y0", "x1", "y1")]
    except (KeyError, TypeError, ValueError):
        return None
    v = [min(max(x / 1000 if x > 1 else x, 0.0), 1.0) for x in v]
    x0, x1 = sorted((v[0], v[2]))
    y0, y1 = sorted((v[1], v[3]))
    if x1 - x0 < 0.01 or y1 - y0 < 0.01:
        return None
    return {"x0": x0, "y0": y0, "x1": x1, "y1": y1}


PROMPT_KADROW = (
    "Numbered round crops from a Polish beauty professional's photos, each shown exactly as it would appear on her website; black areas are "
    "hidden. Judge only what is visible. Reply with JSON only: {\"t\": [{\"n\": 1, \"a\": 4, \"eye\": true, \"upside_down\": false, \"tilt\": 10, \"bad\": false}]} "
    "with one entry per tile. tilt = how many degrees the line through the corners of the eye leans away from horizontal, 0 to 90. a = appeal from 1 to 5: 5 is sharp, flattering, clearly skilled magazine-quality work, 3 is acceptable, 1 is poor. "
    "eye = an open eye is clearly visible. upside_down = the upper lashes or the eyebrow are below the eye. "
    "bad = any of: text, sticker or logo; a collage, split or before/after seam; only neck, chest, chin or shoulders; gloves or tools; "
    "strong purple, pink, magenta, red or blue make-up; a closed or half-cut eye; blurred."
)


PROMPT_CALYCH = (
    "Numbered Instagram posts from a beauty professional. Reply with JSON only: {\"t\": [{\"n\": 1, \"two_photos\": false, \"text\": false}]} with one entry per tile. "
    "two_photos = the tile is assembled from two or more different photos: look for the same eye or face repeated, one photo stacked above another, "
    "two different skin tones or lighting meeting along a straight line, a before and after. "
    "text = any words, stickers, logos or watermarks anywhere, including signs on the wall behind the person."
)


def ocen_cale(kandydatki: list, model: str | None = None, bok: int = 300) -> dict:
    """Kolaz widac tylko na calym poscie: kadr oka z jednej polowki wyglada niewinnie. Jeden arkusz na 16 zdjec."""
    wynik = {}
    for start in range(0, len(kandydatki), 16):
        czesc = kandydatki[start:start + 16]
        obrazy = [ImageOps.fit(obroc(otworz(k["plik"]), k.get("obrot", 0)), (bok, bok)) for k in czesc]
        odp = zapytaj(PROMPT_CALYCH, arkusz(obrazy, list(range(1, len(czesc) + 1)), 4, bok), max_tokens=3000, model=model or MODEL_ARKUSZ)
        for o in odp.get("t", []):
            try:
                wynik[int(o["n"]) + start] = o
            except (KeyError, TypeError, ValueError):
                continue
    return wynik


def ocen_kadry(kadry: list, model: str | None = None, kolumny: int = 4, bok: int = 300) -> dict:
    """Wspolna ocena kilku kadrow na jednym arkuszu. Zwraca odpowiedz wedlug numeru kadru od 1."""
    wynik = {}
    for start in range(0, len(kadry), 16):
        czesc = kadry[start:start + 16]
        odp = zapytaj(PROMPT_KADROW, arkusz(czesc, list(range(1, len(czesc) + 1)), kolumny, bok), max_tokens=3000, model=model or MODEL_ARKUSZ)
        for o in odp.get("t", []):
            try:
                wynik[int(o["n"]) + start] = o
            except (KeyError, TypeError, ValueError):
                continue
    return wynik


def znajdz_obrot(obraz: Image.Image, model: str | None = None) -> int:
    """Pokazuje modelowi cztery obroty naraz, bo opis 'obroc o 90' mylil go w testach."""
    obroty = [0, 90, 180, 270]
    podglad = obraz.copy()
    podglad.thumbnail((512, 512))
    kafle = [podglad.rotate(-o, expand=True) for o in obroty]
    wybor = zapytaj("The same photo shown in four rotations A, B, C, D. Which tile is correctly upright: a person's "
                    "eyebrow above the eye, lashes growing upward, forehead on top, fingers of a hand pointing naturally? "
                    "Reply with JSON only: {\"upright\": \"A\", \"confident\": true}",
                    arkusz(kafle, list("ABCD"), 2, 384), max_tokens=200, model=model)
    return obroty["ABCD".index(str(wybor.get("upright", "A")).strip().upper()[0])]


def obroc(obraz: Image.Image, obrot: int) -> Image.Image:
    return obraz.rotate(-obrot, expand=True) if obrot else obraz


def kadr_lusterka(prosty: Image.Image, pole: dict, cel: str, makro: bool = False) -> tuple:
    """Oko ma zajac okolo 2/3 szerokosci lusterka. Nie przybliza ponizej rozdzielczosci zrodla."""
    w, h = prosty.size
    x0, x1 = sorted((float(pole["x0"]) * w, float(pole["x1"]) * w))
    y0, y1 = sorted((float(pole["y0"]) * h, float(pole["y1"]) * h))
    bok = max((x1 - x0) * 1.5, (y1 - y0) * 2.0, MIN_BOK_KADRU)
    if cel in (OPIS_OKA, OPIS_BRWI) and not makro:
        # model potrafi zaznaczyc cala twarz: oko i brew nigdy nie potrzebuja wiecej niz polowy kadru
        bok = min(bok, max(0.5 * min(w, h), MIN_BOK_KADRU))
    bok = min(bok, min(w, h))
    sx = min(max((x0 + x1) / 2 - bok / 2, 0), w - bok)
    sy = min(max((y0 + y1) / 2 - bok / 2, 0), h - bok)
    pudelko = (int(sx), int(sy), int(sx + bok), int(sy + bok))
    return prosty.crop(pudelko), pudelko


def _kontrola_kadru_lusterka(kadr: Image.Image, cel: str) -> dict:
    return zapytaj(f"This square crop will sit inside a small round mirror on a phone. The goal is {cel}. In this crop find "
                   f"{TEMATY.get(cel, TEMATY[OPIS_OKA])}. Reply with JSON only: {{\"found\": true, \"x0\": 0.0, \"y0\": 0.0, \"x1\": 1.0, "
                   "\"y1\": 1.0, \"upright\": true if the eyebrow is above the eye, \"subject_clear\": true if the subject is sharp and "
                   "fully inside the central circle, \"text_or_sticker\": false, \"strong_colours\": true if eyeshadow or make-up is strongly "
                   "purple, pink, magenta, red or blue, \"appeal\": 1 to 5}", kadr, max_tokens=800, model=MODEL_LUSTERKO)


def dobierz_lusterko(ranking: list, cel: str, typ: str, ile_finalistek: int = 4, pomin: set | None = None) -> dict:
    """Finalistki z oceny kadrow trafiaja do drozszego modelu. Zatrzymuje sie na pierwszej bardzo dobrej."""
    pomin = pomin or set()
    # zdjecie konczy scene na calym ekranie, wiec musi miec szerokosc i nie moze miec nakladek
    pasujace = [k for k in ranking if min(k["rozmiar"]) >= MIN_SZER_LUSTERKA and Path(k["plik"]).name not in pomin and not k.get("tekst_gdzies")]
    for k in pasujace:
        prosty = obroc(otworz(k["plik"]), k.get("obrot", 0))
        # zdjecie konczy scene bez nakladek: liczy sie kolor calego kadru, a nie tylko srodka
        k["kolor_calego"] = mocne_barwy(prosty, srodkowe_kolo=False)["odrzuc"]
        k["oko_px"] = (k["pole"]["x1"] - k["pole"]["x0"]) * prosty.width
        skala_pliku = skala_zdjecia(*prosty.size)
        k["miekkie"] = 3 * max(390 / (prosty.width * skala_pliku), 561 / (prosty.height * skala_pliku)) > 2

    def klucz_lusterka(k: dict) -> tuple:
        # wieksze oko w pikselach zrodla jest ostrzejsze w lusterku: 500 px daje tyle co dwa punkty oceny
        return (1 if k["kolor_calego"] else 0, 1 if k["miekkie"] else 0, 0 if k.get("przechylenie", 0) <= MAX_PRZECHYLENIE_LUSTERKA else 1,
                -(k["ocena"] + min(k["oko_px"], 500) / 250))

    pasujace.sort(key=klucz_lusterka)
    najlepszy, odrzucone = None, []
    for k in pasujace[:ile_finalistek]:
        nazwa = Path(k["plik"]).name
        prosty = obroc(otworz(k["plik"]), k.get("obrot", 0))
        try:
            o = ocen_kandydata(prosty, cel, typ, MODEL_LUSTERKO)
        except (ValueError, RuntimeError) as e:
            odrzucone.append({"plik": nazwa, "powod": f"odpowiedz modelu: {e}"[:160]})
            continue
        pole = pole_z_odpowiedzi(o.get("box"))
        if any(o.get(f) for f in ("text_anywhere", "collage", "strong_colours", "tools")) or not o.get("eye_open", True) or not pole:
            odrzucone.append({"plik": nazwa, "powod": {f: o.get(f) for f in ("text_anywhere", "collage", "strong_colours", "tools", "eye_open")}})
            continue
        makro = not pole_z_odpowiedzi(o.get("face"))
        kadr, pudelko = kadr_lusterka(prosty, pole, cel, makro)
        # drugi przebieg na powiekszeniu: pierwsze pole bywa przesuniete i oko ladowalo w rogu lusterka
        try:
            d = _kontrola_kadru_lusterka(kadr, cel)
        except (ValueError, RuntimeError) as e:
            odrzucone.append({"plik": nazwa, "powod": f"odpowiedz modelu: {e}"[:160]})
            continue
        drugie = pole_z_odpowiedzi(d) if d.get("found", True) else None
        if drugie:
            x, y, x2, _ = pudelko
            bok_kadru = x2 - x
            pole = {"x0": (x + drugie["x0"] * bok_kadru) / prosty.width, "x1": (x + drugie["x1"] * bok_kadru) / prosty.width,
                    "y0": (y + drugie["y0"] * bok_kadru) / prosty.height, "y1": (y + drugie["y1"] * bok_kadru) / prosty.height}
            kadr, pudelko = kadr_lusterka(prosty, pole, cel, makro)
        ocena = float(d.get("appeal", 3))
        if d.get("text_or_sticker") or d.get("strong_colours") or not d.get("upright", True) or not d.get("subject_clear", True):
            odrzucone.append({"plik": nazwa, "powod": {f: d.get(f) for f in ("text_or_sticker", "strong_colours", "upright", "subject_clear")}})
            continue
        if mocne_barwy(kadr)["odrzuc"]:
            odrzucone.append({"plik": nazwa, "powod": "mocne barwy w kadrze"})
            continue
        if najlepszy is None or ocena > najlepszy["ocena"]:
            najlepszy = {"ocena": ocena, "kadr": kadr, "prosty": prosty, "plik": k["plik"], "obrot": k.get("obrot", 0), "pudelko": pudelko, "pole": pole,
                         "przechylenie": k.get("przechylenie"), "kolor_calego": k["kolor_calego"], "miekkie": k["miekkie"]}
        if ocena >= 4:
            break
    if najlepszy is None or najlepszy["ocena"] < 3:
        powody = "; ".join(f"{o['plik']}: {o['powod']}" for o in odrzucone[:6])[:600]
        raise ValueError(f"zadne zdjecie nie przeszlo kontroli lusterka ({len(pasujace)} pasujacych), potrzebny przeglad reczny. Odrzucone: {powody}")
    najlepszy["odrzucone"] = odrzucone
    return najlepszy


def dobierz_lusterko_z_zapasem(profil: dict) -> dict:
    """Tani model odrzuca tez dobre makro, a o lusterku i tak decyduje drozszy. Bez tego klientka odpadala przez jeden falszywy alarm."""
    pomin = set(profil["odrzucone"])
    try:
        return dobierz_lusterko(profil["ranking"], profil["cel"], profil["typ"], pomin=pomin)
    except ValueError:
        pass
    sprawdzone = {k["plik"] for k in profil["ranking"]}
    zapas = [{**k, "ocena": k["arkusz"], "pole": {"x0": 0.25, "y0": 0.25, "x1": 0.75, "y1": 0.75}, "obrot": 0, "przechylenie": 0}
             for k in profil["z_arkuszy"] if k["plik"] not in sprawdzone]
    # bez pola oka kolejnosc wyznacza rodzaj kadru z arkusza: makro przed twarza
    zapas.sort(key=lambda k: (0 if k["rodzaj"] in ("oko", "brew") else 1, -k["arkusz"]))
    try:
        return dobierz_lusterko(zapas, profil["cel"], profil["typ"], pomin=pomin)
    except ValueError as e:
        # wlasciciel 11-12: strona ma byc zawsze w nowym stylu. Bez zdjecia oka (paznokcie, konto szkoleniowe, same grafiki)
        # lusterko dostaje najlepsze zdjecie z profilu, kadr ze srodka, bez kontroli modelu - zamiast spadku do fabryki
        awaryjne = _lusterko_awaryjne(profil, pomin)
        if awaryjne is None:
            raise
        print(f"   lusterko awaryjne: {Path(awaryjne['plik']).name} ({str(e)[:80]})", file=sys.stderr)
        return awaryjne


def _lusterko_awaryjne(profil: dict, pomin: set) -> dict | None:
    """Najlepsze zdjecie bez kontroli oka: najpierw przepuszczone przez arkusze (bez napisu), potem ostre z filtrow lokalnych."""
    z_ark = sorted([k for k in profil.get("z_arkuszy", []) if Path(k["plik"]).name not in pomin and not k.get("tekst_gdzies")],
                   key=lambda k: -k.get("arkusz", 0))
    lokalne = sorted([k for k in profil.get("wszystkie", []) if Path(k["plik"]).name not in pomin],
                     key=lambda k: -k.get("ostrosc", 0))
    for k in z_ark + lokalne:
        try:
            prosty = obroc(otworz(k["plik"]), k.get("obrot", 0))
        except OSError:
            continue
        if min(prosty.size) < 320:
            continue
        pole = {"x0": 0.32, "y0": 0.32, "x1": 0.68, "y1": 0.68}
        kadr, pudelko = kadr_lusterka(prosty, pole, profil["cel"], False)
        skala_pliku = skala_zdjecia(*prosty.size)
        return {"ocena": 3.0, "kadr": kadr, "prosty": prosty, "plik": k["plik"], "obrot": k.get("obrot", 0), "pudelko": pudelko,
                "pole": pole, "przechylenie": 0, "kolor_calego": mocne_barwy(prosty, srodkowe_kolo=False)["odrzuc"],
                "miekkie": 3 * max(390 / (prosty.width * skala_pliku), 561 / (prosty.height * skala_pliku)) > 2,
                "odrzucone": [], "awaryjne": True}
    return None


def skala_zdjecia(w: int, h: int) -> float:
    """Krotszy bok do 1000 px, dluzszy do 1800 px. Sam limit 1200 na dluzszym boku rozmywal okladki reeli i zdjecia poziome w lusterku."""
    return min(1.0, 1000 / min(w, h), 1800 / max(w, h))


def wczytaj_odrzucone(nick: str) -> dict:
    """Zdjecia odrzucone przy ogladaniu przez czlowieka: dobor ich juz nie wezmie."""
    plik = KATALOG / "dobor" / nick / "odrzucone.json"
    return json.loads(plik.read_text(encoding="utf-8")) if plik.exists() else {}


def _ocena_kandydatki(k: dict, cel: str, typ: str) -> dict | None:
    """Jedno wywolanie taniego modelu na kandydatke. Kod sam odrzuca po flagach. Zla odpowiedz to tylko jedna kandydatka mniej."""
    try:
        obraz = otworz(k["plik"])
        o = ocen_kandydata(obraz, cel, typ, MODEL_KOLO)
        obrot = 0
        if not o.get("upright", True):
            obrot = znajdz_obrot(obraz, MODEL_KOLO)
            if obrot:
                # pole z obroconego obrazu nic juz nie znaczy: druga ocena dopiero po obrocie
                o = ocen_kandydata(obroc(obraz, obrot), cel, typ, MODEL_KOLO)
    except Exception as e:
        print("pomijam", Path(k["plik"]).name, type(e).__name__, e)
        return None
    if any(o.get(f) for f in ("text_on_subject", "collage", "strong_colours", "tools")) or not o.get("eye_open", True):
        return None
    pole = pole_z_odpowiedzi(o.get("box"))
    if not pole:
        return None
    return {**k, "obrot": obrot, "pole": pole, "twarz": pole_z_odpowiedzi(o.get("face")), "usta": pole_z_odpowiedzi(o.get("lips")),
            "ocena_modelu": float(o.get("appeal", 3)), "tekst_gdzies": bool(o.get("text_anywhere"))}


def _maska_kola(kadr: Image.Image, bok: int, ciecie: float = 0.0, strona: int = 0) -> Image.Image:
    """Kadr tak, jak zobaczy go telefon: kolo, a przy cieciu krawedzia reszta na czarno."""
    im = kadr.resize((bok, bok), Image.LANCZOS)
    maska = Image.new("L", (bok * 2, bok * 2), 0)
    d = ImageDraw.Draw(maska)
    d.ellipse((0, 0, bok * 2 - 1, bok * 2 - 1), fill=255)
    if ciecie:
        szer = int(bok * 2 * ciecie)
        d.rectangle((0, 0, szer, bok * 2) if strona < 0 else (bok * 2 - szer, 0, bok * 2, bok * 2), fill=0)
    wynik = Image.new("RGB", (bok, bok), "black")
    wynik.paste(im, (0, 0), maska.resize((bok, bok), Image.LANCZOS))
    return wynik


def kadr_oceny(k: dict, cel: str) -> Image.Image:
    """Kwadrat wokol tematu do wspolnej oceny na arkuszu."""
    prosty = obroc(otworz(k["plik"]), k.get("obrot", 0))
    return _maska_kola(kadr_lusterka(prosty, k["pole"], cel)[0], 300)


def ocen_profil(nick: str, ile_kandydatek: int = 16) -> dict:
    """Wspolna ocena dla lusterka i kol. Calosc to kilka arkuszy i po jednym wywolaniu na kandydatke."""
    from concurrent.futures import ThreadPoolExecutor

    folder = DANE / nick
    profil = json.loads((folder / "profile.json").read_text(encoding="utf-8"))
    typ, cel = typ_uslugi(profil)
    raport: dict = {}
    kand = kandydaci(folder, raport)
    if not kand:
        raise ValueError("brak zdjec: " + nick)
    ranking = przeglad(kand, typ)
    raport["po_arkuszach"] = len(ranking)
    odrzucone = wczytaj_odrzucone(nick)
    # pierwszenstwo maja rodzaje pasujace do uslugi. Reszta wyzej ocenionych daje rozne ujecia do kol.
    rodzaje = RODZAJE_LUSTERKA.get(typ, ["oko", "twarz"])
    ranking = [k for k in ranking if Path(k["plik"]).name not in odrzucone]
    ranking.sort(key=lambda k: (0 if k["rodzaj"] in rodzaje[:-1] else 1 if k["rodzaj"] in rodzaje else 2, -k["arkusz"], -k["ostrosc"]))
    finalne: list = []
    start = 0
    while start < len(ranking) and start < MAX_KANDYDATEK:
        # kolejne partie tylko wtedy, gdy brakuje dobrych zdjec na lusterko i siedem kol
        wybrane = ranking[start:start + ile_kandydatek]
        start += len(wybrane)
        with ThreadPoolExecutor(MAX_ROWNOCZESNIE) as ex:
            ocenione = [o for o in ex.map(lambda k: _ocena_kandydatki(k, cel, typ), wybrane) if o]
        raport["po_kontroli_kandydatek"] = raport.get("po_kontroli_kandydatek", 0) + len(ocenione)
        cale = ocen_cale(ocenione)
        bez_kolazy = []
        for i, k in enumerate(ocenione, 1):
            c = cale.get(i) or {}
            if c.get("two_photos"):
                continue
            bez_kolazy.append({**k, "tekst_gdzies": bool(c.get("text") or k["tekst_gdzies"])})
        raport["po_calych_postach"] = raport.get("po_calych_postach", 0) + len(bez_kolazy)
        oceny = ocen_kadry([kadr_oceny(k, cel) for k in bez_kolazy])
        for i, k in enumerate(bez_kolazy, 1):
            o = oceny.get(i) or {}
            przechylenie = float(o.get("tilt") or 0)
            if o.get("bad") or o.get("upside_down") or not o.get("eye", True) or przechylenie > MAX_PRZECHYLENIE_KOLA:
                continue
            finalne.append({**k, "ocena": float(o.get("a", k["ocena_modelu"])), "przechylenie": przechylenie})
        if sum(1 for k in finalne if k["ocena"] >= 4) >= 5 and len(finalne) >= 9:
            break
    finalne.sort(key=lambda k: (-k["ocena"], -k["ostrosc"]))
    raport["ocenionych_kandydatek"] = start
    raport["po_ocenie_kadrow"] = len(finalne)
    return {"typ": typ, "cel": cel, "ranking": finalne, "raport": raport, "odrzucone": odrzucone, "z_arkuszy": ranking, "wszystkie": kand}


def dobierz(nick: str, wyjscie: Path) -> dict:
    wyjscie.mkdir(parents=True, exist_ok=True)
    pamiec_odpowiedzi(wyjscie / "odpowiedzi.json")
    profil = ocen_profil(nick)
    wynik = dobierz_lusterko_z_zapasem(profil)
    wynik["kadr"].save(wyjscie / "lusterko.jpg", quality=90)
    wynik["prosty"].save(wyjscie / "lusterko-pelne.jpg", quality=88)
    raport = {"typ": profil["typ"], **{k: wynik[k] for k in ("ocena", "plik", "obrot", "pudelko")}}
    (wyjscie / "lusterko.json").write_text(json.dumps(raport, ensure_ascii=False, indent=2), encoding="utf-8")
    return raport


if __name__ == "__main__":
    for nick in sys.argv[1:]:
        try:
            r = dobierz(nick, KATALOG / "dobor" / nick)
            print(f"OK  {nick}: {os.path.basename(r['plik'])} obrot={r['obrot']} ocena={r['ocena']} kadr={r['pudelko']}")
        except Exception as e:
            print(f"ERR {nick}: {type(e).__name__}: {e}")
