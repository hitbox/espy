import argparse
import configparser
import logging.config
import pickle
import time
from pathlib import Path

class ESPYError(Exception):
    pass


class Alert:

    def __init__(self, name, alert_src, clear_src=None, level=None, msg=None,
                 context=None):
        self.name = name
        self.alert_src = alert_src
        self.clear_src = clear_src
        self.level = logging.WARNING if level is None else level
        self.msg = msg
        self.context = context

    def do_alert(self):
        msg = self.message()
        logger = logging.getLogger(f'espy.{self.name}')
        logger.log(self.level, msg)

    def message(self):
        return str(self.msg or self.alert_src)

    def _eval(self, source, now, **context):
        globals = dict(now=now, Path=Path, time=time, **context)
        if self.context:
            globals.update(**eval(self.context))
        rv = eval(source, globals)
        return bool(rv)

    def should_alert(self, now, **context):
        return self._eval(self.alert_src, now, **context)

    def should_clear(self, now, **context):
        if self.clear_src:
            return self._eval(self.clear_src, now, **context)


class Manager:

    def __init__(self, lasts, alerts):
        self.lasts = lasts
        self.alerts = alerts

    def process(self, now):
        for alert in self.alerts:
            last = self.lasts.get(alert.name)
            if (alert.name in self.lasts
                    and alert.should_clear(now, last=last)):
                del self.lasts[alert.name]
            if alert.should_alert(now, last=last):
                alert.do_alert()
                self.lasts[alert.name] = now


def _create_alerts(cp):
    # raise errors as early as possible and regardless of alert conditions
    alerts = []
    alertnames = cp['espy']['keys'].replace(',', ' ').split()
    alertsections = [cp[f'espy_{alertname}'] for alertname in alertnames]
    for alertname, section in zip(alertnames, alertsections):
        if not section['alert']:
            raise ESPYError('Config error: alert key must be eval-able string')
        alert_src = section['alert']
        clear_src = section.get('clear')
        level = section.get('level')
        msg = section.get('msg')
        context = section.get('context')
        alert = Alert(alertname, alert_src, clear_src, level=level, msg=msg,
                      context=context)
        alerts.append(alert)
    return alerts

def main(argv=None):
    """
    Alert on configured conditions.
    """
    parser = argparse.ArgumentParser(description=main.__doc__)
    parser.add_argument('config', nargs='+')
    parser.add_argument('-t', '--test', action='store_true', help='Just test configuration.')
    parser.set_defaults(command='run')

    subparsers = parser.add_subparsers()
    # help is shown in the root help and description is shown in the lasts help
    lasts_sp = subparsers.add_parser('lasts',
            help='Utilities for the lasts database.',
            description='List last alerts.')
    lasts_sp.set_defaults(command='lasts')
    lasts_group = lasts_sp.add_mutually_exclusive_group()
    lasts_group.add_argument('--clear', action='store_true')
    lasts_group.add_argument('--delete', nargs='+')

    args = parser.parse_args(argv)

    # exit if any config paths do not exist
    for configpath in args.config:
        if not Path(configpath).exists():
            parser.error(f'{configpath!r} does not exist.')

    # load config and configure logging
    cp = configparser.ConfigParser()
    cp.read(args.config)
    logging.config.fileConfig(cp)

    # ensure handlers for espy logger
    logger = logging.getLogger('espy')
    if not logger.handlers:
        raise ESPYError('No handlers configured for espy')

    # load last alert times
    dbpath = cp['espy']['database']
    if not dbpath:
        raise ESPYError('Invalid configured database path')
    lastsdb = Path(dbpath)
    if lastsdb.exists():
        lasts = pickle.load(lastsdb.open('rb'))
    else:
        lasts = {}

    # process lasts and exit
    if args.command == 'lasts':
        if args.clear:
            pickle.dump({}, lastsdb.open('wb'))
        elif args.delete:
            for key in args.delete:
                del lasts[key]
            pickle.dump(lasts, lastsdb.open('wb'))
        else:
            for key in lasts:
                print(key)
        parser.exit()

    # create alerts from config
    alerts = _create_alerts(cp)
    manager = Manager(lasts, alerts)

    # test config: run expressions and exit
    if args.test:
        # alerts evaluate with bare minimum context
        for alert in manager.alerts:
            alert.should_clear(0, last=None)
            alert.should_alert(0, last=None)
            if alert.context:
                eval(alert.context)
        parser.exit()

    manager.process(time.time())
    pickle.dump(manager.lasts, lastsdb.open('wb'))

    if args.command == 'run':
        logger.info('run completed')

if __name__ == '__main__':
    main()
