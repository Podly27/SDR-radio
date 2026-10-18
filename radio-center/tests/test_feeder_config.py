import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('fr24_config', Path(__file__).resolve().parents[1] / 'configure-fr24.py')
config = importlib.util.module_from_spec(spec)
spec.loader.exec_module(config)


class FeederConfig(unittest.TestCase):
    def test_replaces_usb_settings_without_retaining_old_credentials(self):
        text = 'receiver="dvbt"\nfr24key="old"\npath="/dev/usb"\nprocargs="--net"\nlogmode="1"\n'
        result = config.configure(text, '0123456789ABCDEF')
        self.assertIn('receiver="beast-tcp"', result)
        self.assertIn('host="127.0.0.1:30005"', result)
        self.assertIn('mlat="no"', result)
        self.assertIn('logmode="1"', result)
        self.assertNotIn('old', result)
        self.assertNotIn('procargs=', result)
        self.assertNotIn('path=', result)
        self.assertEqual(result.count('fr24key='), 1)

    def test_rejects_config_injection(self):
        with self.assertRaises(ValueError):
            config.configure('', 'key"\nreceiver="dvbt')
