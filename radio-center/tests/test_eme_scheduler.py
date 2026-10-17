"""Exercise Moon gates and shared leasing without live systemd/SDR."""
import datetime,json,signal,sys,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import eme_scheduler as scheduler
class SchedulerTest(unittest.TestCase):
 def run_cycle(self,mode='auto',elevation=30,running=False,synced=True):
  config=json.loads(json.dumps(scheduler.common.DEFAULT));config.update(latitude=49.5622,longitude=18.1746,callsign='OK2IKT',mode=mode);callbacks={};states=[]
  def save(name,state):states.append(dict(state));callbacks[signal.SIGTERM]()
  with tempfile.TemporaryDirectory() as td:
   data=Path(td);(data/'eme-config.json').write_text(json.dumps(config));moon={'elevation':elevation,'next_stop':(datetime.datetime.now(datetime.timezone.utc)+datetime.timedelta(hours=2)).isoformat()}
   with patch.object(scheduler.common,'DATA',data),patch.object(scheduler,'snapshot',return_value=(running,['radio-ism.service'])),patch.object(scheduler.common,'moon_position',return_value=moon),patch.object(scheduler.signal,'signal',side_effect=lambda sig,fn:callbacks.update({sig:fn})),patch.object(scheduler.common,'atomic',side_effect=save),patch.object(scheduler.subprocess,'run',return_value=SimpleNamespace(stdout='yes' if synced else 'no')),patch.object(scheduler.lease,'generation',return_value=0),patch.object(scheduler.lease,'acquire',return_value=(True,'borrowed')) as acquire,patch.object(scheduler.lease,'release') as release,patch.object(scheduler.lease,'owns',return_value=False):
    scheduler.main();return acquire.call_count,states[0]
 def test_suitable_elevation_requests_borrow_even_with_ism(self):self.assertEqual(self.run_cycle()[0],1)
 def test_start_limit(self):self.assertEqual(self.run_cycle(elevation=16)[0],0);self.assertEqual(self.run_cycle(elevation=17)[0],1)
 def test_running_hysteresis(self):self.assertEqual(self.run_cycle(elevation=16,running=True)[0],1);self.assertEqual(self.run_cycle(elevation=14,running=True)[0],0)
 def test_off_and_unsynced_do_not_start(self):self.assertEqual(self.run_cycle(mode='off')[0],0);self.assertEqual(self.run_cycle(synced=False)[0],0)
if __name__=='__main__':unittest.main()
