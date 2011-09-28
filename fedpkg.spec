# sitelib for noarch packages, sitearch for others (remove the unneeded one)
%{!?python_sitelib: %global python_sitelib %(%{__python} -c "from distutils.sysconfig import get_python_lib; print(get_python_lib())")}

Name:           fedpkg
Version:        1.1
Release:        1%{?dist}
Summary:        Fedora utility for working with dist-git

Group:          Applications/System
License:        GPLv2+
URL:            http://fedorahosted.org/fedpkg
Source0:        http://fedorahosted.org/releases/f/e/fedpkg/fedpkg-%{version}.tar.bz2
BuildRoot:      %{_tmppath}/%{name}-%{version}-%{release}-root-%(%{__id_u} -n)

Requires:       pyrpkg, redhat-rpm-config
Requires:       python-pycurl, koji, python-fedora
Requires:       fedora-cert, python-offtrac, bodhi-client
%if 0%{?rhel} == 5 || 0%{?rhel} == 4
Requires:       python-kitchen
%endif

BuildArch:      noarch
BuildRequires:  python-devel, python-setuptools, python-offtrac
# We br these things for man page generation due to imports
BuildRequires:  pyrpkg


%description
Provides the fedpkg command for working with dist-git


%prep
%setup -q


%build
%{__python} setup.py build
%{__python} src/fedpkg_man_page.py > fedpkg.1


%install
#rm -rf $RPM_BUILD_ROOT
%{__python} setup.py install -O1 --skip-build --root $RPM_BUILD_ROOT
%{__install} -d $RPM_BUILD_ROOT%{_mandir}/man1
%{__install} -p -m 0644 fedpkg.1 $RPM_BUILD_ROOT%{_mandir}/man1

 
%clean
rm -rf $RPM_BUILD_ROOT


%files
%defattr(-,root,root,-)
%doc COPYING README
%config(noreplace) %{_sysconfdir}/rpkg
%config(noreplace) %{_sysconfdir}/koji-rhel.conf
%{_sysconfdir}/bash_completion.d
%{_bindir}/%{name}
%{_mandir}/*/*
# For noarch packages: sitelib
%{python_sitelib}/*


%changelog
* Fri Oct 28 2011 Jesse Keating <jkeating@redhat.com> - 1.1-1
- Overload curl stuff (jkeating)                                                
- Hardcode fedpkg version requires (jkeating)                                   
- Fix up changelog date (jkeating)   