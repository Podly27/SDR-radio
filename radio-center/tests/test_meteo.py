"""Orbit, resource gating and gallery tests; no live satellite reception claims."""
import datetime,json,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import numpy as np
from PIL import Image
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import meteo_common as c
from meteo_scheduler import should_start
from meteo_worker import command,import_images
TLE={'name':'METEOR-M2 4','line1':'1 59051U 24039A   26289.94493436  .00000010  00000+0  24380-4 0  9998','line2':'2 59051  98.7190 247.8003 0007083 168.9412 191.1923 14.22440269136571','fetched':1792226400}
STATION={'latitude':49.5622,'longitude':18.1746,'place':'Lichnov','callsign':'OK2IKT'}
class MeteoTest(unittest.TestCase):
 def test_gate(self):
  orbit={'tle_fresh':True,'passes':[{'start':90,'end':110}]}
  self.assertTrue(should_start('auto',False,[],orbit,100))
  for unit in ['openwebrx.service','radio-ism.service','radio-eme-rx.service','radio-iss.service','radio-aprs.service']:
   self.assertTrue(should_start('auto',False,[unit],orbit,100))
  self.assertFalse(should_start('auto',True,[],orbit,100));self.assertFalse(should_start('auto',False,[],orbit,110));self.assertFalse(should_start('auto',False,[],orbit,89));self.assertFalse(should_start('auto',False,[],orbit,100,False));self.assertFalse(should_start('auto',False,[],dict(orbit,tle_fresh=False),100))
  self.assertTrue(should_start('manual',False,['radio-ism.service'],{},100))
 def test_orbit_and_elevation_crossings(self):
  now=datetime.datetime(2026,10,17,9,tzinfo=datetime.timezone.utc).timestamp()
  with tempfile.TemporaryDirectory() as td,patch.object(c,'DATA',Path(td)),patch.object(c,'station',return_value=STATION):
   Path(td,'meteo-tle-M2-4.json').write_text(json.dumps(TLE));c.PLAN_CACHE.clear();plan=c.position_and_passes(c.DEFAULT,now)
   self.assertTrue(plan['tle_fresh']);self.assertTrue(plan['passes'])
   for p in plan['passes']:
    self.assertLess(p['start'],p['peak']);self.assertLess(p['peak'],p['end']);self.assertGreaterEqual(p['maximum_elevation'],10)
    _,sat=c.read_tle('M2-4');o=c.observer(STATION)
    for key in ('start','end'):
     o.date=datetime.datetime.fromtimestamp(p[key],datetime.timezone.utc);sat.compute(o);self.assertAlmostEqual(float(sat.alt)*180/np.pi,10,delta=.02)
   c.PLAN_CACHE.clear();self.assertFalse(c.position_and_passes(c.DEFAULT,now+8*86400)['tle_fresh'])
 def test_config_and_native_arguments(self):
  for key,value in [('satellite',[]),('frequency',144800000),('symbolrate',12345),('gain',None),('minimum_elevation',float('nan'))]:
   with self.assertRaises(ValueError):c.validate(dict(c.DEFAULT,**{key:value}))
  cmd=command(c.DEFAULT,Path('/tmp/out'),60);self.assertIn('meteor_m2-x_lrpt',cmd);self.assertIn('--ppm_correction',cmd);self.assertEqual(cmd[cmd.index('--ppm_correction')+1],'-7');self.assertIn('M2-4',cmd);self.assertEqual(cmd[cmd.index('--pll_bw')+1],'0.008')
 def test_image_import_and_empty_capture(self):
  with tempfile.TemporaryDirectory() as td,patch.object(c,'DATA',Path(td)):
   out=Path(td,'capture');(out/'MSU-MR').mkdir(parents=True)
   self.assertEqual(import_images(out,c.DEFAULT,'test'),0)
   Image.fromarray(np.tile(np.linspace(0,65535,256,dtype=np.uint16),(64,1))).save(out/'MSU-MR'/'msu_mr_1.png')
   self.assertEqual(import_images(out,c.DEFAULT,'test'),1);data=c.history();self.assertEqual(data['total'],1);row=data['events'][0]
   self.assertEqual((row['width'],row['height']),(256,64));self.assertTrue(Path(td,'meteo-images',row['original']).exists())
   with Image.open(Path(td,'meteo-images',row['filename'])) as image:self.assertEqual(image.mode,'RGB')
if __name__=='__main__':unittest.main()
