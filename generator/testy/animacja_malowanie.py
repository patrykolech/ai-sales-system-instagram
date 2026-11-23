import json, collections
from playwright.sync_api import sync_playwright
from animacja_lib import *
with sync_playwright() as p:
    b, ctx = nowy_kontekst(p, 390, 844, dpr=3)
    s, w = otworz(ctx, "salon_przyklad_15")
    s.evaluate("dispatchEvent(new Event('wheel'))")
    s.add_style_tag(content=".przewin svg{animation:none!important}")
    s.wait_for_timeout(500)
    b.start_tracing(page=s, categories=["devtools.timeline", "disabled-by-default-devtools.timeline"])
    for pr in range(0, 101, 1):
        s.evaluate("(p) => { console.timeStamp('p=' + p); const t = ScrollTrigger.getAll()[0]; scrollTo(0, t.start + p/100 * (t.end - t.start)); return new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r))); }", pr)
    s.evaluate("console.timeStamp('p=END')")
    tr = json.loads(b.stop_tracing())
    ev = tr["traceEvents"]
    marks = sorted([(e["ts"], e["args"]["data"]["message"]) for e in ev if e.get("name") == "TimeStamp"], key=lambda x: x[0])
    def bucket(ts):
        lab = None
        for t, m in marks:
            if t <= ts: lab = m
            else: break
        return lab
    cnt = collections.defaultdict(lambda: collections.Counter())
    for e in ev:
        if e.get("name") in ("Paint", "Layout", "RasterTask") and e.get("ph") == "X":
            cnt[bucket(e["ts"])][e["name"]] += 1
    for t, m in marks:
        c = cnt.get(m)
        if c: print(m, dict(c))
    b.close()
