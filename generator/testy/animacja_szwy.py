from playwright.sync_api import sync_playwright
from animacja_lib import *
from PIL import Image, ImageChops, ImageStat
import io
with sync_playwright() as p:
    b, ctx = nowy_kontekst(p, 390, 844, dpr=2)
    s, w = otworz(ctx, "salon_przyklad_15")
    fr = {}
    for pr in (15, 16.5, 17.5, 18.5, 19.5, 21, 27, 29.6, 30.4, 32, 47, 49, 51, 53, 57, 60):
        przewin_do(s, pr/100, 220)
        fr[pr] = Image.open(io.BytesIO(s.screenshot())).convert('RGB')
    def diff(a,b,box=(0,0,780,1688)):
        d = ImageChops.difference(fr[a].crop(box), fr[b].crop(box))
        return round(sum(ImageStat.Stat(d).mean)/3,2)
    print('seam 29.6 vs 30.4 (srodek):', diff(29.6,30.4), ' 27 vs 29.6:', diff(27,29.6), ' 30.4 vs 32:', diff(30.4,32))
    # kontrolki
    box=(0,300,780,1100)
    W=Image.new('RGB',(780*4//2, 800//2*4),(60,60,60))
    keys=[15,16.5,17.5,18.5,19.5,21,27,29.6,30.4,32,47,49,51,53,57,60]
    cell=(390,400)
    S=Image.new('RGB',(cell[0]*4,cell[1]*4))
    for i,k in enumerate(keys):
        im=fr[k].crop(box).resize(cell,Image.LANCZOS)
        S.paste(im,((i%4)*cell[0],(i//4)*cell[1]))
    S.save('animacja/_dbg_szwy.png')
    b.close()
