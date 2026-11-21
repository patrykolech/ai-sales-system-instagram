#!/usr/bin/env python3
"""Powierzchnie sekcji i wzory tla dla stron "Moment w lustrze" (v3 sekcji). Bez modeli, 0 USD.

1. Powierzchnie: z palety klientki (hero/<nick>/paleta_strony.json, tokeny CSS) liczymy dla kazdej powierzchni
   (papier, papier2, mrok, akcent, przelamanie) komplet rol: tlo, tekst, tekst drugi (>= 4,6:1), linie, kolor wyroznienia
   (>= 3:1, tylko duze litery i ozdoby), przycisk z tekstem (>= 4,5:1, krawedz >= 3:1 wobec tla), wzor. Wszystko liczone
   tutaj i sprawdzane na kontrast WCAG, w CSS laduja gotowe wartosci.
2. Rytm: kolejne sekcje nigdy na tej samej ani bardzo podobnej powierzchni (np. czern przelamania obok mroku w rodzinie nude).
3. Wzor z monogramu: kafel z logo klientki (z logo/<...>/logo-czarne.png wycinamy znak, bez podpisu pod kolem) albo z inicjalow
   (wariant bez logo na wieczku), w kolorze tekstu danej powierzchni i malym kryciu. Kafel = zwykle tlo (bez maski), WebP z alfa.

    python wzor.py salon_przyklad_26        # podglad: kontrasty powierzchni i kafle do scratchpadu nie powstaja, tylko wydruk
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

KATALOG = Path(__file__).resolve().parent
sys.path.insert(0, str(KATALOG))
from kolor import kontrast, luminancja  # noqa: E402

FONT_MONOGRAMU = KATALOG / "baza" / "fonty" / "bodoni-moda-italic-pl.ttf"

# powierzchnia -> (token tla, token tekstu)
BAZY = {
    "papier": ("--papier", "--atrament"),
    "papier2": ("--papier2", "--atrament"),
    "mrok": ("--tlo", "--jasny"),
    "akcent": ("--akcent", "--na-akcencie"),
    "przelamanie": ("--przelamanie", "--na-przelamaniu"),
}
# wzor na powierzchni: monogram maly / duzy, prazki, kropki, samo ziarno ze swiatlem
WZORY = {"papier": "monogram", "papier2": "prazki", "mrok": "swiatlo", "akcent": "monogram-duzy", "przelamanie": "kropki"}


def _rgb(h: str) -> np.ndarray:
    h = h.lstrip("#")
    return np.array([int(h[i:i + 2], 16) for i in (0, 2, 4)], dtype=float)


def _hex(c: np.ndarray) -> str:
    return "#%02x%02x%02x" % tuple(int(round(max(0, min(255, v)))) for v in c)


def mieszaj(a: str, b: str, t: float) -> str:
    """t=0 -> a, t=1 -> b (mieszanie w sRGB, wystarcza do tekstu drugiego i linii)."""
    return _hex(_rgb(a) * (1 - t) + _rgb(b) * t)


def rgb_trojka(h: str) -> str:
    return " ".join(str(int(v)) for v in _rgb(h))


def jasna(h: str) -> bool:
    return luminancja(h) > 0.2


def podobne(a: str, b: str) -> bool:
    """Dwie powierzchnie zlewaja sie w jedna plame (np. #111 obok #1F1A16): rytm by tego nie pokazal."""
    if a.lower() == b.lower():
        return True
    d = float(np.abs(_rgb(a) - _rgb(b)).sum()) / 3
    return kontrast(a, b) < 1.12 and d < 26


def najazd(btn: str, btn_t: str) -> str:
    """Kolor przycisku pod kursorem: rozjasniony przy ciemnym tekscie, przyciemniony przy jasnym; tekst nadal >= 4,5:1."""
    cel = "#ffffff" if luminancja(btn_t) < 0.4 else "#000000"
    for k in (0.16, 0.12, 0.08, 0.04):
        c = mieszaj(btn, cel, k)
        if kontrast(btn_t, c) >= 4.5:
            return c
    return btn


def powierzchnie(t: dict) -> dict[str, dict]:
    """Role kolorow dla kazdej powierzchni, wszystkie pary sprawdzone na kontrast."""
    out = {}
    na = {"--papier": "--atrament", "--papier2": "--atrament", "--tlo": "--jasny", "--akcent": "--na-akcencie",
          "--przelamanie": "--na-przelamaniu", "--guzik": "--guzik-tekst"}
    for nazwa, (k_tla, k_tekstu) in BAZY.items():
        bg, fg = t[k_tla], t[k_tekstu]
        if kontrast(fg, bg) < 4.5:                         # zabezpieczenie: rodzina z kiepska para tekstu
            fg = max((t["--atrament"], t["--jasny"], "#111111", "#ffffff"), key=lambda c: kontrast(c, bg))
        # tekst drugi: jak najblizej tla, ale nadal >= 4,6:1
        fg2 = fg
        for k in range(46, -1, -2):
            kand = mieszaj(fg, bg, k / 100)
            if kontrast(kand, bg) >= 4.6:
                fg2 = kand
                break
        linia = mieszaj(fg, bg, 0.80 if jasna(bg) else 0.76)
        # wyroznienie (duze litery, numery w duzym kroju, iskry): akcent, przelamanie, potem tekst
        wyr = fg
        for k in ("--akcent", "--przelamanie", "--atrament", "--jasny"):
            c = t[k]
            if c.lower() != bg.lower() and kontrast(c, bg) >= 3.0:
                wyr = c
                break
        # przycisk: pierwszy kolor, ktory odcina sie od tla (krawedz >= 3:1) i ma czytelny tekst
        btn, btn_t = t["--tlo"], t["--jasny"]
        kolejnosc = ("--tlo", "--papier", "--akcent", "--przelamanie") if jasna(bg) else ("--guzik", "--papier", "--akcent", "--przelamanie", "--tlo")
        for k in kolejnosc:
            c, ct = t[k], t[na[k]]
            if c.lower() != bg.lower() and kontrast(c, bg) >= 3.0 and kontrast(ct, c) >= 4.5:
                btn, btn_t = c, ct
                break
        out[nazwa] = {
            "bg": bg, "fg": fg, "fg2": fg2, "linia": linia, "wyr": wyr, "btn": btn, "btn_t": btn_t,
            "btn_h": najazd(btn, btn_t), "wyr_t": wyr if kontrast(wyr, bg) >= 4.5 else fg2, "jasna": jasna(bg), "wzor": WZORY[nazwa],
            "kontrast": {"fg": round(kontrast(fg, bg), 2), "fg2": round(kontrast(fg2, bg), 2), "wyr": round(kontrast(wyr, bg), 2),
                         "btn_krawedz": round(kontrast(btn, bg), 2), "btn_tekst": round(kontrast(btn_t, btn), 2)},
        }
    return out


def ziarno_svg(jasne_tlo: bool) -> str:
    """Ziarno jako SVG w data URI (kilkaset bajtow, przegladarka rasteryzuje kafel raz). Na jasnym ciemne drobiny, na ciemnym jasne."""
    c = "0 0 0" if jasne_tlo else "1 1 1"
    a = "0.55" if jasne_tlo else "0.62"
    svg = ("<svg xmlns='http://www.w3.org/2000/svg' width='180' height='180'><filter id='z'>"
           "<feTurbulence type='fractalNoise' baseFrequency='.85' numOctaves='2' stitchTiles='stitch'/>"
           f"<feColorMatrix values='0 0 0 0 {c.split()[0]} 0 0 0 0 {c.split()[1]} 0 0 0 0 {c.split()[2]} {a} 0 0 0 -.25'/></filter>"
           "<rect width='180' height='180' filter='url(%23z)'/></svg>")
    return 'url("data:image/svg+xml,' + svg.replace('"', "'").replace("<", "%3C").replace(">", "%3E") + '")'


def css_powierzchni(pw: dict[str, dict], kafle: dict[str, str]) -> str:
    """Klasy .pw-<nazwa> z gotowymi kolorami i tlem z faktura (wstawiane do <style> w <head> strony: wzgledny url kafla
    liczy sie wtedy od strony, nie od arkusza). kafle: nazwa powierzchni -> url kafla monogramu."""
    reg = []
    for n, p in pw.items():
        dekl = {
            "--bg": p["bg"], "--bg-rgb": rgb_trojka(p["bg"]), "--fg": p["fg"], "--fg-rgb": rgb_trojka(p["fg"]),
            "--fg2": p["fg2"], "--linia": p["linia"], "--wyr": p["wyr"], "--wyr-rgb": rgb_trojka(p["wyr"]),
            "--btn": p["btn"], "--btn-t": p["btn_t"], "--btn-h": p["btn_h"], "--wyr-t": p["wyr_t"],
            "--cien-rgb": rgb_trojka(p["fg"]) if p["jasna"] else "0 0 0",
        }
        warstwy = [ziarno_svg(p["jasna"])]
        w = p["wzor"]
        if w.startswith("monogram") and n in kafle:
            warstwy.append(f'url("{kafle[n]}")')
        elif w == "prazki":
            warstwy.append("repeating-linear-gradient(-58deg,rgb(var(--fg-rgb)/.055) 0 1px,transparent 1px 11px)")
        elif w == "kropki":
            warstwy.append("radial-gradient(rgb(var(--fg-rgb)/.15) 1.1px,transparent 1.6px)")
        elif w == "swiatlo":
            warstwy.append("radial-gradient(90% 60% at 82% 0%,rgb(var(--fg-rgb)/.07),transparent 62%)")
        rozm = {"monogram": "180px 180px,176px 176px", "monogram-duzy": "180px 180px,420px 420px",
                "kropki": "180px 180px,18px 18px"}.get(w, "180px 180px,100% 100%")
        reg.append(f".pw-{n}{{" + ";".join(f"{k}:{v}" for k, v in dekl.items()) + ";background-color:var(--bg);color:var(--fg)}")
        reg.append(f".pw-{n}.faktura,.pw-{n} .faktura{{background-color:var(--bg);background-image:{','.join(warstwy)};"
                   f"background-size:{rozm}}}")
    return "".join(reg)


# ---------------------------------------------------------------- monogram
def znak_z_logo(sciezka: Path) -> Image.Image:
    """Maska alfa znaku z logo-czarne.png. Monogram w kole z podpisem pod spodem: zostaje sam znak (najwyzsze pasmo,
    gdy ma >= 55% wysokosci); stempel i logotyp: calosc."""
    im = Image.open(sciezka).convert("RGBA")
    a = np.asarray(im, dtype=np.float32)
    alfa = a[..., 3] / 255
    if alfa.min() > 0.98:                                   # bez przezroczystosci: tusz = ciemne piksele
        alfa = 1 - a[..., :3].mean(-1) / 255
    alfa = np.where(alfa > 0.08, alfa, 0)
    wiersze = alfa.max(1) > 0.2
    ys = np.where(wiersze)[0]
    if not len(ys):
        raise ValueError("puste logo")
    pasma, start = [], ys[0]
    przerwa = max(6, int(0.03 * alfa.shape[0]))
    for y0, y1 in zip(ys, ys[1:]):
        if y1 - y0 > przerwa:
            pasma.append((start, y0))
            start = y1
    pasma.append((start, ys[-1]))
    wys = ys[-1] - ys[0]
    pasmo = max(pasma, key=lambda p: p[1] - p[0])
    if len(pasma) > 1 and (pasmo[1] - pasmo[0]) >= 0.55 * wys and pasmo == pasma[0]:
        y0, y1 = pasmo
    else:
        y0, y1 = ys[0], ys[-1]
    wyc = alfa[y0:y1 + 1]
    xs = np.where(wyc.max(0) > 0.2)[0]
    wyc = wyc[:, xs[0]:xs[-1] + 1]
    return Image.fromarray((wyc * 255).astype(np.uint8), "L")


def znak_z_inicjalow(nazwa: str) -> Image.Image:
    slowa = [s for s in re.split(r"[\s._-]+", nazwa) if s and s[0].isalpha()]
    inicjaly = "".join(s[0].upper() for s in slowa[:2]) or nazwa[:1].upper()
    font = ImageFont.truetype(str(FONT_MONOGRAMU), 360)
    l, t_, r, b = font.getbbox(inicjaly)
    im = Image.new("L", (r - l + 40, b - t_ + 40), 0)
    ImageDraw.Draw(im).text((20 - l, 20 - t_), inicjaly, font=font, fill=255)
    return im.crop(im.getbbox())


def kafel(znak: Image.Image, kolor: str, krycie: float, bok_css: int, szer_znaku_css: int, cel: Path) -> int:
    """Kafel 2x (retina): znak w dwoch miejscach siatki z przesunieciem (polowa kafla po skosie), kolor z krycie w alfie."""
    s = 2
    bok = bok_css * s
    sz = szer_znaku_css * s
    zn = znak.copy()
    skala = min(sz / zn.width, (sz * 1.05) / zn.height)
    zn = zn.resize((max(1, int(zn.width * skala)), max(1, int(zn.height * skala))), Image.LANCZOS)
    maska = Image.new("L", (bok, bok), 0)
    for cx, cy in ((bok * 0.25, bok * 0.25), (bok * 0.75, bok * 0.75)):
        x, y = int(cx - zn.width / 2), int(cy - zn.height / 2)
        maska.paste(zn, (x, y), zn)
    alfa = (np.asarray(maska, dtype=np.float32) * krycie).astype(np.uint8)
    rgb = _rgb(kolor).astype(np.uint8)
    out = np.zeros((bok, bok, 4), np.uint8)
    out[..., :3] = rgb
    out[..., 3] = alfa
    cel.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(out, "RGBA").save(cel, "WEBP", lossless=True, quality=100, method=6)
    return cel.stat().st_size


def logo_klientki(nick: str, kl: dict) -> Path | None:
    if kl.get("logo"):
        p = KATALOG / kl["logo"]
        return p if p.exists() else None
    stare = {"salon_przyklad_15": "logo/salon_przyklad-monogram/logo-czarne.png",
             "salon_przyklad_12": "logo/studio_przyklad-stempel/logo-czarne.png"}   # jak w hero_dane.TESTOWE
    if nick in stare:
        return KATALOG / stare[nick]
    gotowe = sorted((KATALOG / "logo").glob(f"{nick}-*/logo-czarne.png"), key=lambda p: p.stat().st_mtime)
    return gotowe[-1] if gotowe else None


def kafle_klientki(nick: str, kl: dict, logo: bool, pw: dict[str, dict], dst_img: Path, prefiks: str) -> dict[str, str]:
    """Kafle monogramu dla powierzchni z wzorem monogramu. Zwraca nazwa powierzchni -> sciezka wzgledna do strony."""
    zrodlo = logo_klientki(nick, kl) if logo else None
    znak = znak_z_logo(zrodlo) if zrodlo else znak_z_inicjalow(kl["nazwa"])
    proporcja = znak.width / max(1, znak.height)
    rodzaj = "logo" if zrodlo else "inicjaly"
    wynik = {}
    for n, p in pw.items():
        if not p["wzor"].startswith("monogram"):
            continue
        duzy = p["wzor"] == "monogram-duzy"
        bok = 420 if duzy else 176
        szer = (190 if proporcja > 1.8 else 150) if duzy else (84 if proporcja > 1.8 else 58)
        krycie = (0.075 if p["jasna"] else 0.085) if duzy else (0.085 if p["jasna"] else 0.1)
        plik = dst_img / "wzor" / f"{rodzaj}-{n}.webp"
        kafel(znak, p["fg"], krycie, bok, szer, plik)
        wynik[n] = prefiks + f"wzor/{rodzaj}-{n}.webp"
    return wynik


# ---------------------------------------------------------------- rytm
KOLEJNOSC_POWIERZCHNI = {
    "pasek": ["akcent", "papier2", "papier"],
    "prace": ["papier", "papier2"],
    "z-bliska": ["mrok", "akcent"],
    "uslugi": ["papier2", "papier"],
    "o-mnie": ["akcent", "przelamanie", "papier"],
    "opinie": ["mrok", "przelamanie", "akcent"],
    "szkolenia": ["papier", "papier2"],
    "faq": ["przelamanie", "papier2", "akcent", "papier"],
    "instagram": ["papier2", "papier", "przelamanie"],
    "kontakt": ["mrok"],
    "stopka": ["akcent", "przelamanie", "papier"],
}


def rytm(sekcje: list[str], pw: dict[str, dict], hero: tuple[str, ...] = ("mrok", "przelamanie")) -> dict[str, str]:
    """Powierzchnia dla kazdej sekcji: pierwsza z listy preferencji, ktora nie zlewa sie z poprzednia ani z nastepna
    stala (kontakt = mrok). Hero (okladka) konczy sie mrokiem i pasem w kolorze przelamania, wiec pierwsza sekcja
    nie moze byc podobna do zadnego z nich. Przelamanie musi wystapic w sekcjach co najmniej raz (duza plama)."""
    przed = hero[-1]
    wyn, poprz = {}, przed
    for i, s in enumerate(sekcje):
        nast = sekcje[i + 1] if i + 1 < len(sekcje) else None
        stala_nast = KOLEJNOSC_POWIERZCHNI.get(nast, [None])[0] if nast in ("kontakt",) else None
        wybor = None
        for kand in KOLEJNOSC_POWIERZCHNI.get(s, ["papier", "papier2"]):
            if podobne(pw[kand]["bg"], pw[poprz]["bg"]):
                continue
            if i == 0 and any(kand == h or podobne(pw[kand]["bg"], pw[h]["bg"]) for h in hero):
                continue
            if stala_nast and kand != stala_nast and podobne(pw[kand]["bg"], pw[stala_nast]["bg"]):
                continue
            if stala_nast and kand == stala_nast:
                continue
            wybor = kand
            break
        if wybor is None:
            wybor = next(k for k in ("papier", "papier2", "akcent", "mrok", "przelamanie") if not podobne(pw[k]["bg"], pw[poprz]["bg"]))
        wyn[s] = wybor
        poprz = wybor
    if "przelamanie" not in wyn.values():                     # wymuszenie plamy przelamania tam, gdzie pasuje
        for s in ("faq", "o-mnie", "pasek", "instagram", "stopka"):
            if s not in wyn:
                continue
            i = sekcje.index(s)
            a = wyn[sekcje[i - 1]] if i else przed
            b = wyn.get(sekcje[i + 1]) if i + 1 < len(sekcje) else None
            if not podobne(pw["przelamanie"]["bg"], pw[a]["bg"]) and (b is None or not podobne(pw["przelamanie"]["bg"], pw[b]["bg"])):
                wyn[s] = "przelamanie"
                break
    return wyn


def przejscia(sekcje: list[str], wyn: dict[str, str], pw: dict[str, dict]) -> dict[str, str]:
    """Przejscie na gornej krawedzi sekcji (klucz = sekcja wchodzaca): kolo (lusterko otwiera kolejna sekcje),
    kartka (sekcja nachodzi na poprzednia jak kartka magazynu), plynnie (kolor tla przenika; tylko gdy tekst nowej
    sekcji jest czytelny na obu tlach). Pasek sam jest przejsciem."""
    PINY = {"prace", "z-bliska"}
    out, ostatnie = {}, None
    for i, s in enumerate(sekcje):
        if i == 0:
            continue
        a = sekcje[i - 1]
        if s == "pasek" or a == "pasek":
            continue
        A, B = pw[wyn[a]], pw[wyn[s]]
        if a in PINY or s == "kontakt":
            typ = "kolo"
        elif s == "stopka":                                   # stopka jest poza <main>: kontakt nie moze sie przykleic (sticky konczy sie z main)
            typ = "plynnie" if kontrast(B["fg"], A["bg"]) >= 4.5 and kontrast(A["fg"], B["bg"]) >= 4.5 else "kolo"
        elif kontrast(B["fg"], A["bg"]) >= 4.5 and kontrast(A["fg"], B["bg"]) >= 4.5:
            typ = "plynnie"
        else:
            typ = "kartka" if ostatnie != "kartka" else "kolo"
        out[s] = typ
        ostatnie = typ
    return out


if __name__ == "__main__":
    for nick in sys.argv[1:]:
        t = json.loads((KATALOG / "hero" / nick / "paleta_strony.json").read_text(encoding="utf-8"))["tokeny"]
        pw = powierzchnie(t)
        for n, p in pw.items():
            print(f"{nick:24s} {n:12s} bg {p['bg']} fg {p['fg']} fg2 {p['fg2']} wyr {p['wyr']} btn {p['btn']}/{p['btn_t']} {p['kontrast']}")
        sek = ["pasek", "prace", "z-bliska", "uslugi", "o-mnie", "opinie", "szkolenia", "faq", "instagram", "kontakt", "stopka"]
        r = rytm(sek, pw)
        print(" rytm:", r)
        print(" przejscia:", przejscia(sek, r, pw))
