import json,sys,tempfile,time,unittest
from pathlib import Path
from unittest.mock import patch
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import meteo_common as common
from meteo_diagnostics import selected_pass,spectrum,RATE
from meteo_processing import channelize,enqueue_cadu,safe_path,summarize

class Diagnostics(unittest.TestCase):
 def test_rf_power_alone_never_retunes_and_proven_images_respect_user_changes(self):
  import station_common
  with tempfile.TemporaryDirectory() as td,patch.object(common,'DATA',Path(td)),patch.object(station_common,'DATA',Path(td)):
   (Path(td)/'meteo-reports').mkdir();c=dict(common.DEFAULT);common.atomic('meteo-config.json',c)
   plan={'created':1,'expires':time.time()+60,'satellite':'M2-4','baseline':{'frequency':c['frequency'],'symbolrate':c['symbolrate']}};common.atomic('meteo-diagnostic-plan.json',plan)
   report={'kind':'iq','created':2,'gain':40.2,'rf':{'137100000':{'band_to_noise_db':30}},'results':[{'frequency':137100000,'symbolrate':80000,'returncode':0,'cadu_bytes':0,'images':0}]};common.atomic('meteo-reports/test.json',report)
   summarize();self.assertEqual(common.load_config()['frequency'],c['frequency'])
   # An intervening manual rate change takes precedence over the experiment.
   common.atomic('meteo-config.json',{**c,'symbolrate':80000});report['results'][0].update(cadu_bytes=102400,images=3);common.atomic('meteo-reports/test.json',report)
   summarize();self.assertEqual(common.load_config()['frequency'],c['frequency'])
   common.atomic('meteo-config.json',c);summarize();self.assertEqual(common.load_config()['frequency'],137100000)
 def test_experiment_expires_and_never_changes_manual_reception(self):
  with tempfile.TemporaryDirectory() as td,patch.object(common,'DATA',Path(td)):
   now=time.time();plan={'expires':now+100,'satellite':'M2-4','passes':[{'start':now-1,'end':now+50}]};job={'automatic':True,'config':{'satellite':'M2-4'}}
   common.atomic('meteo-diagnostic-plan.json',plan);common.atomic('meteo-run.json',job);self.assertIsNotNone(selected_pass())
   job['automatic']=False;common.atomic('meteo-run.json',job);self.assertIsNone(selected_pass())
   job['automatic']=True;plan['expires']=now-1;common.atomic('meteo-run.json',job);common.atomic('meteo-diagnostic-plan.json',plan);self.assertIsNone(selected_pass())
 def test_channelizer_sign_and_boundaries(self):
  with tempfile.TemporaryDirectory() as td:
   n=RATE+RATE//4;t=np.arange(n)/RATE;rng=np.random.default_rng(1)
   z=.15*np.exp(2j*np.pi*(400000+10000)*t)+.01*(rng.normal(size=n)+1j*rng.normal(size=n))
   raw=np.empty((n,2),dtype=np.uint8);raw[:,0]=np.clip(z.real*128+127.5,0,255);raw[:,1]=np.clip(z.imag*128+127.5,0,255)
   source=Path(td)/'signal.cu8';source.write_bytes(raw.tobytes());target=Path(td)/'channel.cs16';channelize(source,target,137900000)
   a=np.fromfile(target,dtype='<i2').reshape(-1,2);x=a[:,0]+1j*a[:,1];self.assertEqual(len(x),n//8)
   # A signal 10 kHz above the wanted carrier must stay +10 kHz after shifting.
   measured=np.angle(np.mean(x[200:-1]*np.conj(x[199:-2])))*256000/(2*np.pi);self.assertAlmostEqual(measured,10000,delta=100)
   self.assertLess(abs(x[256000]-x[255999]),12000)
   s=spectrum(source);self.assertGreater(s['channels']['137900000']['band_to_noise_db'],s['channels']['137100000']['band_to_noise_db']+8)
 def test_valid_frames_survive_for_products_and_paths_are_confined(self):
  with tempfile.TemporaryDirectory() as td,patch.object(common,'DATA',Path(td)):
   out=Path(td)/'meteo-work/test';out.mkdir(parents=True)
   frame=out/'meteor.cadu';frame.write_bytes(b'')
   self.assertFalse(enqueue_cadu(out,common.DEFAULT,'test'))
   frame.write_bytes(b'x'*1024);self.assertTrue(enqueue_cadu(out,common.DEFAULT,'test'));self.assertTrue(frame.exists())
   queued=list((Path(td)/'meteo-process').glob('*.json'));self.assertEqual(len(queued),1);self.assertEqual(json.loads(queued[0].read_text())['kind'],'cadu')
   with self.assertRaises(ValueError):safe_path('/etc/passwd')
if __name__=='__main__':unittest.main()
