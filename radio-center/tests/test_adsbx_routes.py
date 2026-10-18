import io
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import server


class AdsbxRoutes(unittest.TestCase):
    def handler(self, path):
        handler = server.Handler.__new__(server.Handler)
        handler.path = path
        handler.send_response = Mock()
        handler.send_header = Mock()
        handler.end_headers = Mock()
        handler.wfile = io.BytesIO()
        return handler

    def test_original_bookmark_opens_local_map(self):
        for path in ('/control/adsb', '/control/adsb/', '/control/adsb/?old=1'):
            handler = self.handler(path)
            handler.do_GET()
            handler.send_response.assert_called_once_with(302)
            handler.send_header.assert_any_call('Location', '/adsbx/')
            self.assertEqual(handler.wfile.getvalue(), b'')

    def test_receiver_settings_still_accessible(self):
        handler = self.handler('/control/adsb/receiver/')
        handler.do_GET()
        handler.send_response.assert_called_once_with(200)
        self.assertIn(b'id="rf-settings"', handler.wfile.getvalue())
        self.assertIn(b'href="/adsbx/"', handler.wfile.getvalue())
