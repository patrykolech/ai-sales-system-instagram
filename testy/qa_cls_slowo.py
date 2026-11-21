#!/usr/bin/env python3
"""QA runda 2: CLS od slowa przy ladowaniu kroju (Slow 4G jak w Lighthouse devtools: RTT 150 ms, 1,6 Mb/s, CPU 4x). Opcjonalnie wstrzykniecie CSS (kopia strony, zrodla bez zmian).

    python testy/qa_cls_slowo.py --port 8796 --warianty salon_przyklad_15-logo,salon_przyklad_26-logo
"""
import argparse, json, statistics
from playwright.sync_api import sync_playwright
INIT = """window.__ls=[]; new PerformanceObserver(l=>{for(const e of l.getEntries()) window.__ls.push({v:e.value,t:Math.round(e.startTime),r:e.hadRecentInput,src:(e.sources||[]).map(s=>({n:(s.node&&(s.node.className||s.node.tagName))||'',p:[s.previousRect.x|0,s.previousRect.y|0,s.previousRect.width|0,s.previousRect.height|0],c:[s.currentRect.x|0,s.currentRect.y|0,s.currentRect.width|0,s.currentRect.height|0]}))})}).observe({type:'layout-shift',buffered:true});"""
KAND = {"obecny": "", "poprawka_wysokosc": "html.js .slowo{height:var(--slowo-fs)!important}"}
def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--port", type=int, default=8796); ap.add_argument("--warianty", default="salon_przyklad_15-logo,salon_przyklad_26-logo"); ap.add_argument("--powt", type=int, default=3); ap.add_argument("--wyj", default="")
    a = ap.parse_args(); out = {}
    with sync_playwright() as p:
        for w in a.warianty.split(","):
            out[w] = {}
            for n, css in KAND.items():
                wyn = []
                for i in range(a.powt):
                    b = p.chromium.launch(); ctx = b.new_context(viewport={"width": 412, "height": 823}, device_scale_factor=2.625, is_mobile=True, has_touch=True)
                    s = ctx.new_page(); s.add_init_script(INIT + ("document.addEventListener('DOMContentLoaded',()=>{const s=document.createElement('style');s.textContent=%r;document.head.appendChild(s)});" % css if css else ""))
                    cdp = ctx.new_cdp_session(s); cdp.send("Network.enable"); cdp.send("Network.setCacheDisabled", {"cacheDisabled": True})
                    cdp.send("Network.emulateNetworkConditions", {"offline": False, "latency": 150, "downloadThroughput": 1.6 * 1024 * 1024 / 8 * 0.9, "uploadThroughput": 750 * 1024 / 8 * 0.9})
                    cdp.send("Emulation.setCPUThrottlingRate", {"rate": 4})
                    s.goto(f"http://127.0.0.1:{a.port}/{w}/index.html", wait_until="load", timeout=120000); s.wait_for_timeout(3000)
                    ls = s.evaluate("window.__ls"); b.close()
                    wyn.append({"cls": round(sum(x["v"] for x in ls if not x["r"]), 4), "zdarzenia": ls})
                out[w][n] = {"cls_przebiegi": [x["cls"] for x in wyn], "zdarzenia_1": wyn[0]["zdarzenia"]}
                print(w, n, [x["cls"] for x in wyn], json.dumps(wyn[0]["zdarzenia"], ensure_ascii=False)[:420])
    if a.wyj: open(a.wyj, "w", encoding="utf-8").write(json.dumps(out, ensure_ascii=False, indent=1))
main()
