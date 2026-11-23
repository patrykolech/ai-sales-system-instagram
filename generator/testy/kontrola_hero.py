#!/usr/bin/env python3
"""Kontrola statyczna wygenerowanych stron prototypu: id, linki, pliki, JSON-LD, zakazane znaki, semantyka."""
import json, re, sys
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlparse

KAT = Path(__file__).resolve().parent.parent / "prototyp"

class P(HTMLParser):
    def __init__(s):
        super().__init__(); s.ids=[]; s.tags={}; s.refs=[]; s.anchors=[]; s.imgs=[]; s.jsonld=[]; s._ld=False; s.text=[]; s.skip=0; s.lang=None
    def handle_starttag(s,t,a):
        a=dict(a); s.tags[t]=s.tags.get(t,0)+1
        if t in('script','style'): s.skip+=1
        if t=='script' and a.get('type')=='application/ld+json': s._ld=True
        if t=='html': s.lang=a.get('lang')
        if 'id' in a: s.ids.append(a['id'])
        for k in('src','href'):
            if k in a: s.refs.append((t,k,a[k]))
        if t=='a' and a.get('href','').startswith('#'): s.anchors.append(a['href'][1:])
        if t=='img': s.imgs.append(a)
    def handle_endtag(s,t):
        if t in('script','style'): s.skip-=1
        if t=='script': s._ld=False
    def handle_data(s,d):
        if s._ld: s.jsonld.append(d)
        elif not s.skip: s.text.append(d)

bledy=[]
for idx in sorted(KAT.glob('*/index.html')):
    if idx.parent.name=='assets': continue
    p=P(); p.feed(idx.read_text(encoding='utf-8')); n=idx.parent.name
    def zle(m): bledy.append(f"{n}: {m}")
    dup={i for i in p.ids if p.ids.count(i)>1}
    if dup: zle(f"duplikaty id {dup}")
    for a in p.anchors:
        if a not in p.ids: zle(f"kotwica #{a} bez celu")
    for t,k,v in p.refs:
        if v.startswith(('http','mailto','tel','data:','#')): continue
        path=idx.parent/unquote(urlparse(v).path)
        if not path.exists(): zle(f"brak pliku {v}")
    for im in p.imgs:
        if 'alt' not in im or 'width' not in im or 'height' not in im: zle(f"img bez alt/width/height {im.get('src')}")
    try: json.loads(''.join(p.jsonld))
    except Exception as e: zle(f"JSON-LD: {e}")
    txt=''.join(p.text)
    for ch in('·','→','*'):
        if ch in txt: zle(f"zakazany znak {ch!r} w tekscie")
    if re.search(r'[A-ZĄĆĘŁŃÓŚŹŻ]{4,}',txt.replace('[DO UZUPEŁNIENIA]','')): zle("ciag wielkich liter w tekscie")
    if p.tags.get('h1')!=1: zle(f"h1: {p.tags.get('h1')}")
    for t in('main','footer','nav','section'):
        if not p.tags.get(t): zle(f"brak <{t}>")
    if p.lang!='pl': zle("lang")
    print(f"{n:26s} id:{len(p.ids)} img:{len(p.imgs)} h1:{p.tags.get('h1')} sekcje:{p.tags.get('section')} ok" if not [b for b in bledy if b.startswith(n+':')] else f"{n}: PROBLEMY")
print("\n".join(bledy) if bledy else "brak bledow")
