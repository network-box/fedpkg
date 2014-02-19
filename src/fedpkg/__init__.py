# fedpkg - a Python library for RPM Packagers
#
# Copyright (C) 2011 Red Hat Inc.
# Author(s): Jesse Keating <jkeating@redhat.com>
#
# This program is free software; you can redistribute it and/or modify it
# under the terms of the GNU General Public License as published by the
# Free Software Foundation; either version 2 of the License, or (at your
# option) any later version.  See http://www.gnu.org/copyleft/gpl.html for
# the full text of the license.

import pyrpkg
import os
import cli
import offtrac
import git
import re
import pycurl
import fedora_cert
import platform

# This check (decorator) can go away after a few months
def _check_newstyle_branches(func):
    """Check to see if the branches are "newstyle" or not.

    Will raise and log an error leading the user to fix branches.
    """

    def checky(self, *args, **kwargs):
        # First only work on the remotes we care about
        fedpkg = 'pkgs.*\.fedoraproject\.org\/'
        # Do this in a try in case we're not in a repo
        try:
            remotes = [remote.name for remote in self.repo.remotes if
                       re.search(fedpkg, remote.url)]
        except:
            self.log.debug("Not in a repo, don't care about remotes")
            return func(self, *args, **kwargs)

        # Now loop through the remotes and see if any of them have
        # old style branch names
        for remote in remotes:
            # Check to see if the remote data matches the old style
            # This regex looks at the ref name which should be
            # "origin/f15/master or simliar.  This regex fills in the remote
            # name we care about and attempts to find any fedora/epel/olpc
            # branch that has the old style /master tail.
            refsre = r'%s/(f\d\d/master|f\d/master|fc\d/master|' % remote
            refsre += r'el\d/master|olpc\d/master)'
            for ref in self.repo.refs:
                if type(ref) == git.RemoteReference and \
                re.match(refsre, ref.name):
                    self.log.error('This repo has old style branches but '
                                   'upstream has converted to new style.\n'
                                   'Please run /usr/libexec/fedpkg-fixbranches '
                                   'to fix your repo.')
                    raise pyrpkg.rpkgError('Unconverted branches')
        return func(self, *args, **kwargs)
    return(checky)

