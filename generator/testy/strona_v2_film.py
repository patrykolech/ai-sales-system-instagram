"""Filmy przewijania calej strony v2 (prototyp_strona, port 8793): telefon 390x844 i komputer 1440x900, prawdziwe kolko myszy
(na komputerze dziala Lenis z hero). Zapis: testy/strona_v2/<nazwa>.mp4 i arkusz klatek <nazwa>salon_przyklad_25 (klatka co 1 s),
plus bledy konsoli. Wzor: film2.py z sesji hero.

    python testy/strona_v2_film.py                 # 4 klientki x 2 ekrany
    python testy/strona_v2_film.py salon_przyklad_26-logo --m
"""
import os, sys, shutil, subprocess, tempfile, time, json
from pathlib import Path
from playwright.sync_api import sync_playwright
from PIL import Image

K = Path(__file__).resolve().parent.parent
WYJ = K / "testy" / "strona_v2"
WYJ.mkdir(parents=True, exist_ok=True)
arg = [a for a in sys.argv[1:] if not a.startswith("--")]
fl = [a for a in sys.argv[1:] if a.startswith("--")]
WARIANTY = arg or ["salon_przyklad_26-logo", "salon_przyklad_14-logo", "salon_przyklad_15-logo", "salon_przyklad_12-logo"]
EKRANY = [("telefon", 390, 844, 2), ("komputer", 1440, 900, 1)]
if "--m" in fl: EKRANY = EKRANY[:1]
if "--d" in fl: EKRANY = EKRANY[1:]


def arkusz(film: Path, cel: Path, kol: int, szer: int) -> int:
    tmp = Path(tempfile.mkdtemp(prefix="ark", dir=WYJ))
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(film), "-vf", "fps=1", str(tmp / "k%03d.png")], check=True)
    pl = sorted(tmp.glob("k*.png"))
    ims = [Image.open(f).convert("RGB") for f in pl]
    ims = [im.resize((szer, int(im.height * szer / im.width))) for im in ims]
    h = ims[0].height
    wier = (len(ims) + kol - 1) // kol
    ark = Image.new("RGB", (kol * szer + (kol - 1) * 6, wier * h + (wier - 1) * 6), (255, 255, 255))
    for k, im in enumerate(ims):
        ark.paste(im, ((k % kol) * (szer + 6), (k // kol) * (h + 6)))
    ark.save(cel, quality=80)
    shutil.rmtree(tmp, ignore_errors=True)
    return len(ims)


srv = subprocess.Popen([sys.executable, "-m", "http.server", "8793", "--bind", "127.0.0.1", "--directory", str(K / "prototyp_strona")],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(1.2)
wyniki = []
try:
    with sync_playwright() as p:
        b = p.chromium.launch()
        for w in WARIANTY:
            for ekran, sz, wy, dpr in EKRANY:
                tmp = tempfile.mkdtemp(prefix="film", dir=WYJ)
                # film ma rozmiar okna w pikselach CSS (Playwright nie skaluje nagrania o DPR; wieksze pole zostaje szare)
                ctx = b.new_context(viewport={"width": sz, "height": wy}, device_scale_factor=dpr, record_video_dir=tmp,
                                    record_video_size={"width": sz, "height": wy})
                s = ctx.new_page()
                bledy = []
                s.on("pageerror", lambda e: bledy.append("pageerror: " + str(e)))
                s.on("console", lambda m: bledy.append(m.type + ": " + m.text) if m.type in ("error", "warning") else None)
                s.goto(f"http://127.0.0.1:8793/{w}/index.html", wait_until="networkidle")
                s.wait_for_timeout(2200)
                s.mouse.move(sz // 2, wy // 2)
                koniec_hero = s.evaluate("document.querySelector('[data-scene=lustro]').offsetHeight - innerHeight")
                krok, y = (18 if sz < 800 else 24), 0
                while y < koniec_hero + 40:                     # hero szybko (ma wlasne filmy)
                    s.mouse.wheel(0, krok * 3); y += krok * 3; time.sleep(0.02)
                s.wait_for_timeout(700)
                H = s.evaluate("document.documentElement.scrollHeight - innerHeight")
                ost, stoi = -1, 0
                while stoi < 25:
                    s.mouse.wheel(0, krok); time.sleep(0.028)
                    yy = s.evaluate("scrollY")
                    stoi = stoi + 1 if abs(yy - ost) < 1 else 0
                    ost = yy
                s.wait_for_timeout(1200)
                sw = s.evaluate("[document.documentElement.scrollWidth, document.documentElement.clientWidth]")
                stan = s.evaluate("window.__SEKCJE__ ? window.__SEKCJE__.stan() : null")
                film = s.video.path()
                ctx.close()
                nazwa = f"{w}_{ekran}"
                cel = WYJ / (nazwa + ".mp4")
                subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(film), "-c:v", "libx264", "-pix_fmt", "yuv420p",
                                "-crf", "26", "-preset", "medium", "-movflags", "+faststart", "-an", str(cel)], check=True)
                shutil.rmtree(tmp, ignore_errors=True)
                n = arkusz(cel, WYJ / (nazwa + "salon_przyklad_25"), 10 if ekran == "telefon" else 5, 200 if ekran == "telefon" else 380)
                wynik = {"film": str(cel), "kb": cel.stat().st_size // 1024, "klatek_arkusza": n, "szerokosc": sw, "bledy": bledy,
                         "tryb": {k: stan[k] for k in ("ruch", "pin", "lite", "lenis")} if stan else None}
                wyniki.append(wynik)
                print(json.dumps(wynik, ensure_ascii=False))
        b.close()
finally:
    srv.terminate()
(WYJ / "filmy.json").write_text(json.dumps(wyniki, ensure_ascii=False, indent=1), encoding="utf-8")
