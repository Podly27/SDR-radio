"""Actual lease journal/locking with fake systemd; never touches a live receiver."""
import sys,tempfile,time,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import radio_lease as lease
class LeaseTest(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.states={'radio-ism.service':'active',**{m:'active' for m in lease.MONITORS.values()}};self.calls=[];self.fail=None
  self.patches=[patch.object(lease,'DATA',Path(self.tmp.name)),patch.object(lease,'snapshot',side_effect=lambda:dict(self.states)),patch.object(lease,'action',side_effect=self.action)]
  for p in self.patches:p.start()
 def tearDown(self):
  for p in reversed(self.patches):p.stop()
  self.tmp.cleanup()
 def action(self,verb,unit):
  self.calls.append((verb,unit))
  if verb=='stop':self.states[unit]='inactive'
  else:
   for u in lease.active_receivers(self.states):self.states[u]='inactive'
   if self.fail==unit:self.fail=None;self.states[unit]='failed';raise RuntimeError('simulated start failure')
   self.states[unit]='active'
 def acquire(self,owner='iss',token='pass-1',generation=None):return lease.acquire(owner,token,time.time()+60,lease.generation() if generation is None else generation)
 def test_take_and_restore_exact_profile(self):
  self.states['radio-ism.service']='inactive';self.states['radio-ft@20m-ft4.service']='active'
  self.assertTrue(self.acquire()[0]);self.assertEqual(lease.read()['lease']['previous'],'radio-ft@20m-ft4.service');lease.release('iss');self.assertEqual(self.states['radio-ft@20m-ft4.service'],'active');self.assertIsNone(lease.read()['lease'])
 def test_current_automatic_owner_wins(self):
  self.assertTrue(self.acquire('eme')[0]);self.assertFalse(self.acquire('iss')[0]);self.assertFalse(self.acquire('meteo')[0]);lease.release('iss');self.assertTrue(lease.owns('eme'));lease.release('eme');self.assertEqual(self.states['radio-ism.service'],'active')
 def test_manual_override_cancels_return_and_old_window(self):
  armed=lease.generation();self.acquire('iss')
  with lease.manual_selection('radio-aprs.service'):self.action('start','radio-aprs.service')
  lease.release('iss');self.assertEqual(self.states['radio-aprs.service'],'active');self.assertEqual(self.states['radio-ism.service'],'inactive');self.assertFalse(self.acquire('iss',generation=armed)[0]);self.assertFalse(self.acquire('eme',generation=armed)[0])
  lease.rearm('iss');self.assertTrue(self.acquire('iss')[0]);lease.release('iss');self.assertEqual(self.states['radio-aprs.service'],'active')
 def test_external_selection_is_not_overwritten(self):
  self.acquire();self.action('start','openwebrx.service');lease.maintain();self.assertIsNone(lease.read()['lease']);self.assertEqual(self.states['openwebrx.service'],'active');self.assertEqual(self.states['radio-ism.service'],'inactive')
 def test_failure_and_watchdog_restore(self):
  self.fail='radio-iss.service'
  with self.assertRaises(RuntimeError):self.acquire()
  lease.maintain();self.assertIsNone(lease.read()['lease']);self.assertEqual(self.states['radio-ism.service'],'active');self.assertFalse(self.acquire()[0])
 def test_expiry_and_dead_monitor_restore(self):
  self.acquire();state=lease.read();state['lease']['expires']=time.time()-1;lease.save(state);lease.maintain();self.assertEqual(self.states['radio-ism.service'],'active')
  self.acquire(token='pass-2');self.states['radio-iss-auto.service']='inactive';lease.maintain();self.assertEqual(self.states['radio-ism.service'],'active')
 def test_no_original_app_leaves_receiver_off(self):
  self.states['radio-ism.service']='inactive';self.acquire();lease.release('iss');self.assertEqual(lease.active_receivers(self.states),[])
 def test_concurrent_automatic_requests_have_one_winner(self):
  import threading
  barrier=threading.Barrier(2);results=[]
  def take(owner):barrier.wait();results.append((owner,self.acquire(owner)[0]))
  threads=[threading.Thread(target=take,args=(owner,)) for owner in ('iss','meteo')]
  for thread in threads:thread.start()
  for thread in threads:thread.join(timeout=3);self.assertFalse(thread.is_alive())
  self.assertEqual(sum(ok for owner,ok in results),1);winner=next(owner for owner,ok in results if ok);lease.release(winner);self.assertEqual(self.states['radio-ism.service'],'active')
 def test_failed_return_keeps_journal_for_retry(self):
  self.acquire();self.fail='radio-ism.service'
  with self.assertRaises(RuntimeError):lease.release('iss')
  self.assertIsNotNone(lease.read()['lease']);lease.maintain();self.assertIsNone(lease.read()['lease']);self.assertEqual(self.states['radio-ism.service'],'active')
 def test_late_start_after_window_is_rejected(self):
  self.assertFalse(lease.acquire('iss','old',time.time()-1,lease.generation())[0]);self.assertEqual(self.calls,[])
if __name__=='__main__':unittest.main()
