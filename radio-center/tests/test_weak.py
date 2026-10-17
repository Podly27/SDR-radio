"""Offline regression checks; all database operations use temporary storage."""
import sys,tempfile,time,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import ft_worker,server,weak_profiles

class WeakTests(unittest.TestCase):
 def test_history_isolation(self):
  with tempfile.TemporaryDirectory() as td,patch.object(ft_worker,'DATA',Path(td)),patch.object(server,'DATA',Path(td)),patch.object(ft_worker,'KIND','weak'),patch.object(ft_worker,'PROFILES',weak_profiles.PROFILES):
   db=ft_worker.connect()
   parsed=ft_worker.parse_line('0000 -16 0.1 1500 : CQ K1ABC FN42 q0','q65-60a')
   ft_worker.save(db,time.time(),'2m-q65-60a',parsed)
   ft_worker.save(db,time.time(),'20m-jt65a',dict(parsed,message='K1ABC W9XYZ EN37'))
   ft_worker.prune(db);db.close()
   records=server.ft_history('profile=2m-q65-60a','weak')['events']
   self.assertEqual(len(records),1);self.assertEqual(records[0]['message'],'CQ K1ABC FN42')
   self.assertEqual(len(server.ft_history('q=K1ABC','weak')['events']),2)
   self.assertEqual(server.ft_history('','ft')['total'],0)
   self.assertEqual(server.clear_ft_history('ft'),0)
   self.assertEqual(server.clear_ft_history('weak'),2)
   with self.assertRaises(ValueError):server.ft_history('profile=2m-ft8','weak')
 def test_validation_and_output(self):
  for freq in (True,1,144000000.0,146000000):
   with self.assertRaises(ValueError):weak_profiles.validate_frequency('2m-q65-60a',freq)
  self.assertEqual(ft_worker.parse_line('123456 -12 0.2 1234 ~ CQ OK2IKT JN89','ft8')['message'],'CQ OK2IKT JN89')
  self.assertIsNotNone(ft_worker.parse_line('123456 -12 0.2 1234 + CQ OK2IKT JN89','ft4'))
  self.assertIsNone(ft_worker.parse_line('<DecodeFinished> 0 0 0','q65-60a'))
  self.assertIsNone(ft_worker.parse_line('0000 -16 0.1 1500 # fake','q65-60a'))
 def test_complete_utc_intervals(self):
  for period in (15,30,60,120,300):
   slots=ft_worker.Slots(period,rate=10)
   # Start part way through an interval: discard its incomplete audio.
   self.assertEqual(slots.feed(b'\0\0'*((period-1)*10),period),[])
   completed=slots.feed(b'\0\0'*(period*10),2*period)
   self.assertEqual(len(completed),1);self.assertEqual(completed[0][0],period)
   self.assertEqual(len(completed[0][1]),period*10*2)

if __name__=='__main__':unittest.main()
