import datetime,json,sqlite3,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import dashboard_activity as activity

class DashboardActivity(unittest.TestCase):
 def test_rolling_window_and_last_message(self):
  now=datetime.datetime(2026,10,17,12,tzinfo=datetime.timezone.utc)
  with tempfile.TemporaryDirectory() as td:
   path=Path(td)
   with sqlite3.connect(path/'ft.sqlite') as db:
    db.execute('CREATE TABLE messages(received TEXT)')
    for seconds in (-7200,-3601,-3600,-60,-1,60):db.execute('INSERT INTO messages VALUES(?)',((now+datetime.timedelta(seconds=seconds)).isoformat(),))
   activity.ensure_indexes(path)
   result=activity.history_stats(path,now)
   self.assertEqual(result['ft']['hour_count'],3)
   self.assertEqual(result['ft']['last_received'],(now-datetime.timedelta(seconds=1)).isoformat())
   self.assertEqual(result['aprs']['hour_count'],0);self.assertIsNone(result['aprs']['last_received'])
   with sqlite3.connect(path/'ft.sqlite') as db:self.assertTrue(db.execute("SELECT name FROM sqlite_master WHERE type='index' AND name='dashboard_messages_received'").fetchone())
 def test_unreadable_is_unknown(self):
  with tempfile.TemporaryDirectory() as td:
   Path(td,'ft.sqlite').write_text('broken database')
   result=activity.history_stats(td)['ft'];self.assertFalse(result['available']);self.assertIsNone(result['hour_count'])
 def test_state_and_cache(self):
  with tempfile.TemporaryDirectory() as td:
   p=Path(td);Path(p,'ft-state.json').write_text(json.dumps({'updated':123,'period':15,'logs':['private log']}))
   with patch.object(activity,'history_stats',wraps=activity.history_stats) as stats:
    first=activity.summary(p);second=activity.summary(p)
    self.assertEqual(stats.call_count,1);self.assertEqual(first['ft']['receiver']['period'],15);self.assertNotIn('logs',second['ft']['receiver'])
    self.assertIsNone(first['openwebrx']['hour_count'])
if __name__=='__main__':unittest.main()
