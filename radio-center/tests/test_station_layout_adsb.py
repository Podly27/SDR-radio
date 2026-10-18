import datetime,json,sys,tempfile,time,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import station_common as station,dashboard_layout as layout,adsb_worker as adsb,eme_common,meteo_common
FIXTURE={**station.BASE,'latitude':49.5625,'longitude':18.125,'callsign':'OK2IKT','place':'Lichnov','device':'00000001'}
class SharedSettings(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.data=Path(self.tmp.name);self.patches=[patch.object(station,'DATA',self.data),patch.object(adsb,'DATA',self.data),patch.object(adsb,'RUN',self.data/'run'),patch.object(eme_common,'DATA',self.data)]
  for p in self.patches:p.start()
 def tearDown(self):
  for p in reversed(self.patches):p.stop()
  self.tmp.cleanup()
 def test_migration_preserves_real_values(self):
  station.atomic('eme-config.json',FIXTURE);self.assertEqual(station.load()['longitude'],18.125);station.atomic('station.json',station.load());self.assertEqual(station.home()['place'],'Lichnov')
 def test_shared_source_overrides_old_eme(self):
  legacy={**eme_common.DEFAULT,**FIXTURE};station.atomic('eme-config.json',legacy);c={**FIXTURE,'longitude':18.5,'gain':29,'ppm':-5};station.atomic('station.json',c)
  self.assertEqual(eme_common.load_config()['longitude'],18.5);self.assertEqual(eme_common.load_config()['gain'],29);self.assertEqual(meteo_common.station()['longitude'],18.5)
 def test_global_elevations_override_applications(self):
  import iss_auto
  with patch.object(meteo_common,'DATA',self.data):
   station.atomic('station.json',{**FIXTURE,'moon_minimum_elevation':20,'satellite_minimum_elevation':12})
   station.atomic('eme-config.json',{**eme_common.DEFAULT,**FIXTURE})
   self.assertEqual(eme_common.load_config()['minimum_elevation'],20)
   self.assertEqual(meteo_common.load_config()['minimum_elevation'],12)
   self.assertEqual(iss_auto.load_config()['minimum_elevation'],12)
  for k,v in [('moon_minimum_elevation',85),('satellite_minimum_elevation',81),('moon_minimum_elevation',True),('satellite_minimum_elevation',float('nan'))]:
   with self.assertRaises(ValueError):station.validate({**FIXTURE,k:v})
 def test_validation_and_locator(self):
  c=station.validate({**FIXTURE,'locator':'JN99CN'});self.assertLess(abs(c['latitude']-49.5625),.03)
  for k,v in [('latitude',float('nan')),('longitude',181),('gain',50),('ppm',1.5),('device','x;sh'),('timezone','not/a-zone'),('callsign','a\nb')]:
   with self.assertRaises(ValueError):station.validate({**FIXTURE,k:v})
 def test_layout_hidden_and_new_panels(self):
  c=layout.validate({'order':['iss','ft'],'hidden':['ft']});self.assertEqual(c['order'][:2],['iss','ft']);self.assertIn('adsb',c['order']);self.assertEqual(c['hidden'],['ft']);station.atomic('dashboard-layout.json',c);self.assertEqual(layout.load(),c)
  for raw in [{'order':['ft','ft']},{'order':['shell']},{'order':[],'hidden':['invalid']},{'order':'ft'}]:
   with self.assertRaises(ValueError):layout.validate(raw)
 def test_native_receive_command(self):
  cmd=adsb.command(FIXTURE);self.assertEqual(cmd[cmd.index('--device')+1],'00000001');self.assertEqual(cmd[cmd.index('--ppm')+1],'-7');self.assertIn('--net',cmd);self.assertEqual(cmd[cmd.index('--net-bind-address')+1],'127.0.0.1');self.assertEqual(cmd[cmd.index('--net-bo-port')+1],'30005');self.assertIn('--lat',cmd)
 def test_ingest_deduplicates_counts_and_handles_reset(self):
  station.atomic('station.json',FIXTURE)
  with adsb.connect() as db:
   now=time.time();a={'hex':'abcdef','flight':'TEST123 ','messages':3,'seen':1,'lat':49.6,'lon':18.1,'alt_baro':10000,'rssi':-20}
   raw={'now':now,'messages':3,'aircraft':[a]};total,planes,delta=adsb.ingest(db,raw,(0,{}));self.assertEqual(delta,3)
   total,planes,delta=adsb.ingest(db,raw,(total,planes));self.assertEqual(delta,0);self.assertEqual(db.execute('SELECT count(*) FROM events').fetchone()[0],1)
   raw['messages']=1;a['messages']=1;total,planes,delta=adsb.ingest(db,raw,(total,planes));self.assertEqual(delta,1)
  self.assertEqual(adsb.summary()['hour_count'],4);h=adsb.history();self.assertIsNone(h['updated']);self.assertEqual(len(h['aircraft']),1);self.assertEqual(h['home']['lat'],49.5625)
if __name__=='__main__':unittest.main()
