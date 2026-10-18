import io,json,sys,unittest,time
from pathlib import Path
from unittest.mock import patch,Mock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import feeder_control as feeder
class FeederControl(unittest.TestCase):
 def test_invalid_key_or_action_never_changes_services(self):
  for payload in ({'action':'shell'}, {'action':'save','adsbx_enabled':True,'fr24_enabled':True,'fr24key':'bad'}):
   with patch.object(feeder,'systemctl') as control:
    with self.assertRaises(ValueError):feeder.execute(payload)
    control.assert_not_called()
 def test_missing_key_cannot_enable_fr24(self):
  with patch.object(feeder,'values',return_value={}),patch.object(feeder,'systemctl') as control:
   with self.assertRaises(ValueError):feeder.execute({'action':'save','adsbx_enabled':True,'fr24_enabled':True})
   control.assert_not_called()
 def test_status_filters_credentials_and_checks_connection(self):
  monitor=io.BytesIO(json.dumps({'fr24key':'PRIVATEKEY123456','feed_status':'connected','feed_alias':'T-TEST','rx_connected':'1'}).encode())
  opener=Mock();opener.open.return_value=monitor
  def ctl(*args):return Mock(stdout='123\n' if args[0]=='show' else 'active\n' if args[0]=='is-active' else 'enabled\n')
  with patch.object(feeder,'values',return_value={'fr24key':'PRIVATEKEY123456'}),patch.object(feeder,'systemctl',side_effect=ctl),patch.object(feeder.subprocess,'run',return_value=Mock(stdout='ESTAB 0 0 local:123 peer:30004 users:(("feed-adsbx",pid=123,fd=1))')),patch.object(Path,'exists',return_value=True),patch.object(Path,'read_text',side_effect=['readsb_net_connector_status{host="feed1.adsbexchange.com",port="30004"} 10',json.dumps({'now':0,'messages':99}),'12345678-1234-1234-1234-123456789abc']),patch.object(Path,'stat',return_value=Mock(st_mtime=time.time())),patch.object(feeder.urllib.request,'build_opener',return_value=opener):
   result=feeder.status()
  self.assertNotIn('PRIVATEKEY',json.dumps(result));self.assertTrue(result['fr24']['key_set']);self.assertTrue(result['fr24']['connected']);self.assertTrue(result['adsbx']['connected']);self.assertIsNone(result['adsbx']['messages'])
