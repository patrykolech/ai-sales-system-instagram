#!/usr/bin/env python3
"""Agenci generatora "Moment w lustrze". Te same role co zespol strona-animowana (web-analityk, web-strateg, web-copywriter,
web-qa), ale jako krotkie zapytania API, ktore generuj.py wywoluje sam przy kazdej klientce. Silnik: ByteCatCode
(Claude Sonnet 5 / Haiku 4.5, zapas GPT-6 Astra). Kazda odpowiedz sprawdza kod: agent nie moze dopisac faktu spoza danych.

  weryfikator  (web-analityk)   nazwa, miasto, ja/my, typ uslugi; kod przyjmuje tylko to, co potwierdzaja dane profilu
  art director (web-strateg)    rodzina palety z arkusza okladek, awatara i postow (paleta_beauty.wybierz_modelem)
  copywriter   (web-copywriter) O mnie, tekst przy kontakcie, zdanie w stopce, poprawki jezykowe pytan FAQ z profilu
  qa           (web-qa)         zrzuty gotowej strony na telefonie -> ocena, lista problemow, "gotowa" albo "do poprawki"
  zapas wizji                   dobierz_zdjecie.zapytaj przechodzi tu, gdy RouteMux nie odpowiada albo saldo spadnie pod prog

Klucze: ../klucz_bytecatcode_claude.txt i ../klucz_bytecatcode_openai.txt albo zmienne BYTECATCODE_CLAUDE_KEY
i BYTECATCODE_OPENAI_KEY (na serwerze). Klucza nie wypisujemy. Pamiec odpowiedzi: dobor/<nick>/agenci.json, wiec drugie
uruchomienie nic nie kosztuje. Koszt: licznik zuzycia kluczy (/api/usage/token, 500 000 jednostek = 1 w walucie panelu).

    python agenci.py test                  # polaczenie, modele, zuzycie
    python agenci.py qa <nick> [...]       # sam przeglad QA zbudowanej strony (prototyp_strona/<nick>-logo)
    python agenci.py weryfikator <nick>    # co agent mysli o nazwie i miescie (bez zapisu)
"""
from __future__ import annotations

import base64
import hashlib
import io
import json
import os
import re
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

from PIL import Image

KATALOG = Path(__file__).resolve().parent
PROJEKT = KATALOG.parent
BAZA = os.environ.get("BYTECATCODE_URL", "https://www.bytecatcode.org").rstrip("/")
JEDNOSTKI_NA_1 = 500_000

SONNET = "claude-sonnet-5"
HAIKU = "claude-haiku-4-5-20251001"
ASTRA = "gpt-6-astra"
ROLE = {                                   # pierwszy model glowny, kolejne to zapas (po bledzie albo zlej odpowiedzi)
    "weryfikator": [HAIKU, SONNET, ASTRA],
    "copywriter": [SONNET, ASTRA],
    "art_director": [SONNET, ASTRA],
    "qa": [SONNET, ASTRA],
    "qa_sprawdzenie": [ASTRA, SONNET],     # drugi przebieg innym modelem: ten sam model chetnie potwierdza wlasne zgloszenie
}
# zapas wizji dla dobierz_zdjecie (model routemux -> model ByteCatCode). Pomiar 2026-11-10 na 14 kandydatkach brwi (6 flag):
# zgodnosc z GLM: GPT-6 Astra 80/84, Sonnet 5 75/84, Haiku 4.5 65/84 (Haiku przepuszczal zamkniete oczy). Wszedzie Astra.
ZAPAS_WIZJI = {
    "google/gemini-3.8-flash": ASTRA,
    "google/gemini-3.5-flash-lite": ASTRA,
    "zhipu/glm-5.3-flash": ASTRA,
}

STAT = {"wywolania": 0, "z_pamieci": 0, "bledy": 0, "modele": {}, "zuzycie_start": None}
_blokada = threading.Lock()
_semafor = threading.BoundedSemaphore(3)


# ---------------------------------------------------------------- klucze i zuzycie
def klucz(rodzaj: str) -> str:
    """rodzaj: 'claude' albo 'openai'."""
    env = os.environ.get(f"BYTECATCODE_{rodzaj.upper()}_KEY")
    if env:
        return env.strip()
    plik = PROJEKT / f"klucz_bytecatcode_{rodzaj}.txt"
    if not plik.exists():
        raise RuntimeError(f"brak klucza ByteCatCode ({plik.name} albo BYTECATCODE_{rodzaj.upper()}_KEY)")
    return plik.read_text(encoding="utf-8-sig").strip().splitlines()[0].strip()


def dostepne() -> bool:
    try:
        klucz("claude")
        return True
    except RuntimeError:
        return False


def zuzycie() -> float:
    """Laczne zuzycie obu kluczy w walucie panelu (od poczatku istnienia kluczy)."""
    suma = 0
    for rodzaj in ("claude", "openai"):
        try:
            req = urllib.request.Request(BAZA + "/api/usage/token", headers={"Authorization": "Bearer " + klucz(rodzaj),
                                                                            "User-Agent": "lustro-agenci/1.0"})
            with urllib.request.urlopen(req, timeout=40) as odp:
                suma += int(json.load(odp)["data"]["total_used"])
        except Exception:
            pass
    return suma / JEDNOSTKI_NA_1


