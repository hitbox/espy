import configparser
import contextlib
import io
import logging
import os
import tempfile
import unittest

import espy

class TestESPY(unittest.TestCase):

    def test__create_alerts(self):
        try:
            fd, temppath = tempfile.mkstemp(suffix='.pickle')
            cp = configparser.ConfigParser()
            cp.read_string(f"""
            [espy]
            database = {temppath}
            keys = alert

            [espy_alert]
            alert = True
            """)
            alerts = espy._create_alerts(cp)
            self.assertEqual(len(alerts), 1)
            self.assertEqual(alerts[0].alert_src, 'True')
            self.assertTrue(alerts[0].should_alert(0))
        finally:
            os.unlink(temppath)

    def test_instantiation(self):
        alert = espy.Alert('alert', 'now > 0', msg='TEST MESSAGE')
        manager = espy.Manager({'alert': 999}, [alert])
        # test alert logs alert message
        with self.assertLogs('espy.alert', logging.WARNING) as cm:
            manager.process(1)
        # test last alerted time is passed
        alert.eval_source = 'now > 0 and last'
        with self.assertLogs('espy.alert', logging.WARNING) as cm:
            manager.process(1)

    def test_main(self):
        with contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaises(SystemExit):
                espy.main(['--help'])

if __name__ == '__main__':
    unittest.main()
