#!/usr/bin/env python3
"""Tekst sekcji "O mnie / O nas" pisany przez tani model tekstowy z faktow profilu. Bez zmyslania. Model: google/gemini-3.8-flash (zapas: 3.5-flash-lite).

Fakty: nazwa, nick, bio (bez emoji), nazwa konta, potwierdzone miasto, uslugi z cennika, fakty z brief_premium.json
z confidence >= 0,9 (adres, rezerwacja) oraz szkolenia (training_found). Model: google/gemini-3.5-flash-lite przez routemux
(to samo API i klucz co dobierz_zdjecie.zapytaj; klucza nie wypisujemy). Odpowiedz w dobor/<nick>/o_mnie.json (pamiec:
drugie uruchomienie nic nie kosztuje). Kontrola po stronie kodu: 2 akapity, liczby tylko z faktow, bez lat doswiadczenia,
nagrod, certyfikatow, wykrzyknikow i emoji. Bez sieci, po bledzie albo po odrzuceniu: None (zostaje wersja z bio).

    python o_mnie.py salon_przyklad_26 salon_przyklad_14     # pokaz (i w razie potrzeby wygeneruj) teksty
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

KATALOG = Path(__file__).resolve().parent
sys.path.insert(0, str(KATALOG))
import dobierz_zdjecie as D  # noqa: E402

# zbuduj_strone.kandydaci_prac wylacza siec w dobierz_zdjecie (D.klucz rzuca wyjatek), wiec bierzemy oryginal przy imporcie
_klucz = D.klucz


def _saldo() -> float:
    req = urllib.request.Request(D.SALDO, headers={"Authorization": "Bearer " + _klucz(), "User-Agent": "o-mnie/1.0"})
    with urllib.request.urlopen(req, timeout=60) as odp:
        return float(json.load(odp)["balance"])

MODEL = "google/gemini-3.8-flash"          # porownanie 2026-11-10: lepsza polszczyzna (odmiana miast) niz 3.5-flash-lite, ok. 0,0002 USD
ZAPAS = "google/gemini-3.5-flash-lite"     # gdy 3.8 odmowi (HTTP 4xx/5xx)
BUDZET_USD = 0.05              # lacznie na wszystkie wywolania w jednym uruchomieniu generatora
SALDO_MIN = 1.6                # ponizej: zadnych nowych zapytan
KOSZT = {"usd": 0.0, "wywolania": 0, "z_pamieci": 0, "odrzucone": 0, "saldo_start": None, "stop": ""}
_saldo_ok: bool | None = None

ZAKAZANE = re.compile(r"\blat\b|\blata\b|rok\w* doświadcz|doświadczen|nagr[oó]d|certyfik|dyplom|najlepsz|gwarant|"
                      r"tysi[aą]c|setk|\bklientek\b.*\d|\d+\s*%|!|\?|#|@(?!\w)", re.I)
EMOJI = re.compile("[\U0001F000-\U0001FAFF←-⇿⌀-⏿①-➿⤀-⥿⬀-⯿︀-️‍]")


def _saldo_pozwala() -> bool:
    global _saldo_ok
    if _saldo_ok is None:
        try:
            s = _saldo()
            KOSZT["saldo_start"] = s
            _saldo_ok = s >= SALDO_MIN
            if not _saldo_ok:
                KOSZT["stop"] = f"saldo {s:.3f} USD < {SALDO_MIN}"
        except Exception as e:  # bez sieci
            KOSZT["stop"] = f"brak sieci ({type(e).__name__})"
            _saldo_ok = False
    return _saldo_ok


def _zapytaj_tekst(prompt: str, max_tokens: int = 700, model: str | None = None) -> str:
    model = model or MODEL
    tresc = {"model": model, "max_tokens": max_tokens, "temperature": 0.4,
             "messages": [{"role": "user", "content": prompt}]}
    if model.startswith("google/gemini-3.8"):
        tresc["reasoning_effort"] = "minimal"                  # routemux odrzuca "none" (HTTP 400)
    req = urllib.request.Request(D.API, data=json.dumps(tresc).encode(), headers={
        "Authorization": "Bearer " + _klucz(), "Content-Type": "application/json", "User-Agent": "o-mnie/1.0"})
    for proba in range(3):
        try:
            with urllib.request.urlopen(req, timeout=90) as odp:
                d = json.load(odp)
            break
        except urllib.error.HTTPError as e:
            if e.code not in (429, 500, 502, 503) or proba == 2:
                if model != ZAPAS:
                    return _zapytaj_tekst(prompt, max_tokens, ZAPAS)
                raise RuntimeError(f"{model} HTTP {e.code}") from e
            time.sleep(3 * (proba + 1))
    u = d.get("usage") or {}
    # routemux nie zawsze zwraca koszt: wtedy szacunek z tokenow (z zapasem: 0,15 / 0,60 USD za mln), saldo sprawdzamy na koniec
    KOSZT["usd"] += float(u.get("cost") or 0) or (int(u.get("prompt_tokens") or 0) * 0.15 + int(u.get("completion_tokens") or 0) * 0.6) / 1e6
    KOSZT["wywolania"] += 1
    t = d["choices"][0]["message"].get("content") or ""
    if isinstance(t, list):
        t = "".join(c.get("text", "") for c in t)
    return t


def fakty_tekst(f: dict) -> str:
    return "\n".join(f"- {k}: {v}" for k, v in f.items() if v)


def prompt(fakty: dict, mnoga: bool) -> str:
    osoba = ("pierwszej osobie liczby mnogiej (salon: „robimy”, „zapraszamy”)" if mnoga
             else "pierwszej osobie liczby pojedynczej (stylistka mówi o sobie: „robię”, „pracuję”)")
    return f"""Napisz krótki tekst do sekcji „O mnie” na stronie wizytówce stylistki beauty. Jedyne źródło wiedzy to fakty poniżej.