def start_licznika() -> None:
    if STAT["zuzycie_start"] is None:
        STAT["zuzycie_start"] = zuzycie()


def koszt_od_startu() -> float:
    if STAT["zuzycie_start"] is None:
        return 0.0
    return round(zuzycie() - STAT["zuzycie_start"], 4)


# ---------------------------------------------------------------- zapytania
def _jpeg(obraz: Image.Image | bytes, bok: int = 1568, jakosc: int = 82) -> bytes:
    if isinstance(obraz, bytes):
        return obraz
    im = obraz.convert("RGB")
    if max(im.size) > bok:
        im.thumbnail((bok, bok), Image.LANCZOS)
    b = io.BytesIO()
    im.save(b, "JPEG", quality=jakosc)
    return b.getvalue()


def _post(sciezka: str, tresc: dict, naglowki: dict, timeout: int) -> dict:
    req = urllib.request.Request(BAZA + sciezka, data=json.dumps(tresc).encode(), headers={
        "Content-Type": "application/json", "User-Agent": "lustro-agenci/1.0", **naglowki})
    with _semafor, urllib.request.urlopen(req, timeout=timeout) as odp:
        return json.load(odp)


def _jeden(model: str, prompt: str, obrazy: list[bytes], max_tokens: int, system: str, temperatura: float, timeout: int,
           proby: int = 3) -> str:
    """Surowy tekst odpowiedzi jednego modelu (z ponowieniem przy 429/5xx i przerwie sieci)."""
    for proba in range(proby):
        try:
            if model.startswith("claude"):
                tresc = [{"type": "image", "source": {"type": "base64", "media_type": "image/jpeg",
                                                      "data": base64.b64encode(o).decode()}} for o in obrazy]
                tresc.append({"type": "text", "text": prompt})
                body = {"model": model, "max_tokens": max_tokens, "temperature": temperatura,
                        "messages": [{"role": "user", "content": tresc}]}
                if system:
                    body["system"] = system
                d = _post("/v1/messages", body, {"x-api-key": klucz("claude"), "anthropic-version": "2023-06-01"}, timeout)
                t = "".join(c.get("text", "") for c in d.get("content") or [] if c.get("type") == "text")
                u = d.get("usage") or {}
                wej, wyj = int(u.get("input_tokens") or 0), int(u.get("output_tokens") or 0)
            else:
                tresc = [{"type": "text", "text": prompt}] + [
                    {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + base64.b64encode(o).decode()}} for o in obrazy]
                wiad = ([{"role": "system", "content": system}] if system else []) + [{"role": "user", "content": tresc}]
                body = {"model": model, "max_tokens": max_tokens, "temperature": temperatura, "messages": wiad}
                d = _post("/v1/chat/completions", body, {"Authorization": "Bearer " + klucz("openai")}, timeout)
                t = d["choices"][0]["message"].get("content") or ""
                if isinstance(t, list):
                    t = "".join(c.get("text", "") for c in t)
                u = d.get("usage") or {}
                wej, wyj = int(u.get("prompt_tokens") or 0), int(u.get("completion_tokens") or 0)
            with _blokada:
                STAT["wywolania"] += 1
                m = STAT["modele"].setdefault(model, {"wywolania": 0, "wejscie": 0, "wyjscie": 0})
                m["wywolania"] += 1
                m["wejscie"] += wej
                m["wyjscie"] += wyj
            if not t.strip():
                raise RuntimeError(f"{model}: pusta odpowiedz")
            return t
        except urllib.error.HTTPError as e:
            tekst = e.read().decode(errors="replace")[:300]
            if e.code not in (408, 429, 500, 502, 503, 504) or proba == proby - 1:
                raise RuntimeError(f"{model} HTTP {e.code}: {tekst}") from e
            time.sleep(4 * (proba + 1))
        except (TimeoutError, socket.timeout, urllib.error.URLError, ConnectionError) as e:
            if proba == proby - 1:
                raise RuntimeError(f"{model}: siec ({type(e).__name__})") from e
            time.sleep(5)
    raise RuntimeError(f"{model}: brak odpowiedzi")


def json_z_tekstu(t: str) -> dict:
    t = re.sub(r"^```(?:json)?|```$", "", t.strip(), flags=re.M).strip()
    m = re.search(r"\{.*\}", t, re.S)
    if not m:
        raise ValueError("odpowiedz bez JSON: " + t[:120])
    return json.loads(m.group(0))


class Pamiec:
    """Odpowiedzi agentow na dysku (dobor/<nick>/agenci.json)."""

    def __init__(self, nick: str | None):
        self.plik = KATALOG / "dobor" / nick / "agenci.json" if nick else None
        self.d = json.loads(self.plik.read_text(encoding="utf-8")) if self.plik and self.plik.exists() else {}

    def get(self, k):
        return self.d.get(k)

    def put(self, k, v):
        if not self.plik:
            return
        self.d[k] = v
        self.plik.parent.mkdir(parents=True, exist_ok=True)
        self.plik.write_text(json.dumps(self.d, ensure_ascii=False, indent=1), encoding="utf-8")


