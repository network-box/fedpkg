#!/usr/bin/python
# fedpkg - a script to interact with the Fedora Packaging system
#
# Copyright (C) 2011 Red Hat Inc.
# Author(s): Jesse Keating <jkeating@redhat.com>
#
# This program is free software; you can redistribute it and/or modify it
# under the terms of the GNU General Public License as published by the
# Free Software Foundation; either version 2 of the License, or (at your
# option) any later version.  See http://www.gnu.org/copyleft/gpl.html for
# the full text of the license.

import os
import sys
import logging
import ConfigParser
import argparse

import pyrpkg
import fedpkg


def main():
    # Setup an argparser and parse the known commands to get the config file
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument('-C', '--config', help='Specify a config file to use',
                        default='/etc/rpkg/fedpkg.conf')

    (args, other) = parser.parse_known_args()

    # Make sure we have a sane config file
    if not os.path.exists(args.config) and not other[-1] in ['--help', '-h', 'help']:
        sys.stderr.write('Invalid config file %s\n' % args.config)
        sys.exit(1)

    # Setup a configuration object and read config file data
    config = ConfigParser.SafeConfigParser()
    config.read(args.config)

    client = fedpkg.cli.fedpkgClient(config)
    client.do_imports(site='fedpkg')
    client.parse_cmdline()

    if not client.args.path:
        try:
            client.args.path=os.getcwd()
        except:
            print('Could not get current path, have you deleted it?')
            sys.exit(1)

    # setup the logger -- This logger will take things of INFO or DEBUG and
    # log it to stdout.  Anything above that (WARN, ERROR, CRITICAL) will go
    # to stderr.  Normal operation will show anything INFO and above.
    # Quiet hides INFO, while Verbose exposes DEBUG.  In all cases WARN or
    # higher are exposed (via stderr).
    log = pyrpkg.log
    client.setupLogging(log)

    if client.args.v:
        log.setLevel(logging.DEBUG)
    elif client.args.q:
        log.setLevel(logging.WARNING)
    else:
        log.setLevel(logging.INFO)

    # Run the necessary command
    try:
        sys.exit(client.args.command())
    except KeyboardInterrupt:
        pass
    except Exception, e:
        log.error('Could not execute %s: %s' % (client.args.command.__name__, e))
        sys.exit(1)

if __name__ == "__main__":
    main()
