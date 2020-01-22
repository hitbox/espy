import logging
import time
import unittest

from espy import Alert, ESPY

class TestESPY(unittest.TestCase):

    def test_instantiation(self):
        alert = Alert('testalert', 'now > 0', msg='TEST MESSAGE')
        espy = ESPY({'testalert': 999}, [alert])
        # test alert logs alert message
        with self.assertLogs('espy.testalert', logging.WARNING) as cm:
            espy.process(1)
        # test last alerted time is passed
        alert.eval_source = 'now > 0 and last'
        with self.assertLogs('espy.testalert', logging.WARNING) as cm:
            espy.process(1)


if __name__ == '__main__':
    unittest.main()