def zapytaj(rola: str, prompt: str, obrazy=(), max_tokens: int = 1200, system: str = "", temperatura: float = 0.2,
            nick: str | None = None, sprawdz=None, timeout: int = 150) -> tuple[dict, str]:
    """(JSON, model). Modele z ROLE[rola] po kolei. sprawdz(dane) -> powod odrzucenia albo None; po odrzuceniu jedna
    poprawka tym samym modelem, potem nastepny model. Odpowiedz zaakceptowana trafia do pamieci klientki."""
    jpegi = [_jpeg(o) for o in obrazy]
    odcisk = hashlib.sha1("|".join([rola, ROLE[rola][0], system, prompt] + [hashlib.sha1(j).hexdigest() for j in jpegi]).encode()).hexdigest()
    pam = Pamiec(nick)
    if pam.get(odcisk):
        STAT["z_pamieci"] += 1
        w = pam.get(odcisk)
        return w["dane"], w["model"]
    bledy = []
    for model in ROLE[rola]:
        p = prompt
        for proba in range(2):
            try:
                dane = json_z_tekstu(_jeden(model, p, jpegi, max_tokens, system, temperatura, timeout))
            except (RuntimeError, ValueError, json.JSONDecodeError) as e:
                bledy.append(f"{model}: {e}"[:200])
                STAT["bledy"] += 1
                if isinstance(e, RuntimeError):
                    break                                    # blad API: od razu nastepny model
                continue
            powod = sprawdz(dane) if sprawdz else None
            if not powod:
                pam.put(odcisk, {"rola": rola, "model": model, "dane": dane, "czas": time.strftime("%Y-%m-%d %H:%M")})
                return dane, model
            bledy.append(f"{model}: odrzucone ({powod})"[:200])
            p = prompt + f"\n\nPoprzednia odpowiedź złamała zasady: {powod}. Popraw i odpowiedz ponownie samym JSON."
    raise RuntimeError(f"agent {rola}: brak poprawnej odpowiedzi | " + " | ".join(bledy[-4:]))


def tekst_z_obrazem(tekst: str, jpeg: bytes, model_routemux: str, max_tokens: int) -> tuple[str, str]:
    """Zapas wizji dla dobierz_zdjecie.zapytaj: surowy tekst (parsuje go wywolujacy) i nazwa modelu ByteCatCode."""
    model = ZAPAS_WIZJI.get(model_routemux, ASTRA)
    # GPT liczy ukryty prompt serwisu do limitu, Claude nie; zapas tokenow, zeby lista z arkusza nie urwala sie w polowie
    return _jeden(model, tekst, [jpeg], max(max_tokens, 1500), "", 0.0, 180), model


# ---------------------------------------------------------------- dane i pomocnicze
def _bez_ogonkow(t: str) -> str:
    return t.lower().translate(str.maketrans("ąćęłńóśźż", "acelnoszz"))


def _zrodlo(nick: str, prof: dict, brief: dict) -> str:
    f = brief.get("facts") or {}
    adres = " ".join(str((f.get(k) or {}).get("value") or "") for k in ("address_city", "address_street", "address"))
    return _bez_ogonkow(" ".join([prof.get("biography") or "", prof.get("full_name") or "", nick.replace("_", " ").replace(".", " "),
                                  (brief.get("content") or {}).get("brand_name") or "", adres]))


ZAKAZANE = re.compile(r"\blat\b|\blata\b|rok\w* doświadcz|doświadczen|nagr[oó]d|certyfik|dyplom|najlepsz|gwarant|"
                      r"tysi[aą]c|setk|\d+\s*%|!|#", re.I)
EMOJI = re.compile("[\U0001F000-\U0001FAFF←-⇿⌀-⏿①-➿⤀-⥿⬀-⯿︀-️‍]")


def _liczby_spoza(tekst: str, zrodlo: str) -> str | None:
    for liczba in re.findall(r"\d+", tekst):
        if liczba not in zrodlo:
            return liczba
    return None


# ---------------------------------------------------------------- 1. weryfikator (web-analityk)
TYPY = ["rzesy", "brwi", "pmu", "makijaz", "paznokcie", "wlosy", "ogolny"]


OPISOWE = {"profesjonalne", "profesjonalna", "profesjonalny", "szkolenia", "szkolenie", "kursy", "stylizacja", "stylistka",
           "rzesy", "rzes", "brwi", "brew", "laminacja", "henna", "przedluzanie", "makijaz", "permanentny", "permanentnego",
           "kosmetologia", "kosmetyka", "zabiegi", "gabinet", "salon", "studio", "beauty", "lashes", "lash", "brows", "makeup",
           "manicure", "pedicure", "paznokcie", "paznokci", "pmu", "artist", "and", "oraz", "urody", "uroda", "twarzy", "ciala"}


def _bio_mnoga(prof: dict) -> bool:
    """Ta sama regula co zbuduj_strone.liczba_mnoga: czasownik w 1. osobie l. mnogiej w bio."""
    return bool(re.search(r"\b\w+(amy|emy|imy)\b", prof.get("biography") or "", re.I))


