#!/usr/bin/env python3
#
# Nagios plugin for basic monitor of Varnish Administration Console
#

import sys
import argparse
import requests
from operator import itemgetter
import math


class Requestor(object):
    def __init__(self, vacurl, user, password):
        self.vacurl = vacurl
        self.user = user
        self.password = password

    def make(self, url, okresponses=[200]):
        r = requests.get("{0}{1}".format(self.vacurl, url),
                         auth=(self.user, self.password),
                         headers={'Accept': 'application/json'},
                     )
        if not r.status_code in okresponses:
            raise Exception("API call to {0} returned {1}".format(url, r.status_code))
        return r

OK=0
WARNING=1
CRITICAL=2
leveltexts = {
    OK: 'OK',
    WARNING: 'WARNING',
    CRITICAL: 'CRITICAL',
}

class Errors(object):
    def __init__(self):
        self.maxlevel = OK
        self.errors = []

    def add(self, level, txt):
        if level > self.maxlevel:
            self.maxlevel = level
        self.errors.append((level, txt))

    def print_and_exit(self):
        if not self.errors:
            print("OK")
            sys.exit(0)

        self.errors.sort(key=itemgetter(0), reverse=True)
        print(" :: ".join(["{0}: {1}".format(leveltexts[l],t) for l,t in self.errors]))
        sys.exit(self.maxlevel)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="VAC monitor")
    ap.add_argument('vacurl', help='Full base URL to VAC server (protocol and hostname)')
    ap.add_argument('--user', default='vac', help='VAC user')
    ap.add_argument('--password', default='vac', help='VAC password')
    ap.add_argument('--check', choices=('all', 'global', 'stats'), default='all', help='What to check')

    args = ap.parse_args()

    req = Requestor(args.vacurl, args.user, args.password)
    errors = Errors()

    try:
        if args.check in ('global', 'all'):
            res = req.make("/api/rest/status/all").json()
            if res['license'] != 'OK':
                errors.add(WARNING, "License not OK")
            if res['database'].find('Status: Ok') < 0:
                errors.add(CRITICAL, "MongoDB not OK")
            for l in res['caches'].splitlines():
                if l.startswith('Group'): continue
                if l.find('Status: Ok') < 0:
                    errors.add(CRITICAL, l)

        if args.check in ('stats', 'all'):
            # For each cache, check that we're receiving stats
            res = req.make("/api/v1/cache/").json()
            for cache in res['caches']:
                id = cache['id']
                name = cache['name']

                res = req.make('/api/v1/cache/{0}/stats/client_req/1/10/last'.format(id)).json()
                # VAC seems quite broken - sometimes it returns NaN for a time
                # entry even when there is one,
                has_number = False
                for k in res['values']:
                    has_number = False
                    try:
                        v = float(k['value'])
                        if not math.isnan(v):
                            has_number=True
                    except ValueError:
                        pass
                if not has_number:
                    errors.add(WARNING, "Cache {0} is not receiving stats".format(name))
    except requests.exceptions.ConnectionError:
        errors.add(CRITICAL, "API connection failed")
    except:
        raise

    errors.print_and_exit()