FAKTY:
{fakty_tekst(fakty)}

ZASADY:
- Dokładnie 2 akapity, każdy 1-2 krótkie zdania (do 20 słów w zdaniu), razem 30-55 słów. Pisz w {osoba}, po polsku,
  naturalnie, jak sama właścicielka w rozmowie z klientką.
- Normalna polska pisownia: każde zdanie zaczynaj wielką literą, nazwy własne (miasto, nazwa studia, Instagram, Booksy)
  wielką literą, skróty jak UV wielkimi literami.
- Nie pisz „Jestem {fakty.get('nazwa', '')}” (to nazwa marki). Nazwy możesz użyć jako nazwy studia albo ją pominąć.
- Używaj wyłącznie informacji z faktów. Nie dodawaj lat doświadczenia, liczby klientek, nagród, certyfikatów, kursów,
  cen, czasu trwania, liczb ani obietnic efektu. Bez przymiotników reklamowych (profesjonalny, idealny, perfekcyjny,
  najwyższej jakości, wyjątkowy). Lepiej krócej niż zmyślać.
- Pierwszy akapit: czym się zajmuję i gdzie (usługi, miasto). Drugi akapit: jak pracuję, wyłącznie na podstawie faktów
  (np. technika albo metoda z bio), i krótkie zaproszenie do wiadomości na Instagramie. Nie powtarzaj tych samych
  usług w obu akapitach i nie łącz faktów, które w danych nie są ze sobą powiązane.
- Bez emoji, wykrzykników, pytań, hashtagów i cudzysłowów. Nie zaczynaj od „Cześć” ani „Hej”.

