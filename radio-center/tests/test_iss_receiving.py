import datetime,math,struct,sys,tempfile,time,unittest
from pathlib import Path
from unittest.mock import patch
import ephem
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import iss_auto as c,iss_receiver
class ReceivingTest(unittest.TestCase):
 def test_profiles_are_receive_frequencies(self):
  expected={'voice-vhf':145800000,'repeater-uhf':437800000,'packet-vhf':145825000,'packet-uhf':437825000,'sstv-uhf':437550000,'sstv-vhf':145800000}
  for key,f in expected.items():self.assertEqual(c.validate({'profile':key})['frequency'],f)
  with self.assertRaises(ValueError):c.validate({'profile':'uplink'})
  with self.assertRaises(ValueError):c.validate({'doppler':'yes'})
  self.assertEqual(c.validate({'frequency':145800000})['profile'],'sstv-vhf')
  self.assertTrue(c.validate({})['doppler'])
 def test_doppler_sign_and_scaling(self):
  self.assertGreater(c.doppler_shift(437550000,-7000),0);self.assertLess(c.doppler_shift(437550000,7000),0)
  self.assertAlmostEqual(c.doppler_shift(437550000,7000)/c.doppler_shift(145800000,7000),437550000/145800000)
 def test_tle_velocity_and_stale_fallback(self):
  sat=ephem.readtle('ISS','1 25544U 98067A   03097.78853147  .00021906  00000-0  28403-3 0  8652','2 25544  51.6361  13.7980 0004256  35.6671  59.2566 15.58778559250029')
  now=datetime.datetime(2003,4,7,19,tzinfo=datetime.timezone.utc).timestamp()
  with patch.object(c.common,'read_tle',return_value=({'epoch':now},sat)),patch.object(c.common,'station',return_value={'latitude':49.5625,'longitude':18.125,'height':380}):
   r=c.tuning(c.validate({}),now);self.assertIsNone(r['doppler_error']);self.assertTrue(math.isfinite(r['range_velocity']));self.assertAlmostEqual(r['doppler_hz'],-437550000*r['range_velocity']/299792458.)
   old=c.tuning(c.validate({}),now+8*86400);self.assertIsNotNone(old['doppler_error']);self.assertEqual(old['doppler_hz'],0)
  self.assertEqual(c.tuning(c.validate({'doppler':False}))['doppler_hz'],0)
 def test_audio_window_is_bounded_and_sequenced(self):
  with tempfile.TemporaryDirectory() as td,patch.object(iss_receiver,'RUN',Path(td)):
   window=iss_receiver.AudioWindow();window.feed(b'\x01\x00'*60000)
   raw=(Path(td)/'audio.bin').read_bytes();session,end=struct.unpack('<dQ',raw[:16]);self.assertEqual(end,60000);self.assertLess(abs(session-time.time()),1);self.assertEqual(len(raw),96016)