def weryfikator(nick: str, prof: dict, brief: dict, propozycja: dict, logo: str = "") -> dict:
    """{'nazwa','miasto','mnoga','typ','uwagi','przyjete':{pole: bool},'model'}. Pola nieprzyjete = propozycja kodu.
    logo = napis odczytany z jej logo (awatar, okladki): wtedy nazwa ma sie z nim zgadzac i moze z niego pochodzic."""
    f, c = brief.get("facts") or {}, brief.get("content") or {}
    uslugi = list(dict.fromkeys((s.get("category") or s.get("name") or "").strip() for s in c.get("services") or []))[:10]
    adres = {k: (f.get(k) or {}).get("value") for k in ("address_city", "address_street") if (f.get(k) or {}).get("value")}
    dane = {
        "nick": nick, "nazwa konta": prof.get("full_name") or "", "bio": prof.get("biography") or "",
        "nazwa marki z analizy (bywa zgadywana)": c.get("brand_name") or "", "kicker (bywa zgadywany)": c.get("hero_kicker") or "",
        "adres z analizy": adres, "rezerwacja": (f.get("booking_url") or {}).get("value") or "",
        "kategorie usług z cennika": uslugi, "propozycja kodu": propozycja,
    }
    if logo:
        dane["napis na jej logo (z awatara lub okładek, najpewniejsze źródło nazwy marki)"] = logo
    prompt = f"""Jesteś analitykiem danych zespołu, który robi strony dla stylistek beauty z ich profilu na Instagramie.
Sprawdź dane profilu i ustal fakty do strony. Nie zgaduj: wszystko musi wynikać z danych poniżej.

DANE:
{json.dumps(dane, ensure_ascii=False, indent=1)}

Ustal:
- "nazwa": nazwa marki tak, jak klientka się przedstawia (nazwa studia albo imię z usługą, np. "Rzesy Przyklad"), max 40 znaków,
  z poprawnymi polskimi znakami i wielkimi literami. Kolejność źródeł: napis na logo (jeśli jest), nazwa konta, bio,
  a nick dopiero gdy nic innego nie podaje nazwy. Nie składaj nazwy z rozbitego nicka (np. "salon_c" ->
  "Irina Lash Studio"), gdy logo albo nazwa konta mówi inaczej; nazwa z analizy bywa właśnie takim zgadywaniem.
  Słowa usług i miasta z nazwy konta ("Rzęsy & Brwi | Ruda Śląska | Mon Ami" -> "Mon Ami") pomijaj. Sam opis usług to nie
  nazwa ("Profesjonalne Szkolenia Rzęsy & Brwi", "Stylizacja rzęs Kraków"): wtedy imię i nazwisko z nicka lub nazwy
  z analizy, z polskimi znakami (np. "zaneta_stoszek_" -> "Żaneta Stoszek"). Bez emoji.
- "miasto": miasto, w którym przyjmuje, w mianowniku (np. "Poznań"), tylko jeśli wprost widać je w bio, nazwie konta,
  nicku albo adresie. Jeśli nie ma pewności, pusty napis.
- "mnoga": true, gdy to salon albo zespół mówiący o sobie „my” (robimy, zapraszamy, nasze studio); false, gdy jedna osoba.
- "typ": główna usługa, jedna z: {", ".join(TYPY)} (pmu = makijaż permanentny; ogolny = kilka różnych usług bez przewagi).
- "uwagi": do 3 krótkich zdań o sprzecznościach lub ryzykach w danych (np. dwa miasta, to nie jest profil beauty,
  nazwa z analizy nie zgadza się z profilem). Pusta lista, gdy wszystko się zgadza.

Odpowiedz wyłącznie JSON: {{"nazwa": "", "miasto": "", "mnoga": false, "typ": "", "uwagi": []}}"""
    zrodlo = _zrodlo(nick, prof, brief) + " " + _bez_ogonkow(logo)

    def sprawdz(o):
        if not isinstance(o, dict) or not isinstance(o.get("nazwa"), str) or o.get("typ") not in TYPY:
            return "zly format albo typ spoza listy"
        return None

    o, model = zapytaj("weryfikator", prompt, max_tokens=500, nick=nick, sprawdz=sprawdz)
    przyjete = {}
    nazwa = re.sub(r"\s+", " ", o.get("nazwa") or "").strip()
    slowa = [s for s in re.split(r"[\s&|•·-]+", nazwa) if len(s) >= 3]
    przyjete["nazwa"] = bool(nazwa) and len(nazwa) <= 40 and not EMOJI.search(nazwa) and \
        all(re.search(r"\b" + re.escape(_bez_ogonkow(s)[:5]), zrodlo) for s in slowa) and \
        not all(_bez_ogonkow(s) in OPISOWE for s in slowa)   # "Profesjonalne Szkolenia Rzesy & Brwi" to opis, nie marka
    miasto = (o.get("miasto") or "").strip()
    przyjete["miasto"] = miasto == "" or bool(re.search(r"\b" + re.escape(_bez_ogonkow(miasto)[:6]), zrodlo))
    przyjete["mnoga"] = isinstance(o.get("mnoga"), bool)
    return {"nazwa": nazwa if przyjete["nazwa"] else propozycja.get("nazwa"),
            "miasto": miasto if przyjete["miasto"] else propozycja.get("miasto"),
            # "my" z bio (robimy, zapraszamy) wygrywa: agent bral "Studio" za jedna osobe przy bio "Tworzymy. Doradzamy."
            "mnoga": (o["mnoga"] or _bio_mnoga(prof)) if przyjete["mnoga"] else propozycja.get("mnoga"),
            "typ": o.get("typ"), "uwagi": [str(u)[:200] for u in (o.get("uwagi") or [])][:3],
            "przyjete": przyjete, "agent": {k: o.get(k) for k in ("nazwa", "miasto", "mnoga", "typ")}, "model": model}