Odpowiedz wyłącznie JSON: {{"akapity": ["pierwszy akapit", "drugi akapit"]}}"""


def popraw_pisownie(akap: list[str], fakty: dict) -> list[str]:
    """Gdy model zgubi wielkie litery: poczatek zdania, nazwa, miasto, Instagram, Booksy, UV."""
    out = []
    wlasne = [fakty.get("nazwa", ""), fakty.get("miasto", ""), fakty.get("miasto z adresu", ""), "Instagram", "Booksy", "UV"]
    for a in akap:
        for w in (x for x in wlasne if x):
            a = re.sub(r"(?<![\w@.])" + re.escape(w) + r"(?!\w)", w, a, flags=re.I)
        a = re.sub(r"(^|[.!?…]\s+)([a-ząćęłńóśźż])", lambda m: m.group(1) + m.group(2).upper(), a)
        nick = (fakty.get("Instagram") or "").lstrip("@")
        if nick:                                                  # nick bez @ -> @nick
            a = re.sub(r"(?<![@\w.])" + re.escape(nick) + r"(?![\w])", "@" + nick, a)
        out.append(a)
    return out


def sprawdz(akapity, fakty: dict) -> str | None:
    """Powod odrzucenia albo None. Liczby musza byc w faktach; zakazane slowa (lata, nagrody...) tylko gdy sa w faktach."""
    # 2 akapity (o_mnie.py) albo 3 dluzsze (copywriter w agenci.py, od 2026-11-11: "o mnie niech bedzie dluzsza")
    if not isinstance(akapity, list) or len(akapity) not in (2, 3) or not all(isinstance(a, str) and a.strip() for a in akapity):
        return "nie 2-3 akapity"
    zrodlo = fakty_tekst(fakty).lower()
    calosc = " ".join(akapity)
    slowa = len(calosc.split())
    if not 20 <= slowa <= 135:
        return f"{slowa} slow"
    if EMOJI.search(calosc):
        return "emoji"
    for liczba in re.findall(r"\d+", calosc):
        if liczba not in zrodlo:
            return f"liczba {liczba} spoza faktow"
    for m in ZAKAZANE.finditer(calosc):
        if m.group(0).lower() not in zrodlo:
            return f"zakazane: {m.group(0)}"
    # krzyk WIELKIMI literami odpada, ale nazwa marki pisana wersalikami ("NICCA Beauty Place") jest w faktach i zostaje
    if any(w.lower() not in zrodlo for w in re.findall(r"\b[A-ZĄĆĘŁŃÓŚŹŻ]{4,}\b", calosc)):
        return "wielkie litery"
    return None


def tekst_o_mnie(nick: str, fakty: dict, mnoga: bool) -> list[str] | None:
    """Dwa akapity albo None. Pamiec w dobor/<nick>/o_mnie.json (klucz: odcisk promptu)."""
    plik = KATALOG / "dobor" / nick / "o_mnie.json"
    p = prompt(fakty, mnoga)
    odcisk = hashlib.sha1((MODEL + "|" + p).encode()).hexdigest()
    pamiec = json.loads(plik.read_text(encoding="utf-8")) if plik.exists() else {}
    if odcisk in pamiec:
        KOSZT["z_pamieci"] += 1
        w = pamiec[odcisk]
        return popraw_pisownie(w["akapity"], fakty) if not w.get("odrzucone") and w.get("akapity") else None
    if KOSZT["usd"] >= BUDZET_USD:
        KOSZT["stop"] = KOSZT["stop"] or "budzet"
        return None
    if not _saldo_pozwala():
        return None
    wynik = None
    for proba in range(2):
        try:
            t = _zapytaj_tekst(p if proba == 0 else p + "\n\nPoprzednia odpowiedź łamała zasady (" + powod + "). Popraw.")
            dane = json.loads(re.search(r"\{.*\}", t, re.S).group(0))
            akap = popraw_pisownie([re.sub(r"\s+", " ", a).strip() for a in dane.get("akapity", [])], fakty)
        except Exception as e:  # siec, JSON
            powod = f"blad: {type(e).__name__}"
            akap = None
        else:
            powod = sprawdz(akap, fakty)
        if akap and not powod:
            wynik = akap
            break
        KOSZT["odrzucone"] += 1
        if KOSZT["usd"] >= BUDZET_USD:
            break
    plik.parent.mkdir(parents=True, exist_ok=True)
    pamiec[odcisk] = {"model": MODEL, "fakty": fakty, "akapity": wynik, "odrzucone": wynik is None,
                      "powod": None if wynik else powod}
    plik.write_text(json.dumps(pamiec, ensure_ascii=False, indent=1), encoding="utf-8")
    return wynik


if __name__ == "__main__":
    import zbuduj_strone as S
    for nick in sys.argv[1:]:
        print(nick, S.fakty_o_mnie(nick))
    print(KOSZT)
