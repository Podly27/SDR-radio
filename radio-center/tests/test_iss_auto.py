import sys,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import iss_auto,meteo_common
class IssAutoTest(unittest.TestCase):
 def test_frequencies_and_elevation(self):
  for f in (145800000,437550000):self.assertEqual(iss_auto.validate({'frequency':f})['frequency'],f)
  for c in ({'frequency':123},{'minimum_elevation':-1},{'minimum_elevation':90}):
   with self.assertRaises(ValueError):iss_auto.validate(c)
 def test_iss_orbit_uses_station_predictor(self):
  with patch.object(iss_auto,'load_config',return_value={'minimum_elevation':12,'frequency':145800000}),patch.object(meteo_common,'position_and_passes',return_value={'passes':[]}) as predict:
   self.assertEqual(iss_auto.orbit(),{'passes':[]});self.assertEqual(predict.call_args.args[0]['satellite'],'ISS');self.assertEqual(predict.call_args.args[0]['minimum_elevation'],12)
  self.assertEqual(meteo_common.ORBIT_SATELLITES['ISS'],25544)
