%{!?python_sitelib: %define python_sitelib %(%{__python} -c "from distutils.sysconfig import get_python_lib; print get_python_lib()")}

Name:           supybot-fedora
Version:        0.2.3
Release:        2%{?dist}
Summary:        Plugin for Supybot to interact with Fedora services

Group:          Applications/Internet
License:        BSD
URL:            https://fedorahosted.org/supybot-fedora
Source0:        https://fedorahosted.org/releases/s/u/%{name}/%{name}-%{version}.tar.bz2
BuildRoot:      %{_tmppath}/%{name}-%{version}-%{release}-root-%(%{__id_u} -n)

Requires:       python-fedora >= 0.3.7, supybot

BuildArch:      noarch
BuildRequires:  python

%description
A Supybot plugin which provides access to Fedora information. Implements a
variety of commands, such as:

 * fas
 * fasinfo
 * ext
 * bug
 * whoowns

These provide various information from the Fedora Package Database and
Account System and provide it via IRC


%prep
%setup -q


%build


%install
rm -rf $RPM_BUILD_ROOT
install -dm 755 $RPM_BUILD_ROOT/%{python_sitelib}/supybot/plugins/Fedora
install -pm 644 *.py $RPM_BUILD_ROOT/%{python_sitelib}/supybot/plugins/Fedora


%clean
rm -rf $RPM_BUILD_ROOT


%files
%defattr(-,root,root,-)
%doc README.txt TODO.txt
%{python_sitelib}/supybot/plugins/Fedora


%changelog
* Wed Feb 25 2009 Fedora Release Engineering <rel-eng@lists.fedoraproject.org> - 0.2.3-2
- Rebuilt for https://fedoraproject.org/wiki/Fedora_11_Mass_Rebuild

* Sun Jan 25 2009 Jon Stanley <jonstanley@gmail.com> - 0.2.3-1
- New upstream 0.2.3

* Sun Jan 11 2009 Jon Stanley <jonstanley@gmail.com> - 0.2.2-1
- New upstream 0.2.2

* Sun Jan 4 2009 Jon Stanley <jonstanley@gmail.com> - 0.2.1-1
- New upstream 0.2.1

* Sun Dec 7 2008 Jon Stanley <jonstanley@gmail.com> - 0.2-4
- Fix license tag per review

* Fri Dec 5 2008 Jon Stanley <jonstanley@gmail.com> - 0.2-3
- More review fixups

* Thu Dec 4 2008 Jon Stanley <jonstanley@gmail.com> - 0.2-2
- Fixup from package review

* Thu Dec 4 2008 Jon Stanley <jonstanley@gmail.com> - 0.2-1
- Initial package
