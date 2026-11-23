import sys
from PIL import Image
f, y0, wys, kol = sys.argv[1], int(sys.argv[2]), int(sys.argv[3]), int(sys.argv[4])
im = Image.open(f); w, h = im.size
n = min(kol, max(1, (h - y0 + wys - 1) // wys))
sheet = Image.new("RGB", (w * n + 10 * (n - 1), wys), "white")
for i in range(n):
    sheet.paste(im.crop((0, y0 + i * wys, w, min(h, y0 + (i + 1) * wys))), (i * (w + 10), 0))
out = sys.argv[5]; sheet.save(out); print(out, sheet.size, "h", h)