# ---------------------------------------------------------------- 2. art director (web-strateg): paleta
def art_director_paleta(nick: str, pytanie: str, arkusz: Image.Image, rodziny: set[str]) -> dict:
    """Ta sama prosba co w paleta_beauty (PYTANIE), ale do Claude Sonnet: wybor rodziny z 11."""
    system = ("You are the art director of a studio designing premium websites for Polish beauty professionals. "
              "You care about taste, contrast and a clear accent colour. Answer with JSON only.")

    def sprawdz(o):
        return None if isinstance(o, dict) and o.get("family") in rodziny else "family spoza listy"

    o, model = zapytaj("art_director", pytanie, [arkusz], max_tokens=400, system=system, nick=nick, sprawdz=sprawdz)
    return dict(o, model=model)


# ---------------------------------------------------------------- 3. copywriter (web-copywriter)
def copywriter(nick: str, fakty: dict, mnoga: bool, faq: list[tuple[str, str]], kontakt: str, stopka: str) -> dict:
    """{'o_mnie': [2 akapity] | None, 'kontakt': str | None, 'stopka': str | None, 'faq': [(q, a)] | None, 'model', 'odrzucone'}.
    Kazde pole sprawdzane osobno: zle pole wypada (zostaje wersja z danych), reszta zostaje."""
    import o_mnie as OM
    osoba = ("pierwszej osobie liczby mnogiej (salon: „robimy”, „zapraszamy”)" if mnoga
             else "pierwszej osobie liczby pojedynczej (stylistka mówi o sobie: „robię”, „pracuję”)")
    faq_wej = [{"q": q, "a": a} for q, a in faq]
    prompt = f"""Jesteś copywriterem zespołu, który robi strony wizytówki dla stylistek beauty. Piszesz po polsku, naturalnie,
spokojnie i konkretnie, jak sama właścicielka w rozmowie z klientką. Jedyne źródło wiedzy to fakty poniżej.

FAKTY (zweryfikowane):
{OM.fakty_tekst(fakty)}

OBECNE TEKSTY (z automatycznej analizy profilu, mogą mieć błędy językowe albo zmyślenia):
- tekst przy kontakcie: {kontakt or "(brak)"}
- zdanie w stopce: {stopka or "(brak)"}
- pytania FAQ z profilu: {json.dumps(faq_wej, ensure_ascii=False) if faq_wej else "(brak)"}

NAPISZ:
1. "o_mnie": dokładnie 3 akapity sekcji „O mnie”, każdy 2-3 zdania (do 22 słów w zdaniu), razem 70-120 słów,
   w {osoba}, ciepło i osobiście, ale rzeczowo. Pierwszy: czym się zajmuje i gdzie, z nazwami usług z faktów.
   Drugi: jak pracuje - fakty z bio (technika, metoda, podejście), a do tego zwykły przebieg wizyty w tej usłudze
   bez obietnic (np. rozmowa o oczekiwanym efekcie, dobranie stylizacji do oka lub twarzy, wskazówki po zabiegu).
   Trzeci: dla kogo jest ta wizyta i zaproszenie: jak się umówić (rezerwacja online, jeśli jest w faktach,
   albo wiadomość na Instagramie). Nie zaczynaj od „Jestem {fakty.get('nazwa', '')}”, „Cześć” ani „Hej”.
2. "kontakt": 1-2 zdania zachęty przy przycisku rezerwacji (max 180 znaków), bez obietnic efektu.
3. "stopka": jedno krótkie zdanie do stopki (max 110 znaków), np. o tym, gdzie i czym się zajmuje.
4. "faq": te same pytania z profilu z poprawioną polszczyzną (pytanie i odpowiedź). Nie dodawaj nowych pytań. Usuń pytanie,
   którego odpowiedź twierdzi coś, czego nie ma w faktach (czas, ból, trwałość, ceny). Pusta lista, gdy pytań nie było.

ZASADY dla wszystkich tekstów: tylko informacje z faktów; bez lat doświadczenia, liczby klientek, nagród, certyfikatów,
kursów, cen, liczb i obietnic efektu; bez przymiotników reklamowych (profesjonalny, idealny, perfekcyjny, wyjątkowy,
najwyższej jakości); bez emoji, wykrzykników, hashtagów i cudzysłowów; zdania wielką literą, nazwy własne (miasto,
nazwa studia, Instagram, Booksy) wielką literą. Lepiej krócej niż zmyślać.

Odpowiedz wyłącznie JSON: {{"o_mnie": ["", ""], "kontakt": "", "stopka": "", "faq": [{{"q": "", "a": ""}}]}}"""
    zrodlo = (OM.fakty_tekst(fakty) + " " + json.dumps(faq_wej, ensure_ascii=False)).lower()

    def zly_tekst(t, limit):
        if not isinstance(t, str) or not t.strip():
            return "pusty"
        if len(t) > limit:
            return f"za dlugi ({len(t)} znakow, limit {limit})"
        if EMOJI.search(t):
            return "emoji"
        n = _liczby_spoza(t, zrodlo)
        if n:
            return f"liczba {n} spoza faktow"
        for m in ZAKAZANE.finditer(t):
            if m.group(0).lower() not in zrodlo:
                return f"zakazane: {m.group(0)}"
        return None

    def sprawdz(o):
        if not isinstance(o, dict) or not isinstance(o.get("o_mnie"), list):
            return "zly format"
        return OM.sprawdz(o["o_mnie"], fakty)          # O mnie musi przejsc; pozostale pola oceniamy osobno ponizej

    o, model = zapytaj("copywriter", prompt, max_tokens=1400, temperatura=0.4, nick=nick, sprawdz=sprawdz)
    wynik = {"model": model, "odrzucone": {}}
    wynik["o_mnie"] = OM.popraw_pisownie([re.sub(r"\s+", " ", a).strip() for a in o["o_mnie"]], fakty)
    for pole, limit in (("kontakt", 200), ("stopka", 130)):
        t = re.sub(r"\s+", " ", o.get(pole) or "").strip()
        powod = zly_tekst(t, limit)
        wynik[pole] = None if powod else OM.popraw_pisownie([t], fakty)[0]
        if powod:
            wynik["odrzucone"][pole] = powod
    poz = []
    for q in o.get("faq") or []:
        if not isinstance(q, dict):
            continue
        pq, pa = re.sub(r"\s+", " ", str(q.get("q") or "")).strip(), re.sub(r"\s+", " ", str(q.get("a") or "")).strip()
        powod = zly_tekst(pq, 120) or zly_tekst(pa.replace("!", "."), 320)
        if powod:
            wynik["odrzucone"].setdefault("faq", []).append(f"{pq[:40]}: {powod}")
            continue
        poz.append((pq, pa))
    wynik["faq"] = poz if faq else None
    return wynik


