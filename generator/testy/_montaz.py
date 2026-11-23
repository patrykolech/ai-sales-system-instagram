import sys
from PIL import Image
d='testy/budowa/'
def montaz(nazwy,wyj,skala=1.0,odstep=16,tlo=(90,90,90)):
    ims=[Image.open(d+n).convert('RGB') for n in nazwy]
    if skala!=1: ims=[i.resize((int(i.width*skala),int(i.height*skala)),Image.LANCZOS) for i in ims]
    W=sum(i.width for i in ims)+odstep*(len(ims)-1); H=max(i.height for i in ims)
    s=Image.new('RGB',(W,H),tlo); x=0
    for i in ims: s.paste(i,(x,0)); x+=i.width+odstep
    s.save(d+wyj)
if __name__=='__main__':
    ekran=sys.argv[1]; stan=sys.argv[2]; wyj=sys.argv[3]
    war=["salon_przyklad_15","salon_przyklad_15-logo","salon_przyklad_12","salon_przyklad_12-logo","salon_przyklad_14","salon_przyklad_26"]
    montaz([f"{w}__{ekran}__{stan}.png" for w in war],wyj, float(sys.argv[4]) if len(sys.argv)>4 else 1.0)
