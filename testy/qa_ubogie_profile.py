#!/usr/bin/env python3
"""QA: ubogie profile bez modeli i bez generatora. Zmienia DOM gotowej strony w przegladarce (brak awatara, dlugi nick, malo kol,
puste lusterka, dlugi H1, dlugie slowo, dluga linia z nazwa) i mierzy nachodzenie / wyjscie poza okno. To symulacja: pelna macierz profili
z briefu (sekcja 15 pkt 8) wymaga generatora, ktorego nie ma.

    python testy/qa_ubogie_profile.py --port 8790 --zrzuty KAT --wyj docs/qa/ubogie_profile.json
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

from playwright.sync_api import sync_playwright

POMIAR = """
() => {
  const r2 = e => { const b = e.getBoundingClientRect(); return {x: b.left, y: b.top, r: b.right, b: b.bottom}; };
  const tekst = e => { const g = document.createRange(); g.selectNodeContents(e); const rs = [...g.getClientRects()].filter(r => r.width > 1);
    return {x: Math.min(...rs.map(r => r.left)), y: Math.min(...rs.map(r => r.top)), r: Math.max(...rs.map(r => r.right)), b: Math.max(...rs.map(r => r.bottom)), linii: new Set(rs.map(r => Math.round(r.top / 4))).size}; };
  const vis = e => { const c = getComputedStyle(e); return c.display !== 'none' && c.visibility !== 'hidden' && +c.opacity > 0.05; };
  const L = document.querySelector('.panel-przod img.warstwa').getBoundingClientRect();
  const kola = [...document.querySelectorAll('.kolo')].filter(vis).map(k => { const b = k.getBoundingClientRect(); return {m: k.dataset.miejsce, cx: b.x + b.width / 2, cy: b.y + b.height / 2, r: b.width / 2}; });
  const pr = document.querySelector('.pasek__profil'), cta = document.querySelector('.pasek__cta');
  return {vw: innerWidth, vh: innerHeight, sw: document.documentElement.scrollWidth, h1: tekst(document.querySelector('h1')), przewin: r2(document.querySelector('.przewin')),
          lid: {cx: L.x + L.width / 2, cy: L.y + L.height / 2, r: L.width / 2}, kola, profil: r2(pr), cta: r2(cta), profil_sw: pr.scrollWidth, profil_cw: pr.clientWidth,
          slowo: (() => { const s = document.querySelector('.slowo'); return s ? tekst(s) : null; })(), pasek_wys: r2(document.querySelector('.pasek')).b};
}
"""

MUT = {
    "baza": "() => {}",
    "bez_awatara_dlugi_nick": """() => { document.querySelector('.pasek__profil img').remove(); document.querySelector('.pasek__profil span').textContent = '@salon_kosmetyczny_dlugi_nick_krakow_2024'; }""",
    "3_kola_puste_lusterka": """() => { document.querySelectorAll('.kolo').forEach(k => { const m = +k.dataset.miejsce.slice(1); if (m >= 4) k.remove(); else if (m === 3) { k.classList.add('kolo--puste'); k.querySelector('img').remove(); } }); }""",
    "1_kolo": """() => { document.querySelectorAll('.kolo').forEach(k => { if (k.dataset.miejsce !== 'S1') k.remove(); }); }""",
    "H1_5_linii_tekstu": """() => { document.querySelector('h1').textContent = 'Makijaż permanentny brwi, ust i powiek oraz stylizacja rzęs w Szczebrzeszynie'; }""",
    "slowo_Paznokcie": """() => { for (const e of document.querySelectorAll('.slowo')) e.textContent = 'Paznokcie';
        const c = document.createElement('canvas').getContext('2d'); c.font = '400 100px "Bodoni Moda Kursywa"'; document.documentElement.style.setProperty('--slowo-em', (c.measureText('Paznokcie').width / 100).toFixed(4)); }""",
}


def odstep(e, c):
    nx = min(max(c["cx"], e["x"]), e["r"]); ny = min(max(c["cy"], e["y"]), e["b"])
    return math.hypot(c["cx"] - nx, c["cy"] - ny) - c["r"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8790)
    ap.add_argument("--wariant", default="salon_przyklad_15-logo")
    ap.add_argument("--zrzuty", default="")
    ap.add_argument("--wyj", default="")
    a = ap.parse_args()
    wyn = []
    with sync_playwright() as p:
        b = p.chromium.launch()
        for (w, h) in ((390, 844), (390, 720), (360, 640)):
            for nazwa, js in MUT.items():
                ctx = b.new_context(viewport={"width": w, "height": h}, device_scale_factor=1, is_mobile=True, has_touch=True)
                s = ctx.new_page()
                s.goto(f"http://127.0.0.1:{a.port}/{a.wariant}/index.html", wait_until="networkidle")
                s.evaluate("document.fonts.ready")
                s.evaluate("dispatchEvent(new Event('wheel'))")
                s.add_style_tag(content=".przewin svg{animation:none!important}")
                s.evaluate(js)
                s.wait_for_timeout(450)
                m = s.evaluate(POMIAR)
                h1 = {"x": m["h1"]["x"], "y": m["h1"]["y"], "r": m["h1"]["r"], "b": m["h1"]["b"]}
                ob = [m["lid"]] + m["kola"]
                wiersz = {"ekran": f"{w}x{h}", "mutacja": nazwa, "linii_h1": m["h1"]["linii"], "h1_b": round(h1["b"]), "przycisk_y": round(m["przewin"]["y"]),
                          "h1_nachodzi_na_przycisk": h1["b"] > m["przewin"]["y"] + 1, "odstep_h1_kola": round(min(odstep(h1, c) for c in ob), 1),
                          "poziomy_scroll": m["sw"] > m["vw"], "nick_obciety_lub_nachodzi_na_cta": (m["profil"]["r"] > m["cta"]["x"] - 4) or m["profil_sw"] > m["profil_cw"],
                          "slowo_szer_px": round(m["slowo"]["r"] - m["slowo"]["x"]) if m["slowo"] else None, "slowo_poza_oknem": bool(m["slowo"] and (m["slowo"]["x"] < -1 or m["slowo"]["r"] > m["vw"] + 1)),
                          "h1_poza_dolem": h1["b"] > m["vh"], "kol": len(m["kola"])}
                wyn.append(wiersz)
                if a.zrzuty and (w, h) in ((360, 640), (390, 844)):
                    Path(a.zrzuty).mkdir(parents=True, exist_ok=True)
                    s.screenshot(path=str(Path(a.zrzuty) / f"ubogi_{nazwa}_{w}x{h}.png"))
                ctx.close()
        b.close()
    for r in wyn:
        zle = [k for k in ("h1_nachodzi_na_przycisk", "poziomy_scroll", "nick_obciety_lub_nachodzi_na_cta", "slowo_poza_oknem", "h1_poza_dolem") if r[k]]
        print(r["ekran"], r["mutacja"].ljust(24), "H1", r["linii_h1"], "lin, odstep H1-kola", r["odstep_h1_kola"], "slowo", r["slowo_szer_px"], "kol", r["kol"], "| PROBLEMY:", zle or "brak")
    if a.wyj:
        Path(a.wyj).write_text(json.dumps(wyn, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
