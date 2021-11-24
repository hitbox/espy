import argparse
import configparser
import logging.config
import os
import pickle
import time

from pathlib import Path

try:
    import wmi
except ImportError:
    wmi = None

class ESPYError(Exception):
    pass


class Alert:
    """
    Alerting through standard library logging.
    """

    def __init__(
        self,
        name,
        alert_expression,
        clear_expression = None,
        sanity_expression = None,
        level = None,
        msg = None,
        context = None
    ):
        """
        :param name: a name for the alert.
        :param alert_expression: eval-able expression return truthy to alert.
        :param clear_expression:
                eval-able expression return truthy to clear last alert.
        :param sanity_expression:
                eval-able expression before alert_expression logs all exceptions.
        :param level: level to log alert as.
        :param msg: alert message to log with.
        :param context:
                dict addition context. By default eval context is Path, now,
                os, time, and wmi.
        """
        self.name = name
        self.alert_expression = alert_expression
        self.clear_expression = clear_expression
        self.sanity_expression = sanity_expression
        self.level = logging.WARNING if level is None else level
        self.msg = msg
        self.context = context

    def do_alert(self):
        msg = self.message()
        logger = self._getlogger()
        logger.log(self.level, msg)

    def message(self):
        return str(self.msg or self.alert_expression)

    def _getlogger(self):
        return logging.getLogger(f'espy.{self.name}')

    def _eval(self, source, now, **context):
        context = dict(
            Path = Path,
            now = now,
            os = os,
            time = time,
            wmi = wmi,
            **context
        )
        if self.context:
            context.update(**eval(self.context))
        rv = eval(source, context)
        return bool(rv)

    def should_alert(self, now, **context):
        if self.sanity_expression:
            try:
                self._eval(self.sanity_expression, now, **context)
            except:
                logger = self._getlogger()
                logger.exception('sanity check failed')
        return self._eval(self.alert_expression, now, **context)

    def should_clear(self, now, **context):
        if self.clear_expression:
            return self._eval(self.clear_expression, now, **context)


class Manager:
    """
    Manage running alerts and clearing last alerts.
    """

    def __init__(self, lasts, alerts):
        self.lasts = lasts
        self.alerts = alerts

    def process(self, now, logger):
        for alert in self.alerts:
            logger.info('processing alert: %s', alert.name)
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
        alert_expression = section['alert']
        clear_expression = section.get('clear')
        sanity_expression = section.get('sanity')
        level = section.get('level')
        msg = section.get('msg')
        context = section.get('context')
        alert = Alert(
            alertname,
            alert_expression,
            clear_expression,
            sanity_expression = sanity_expression,
            level = level,
            msg = msg,
            context = context
        )
        alerts.append(alert)
    return alerts

def get_parser():
    parser = argparse.ArgumentParser(description=main.__doc__)

    subparsers = parser.add_subparsers()
    run_sp = subparsers.add_parser('run')
    run_sp.add_argument('config', nargs='+', help='Path to config file.')
    run_sp.add_argument('-t', '--test', action='store_true', help='Just test configuration.')
    run_sp.set_defaults(func='run')

    # help is shown in the root help and description is shown in the lasts help
    lasts_sp = subparsers.add_parser('lasts',
            help='Utilities for the lasts database.',
            description='List last alerts.')
    lasts_sp.add_argument('config', nargs='+', help='Path to config file.')
    lasts_sp.set_defaults(func='lasts')

    lasts_group = lasts_sp.add_mutually_exclusive_group()
    lasts_group.add_argument('--clear', action='store_true')
    lasts_group.add_argument('--delete', nargs='+')

    return parser

def main(argv=None):
    """
    Alert on configured conditions.
    """
    parser = get_parser()
    args = parser.parse_args(argv)

    # exit if any config paths do not exist
    for configpath in args.config:
        if not Path(configpath).exists():
            parser.error(f'{configpath!r} does not exist.')

    # load config and configure logging
    cp = configparser.ConfigParser()
    cp.read(args.config)
    logging.config.fileConfig(cp)

    # raise for missing handlers
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
            else:
                print('nothing in lasts')
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

    manager.process(time.time(), logger)
    pickle.dump(manager.lasts, lastsdb.open('wb'))

    logger.info('run completed')

if __name__ == '__main__':
    main()
