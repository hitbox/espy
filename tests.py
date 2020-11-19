import configparser
import contextlib
import io
import logging
import os
import tempfile
import unittest

import espy

@contextlib.contextmanager
def tempconfig(text):
    try:
        fd, temppath = tempfile.mkstemp(suffix='.pickle')
        cp = configparser.ConfigParser()
        cp.read_string(text.format(temppath=temppath))
        yield cp
    finally:
        os.unlink(temppath)

class TestESPY(unittest.TestCase):

    def test_create_alerts(self):
        "test creating alerts from configparser"
        text = """
            [espy]
            database = {temppath}
            keys = alert

            [espy_alert]
            alert = True
            """
        with tempconfig(text) as cp:
            alerts = espy._create_alerts(cp)
            self.assertEqual(len(alerts), 1)
            self.assertEqual(alerts[0].alert_src, 'True')
            self.assertIsNone(alerts[0].clear_src)
            self.assertTrue(alerts[0].should_alert(0))
            self.assertEqual(alerts[0].level, logging.WARNING)
            self.assertIsNone(alerts[0].msg)

    def test_context(self):
        "test that context is passed to alert and clear expressions"
        text = """
            [espy]
            database = {temppath}
            keys = alert

            [espy_alert]
            context = dict(pathobj = Path('tests.py'))
            alert = pathobj.stat().st_mtime > 0
            clear = pathobj
            """
        with tempconfig(text) as cp:
            alerts = espy._create_alerts(cp)
            self.assertEqual(len(alerts), 1)
            alert = alerts[0]
            self.assertTrue(alert.should_alert(0))
            self.assertTrue(alert.should_clear(0))

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
