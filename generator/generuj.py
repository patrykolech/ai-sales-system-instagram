#!/usr/bin/env python3
"""Generator strony "Moment w lustrze" jedna komenda: profil Instagrama -> gotowa strona. Nic nie publikuje.

    python generuj.py salon_przyklad_4                # jedna klientka
    python generuj.py nick1 nick2 nick3                     # kilka po kolei
    python generuj.py nick --nazwa "Rzesy Przyklad" --miasto Kraków   # reczna poprawka, gdy dane sa zle
    python generuj.py nick --od-nowa                        # od nowa logo i dobor zdjec (platne)

Kroki dla kazdego nicka (dane z beauty-site-factory/data/<nick>/):
  1. nazwa i miasto z danych (brand_name / full_name / nick, miasto potwierdzone w bio, nazwie, nicku lub adresie)
     + AGENT WERYFIKATOR (web-analityk): nazwa z polskimi znakami, miasto, ja/my; kod przyjmuje tylko to, co potwierdzaja dane
  2. logo: odtworzone z awatara / okladek albo wygenerowane (generator_logo.py, routemux)
  3. hero: warstwy puderniczki, kolor wieczka z feedu, lusterko, kola (hero_dane.py; wizja routemux, ponizej 1,6 USD ByteCatCode)
  4. paleta: AGENT ART DIRECTOR (web-strateg) wybiera jedna z 11 rodzin beauty z arkusza okladek i postow
  5. wpis w klientki.json + AGENT COPYWRITER (web-copywriter): O mnie, kontakt, stopka, FAQ -> hero/<nick>/teksty.json
  6. budowa hero (prototyp/) i calej strony (prototyp_strona/<nick>-logo/)
  7. AGENT QA (web-qa): zrzuty telefonu, ocena, problemy sprawdzone drugi raz -> gotowa / do poprawki (testy/qa_agent/<nick>/)
Agenci dzialaja przez ByteCatCode (agenci.py, Claude Sonnet 5 / Haiku 4.5, zapas GPT-6 Astra). Kroki 1-5 sa pomijane,
gdy wyniki juz sa (drugie uruchomienie prawie nic nie kosztuje). --bez-agentow = stary tryb bez ByteCatCode.
Na koniec raport: nazwa, miasto, H1, typ, logo, ocena QA, koszt routemux i ByteCatCode, sciezka strony.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

KATALOG = Path(__file__).resolve().parent
sys.path.insert(0, str(KATALOG))

import agenci as A  # noqa: E402
import dobierz_zdjecie as D  # noqa: E402
import zbuduj_hero as Z  # noqa: E402
from zbuduj_hero import DANE, MIEJSCOWNIK, REJESTR, bez_ogonkow, miejscownik  # noqa: E402

TYP_LOGO = {"rzesy": "lashes", "brwi": "brows", "pmu": "pmu", "makijaz": "makeup", "paznokcie": "nails", "wlosy": "hair", "ogolny": ""}
BEZ_GRAFIK = {"wlosy": "brak wkladu puderniczki dla fryzjerow (lusterko z raczka, decyzja D4)"}
OGOLNE = {"lashes", "lash", "nails", "nail", "brows", "brow", "studio", "beauty", "salon", "makeup", "make", "up", "rzesy", "rzes",
          "brwi", "urody", "uroda", "stylizacja", "stylistka", "paznokcie", "pmu", "permanentny", "makijaz", "by", "and", "&", "i"}
OGONKI = {"rzesy": "Rzęsy", "rzes": "Rzęs", "piekno": "Piękno", "pieknosci": "Piękności", "zakatek": "Zakątek", "swiat": "Świat",
          "salonik": "Salonik", "urode": "Urodę", "spojrzenie": "Spojrzenie", "dloni": "Dłoni", "reka": "Ręka", "rece": "Ręce",
          "zaneta": "Żaneta", "lucja": "Łucja", "malgorzata": "Małgorzata", "elzbieta": "Elżbieta", "bozena": "Bożena",
          "grazyna": "Grażyna", "jozefina": "Józefina", "wiktoria": "Wiktoria", "zuzia": "Zuzia", "zaklina": "Żaklina"}


def tytulowo(slowo: str) -> str:
    """WERONIKA -> Weronika; Brwi Przyklad i '&' bez zmian."""
    if slowo.isupper() and len(slowo) > 1:
        return slowo[0] + slowo[1:].lower()
    return slowo


def zrodlo_tekstu(prof: dict, nick: str, adres: str = "") -> str:
    return bez_ogonkow(" ".join([prof.get("biography") or "", prof.get("full_name") or "", nick.replace("_", " ").replace(".", " "), adres]))


def nazwa_z_danych(nick: str, prof: dict, brief: dict) -> str:
    """brand_name z briefu, ale tylko slowa potwierdzone w nicku, nazwie konta albo bio (model potrafi dopisac imie)."""
    zrodlo = zrodlo_tekstu(prof, nick)
    kandydat = (brief["content"].get("brand_name") or "").strip()
    slowa = [s for s in re.split(r"\s+", kandydat) if s]
    potwierdzone = [s for s in slowa if re.search(r"\b" + re.escape(bez_ogonkow(s.strip("|•-"))[:5]), zrodlo)]
    if potwierdzone and len(potwierdzone) == len(slowa) or any(bez_ogonkow(s) not in OGOLNE for s in potwierdzone):
        slowa = potwierdzone
    else:                                              # z nicka: salon_przyklad_26 -> Rzesy Przyklad
        slowa = [s.capitalize() for s in re.split(r"[._\-\s]+", nick) if s and not s.isdigit()]
    slowa = [OGONKI.get(bez_ogonkow(s), tytulowo(s)) for s in slowa]
    return " ".join(slowa)[:40].strip()


def miasto_z_danych(nick: str, prof: dict, brief: dict) -> str:
    """Miasto, ktore widac w bio, nazwie konta, nicku albo adresie z wysoka pewnoscia. Inaczej puste."""
    f = brief["facts"]
    adres_pewny = f["address_city"]["value"] if f["address_city"]["confidence"] >= 0.9 else ""
    zrodlo = zrodlo_tekstu(prof, nick)
    kandydaci = []
    if adres_pewny:
        kandydaci.append(adres_pewny)
    m = re.split(r"\s+[--]\s*(?:w\s+)?", brief["content"].get("hero_kicker") or "", maxsplit=1)
    if len(m) == 2:
        kandydaci.append(m[1])
    for k in kandydaci:                                # adres i kicker: wystarczy, ze sa gdziekolwiek (tez sklejone w nicku)
        k = " ".join(tytulowo(s) for s in k.strip().split())
        odm = {v: n for n, v in MIEJSCOWNIK.items()}.get(k, k)     # 'Poznaniu' -> 'Poznań'
        if odm and bez_ogonkow(odm)[:6] in zrodlo:
            return odm
    for k in MIEJSCOWNIK:                              # znane miasta w bio: od poczatku slowa ('Piła' to nie 'pilates')
        if re.search(r"\b" + re.escape(bez_ogonkow(k)[:6]), zrodlo):
            return k
    return ""


# limity krokow: 11.11 o 01:56 logo bluare_dariabluszcz zawislo na zapytaniu do RouteMux i przez 30 min blokowalo kolejke
LIMIT_LOGO_S = 300
LIMIT_BUDOWY_S = 900


def _uruchom(cmd: list, limit: int) -> subprocess.CompletedProcess:
    """Podproces z limitem czasu; po przekroczeniu jest zabijany i wraca jak nieudany (zamiast wisiec)."""
    try:
        return subprocess.run(cmd, cwd=KATALOG, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=limit)
    except subprocess.TimeoutExpired as e:
        return subprocess.CompletedProcess(cmd, 1, (e.stdout or "") if isinstance(e.stdout, str) else "",
                                           f"przekroczono {limit} s, przerwane")


def logo_klientki(nick: str, nazwa: str, typ: str, od_nowa: bool) -> tuple[str, str]:
    gotowe = sorted((KATALOG / "logo").glob(f"{nick}-*/logo-czarne.png"), key=lambda p: p.stat().st_mtime)
    if gotowe and not od_nowa:
        p = gotowe[-1]
        return str(p.relative_to(KATALOG)).replace("\\", "/"), "gotowe (" + p.parent.name.split("-")[-1] + ")"
    cmd = [sys.executable, str(KATALOG / "generator_logo.py"), "--profil", nick, "--nazwa", nazwa, "--typ", TYP_LOGO.get(typ, "")]
    wynik = _uruchom(cmd, LIMIT_LOGO_S)
    print("   " + " | ".join(l for l in (wynik.stdout + wynik.stderr).strip().splitlines()[-3:]))
    gotowe = sorted((KATALOG / "logo").glob(f"{nick}-*/logo-czarne.png"), key=lambda p: p.stat().st_mtime)
    if not gotowe:
        # odtworzenie z jej materialow nie przeszlo kontroli napisu: nowe logo z potwierdzonej nazwy (bez wzoru)
        print("   logo: odtworzenie odrzucone, generuje nowe z nazwy (--wymus)")
        wynik = _uruchom(cmd + ["--wymus", "--proby", "1"], LIMIT_LOGO_S)
        print("   " + " | ".join(l for l in (wynik.stdout + wynik.stderr).strip().splitlines()[-3:]))
        gotowe = sorted((KATALOG / "logo").glob(f"{nick}-*/logo-czarne.png"), key=lambda p: p.stat().st_mtime)
    if not gotowe:
        raise RuntimeError("logo sie nie udalo (generator_logo.py, tez bez wzoru)")
    p = gotowe[-1]
    return str(p.relative_to(KATALOG)).replace("\\", "/"), p.parent.name.split("-")[-1]


def hero_gotowe(nick: str) -> bool:
    h = KATALOG / "hero" / nick
    return all((h / x).exists() for x in ("warstwy/paleta.json", "warstwy/wieczko-logo.webp", "lusterko/lusterko.json", "tlo/kola.json"))


def zapisz_rejestr(nick: str, wpis: dict) -> None:
    rej = json.loads(REJESTR.read_text(encoding="utf-8")) if REJESTR.exists() else {}
    rej[nick] = wpis
    REJESTR.write_text(json.dumps(rej, ensure_ascii=False, indent=1), encoding="utf-8")
    Z.KLIENTKI[nick] = wpis                         # ten sam slownik czyta zbuduj_strone (copywriter w tym procesie)


def paczka_serwer(nick: str) -> Path:
    """Samodzielny folder do_serwera/<nick>/ (index.html, img/, assets/) dla wysylki FTP automatu (ig/serwer.py wysyla
    caly katalog strony pod examplewebsite.pl/<nick>/). Bez odwolan ../, wiec stara strona nie zalezy od nowszych assets.
    img/hero.webp = zdjecie z lusterka: z niego serwer.przygotuj_og_jpg robi obrazek podgladu linku (og-preview.jpg)."""
    zrodlo = KATALOG / "prototyp_strona"
    cel = KATALOG / "do_serwera" / nick
    if cel.exists():
        shutil.rmtree(cel)
    shutil.copytree(zrodlo / nick / "img", cel / "img")
    shutil.copytree(zrodlo / "assets", cel / "assets")
    t = (zrodlo / f"{nick}-logo" / "index.html").read_text(encoding="utf-8")
    t = t.replace(f"../{nick}/img/", "img/").replace("../assets/", "assets/")
    if "../" in t:
        raise RuntimeError("paczka: w index.html zostalo odwolanie ../")
    if 'class="todo"' in t:
        raise RuntimeError("paczka: na stronie zostal znacznik [DO ...] (budowa bez LUSTRO_PRODUKCJA=1?)")
    (cel / "index.html").write_text(t, encoding="utf-8")
    zdj = cel / "img" / "lusterko" / "zdjecie.webp"
    if zdj.exists():
        shutil.copyfile(zdj, cel / "img" / "hero.webp")
    return cel / "index.html"


def nazwa_zgodna_z_logo(nick: str, prof: dict, brief: dict, nazwa: str, miasto: str, mnoga, logo: str, agent: bool) -> str:
    """Logo odtworzone z jej materialow z innym napisem niz nazwa (np. nick salon_c, na awatarze 'Mon Ami studio'):
    weryfikator dostaje napis z logo i wybiera nazwe marki. Bez wspolnego slowa strona mowilaby co innego niz wieczko."""
    try:
        info = json.loads((KATALOG / logo).parent.joinpath("logo.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return nazwa
    napis = str(info.get("name") or "")
    if not agent or not str(info.get("status", "")).startswith(("odtworzone", "wyciete")) or not napis:
        return nazwa
    slowa = {s for s in re.findall(r"\w{3,}", bez_ogonkow(nazwa)) if s not in OGOLNE}
    if not slowa or any(s in bez_ogonkow(napis) for s in slowa):
        return nazwa
    try:
        w = A.weryfikator(nick, prof, brief, {"nazwa": nazwa, "miasto": miasto, "mnoga": mnoga}, logo=napis)
    except Exception as e:
        print(f"   nazwa a logo: {type(e).__name__}: {str(e)[:120]}")
        return nazwa
    if w["przyjete"]["nazwa"] and w["nazwa"] and w["nazwa"] != nazwa:
        print(f"   nazwa z logo: {nazwa!r} -> {w['nazwa']!r} (napis na logo: {napis!r})")
        return w["nazwa"]
    return nazwa


def zrzuty_oferty(nick: str, index: Path) -> dict:
    """Pierwszy ekran strony (zamknieta puderniczka z logo i kola z jej zdjeciami) do wiadomosci z oferta.
    Automat robi zrzuty z ograniczonym ruchem, a wtedy strona pokazuje stan statyczny (otwarte lusterko), wiec lustro
    daje wlasne: te same rozmiary co automatDM2/ig/podglady_dm (1440x900, 415x895), PNG poza katalogiem strony (FTP ich
    nie wysle). tools/automat.podglady bierze je dla stron lustra."""
    from playwright.sync_api import sync_playwright
    cel = KATALOG / "do_serwera" / "_podglady" / nick
    cel.mkdir(parents=True, exist_ok=True)
    wynik = {}
    with sync_playwright() as pw:
        b = pw.chromium.launch()
        try:
            for klucz, w, h in (("komputer", 1440, 900), ("telefon", 415, 895)):
                ctx = b.new_context(viewport={"width": w, "height": h}, locale="pl-PL",
                                    is_mobile=klucz == "telefon", has_touch=klucz == "telefon")
                try:
                    pg = ctx.new_page()
                    pg.goto(index.resolve().as_uri(), wait_until="load", timeout=60000)
                    pg.wait_for_function("document.fonts.status === 'loaded'", timeout=15000)
                    pg.wait_for_timeout(1500)
                    plik = cel / f"{klucz}.png"
                    plik.write_bytes(pg.screenshot(full_page=False))
                    wynik[klucz] = [str(plik)]
                finally:
                    ctx.close()
        finally:
            b.close()
    return wynik


def braki_strony(nick: str) -> list[str]:
    """Twarde braki, ktorych QA na zrzutach nie zauwazy (nie wie, co powinno byc): galeria prac i kola w hero."""
    braki = []
    try:
        raport = {w["folder"]: w for w in json.loads((KATALOG / "prototyp_strona" / "raport.json").read_text(encoding="utf-8"))}
        w = raport.get(nick + "-logo") or {}
        if not w.get("prace"):
            braki.append(f"brak galerii prac (dobrych zdjec: {w.get('zdjec_dostepnych', 0)}, potrzeba min. 3)")
        przebieg = json.loads((KATALOG / "dobor" / nick / "przebieg.json").read_text(encoding="utf-8"))
        if len(przebieg.get("kola") or []) < 3:
            l = przebieg.get("lejek") or {}
            braki.append(f"tylko {len(przebieg.get('kola') or [])} kol ze zdjeciami w hero (postow {l.get('postow')}, "
                         f"po arkuszach {l.get('po_arkuszach')}, po kontroli {l.get('po_calych_postach')})")
    except (OSError, json.JSONDecodeError, KeyError):
        pass
    return braki


def teksty_copywritera(nick: str, prof: dict, brief: dict, mnoga: bool | None) -> dict:
    """Agent copywriter -> hero/<nick>/teksty.json (czyta go zbuduj_strone.teksty_agentow)."""
    import zbuduj_strone as S
    c = brief["content"]
    fakty = S.fakty_o_mnie(nick)
    mn = mnoga if isinstance(mnoga, bool) else S.liczba_mnoga(prof)
    t = A.copywriter(nick, fakty, mn, S.faq_z_danych(nick, c), S.tekst(c.get("contact_text") or ""),
                     S.tekst(c.get("footer_intro") or ""))
    plik = KATALOG / "hero" / nick / "teksty.json"
    plik.write_text(json.dumps(t, ensure_ascii=False, indent=1), encoding="utf-8")
    return t


def generuj(nick: str, a) -> dict:
    start = time.time()
    folder = DANE / nick
    if not (folder / "profile.json").exists() or not (folder / "brief_premium.json").exists():
        raise RuntimeError(f"brak danych w {folder} (profile.json i brief_premium.json)")
    prof = json.loads((folder / "profile.json").read_text(encoding="utf-8"))
    brief = json.loads((folder / "brief_premium.json").read_text(encoding="utf-8"))
    typ, _ = D.typ_uslugi({"username": nick, **prof})
    if typ in BEZ_GRAFIK:
        raise RuntimeError(f"typ '{typ}': {BEZ_GRAFIK[typ]}")
    agenci = not a.bez_agentow and A.dostepne()
    if agenci:
        A.start_licznika()
        zuzycie_przed = A.zuzycie()
    stary = Z.KLIENTKI.get(nick) if not a.od_nowa else None      # znana klientka: nazwa zostaje (jest na logo)
    nazwa = a.nazwa or (stary or {}).get("nazwa") or nazwa_z_danych(nick, prof, brief)
    miasto = a.miasto if a.miasto is not None else ((stary or {}).get("miasto") if stary else miasto_z_danych(nick, prof, brief))
    mnoga = (stary or {}).get("mnoga")
    uwagi = []
    if agenci and not stary:
        try:
            w = A.weryfikator(nick, prof, brief, {"nazwa": nazwa, "miasto": miasto, "mnoga": mnoga})
            if not a.nazwa:
                nazwa = w["nazwa"] or nazwa
            if a.miasto is None:
                miasto = w["miasto"] or miasto                # pusty u agenta = niepewny; miasto potwierdzone kodem zostaje
            mnoga = w["mnoga"]
            uwagi = w["uwagi"] + ([f"agent widzi typ '{w['typ']}', kod '{typ}'"] if w["typ"] not in (typ, "ogolny") else [])
            odrzucone = [k for k, v in w["przyjete"].items() if not v]
            print(f"   weryfikator ({w['model']}): {nazwa!r}, miasto {miasto or '(brak)'}, {'my' if mnoga else 'ja'}"
                  + (f" | odrzucone pola: {', '.join(odrzucone)} (agent: {', '.join(repr(w['agent'][k]) for k in odrzucone)})" if odrzucone else ""))
        except Exception as e:
            print(f"   weryfikator: {type(e).__name__}: {str(e)[:160]} -> zostaja dane z kodu")
    print(f"-> {nick}: {nazwa!r}, miasto {miasto or '(brak)'}, typ {typ}")
    for u in uwagi:
        print(f"   uwaga: {u}")

    def saldo_rm():
        try:
            return D.saldo()
        except Exception:
            return None
    saldo_przed = saldo_rm()
    logo, skad_logo = logo_klientki(nick, nazwa, typ, a.od_nowa)
    print(f"   logo: {logo} [{skad_logo}]")
    nazwa = nazwa_zgodna_z_logo(nick, prof, brief, nazwa, miasto, mnoga, logo, agenci and not a.nazwa)
    if a.od_nowa or not hero_gotowe(nick):
        import hero_dane
        hero_dane.klientka(nick, nazwa, logo)
    print("   hero: warstwy, lusterko i kola gotowe")
    plik_palety = KATALOG / "hero" / nick / "paleta_strony.json"
    if a.paleta or a.od_nowa or not plik_palety.exists():
        import paleta_beauty
        p = paleta_beauty.zapisz(nick, a.paleta)
        print(f"   paleta: {p['nazwa_rodziny']} ({(p.get('model') or {}).get('why', 'liczona z feedu')})")
    else:
        print(f"   paleta: {json.loads(plik_palety.read_text(encoding='utf-8'))['nazwa_rodziny']} (zapisana)")
    time.sleep(2)
    saldo_po = saldo_rm()
    koszt = round(saldo_przed - saldo_po, 4) if saldo_przed is not None and saldo_po is not None else 0.0

    wpis = {"nazwa": nazwa, "miasto": miasto, "wariant_logo": True, "logo": logo, "typ": typ}
    if isinstance(mnoga, bool):
        wpis["mnoga"] = mnoga
    if uwagi:
        wpis["uwagi"] = uwagi
    zapisz_rejestr(nick, wpis)
    plik_tekstow = KATALOG / "hero" / nick / "teksty.json"
    if agenci and (a.od_nowa or a.teksty_od_nowa or not plik_tekstow.exists()):
        try:
            t = teksty_copywritera(nick, prof, brief, mnoga)
            print(f"   copywriter ({t['model']}): O mnie, kontakt {'ok' if t['kontakt'] else '-'}, stopka {'ok' if t['stopka'] else '-'}, "
                  f"FAQ {len(t['faq']) if t['faq'] is not None else '-'}" + (f" | odrzucone: {t['odrzucone']}" if t["odrzucone"] else ""))
        except Exception as e:
            print(f"   copywriter: {type(e).__name__}: {str(e)[:160]} -> teksty z danych")
    for skrypt in ("zbuduj_hero.py", "zbuduj_strone.py"):
        w = subprocess.run([sys.executable, str(KATALOG / skrypt), nick], cwd=KATALOG, capture_output=True, text=True, timeout=LIMIT_BUDOWY_S,
                           encoding="utf-8", errors="replace", env={**os.environ, "PYTHONIOENCODING": "utf-8"})
        if w.returncode:
            raise RuntimeError(f"{skrypt}: " + (w.stderr or w.stdout).strip().splitlines()[-1])
        print("   " + skrypt + ": " + next((l for l in w.stdout.splitlines() if l.startswith(nick + "-logo")), "ok")[:160])
    wagi = json.loads((KATALOG / "prototyp" / "wagi.json").read_text(encoding="utf-8"))
    h1 = next((w["h1"] for w in wagi if w["folder"] == nick + "-logo"), "")
    strona = KATALOG / "prototyp_strona" / f"{nick}-logo" / "index.html"
    braki = braki_strony(nick)
    for b in braki:
        print(f"   uwaga: {b}")
    q = None
    if agenci and not a.bez_qa:
        try:
            q = A.qa(nick, nazwa, typ, miasto)
            print(f"   QA ({q['model']}): ocena {q['ocena']}/10, {'GOTOWA' if q['gotowa'] else 'DO POPRAWKI'}, "
                  f"{len(q['problemy'])} problemow ({len(q['odrzucone_przy_sprawdzeniu'])} falszywych odrzuconych)")
            for p_ in q["problemy"]:
                if p_.get("waga") in ("krytyczny", "sredni"):
                    print(f"      [{p_['waga']}] {p_.get('ekran')} {p_.get('sekcja')}: {p_.get('opis')}")
            q["gotowa"] = q["gotowa"] and not braki                 # QA nie wie, czego na stronie brakuje: to mowi kod
            q["braki"] = braki
            wpis["qa"] = {"ocena": q["ocena"], "gotowa": q["gotowa"], "problemy": len(q["problemy"]), "braki": braki, "czas": q["czas"]}
            zapisz_rejestr(nick, wpis)
        except Exception as e:
            print(f"   QA: {type(e).__name__}: {str(e)[:160]}")
    koszt_bc = round(A.zuzycie() - zuzycie_przed, 4) if agenci else 0.0
    podglady = {}
    if a.serwer:
        strona = paczka_serwer(nick)
        print(f"   paczka dla serwera: {strona.parent}")
        try:
            podglady = zrzuty_oferty(nick, strona)
        except Exception as e:                       # bez zrzutow automat zrobi swoje (stan statyczny)
            print(f"   zrzuty do oferty: {type(e).__name__}: {str(e)[:120]}")
    return {"nick": nick, "nazwa": nazwa, "miasto": miasto, "h1": h1, "typ": typ, "logo": skad_logo, "braki": braki,
            "gotowa": (q["gotowa"] if q else not braki), "podglady": podglady, "koszt_usd": koszt, "koszt_bytecat": koszt_bc, "qa": q,
            "sek": round(time.time() - start), "strona": str(strona)}


def main() -> None:
    for strumien in (sys.stdout, sys.stderr):                 # konsola Windows (cp1250) nie zna czesci znakow z modeli
        try:
            strumien.reconfigure(encoding="utf-8", errors="replace")
        except AttributeError:
            pass
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("nicki", nargs="+")
    p.add_argument("--nazwa", help="nadpisz nazwe (tylko przy jednym nicku)")
    p.add_argument("--miasto", help="nadpisz miasto; pusty napis = bez miasta w H1")
    p.add_argument("--od-nowa", action="store_true", help="logo i dobor zdjec od nowa (platne)")
    p.add_argument("--paleta", help="reczna rodzina palety (klucz z paleta_beauty.RODZINY), np. nude-atrament")
    p.add_argument("--bez-agentow", action="store_true", help="bez agentow ByteCatCode (stary tryb: tylko RouteMux)")
    p.add_argument("--bez-qa", action="store_true", help="bez przegladu QA po budowie")
    p.add_argument("--teksty-od-nowa", action="store_true", help="copywriter pisze teksty od nowa")
    p.add_argument("--serwer", action="store_true", help="dla automatu: strona bez znacznikow [DO ...], paczka do_serwera/<nick>/ "
                                                       "i ostatnia linia 'LUSTRO_WYNIK {json}'; kod wyjscia 1 przy bledzie")
    a = p.parse_args()
    if a.serwer:
        os.environ["LUSTRO_PRODUKCJA"] = "1"                 # zbuduj_strone (podproces) usuwa znaczniki robocze
        # QA na serwerze o niczym juz nie decyduje (strona lustra idzie zawsze), a zajmowal ok. 40 % czasu budowy
        if os.environ.get("LUSTRO_QA") != "1":
            a.bez_qa = True
    if a.bez_agentow:
        os.environ["LUSTRO_AGENCI"] = "0"                    # paleta_beauty: art director tez wylaczony
    if (a.nazwa or a.miasto is not None) and len(a.nicki) > 1:
        p.error("--nazwa i --miasto tylko przy jednym nicku")
    wyniki = []
    for nick in a.nicki:
        try:
            wyniki.append(generuj(nick, a))
        except Exception as e:
            print(f"   BLAD {nick}: {type(e).__name__}: {e}")
            wyniki.append({"nick": nick, "blad": str(e)})
    print("\nRAPORT")
    for w in wyniki:
        if "blad" in w:
            print(f"  {w['nick']}: BLAD {w['blad']}")
        else:
            q = w.get("qa")
            ocena = f"QA {q['ocena']}/10 {'GOTOWA' if q['gotowa'] else 'DO POPRAWKI'}" if q else "QA -"
            print(f"  {w['nick']}: {w['nazwa']} | {w['h1']} | typ {w['typ']} | logo {w['logo']} | {ocena} | "
                  f"RouteMux {w['koszt_usd']} USD + ByteCatCode {w['koszt_bytecat']} | {w['sek']} s\n     {w['strona']}")

    if a.serwer:                                             # automat czyta ostatnia linie (tools/automat.zbuduj_lustro)
        w = wyniki[-1]
        wynik = {"ok": "blad" not in w, "nick": w["nick"], "blad": w.get("blad")}
        if wynik["ok"]:
            q = w.get("qa") or {}
            # 2026-11-11 wlasciciel: "ma robic w nowym" - automat bierze strone lustra zawsze, gdy sie zbudowala;
            # ocena QA i braki ida tylko jako informacja (qa_gotowa), fabryka zostaje na wypadek bledu budowy
            wynik.update(index=w["strona"], gotowa=True, qa_gotowa=w["gotowa"], braki=w["braki"], nazwa=w["nazwa"], h1=w["h1"],
                         podglady=w.get("podglady") or {},
                         ocena=q.get("ocena"), problemy=[f"[{p_.get('waga')}] {p_.get('opis')}" for p_ in q.get("problemy", [])
                                                          if p_.get("waga") in ("krytyczny", "sredni")][:5],
                         koszt_routemux=w["koszt_usd"], koszt_bytecat=w["koszt_bytecat"], sek=w["sek"])
        print("LUSTRO_WYNIK " + json.dumps(wynik, ensure_ascii=False))
        sys.exit(0 if wynik["ok"] else 1)


if __name__ == "__main__":
    main()
