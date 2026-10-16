from PIL import Image,ImageDraw
import glob
R='android/app/src/main/res/'
def mk(sz,mode):
    S=1024;im=Image.new('RGBA',(S,S),(0,0,0,0));d=ImageDraw.Draw(im);g=(30,215,96,255)
    if mode=='sq':d.rounded_rectangle([0,0,S,S],radius=int(S*.22),fill=g)
    if mode=='rd':d.ellipse([0,0,S,S],fill=g)
    for a,b,c,e in((.30,.27,.40,.73),(.60,.27,.70,.73),(.40,.45,.60,.55)):d.rectangle([a*S,b*S,c*S,e*S],fill=(0,0,0,255))
    return im.resize((sz,sz),Image.LANCZOS)
for dpi,l,f in(('mdpi',48,108),('hdpi',72,162),('xhdpi',96,216),('xxhdpi',144,324),('xxxhdpi',192,432)):
    mk(l,'sq').save(f'{R}mipmap-{dpi}/ic_launcher.png');mk(l,'rd').save(f'{R}mipmap-{dpi}/ic_launcher_round.png');mk(f,'fg').save(f'{R}mipmap-{dpi}/ic_launcher_foreground.png')
open(R+'values/ic_launcher_background.xml','w').write('<?xml version="1.0" encoding="utf-8"?>\n<resources>\n    <color name="ic_launcher_background">#1ED760</color>\n</resources>\n')
for p in glob.glob(R+'**/splash.png',recursive=True):
    w,h=Image.open(p).size;im=Image.new('RGB',(w,h),(0,0,0));s=int(min(w,h)*.28);ic=mk(s,'rd');im.paste(ic,((w-s)//2,(h-s)//2),ic);im.save(p)
print('icons done')
