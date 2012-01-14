from setuptools import setup

setup(
    name = "fedpkg",
    version = "1.7",
    author = "Jesse Keating",
    author_email = "jkeating@redhat.com",
    description = ("Red Hat plugin to rpkg to manage "
                   "package sources in a git repository"),
    license = "GPLv2+",
    url = "http://fedorahosted.org/fedpkg",
    package_dir = {'': 'src'},
    packages = ['pyrpkg.fedpkg'],
    scripts = ['src/fedpkg'],
    data_files = [('/etc/bash_completion.d', ['src/fedpkg.bash']),
                  ('/etc/rpkg', ['src/fedpkg.conf']),
                  ('/usr/libexec/', ['src/fedpkg-fixbranches.py']),
                 ]
)
