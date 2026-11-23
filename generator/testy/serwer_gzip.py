#!/usr/bin/env python3
"""Lokalny serwer podgladu z kompresja tekstu, jak na prawdziwym hostingu (Cloudflare Pages, Netlify).

    python testy/serwer_gzip.py 8794                 # gzip (domyslnie)
    python testy/serwer_gzip.py 8795 --kodowanie br  # brotli (to daje Cloudflare/Netlify)
    python testy/serwer_gzip.py 8796 --kodowanie brak  # bez kompresji, do porownania

Serwuje folder prototyp/. Kompresuje tylko typy tekstowe (html, css, js, json, svg, txt).
WebP i WOFF2 sa juz skompresowane, wiec ida bez zmian, tak jak na hostingu.
Naglowki: Cache-Control: no-store (test zawsze z zimnego cache), Content-Length, Vary: Accept-Encoding.
Skompresowane odpowiedzi sa liczone raz i trzymane w pamieci (czas serwera nie zaniza ani nie zawyza LCP).
"""
from __future__ import annotations

import argparse
import gzip
import mimetypes
import sys
from functools import lru_cache
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

KAT = Path(__file__).resolve().parent.parent / "prototyp"
TEKST = {".html", ".css", ".js", ".json", ".svg", ".txt", ".xml", ".mjs"}
mimetypes.add_type("font/woff2", ".woff2")
mimetypes.add_type("image/webp", ".webp")
mimetypes.add_type("text/javascript", ".js")

try:
    import brotli
except ImportError:  # brotli opcjonalne
    brotli = None


@lru_cache(maxsize=512)
def skompresowane(sciezka: str, mtime: float, kodowanie: str) -> bytes:
    dane = Path(sciezka).read_bytes()
    if kodowanie == "gzip":
        return gzip.compress(dane, compresslevel=9, mtime=0)
    return brotli.compress(dane, quality=11)


class Uchwyt(BaseHTTPRequestHandler):
    kodowanie = "gzip"
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *a):  # cicho
        if "-v" in sys.argv:
            super().log_message(fmt, *a)

    def _plik(self) -> Path | None:
        sciezka = unquote(urlparse(self.path).path)
        if sciezka.endswith("/"):
            sciezka += "index.html"
        cel = (KAT / sciezka.lstrip("/")).resolve()
        if KAT not in cel.parents and cel != KAT:
            return None
        return cel if cel.is_file() else None

    def _odpowiedz(self, glowa: bool) -> None:
        cel = self._plik()
        if cel is None:
            self.send_response(404)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        typ = mimetypes.guess_type(cel.name)[0] or "application/octet-stream"
        if typ.startswith("text/") or typ in ("application/json", "image/svg+xml", "text/javascript"):
            typ += "; charset=utf-8"
        akceptuje = self.headers.get("Accept-Encoding", "")
        kod = self.kodowanie
        if kod == "br" and (brotli is None or "br" not in akceptuje):
            kod = "gzip" if "gzip" in akceptuje else "brak"
        if kod == "gzip" and "gzip" not in akceptuje:
            kod = "brak"
        if cel.suffix.lower() in TEKST and kod != "brak":
            cialo = skompresowane(str(cel), cel.stat().st_mtime, kod)
            enc = "gzip" if kod == "gzip" else "br"
        else:
            cialo = cel.read_bytes()
            enc = None
        self.send_response(200)
        self.send_header("Content-Type", typ)
        if enc:
            self.send_header("Content-Encoding", enc)
        self.send_header("Vary", "Accept-Encoding")
        self.send_header("Content-Length", str(len(cialo)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        if not glowa:
            self.wfile.write(cialo)

    def do_GET(self):
        self._odpowiedz(False)

    def do_HEAD(self):
        self._odpowiedz(True)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("port", type=int)
    ap.add_argument("--kodowanie", choices=["gzip", "br", "brak"], default="gzip")
    ap.add_argument("-v", action="store_true")
    a = ap.parse_args()
    Uchwyt.kodowanie = a.kodowanie
    serwer = ThreadingHTTPServer(("127.0.0.1", a.port), Uchwyt)
    print(f"serwer {a.kodowanie} na http://127.0.0.1:{a.port}/ (folder {KAT})", flush=True)
    serwer.serve_forever()


if __name__ == "__main__":
    main()
