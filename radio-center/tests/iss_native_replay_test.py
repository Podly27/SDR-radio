"""Optional slow integration test: synthetic PD120, never live ISS or RF.

Run with a test-only venv containing PySSTV and system-site-packages (native
pycsdr, NumPy, Pillow). Real-time replay takes about 135 seconds.
"""
import argparse,json,sqlite3,sys,wave
from pathlib import Path
import numpy as np
from PIL import Image
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from iss_worker import replay

def generate(path):
 from pysstv.color import PD120
 image=Image.new('RGB',(640,496));colors=[(255,255,255),(255,255,0),(0,255,255),(0,255,0),(255,0,255),(255,0,0),(0,0,255),(0,0,0)]
 for i,color in enumerate(colors):image.paste(color,(i*80,0,(i+1)*80,496))
 encoder=PD120(image,24000,16);encoder.vox_enabled=False
 with wave.open(str(path),'wb') as out:
  out.setparams((1,2,24000,0,'NONE','not compressed'));out.writeframes(np.zeros(24000,dtype='<i2').tobytes());phase=0;fraction=0;pending=bytearray()
  for frequency,msec in encoder.gen_freq_bits():
   exact=msec*24+fraction;n=int(exact);fraction=exact-n;step=2*np.pi*frequency/24000
   pending.extend((np.sin(phase+np.arange(n)*step)*20000).astype('<i2').tobytes());phase=(phase+n*step)%(2*np.pi)
   if len(pending)>100000:out.writeframesraw(pending);pending.clear()
  out.writeframesraw(pending);out.writeframes(np.zeros(48000,dtype='<i2').tobytes())
 return np.asarray(image).astype(float)

def main():
 parser=argparse.ArgumentParser();parser.add_argument('--data',required=True);args=parser.parse_args();data=Path(args.data)
 if data.exists():raise SystemExit('Choose a new isolated output directory; production data must never be used')
 data.mkdir(parents=True);wav=data/'synthetic-pd120.wav';reference=generate(wav);replay(wav,data)
 db=sqlite3.connect(data/'iss.sqlite')
 try:row=db.execute('SELECT filename,mode,width,height,lines,complete FROM images').fetchone()
 finally:db.close()
 assert row[1:]==('PD 120',640,496,496,1),row
 with Image.open(data/'iss-images'/row[0]) as image:decoded=np.asarray(image).astype(float)
 errors=[float(np.abs(decoded[100:400,x-10:x+10]-reference[100:400,x-10:x+10]).mean()) for x in range(40,640,80)]
 assert max(errors)<30,errors
 print(json.dumps({'synthetic':True,'mode':row[1],'width':row[2],'height':row[3],'lines':row[4],'complete':bool(row[5]),'rgb_bar_errors':errors},indent=2))
if __name__=='__main__':main()