# ---------------------------------------------------------------- 4. qa (web-qa): zrzuty i ocena
QA_PROMPT = """Jesteś testerem jakości (QA) i art directorem w studiu, które robi premium strony dla stylistek beauty.
Na obrazach są kolejne ekrany jednej strony na telefonie (390 px szerokości), od góry do dołu, numerowane E1, E2...
Pierwsze ekrany to animowane hero w trzech stanach: zamknięta puderniczka, otwarte lusterko, okładka ze spisem treści.
Klientka: {nazwa} (@{nick}), usługa: {typ}{miasto}.

Sprawdź, czy strona może trafić do klientki jako podgląd. Szukaj problemów, które widać na zrzutach:
- tekst zasłonięty zdjęciem lub innym elementem, ucięty, nachodzący na siebie, nieczytelny (za mały kontrast);
- puste albo dziwnie duże puste pasy, sekcja bez treści, zepsute lub brakujące zdjęcia, rozjechany układ;
- zdjęcia słabe dla tej usługi: rozmazane, z napisami lub naklejkami, memy, grafiki z tekstem, zdjęcia niezwiązane z pracą,
  sklejki (dwa lub więcej kadrów w jednym zdjęciu z widocznym szwem, np. przed/po jedno nad drugim);
- w lusterku hero powinno być widać oko, brew albo usta z jej pracy, a nie przypadkowy fragment;
- kolory: czy paleta pasuje do beauty i do jej zdjęć, czy jest akcent na przełamanie, czy tła nie są monotonne;
- zakazana jest ramka w kształcie łuku jak okno kościelne: tylko góra półokrągła, dół prosty z ostrymi rogami.
  Koło, owal i prostokąt z zaokrąglonymi WSZYSTKIMI rogami są w porządku i nie są łukiem;
- błędy językowe, angielskie wtrącenia w polskim tekście, dziwne nazwy usług, ceny bez sensu.
Znacznik [DO UZUPEŁNIENIA] / [DO POTWIERDZENIA] jest celowy, nie zgłaszaj go. W otwartej puderniczce (E2) górna
połowa to lusterko ze zdjęciem z jej pracy, a dolna to celowa grafika wkładu (pasek rzęs, puder albo pigment na
kremowej poduszce) - wkładu nie zgłaszaj. Ekrany od E4 to kolejne kawałki jednego
długiego zrzutu: element przecięty górną lub dolną krawędzią ekranu to skutek cięcia (ciąg dalszy jest na sąsiednim
ekranie), nie zgłaszaj go. Zanim zgłosisz brak czegoś, obejrzyj sąsiednie ekrany.

Waga: "krytyczny" = wstyd pokazać (zasłonięty tekst, zepsute zdjęcie, zła osoba/treść, rozjechany ekran),
"sredni" = wyraźnie słabsze miejsce, "drobny" = kosmetyka. Nie zgłaszaj rzeczy, których nie widać na zrzutach.

Odpowiedz wyłącznie JSON:
{{"ocena": 1-10, "problemy": [{{"ekran": "E3", "sekcja": "krótko", "waga": "krytyczny|sredni|drobny", "opis": "co i gdzie, max 25 słów", "obszar": "zdjecia|kolory|tekst|uklad"}}], "mocne_strony": ["max 3 krótkie"]}}"""


