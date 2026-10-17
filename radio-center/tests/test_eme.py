"""EME tests use synthetic signals and temporary databases, never a live SDR."""
import datetime,json,math,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import numpy as np
from scipy.signal import upfirdn
import eme_common as common
from eme_worker import Resampler,IQSlots,parse_log,save,jt65_audio
import wave,struct

class EME(unittest.TestCase):
 def setUp(self):self.c=common.validate(json.loads((Path(__file__).resolve().parents[1]/'eme-initial-config.json').read_text()))
 def test_location_and_moon(self):
  self.assertEqual(common.location_grid(49.5622,18.1746),'JN99CN')
  lat,lon=common.grid_location('JN99CN');self.assertLess(abs(lat-49.5622),.03);self.assertLess(abs(lon-18.1746),.05)
  m=common.moon_position(self.c,datetime.datetime(2026,10,16,13,38,tzinfo=datetime.timezone.utc))
  self.assertAlmostEqual(m['azimuth'],159.8,delta=.3);self.assertAlmostEqual(m['elevation'],9.23,delta=.1)
  self.assertIsNotNone(m['next_start'])
 def test_hysteresis(self):
  check=common.should_receive
  self.assertFalse(check('auto',16,False,15,2));self.assertTrue(check('auto',17,False,15,2))
  self.assertTrue(check('auto',16,True,15,2));self.assertTrue(check('auto',15,True,15,2));self.assertFalse(check('auto',14.9,True,15,2))
  self.assertTrue(check('manual',-20,False,15,2));self.assertFalse(check('off',80,True,15,2))
 def test_config(self):
  for key,value in (('band',[]),('mode','unknown'),('q65',[None]),('latitude',float('nan')),('device','0; touch x'),('hysteresis',0)):
   with self.assertRaises(ValueError):common.validate(dict(self.c,**{key:value}))
  with self.assertRaises(ValueError):common.validate(dict(self.c,q65=[],jt65=[]))
 def test_streaming_resampler(self):
  r=Resampler();x=np.exp(2j*np.pi*10000*np.arange(48000)/240000).astype(np.complex64)*20
  chunks=r.feed(x[:24000])+r.feed(x[24000:]);z=np.frombuffer(chunks,dtype='<i2').reshape(-1,2);y=z[:,0]+1j*z[:,1]
  reference=upfirdn(r.h,np.concatenate((np.zeros(400,np.complex64),x)),up=2,down=5)[160:160+19200];reference=np.conj(reference);reference[1::2]*=-1
  self.assertLess(np.max(abs(y-reference*256)),2)
  # The backward MAP65 FFT places an RF +10 kHz tone at bin +58 kHz.
  spectrum=abs(np.fft.ifft(y[2000:18000]));peak=int(np.argmax(spectrum));self.assertAlmostEqual(peak/16000*96000,58000,delta=8)
 def test_iq_slot_alignment(self):
  slots=IQSlots();self.assertEqual(slots.feed(b'\0'*(4*96000),1),[])
  # Entire first minute is complete because feed began exactly at UTC 0.
  completed=slots.feed(b'\0'*(4*96000*59),60);self.assertEqual(completed[0][0],0);self.assertEqual(len(completed[0][1]),4*96000*60)
 def test_jt65_channel_slice(self):
  with tempfile.TemporaryDirectory() as td:
   p=Path(td)/'test.iq';w=Path(td)/'test.wav';center=432045000;dial=432065000
   n=np.arange(192000);original=np.exp(2j*np.pi*21500*n/96000)*2000
   y=np.conj(original);y[1::2]*=-1;iq=np.empty((len(y),2),dtype='<i2');iq[:,0]=y.real;iq[:,1]=y.imag
   p.write_bytes(struct.pack('<d',center/1e6)+iq.tobytes());jt65_audio(p,w,center,dial)
   with wave.open(str(w)) as f:
    self.assertEqual(f.getframerate(),12000);self.assertEqual(f.getnframes(),24000);audio=np.frombuffer(f.readframes(f.getnframes()),dtype='<i2')
   peak=np.argmax(abs(np.fft.rfft(audio[1200:-1200])));self.assertAlmostEqual(peak/(len(audio)-2400)*12000,1500,delta=1)
 def test_native_log_and_history(self):
  line=f'{432.045:8.3f}{125:5d}{2.5:5.1f}{0:4d}{-23:4d}{1200:05d}  '+f'{"CQ K1ABC FN42":28s}'+': B  q0'
  parsed=parse_log(line);self.assertEqual(parsed['frequency'],432045125);self.assertEqual(parsed['submode'],'60B')
  with tempfile.TemporaryDirectory() as td,patch.object(common,'DATA',Path(td)):
   db=common.connect();save(db,0,self.c,parsed);save(db,0,self.c,parsed);db.close()
   h=common.history('');self.assertEqual(h['total'],1);self.assertEqual(h['events'][0]['message'],'CQ K1ABC FN42')
if __name__=='__main__':unittest.main()
