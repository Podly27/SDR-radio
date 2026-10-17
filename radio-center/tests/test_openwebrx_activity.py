import sys,unittest
from pathlib import Path
from types import SimpleNamespace as NS
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from openwebrx_activity import snapshot
class Source:
 def getName(self):return 'RTL-SDR'
 def getProfileName(self):return '2 m'
 def getProps(self):return {'center_freq':145000000,'samp_rate':2400000}
class ActivityTest(unittest.TestCase):
 def test_independent_tunings_no_identity(self):
  source=Source();clients=[NS(sdr=source,dsp=NS(props={'center_freq':145000000,'offset_freq':525000,'mod':'nfm','low_cut':-4000,'high_cut':4000}),ip='private'),NS(sdr=source,dsp=NS(props={'start_freq':144174000,'start_mod':'usb','secondary_mod':'ft8'})),NS(sdr=source,dsp=None)]
  data=snapshot(NS(clients=clients),[source])
  self.assertEqual(len(data['listeners']),2);self.assertEqual(data['listeners'][0]['frequency'],145525000);self.assertEqual(data['listeners'][0]['bandwidth'],8000);self.assertEqual(data['listeners'][1]['secondary_modulation'],'ft8');self.assertNotIn('private',str(data))
 def test_no_listeners_retains_receiver_profile(self):
  data=snapshot(NS(clients=[]),[Source()]);self.assertEqual(data['listeners'],[]);self.assertEqual(data['receivers'][0]['profile'],'2 m')
if __name__=='__main__':unittest.main()