def _wolny_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def zrzuty_strony(nick: str, folder: str | None = None, katalog_wyj: Path | None = None) -> list[Image.Image]:
    """Ekrany telefonu 390x844: trzy stany hero (?faza=) i cala strona w stanie koncowym (reduced motion), pociete na ekrany."""
    from playwright.sync_api import sync_playwright
    wyj = KATALOG / "prototyp_strona"
    folder = folder or (nick + "-logo")
    port = _wolny_port()
    srv = subprocess.Popen([sys.executable, "-m", "http.server", str(port), "--bind", "127.0.0.1", "--directory", str(wyj)],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    ekrany: list[Image.Image] = []
    try:
        time.sleep(1.0)
        url = f"http://127.0.0.1:{port}/{folder}/index.html"
        with sync_playwright() as p:
            b = p.chromium.launch()
            ctx = b.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=1, is_mobile=True, has_touch=True)
            pg = ctx.new_page()
            for faza in ("zamknieta", "otwarta", "koncowa"):
                pg.goto(url + "?faza=" + faza, wait_until="networkidle")
                pg.wait_for_timeout(700)
                ekrany.append(Image.open(io.BytesIO(pg.screenshot())).convert("RGB"))
            ctx.close()
            ctx = b.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=1, is_mobile=True, has_touch=True,
                                reduced_motion="reduce")
            pg = ctx.new_page()
            pg.goto(url, wait_until="networkidle")
            pg.evaluate("""async () => { for (let y = 0; y < document.body.scrollHeight; y += 600) { scrollTo(0, y); await new Promise(r => setTimeout(r, 60)); } scrollTo(0, 0); }""")
            pg.wait_for_timeout(600)
            start = pg.evaluate("(() => { const h = document.querySelector('#hero'); return h ? Math.round(h.getBoundingClientRect().bottom + scrollY) : 0; })()")
            cala = Image.open(io.BytesIO(pg.screenshot(full_page=True))).convert("RGB")
            b.close()
        for y in range(max(0, start), cala.height, 844):
            kawalek = cala.crop((0, y, 390, min(cala.height, y + 844)))
            if kawalek.height > 120:
                ekrany.append(kawalek)
    finally:
        srv.terminate()
    if katalog_wyj:
        katalog_wyj.mkdir(parents=True, exist_ok=True)
        for i, e in enumerate(ekrany, 1):
            e.save(katalog_wyj / f"E{i:02d}.jpg", quality=80)
    return ekrany


def _arkusze(ekrany: list[Image.Image], na_arkusz: int = 4) -> list[Image.Image]:
    from PIL import ImageDraw
    out = []
    for i in range(0, len(ekrany), na_arkusz):
        grupa = ekrany[i:i + na_arkusz]
        ark = Image.new("RGB", (len(grupa) * 400 - 10, 844 + 34), "white")
        d = ImageDraw.Draw(ark)
        for j, e in enumerate(grupa):
            ark.paste(e, (j * 400, 34))
            d.rectangle((j * 400, 0, j * 400 + 70, 30), fill="black")
            d.text((j * 400 + 10, 8), f"E{i + j + 1}", fill="white")
        out.append(ark)
    return out


