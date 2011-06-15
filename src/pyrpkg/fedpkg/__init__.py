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

# This check (decorator) can go away after a few months
def _check_newstyle_branches(func):
    """Check to see if the branches are "newstyle" or not.

    Will raise and log an error leading the user to fix branches.
    """

    def checky(self, *args, **kwargs):
        # First only work on the remotes we care about
        fedpkg = 'pkgs.*\.fedoraproject\.org\/'
        remotes = [remote.name for remote in self.repo.remotes if
                   re.search(fedpkg, remote.url)]

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
                if type(ref) == git.refs.RemoteReference and \
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
                 gitbaseurl, anongiturl, branchre, kojiconfig,
                 build_client, user=None, dist=None, target=None):
        """Init the object and some configuration details."""

        # We are subclassing to set kojiconfig to none, so that we can
        # make it a property to potentially use a secondary config
        pyrpkg.Commands.__init__(self, path, lookaside, lookasidehash,
                                 lookaside_cgi, gitbaseurl, anongiturl,
                                 branchre, kojiconfig, build_client, user,
                                 dist, target)

        # New data
        self.secondary_arch = {'sparc': ['silo', 'prtconf', 'lssbus', 'afbinit',
                                         'piggyback', 'xorg-x11-drv-sunbw2',
                                         'xorg-x11-drv-suncg14',
                                         'xorg-x11-drv-suncg3',
                                         'xorg-x11-drv-suncg6',
                                         'xorg-x11-drv-sunffb',
                                         'xorg-x11-drv-sunleo',
                                         'xorg-x11-drv-suntcx'],
                               'ppc': ['ppc64-utils', 'yaboot'],
                               'arm': ['xorg-x11-drv-omapfb'],
                               's390': ['s390utils', 'openssl-ibmca', 'libica']}

        # New properties
        del(self.kojiconfig)
        self._kojiconfig = None
        # Store this for later
        self._orig_kojiconfig = kojiconfig

    # Add new properties
    @property
    def kojiconfig(self):
        """This property ensures the kojiconfig attribute"""

        if not self._kojiconfig:
            self.load_kojiconfig()
        return self._kojiconfig

    def load_kojiconfig(self):
        """This loads the kojiconfig attribute

        This will either use the one passed in via arguments or a
        secondary arch config depending on the package
        """

        for arch in self.secondary_arch.keys():
            if self.module_name in self.secondary_arch[arch]:
                self._kojiconfig = os.path.expanduser('~/.koji/%s-config' %
                                                      arch)
                return
        self._kojiconfig = self._orig_kojiconfig

    # Overloaded property loaders
    def load_rpmdefines(self):
        """Populate rpmdefines based on branch data"""

        if self.branch_merge.startswith('f'):
            self.distval = self.branch_merge.split('f')[1]
            self.distvar = 'fedora'
            self.dist = 'fc%s' % self.distval
            self.mockconfig = 'fedora-%s-%s' % (self.distval, self.localarch)
            self.override = 'dist-f%s-override' % self.distval
        elif self.branch_merge.startswith('el'):
            self.distval = self.branch_merge.split('el')[1]
            self.distvar = 'rhel'
            self.dist = 'el%s' % self.distval
            self.mockconfig = 'epel-%s-%s' % (self.distval, self.localarch)
            self.override = 'dist-%sE-epel-override' % self.distval
        elif self.branch_merge.startswith('olpc'):
            self.distval = self.branch_merge.split('olpc')[1]
            self.distvar = 'olpc'
            self.dist = 'olpc%s' % self.distval
            self.override = 'dist-olpc%s-override' % self.distval
        # If we don't match one of the above, assume master or a branch of
        # master
        else:
            self.distval = self._findmasterbranch()
            self.distvar = 'fedora'
            self.distshort = 'fc%s' % self.distval
            self.dist = 'fc%s' % self.distval
            self.target = 'dist-rawhide'
            self.mockconfig = 'fedora-devel-%s' % self.localarch
            self.override = None
        self._rpmdefines = ["--define '_sourcedir %s'" % self.path,
                            "--define '_specdir %s'" % self.path,
                            "--define '_builddir %s'" % self.path,
                            "--define '_srcrpmdir %s'" % self.path,
                            "--define '_rpmdir %s'" % self.path,
                            "--define 'dist .%s'" % self.dist,
                            "--define '%s %s'" % (self.distvar, self.distval),
                            "--define '%s 1'" % self.dist]

    def load_target(self):
        """This creates the target attribute based on branch merge"""

        if self.branch_merge == 'master':
            branch_merge = self._findmasterbranch()
            self._target = 'f%s-candidate' % branch_merge
        else:
            self._target = '%s-candidate' % self.branch_merge

    # Other overloaded functions
    # These are overloaded to throw in the check for newstyle branches
    @_check_newstyle_branches
    def import_srpm(self):
        pyrpkg.Commands.import_srpm(self)

    @_check_newstyle_branches
    def pull(self, rebase=False, norebase=False):
        pyrpkg.Commands.pull(self, rebase, norebase)

    @_check_newstyle_branches
    def push(self):
        pyrpkg.Commands.push(self)

    @_check_newstyle_branches
    def build(self, *args, **kwargs):
        pyrpkg.Commands.build(self, *args, **kwargs)

    # New functionality
    def _findmasterbranch(self):
        """Find the right "fedora" for master"""

        # Create a list of "fedoras"
        fedoras = []

        # Create a regex to find branches that exactly match f##.  Should not
        # catch branches such as f14-foobar
        branchre = 'f\d\d$'

        # Find the repo refs
        for ref in self.repo.refs:
            # Only find the remote refs
            if type(ref) == git.refs.RemoteReference:
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
                                                              'dist-rawhide')
            except:
                # We couldn't hit koji, bail.                                   
                raise pyrpkg.rpkgError('Unable to query koji to find rawhide \
                                       target')
            desttag = rawhidetarget['dest_tag_name']
            return desttag.replace('dist-f', '')

    def mockbuild(self, mockargs=[]):
        """Build the package in mock, using mockargs

        Log the output and returns nothing

        """

        # Make sure we have an srpm to run on
        self.srpm()

        # setup the command
        cmd = ['mock']
        cmd.extend(mockargs)
        cmd.extend(['-r', self.mockconfig, '--resultdir',
                    os.path.join(self.path, self.module_name, self.ver, self.rel),
                    '--rebuild', self.srpmname])
        # Run the command
        self._run_command(cmd)
        return

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

        cmd = ['git', 'rm', '-rf', '.']
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
