import configparser
import contextlib
import io
import logging
import os
import tempfile
import unittest

import espy

@contextlib.contextmanager
def tempconfig(config_text):
    """
    Create a config parser object from config_text and give it the path to a
    temporary pickle file to use as the database.
    """
    with tempfile.TemporaryFile(suffix='.pickle') as tempdb:
        cp = configparser.ConfigParser()
        cp.read_string(config_text.format(temppath=tempdb.name))
        yield cp

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

    def test_alert_over_time(self):
        """
        Alerts when there's no last last, clears when there is and last
        modified time is greater than it.
        """
        _mtime = 12
        mtime = lambda: _mtime
        alert = espy.Alert('test', alert_src=f'not last and now - mtime() > 10',
                           clear_src=f'last and mtime() > last')
        # should throw exception because last not given
        with self.assertRaises(NameError):
            self.assertFalse(alert.should_alert(now=mtime()+8, mtime=mtime))
        # should not alert because last is given
        self.assertFalse(alert.should_alert(now=mtime()+8, last=2, mtime=mtime))
        # should alert because `last` is falsey and the difference between now
        # and `mtime` is greater than 10...
        self.assertTrue(alert.should_alert(now=mtime()+11, last=None, mtime=mtime))
        # ...the given now should get stored as last...
        # ...then, should not alert on subsequent calls until cleared
        self.assertFalse(alert.should_alert(now=mtime()+20, last=mtime()+11, mtime=mtime))
        # suppose mtime is updated...
        _mtime = 20
        self.assertFalse(alert.should_alert(now=mtime()+20, last=mtime()+11, mtime=mtime))
        with self.assertRaises(NameError):
            self.assertFalse(alert.should_clear(now=mtime()+8))
        # should clear because mtime > last
        self.assertTrue(alert.should_clear(now=mtime()+8, last=2, mtime=mtime))


if __name__ == '__main__':
    unittest.main()