def qa(nick: str, nazwa: str, typ: str, miasto: str = "", folder: str | None = None) -> dict:
    """{'ocena','gotowa','problemy','mocne_strony','ekrany','model','arkusze'}; gotowa = ocena >= 7 i zero krytycznych."""
    katalog = KATALOG / "testy" / "qa_agent" / nick
    ekrany = zrzuty_strony(nick, folder, katalog)
    arkusze = _arkusze(ekrany)
    for i, a in enumerate(arkusze, 1):
        a.save(katalog / f"arkusz_{i}.jpg", quality=78)
    prompt = QA_PROMPT.format(nazwa=nazwa, nick=nick, typ=typ, miasto=f", {miasto}" if miasto else "")

    def sprawdz(o):
        if not isinstance(o, dict) or not isinstance(o.get("ocena"), (int, float)) or not isinstance(o.get("problemy"), list):
            return "zly format"
        return None

    o, model = zapytaj("qa", prompt, arkusze, max_tokens=1800, temperatura=0.0, nick=nick, sprawdz=sprawdz, timeout=240)
    problemy = [p for p in o["problemy"] if isinstance(p, dict)]
    # drugi przebieg: kazdy krytyczny i sredni problem sprawdzany na samym ekranie (i sasiednich), w pelnej rozdzielczosci.
    # Pierwszy przebieg na arkuszach potrafi zglosic brak czegos, co jest (pomiar 2026-11-10: 2 z 3 zgloszen falszywe)
    potwierdzone, odrzucone = [], []
    for pr in problemy:
        if pr.get("waga") not in ("krytyczny", "sredni"):
            potwierdzone.append(pr)
            continue
        m = re.search(r"\d+", str(pr.get("ekran") or ""))
        nr = int(m.group(0)) if m else 0
        if not 1 <= nr <= len(ekrany):
            odrzucone.append(dict(pr, powod="brak numeru ekranu"))
            continue
        obok = [i for i in (nr - 1, nr, nr + 1) if 1 <= i <= len(ekrany) and (i >= 4 or i == nr)]
        obraz = _arkusze([ekrany[i - 1] for i in obok], 3)[0]
        etykiety = ", ".join(f"E{i}" for i in obok)
        pyt = (f"Na obrazie ekrany telefonu {etykiety} (kolejne kawałki jednej strony; to, co przecina krawędź, ciągnie się "
               f"na sąsiednim ekranie). Tester zgłosił na ekranie E{nr}: „{pr.get('opis')}”.\nCzy ten problem naprawdę "
               f"widać? Odpowiedz wyłącznie JSON: {{\"widoczny\": true/false, \"dlaczego\": \"max 15 słów\"}}")
        try:
            w, _ = zapytaj("qa", pyt, [obraz], max_tokens=200, temperatura=0.0, nick=nick,
                           sprawdz=lambda x: None if isinstance(x, dict) and isinstance(x.get("widoczny"), bool) else "zly format")
        except RuntimeError:
            potwierdzone.append(dict(pr, weryfikacja="nieudana"))
            continue
        (potwierdzone if w["widoczny"] else odrzucone).append(dict(pr, weryfikacja=str(w.get("dlaczego") or "")[:120]))
    # znaczniki [DO UZUPEŁNIENIA] / [DO POTWIERDZENIA] sa celowe (decyzja wlasciciela), model i tak je czasem zglasza
    potwierdzone = [p for p in potwierdzone if not re.search(r"DO UZUPE|DO POTWIERDZ", str(p.get("opis")), re.I)]
    krytyczne = [p for p in potwierdzone if p.get("waga") == "krytyczny"]
    ocena = o["ocena"]
    wynik = {"ocena": ocena, "gotowa": ocena >= 7 and not krytyczne, "problemy": potwierdzone,
             "odrzucone_przy_sprawdzeniu": odrzucone, "mocne_strony": o.get("mocne_strony") or [], "ekrany": len(ekrany),
             "model": model, "arkusze": str(katalog.relative_to(KATALOG)).replace("\\", "/"), "czas": time.strftime("%Y-%m-%d %H:%M")}
    (katalog / "qa.json").write_text(json.dumps(wynik, ensure_ascii=False, indent=1), encoding="utf-8")
    return wynik


# ---------------------------------------------------------------- CLI
def _druk(t: str) -> None:
    sys.stdout.buffer.write((t + "\n").encode("utf-8", "replace"))
    sys.stdout.flush()


def main() -> None:
    if len(sys.argv) < 2:
        _druk(__doc__)
        return
    cmd, nicki = sys.argv[1], sys.argv[2:]
    start_licznika()
    if cmd == "test":
        for model in (HAIKU, SONNET, ASTRA):
            t0 = time.time()
            t = _jeden(model, 'Odpowiedz JSON: {"ok": true}', [], 50, "", 0, 60)
            _druk(f"{model}: {t.strip()[:60]} ({time.time() - t0:.1f} s)")
    elif cmd in ("qa", "weryfikator"):
        sys.path.insert(0, str(KATALOG))
        from zbuduj_hero import DANE, KLIENTKI
        for nick in nicki:
            kl = KLIENTKI.get(nick, {})
            if cmd == "qa":
                w = qa(nick, kl.get("nazwa", nick), kl.get("typ", ""), kl.get("miasto", ""))
                _druk(f"{nick}: ocena {w['ocena']} | {'GOTOWA' if w['gotowa'] else 'DO POPRAWKI'} | {w['ekrany']} ekranow | {w['model']}")
                for p in w["problemy"]:
                    _druk(f"   [{p.get('waga')}] {p.get('ekran')} {p.get('sekcja')}: {p.get('opis')}")
                for p in w["odrzucone_przy_sprawdzeniu"]:
                    _druk(f"   (odrzucone przy sprawdzeniu) {p.get('ekran')}: {p.get('opis')} -> {p.get('weryfikacja') or p.get('powod')}")
            else:
                prof = json.loads((DANE / nick / "profile.json").read_text(encoding="utf-8"))
                brief = json.loads((DANE / nick / "brief_premium.json").read_text(encoding="utf-8"))
                _druk(json.dumps(weryfikator(nick, prof, brief, {"nazwa": kl.get("nazwa"), "miasto": kl.get("miasto")}),
                                 ensure_ascii=False, indent=1))
    _druk(f"ByteCatCode: {STAT['wywolania']} zapytan, {STAT['z_pamieci']} z pamieci, koszt {koszt_od_startu()} (waluta panelu)")


if __name__ == "__main__":
    main()
