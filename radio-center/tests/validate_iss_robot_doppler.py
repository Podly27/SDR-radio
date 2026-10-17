import sys,time,wave,json,numpy as np
from pathlib import Path
sys.path.insert(0,'radio-center')
from iss_dsp import Demodulator
from iss_worker import Frames,Decoder
out=Path('/tmp/iss-robot36-validation/result');out.mkdir(parents=True,exist_ok=True);frames=Frames(out,437550000);decoder=Decoder(frames);fm=Demodulator(decoder.feed);phase0=0;started=time.monotonic();i=0
try:
 with wave.open('/tmp/iss-robot36-validation/robot36.wav') as wav:
  while pcm:=wav.readframes(2400):
   audio=np.frombuffer(pcm,dtype='<i2').astype(float)/32768;doppler=9000-450*i/10;fm.tune(doppler);instant=doppler+np.repeat(audio,10)*5000;phase=phase0+2*np.pi*np.cumsum(instant)/240000;phase0=float(phase[-1]%(2*np.pi));iq=np.exp(1j*phase)*90;data=np.column_stack([iq.real+127.5,iq.imag+127.5]).astype('uint8').tobytes();fm.feed(data);i+=1;time.sleep(max(0,started+i*.1-time.monotonic()))
 for j in range(25):
  phase=phase0+2*np.pi*np.arange(1,24001)*doppler/240000;phase0=float(phase[-1]%(2*np.pi));iq=np.exp(1j*phase)*90;fm.feed(np.column_stack([iq.real+127.5,iq.imag+127.5]).astype('uint8').tobytes());time.sleep(.1)
finally:fm.close();decoder.close()
print(json.dumps(frames.state()));assert frames.count>=1
import sqlite3
with sqlite3.connect(out/'iss.sqlite') as db:
 rows=db.execute('SELECT mode,width,height,complete,frequency FROM images').fetchall();print('Synthetic Robot36 + moving Doppler:',rows);assert any(r==('Robot 36',320,240,1,437550000) for r in rows)
