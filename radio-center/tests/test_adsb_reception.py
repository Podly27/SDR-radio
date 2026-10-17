import json,sys,tempfile,time,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import adsb_worker as adsb
class Reception(unittest.TestCase):
 def test_recent_planes_and_explicit_position_age(self):
  raw={'now':1000,'aircraft':[{'hex':'a','seen':80},{'hex':'b','seen':1,'lat':49,'lon':18,'seen_pos':90},{'hex':'c','seen':301}]}
  cached={'a':{'received':850,'lat':50,'lon':19}}
  rows=adsb.live_aircraft(raw,cached,1001);self.assertEqual([a['hex'] for a in rows],['b','a']);self.assertEqual(rows[0]['position_age'],91);self.assertEqual(rows[1]['position_age'],151);self.assertEqual(rows[1]['position_source'],'last_local')
  self.assertNotIn('lat',adsb.live_aircraft(raw,{'a':{'received':600,'lat':50,'lon':19}},1001)[1])
 def test_cache_preserves_actual_position_time(self):
  with tempfile.TemporaryDirectory() as td,patch.object(adsb,'DATA',Path(td)):
   db=adsb.connect()
   try:
    a={'hex':'a','messages':1,'seen':1,'lat':49,'lon':18,'seen_pos':30};previous=adsb.ingest(db,{'now':1000,'messages':1,'aircraft':[a]},(0,{}))[:2]
    self.assertEqual(db.execute('SELECT received FROM positions').fetchone()[0],970)
    a['seen_pos']=40;adsb.ingest(db,{'now':1010,'messages':1,'aircraft':[a]},previous);self.assertEqual(db.execute('SELECT received FROM positions').fetchone()[0],970)
   finally:db.close()
 def test_rf_stats_use_valid_messages_and_drop_counts(self):
  with tempfile.TemporaryDirectory() as td,patch.object(adsb,'RUN',Path(td)):
   (Path(td)/'stats.json').write_text(json.dumps({'last1min':{'start':10,'end':70,'local':{'accepted':[600,60],'samples_processed':999,'samples_dropped':1,'gain_db':48,'noise':-33},'cpr':{'global_ok':7,'local_ok':3}},'total':{'end':70}}))
   stats=adsb.rf_stats();self.assertEqual(stats['messages_per_second'],11);self.assertEqual(stats['positions'],10);self.assertEqual(stats['drop_percent'],.1)
 def test_gain_selection_is_local_to_adsb(self):
  c={'device':'00000001','gain':40.2,'ppm':-7,'latitude':49,'longitude':18}
  adaptive=adsb.command(c,{'gain_mode':'adaptive'});self.assertIn('--adaptive-range',adaptive);self.assertIn('--fix',adaptive)
  manual=adsb.command(c,{'gain_mode':'manual','gain':29.7});self.assertNotIn('--adaptive-range',manual);self.assertEqual(manual[manual.index('--gain')+1],'29.7');self.assertEqual(c['gain'],40.2)
  for gain in [float('nan'),50,True,[],{}]:
   with self.assertRaises(ValueError):adsb.validate_config({'gain':gain})