class Commands(pyrpkg.Commands):

    def __init__(self, path, lookaside, lookasidehash, lookaside_cgi,
                 gitbaseurl, anongiturl, branchre, remote, kojiconfig,
                 build_client, user=None, dist=None, target=None,
                 quiet=False):
        """Init the object and some configuration details."""

        # We are subclassing to set kojiconfig to none, so that we can
        # make it a property to potentially use a secondary config
        super(Commands, self).__init__(path, lookaside, lookasidehash,
                                 lookaside_cgi, gitbaseurl, anongiturl,
                                 branchre, remote, kojiconfig, build_client,
                                 user, dist, target, quiet)

        # New data
        self.secondary_arch = {
            'ppc': [
                'apmud',
                'libbsr',
                'librtas',
                'libservicelog',
                'libvpd',
                'lsvpd',
                'powerpc-utils',
                'powerpc-utils-papr',
                'ppc64-utils',
                'yaboot',
            ], 'arm': ['xorg-x11-drv-omapfb'],
               's390': ['s390utils', 'openssl-ibmca', 'libica']
        }

        # New properties
        self._kojiconfig = None
        self._cert_file = None
        self._ca_cert = None
        # Store this for later
        self._orig_kojiconfig = kojiconfig

    # Add new properties
    @property
    def kojiconfig(self):
        """This property ensures the kojiconfig attribute"""

        if not self._kojiconfig:
            self.load_kojiconfig()
        return self._kojiconfig

    @kojiconfig.setter
    def kojiconfig(self, value):
        self._kojiconfig = value

    def load_kojiconfig(self):
        """This loads the kojiconfig attribute

        This will either use the one passed in via arguments or a
        secondary arch config depending on the package
        """

        # We have to allow this to work, even if we don't have a package
        # we're working on, for things like gitbuildhash.
        try:
            null = self.module_name
        except:
            self._kojiconfig = self._orig_kojiconfig
            return
        for arch in self.secondary_arch.keys():
            if self.module_name in self.secondary_arch[arch]:
                self._kojiconfig = os.path.expanduser('/etc/koji/%s-config' %
                                                      arch)
                return
        self._kojiconfig = self._orig_kojiconfig

    @property
    def cert_file(self):
        """This property ensures the cert_file attribute"""

        if not self._cert_file:
            self.load_cert_files()
        return self._cert_file

    @property
    def ca_cert(self):
        """This property ensures the ca_cert attribute"""

        if not self._ca_cert:
            self.load_cert_files()
        return self._ca_cert

    def load_cert_files(self):
        """This loads the cert_file attribute"""

        self._cert_file = os.path.expanduser('~/.fedora.cert')
        self._ca_cert = os.path.expanduser('~/.fedora-server-ca.cert')

    # Overloaded property loaders
    @_check_newstyle_branches
    def load_rpmdefines(self):
        """Populate rpmdefines based on branch data"""

        # Determine runtime environment
        self._runtime_disttag = self._determine_runtime_env()

        # We only match the top level branch name exactly.
        # Anything else is too dangerous and --dist should be used
        # This regex works until after Fedora 99.
        if re.match(r'f\d\d$', self.branch_merge):
            self._distval = self.branch_merge.split('f')[1]
            self._distvar = 'fedora'
            self.dist = 'fc%s' % self._distval
            self.mockconfig = 'fedora-%s-%s' % (self._distval, self.localarch)
            self.override = 'f%s-override' % self._distval
            self._distunset = 'rhel'
        # Works until RHEL 10
        elif re.match(r'el\d$', self.branch_merge) or re.match(r'epel\d$', self.branch_merge):
            self._distval = self.branch_merge.split('el')[1]
            self._distvar = 'rhel'
            self.dist = 'el%s' % self._distval
            self.mockconfig = 'epel-%s-%s' % (self._distval, self.localarch)
            self.override = 'epel%s-override' % self._distval
            self._distunset = 'fedora'
        elif re.match(r'olpc\d$', self.branch_merge):
            self._distval = self.branch_merge.split('olpc')[1]
            self._distvar = 'olpc'
            self.dist = 'olpc%s' % self._distval
            self.override = 'dist-olpc%s-override' % self._distval
            self._distunset = 'rhel'
        # master
        elif re.match(r'master$', self.branch_merge):
            self._distval = self._findmasterbranch()
            self._distvar = 'fedora'
            self.dist = 'fc%s' % self._distval
            self.mockconfig = 'fedora-devel-%s' % self.localarch
            self.override = None
            self._distunset = 'rhel'
        # If we don't match one of the above, punt
        else:
            raise pyrpkg.rpkgError('Could not find the dist from branch name '
                                   '%s\nPlease specify with --dist' %
                                   self.branch_merge)
        self._rpmdefines = ["--define '_sourcedir %s'" % self.path,
                            "--define '_specdir %s'" % self.path,
                            "--define '_builddir %s'" % self.path,
                            "--define '_srcrpmdir %s'" % self.path,
                            "--define '_rpmdir %s'" % self.path,
                            "--define 'dist .%s'" % self.dist,
                            "--define '%s %s'" % (self._distvar, self._distval),
                            "--eval '%%undefine %s'" % self._distunset,
                            "--define '%s 1'" % self.dist]
        if self._runtime_disttag:
            if self.dist != self._runtime_disttag:
                # This means that the runtime is known, and is different from
                # the target, so we need to unset the _runtime_disttag
                self._rpmdefines.append("--eval '%%undefine %s'" %
                                        self._runtime_disttag)

    def load_target(self):
        """This creates the target attribute based on branch merge"""

        if self.branch_merge == 'master':
            self._target = 'rawhide'
        else:
            self._target = '%s-candidate' % self.branch_merge

    def load_user(self):
        """This sets the user attribute, based on the Fedora SSL cert."""
        try:
            self._user = fedora_cert.read_user_cert()
        except Exception, e:
            self.log.debug('Could not read Fedora cert, falling back to '
                           'default method: %s' % e)
            super(Commands, self).load_user()

    # Other overloaded functions
    # These are overloaded to throw in the check for newstyle branches
    @_check_newstyle_branches
    def import_srpm(self, *args):
        return super(Commands, self).import_srpm(*args)

    @_check_newstyle_branches
    def pull(self, *args, **kwargs):
        super(Commands, self).pull(*args, **kwargs)

    @_check_newstyle_branches
    def push(self):
        super(Commands, self).push()

    @_check_newstyle_branches
    def build(self, *args, **kwargs):
        return(super(Commands, self).build(*args, **kwargs))

    # New functionality
    def _create_curl(self):
        """Common curl setup options used for all requests to lookaside."""

        # Overloaded to add cert files to curl objects
        # Call the super class
        curl = super(Commands, self)._create_curl()

        # Set the users Fedora certificate:
        if os.path.exists(self.cert_file):
            curl.setopt(pycurl.SSLCERT, self.cert_file)
        else:
            self.log.warn("Missing certificate: %s" % self.cert_file)

        # Set the Fedora CA certificate:
        if os.path.exists(self.ca_cert):
            curl.setopt(pycurl.CAINFO, self.ca_cert)
        else:
            self.log.warn("Missing certificate: %s" % self.ca_cert)

        return curl

    def _do_curl(self, file_hash, file):
        """Use curl manually to upload a file"""

        # This is overloaded to add in the fedora user's cert
        cmd = ['curl', '-k', '--cert', self.cert_file, '--fail', '-o',
               '/dev/null', '--show-error', '--progress-bar', '-F',
               'name=%s' % self.module_name, '-F', 'md5sum=%s' % file_hash,
               '-F', 'file=@%s' % file]
        if self.quiet:
            cmd.append('-s')
        cmd.append(self.lookaside_cgi)
        self._run_command(cmd)

    def _findmasterbranch(self):
        """Find the right "fedora" for master"""

        # If we already have a koji session, just get data from the source
        if self._kojisession:
            rawhidetarget = self.kojisession.getBuildTarget('rawhide')
            desttag = rawhidetarget['dest_tag_name']
            return desttag.replace('f', '')

        # Create a list of "fedoras"
        fedoras = []

        # Create a regex to find branches that exactly match f##.  Should not
        # catch branches such as f14-foobar
        branchre = 'f\d\d$'

        # Find the repo refs
        for ref in self.repo.refs:
            # Only find the remote refs
            if type(ref) == git.RemoteReference:
                # Search for branch name by splitting off the remote
                # part of the ref name and returning the rest.  This may
                # fail if somebody names a remote with / in the name...
                if re.match(branchre, ref.name.split('/', 1)[1]):
                    # Add just the simple f## part to the list
                    fedoras.append(ref.name.split('/')[1])
        if fedoras:
            # Sort the list
            fedoras.sort()
            # Start with the last item, strip the f, add 1, return it.
            return(int(fedoras[-1].strip('f')) + 1)
        else:
            # We may not have Fedoras.  Find out what rawhide target does.
            try:
                rawhidetarget = self.anon_kojisession.getBuildTarget(
                                                              'rawhide')
            except:
                # We couldn't hit koji, bail.
                raise pyrpkg.rpkgError('Unable to query koji to find rawhide \
                                       target')
            desttag = rawhidetarget['dest_tag_name']
            return desttag.replace('f', '')

    def _determine_runtime_env(self):
        """Need to know what the runtime env is, so we can unset anything
           conflicting
        """

        try:
           mydist = platform.linux_distribution()
        except:
           # This is marked as eventually being deprecated.
           try:
              mydist = platform.dist()
           except:
              runtime_os = 'unknown'
              runtime_version = '0'

        if mydist:
           runtime_os = mydist[0]
           runtime_version = mydist[1]
        else:
           runtime_os = 'unknown'
           runtime_version = '0'

        if runtime_os in ['redhat', 'centos']:
            return 'el%s' % runtime_version
        if runtime_os == 'Fedora':
            return 'fc%s' % runtime_version

        # fall through, return None
        return None

    def new_ticket(self, passwd, desc, build=None):
        """Open a new ticket on Rel-Eng trac instance.

        Get ticket component and assignee from current branch

        Create a new task ticket using username/password/desc

        Discover build nvr from module or optional build argument

        Return ticket number on success
        """

        override = self.override
        if not override:
            raise pyrpkg.rpkgError('Override tag is not required for %s' %
                                   self.branch_merge)

        uri = self.tracbaseurl % {'user': self.user, 'password': passwd}
        self.trac = offtrac.TracServer(uri)

        # Set trac's component and assignee from related distvar
        if self.distvar == 'fedora':
            component = 'koji'
            #owner = 'rel-eng@lists.fedoraproject.org'
        elif self.distvar == 'rhel':
            component = 'epel'
            #owner = 'releng-epel@lists.fedoraproject.org'

        # Raise if people request a tag against something that self updates
        build_target = self.anon_kojisession.getBuildTarget(self.target)
        if not build_target:
            raise pyrpkg.rpkgError('Unknown build target: %s' % self.target)
        dest_tag = self.anon_kojisession.getTag(build_target['dest_tag_name'])
        ancestors = self.anon_kojisession.getFullInheritance(
                                                    build_target['build_tag'])
        if dest_tag['id'] in [build_target['build_tag']] + \
                                  [ancestor['parent_id'] for
                                   ancestor in ancestors]:
            raise pyrpkg.rpkgError('Override tag is not required for %s' %
                                   self.branch_merge)

        if not build:
            build = self.nvr

        summary = 'Tag request %s for %s' % (build, override)
        type = 'task'
        try:
            ticket = self.trac.create_ticket(summary, desc,
                                             component=component,
                                             notify=True)
        except Exception, e:
            raise pyrpkg.rpkgError('Could not request tag %s: %s' % (build, e))

        self.log.debug('Task %s created' % ticket)
        return ticket

    def retire(self, message=None):
        """Delete all tracked files and commit a new dead.package file

        Use optional message in commit.

        Runs the commands and returns nothing
        """


        cmd = ['git']
        if self.quiet:
            cmd.append('--quiet')
        cmd.extend(['rm', '-rf', '.'])
        self._run_command(cmd, cwd=self.path)

        if not message:
            message = 'Package is retired'

        fd = open(os.path.join(self.path, 'dead.package'), 'w')
        fd.write(message + '\n')
        fd.close()

        cmd = ['git', 'add', os.path.join(self.path, 'dead.package')]
        self._run_command(cmd, cwd=self.path)

        self.commit(message=message)


    def update(self, template='bodhi.template', bugs=[]):
        """Submit an update to bodhi using the provided template."""

        # build up the bodhi arguments
        cmd = ['bodhi', '--new', '--release', self.branch_merge,
               '--file', 'bodhi.template', self.nvr, '--username',
               self.user]
        self._run_command(cmd, shell=True)


if __name__ == "__main__":
    from fedpkg.__main__ import main
    main()
