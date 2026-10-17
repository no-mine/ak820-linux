Name:           ak820-linux
Version:        0.1.0
Release:        1%{?dist}
Summary:        Configuration tool for the AJAZZ AK820 Pro keyboard
License:        MIT
URL:            https://github.com/no-mine/ak820-linux
Source0:        %{name}-%{version}.tar.gz
BuildArch:      noarch

BuildRequires:  python3-devel
BuildRequires:  pyproject-rpm-macros
BuildRequires:  python3-pillow
BuildRequires:  desktop-file-utils
BuildRequires:  systemd-rpm-macros
Requires:       python3-pillow
Requires:       python3-gobject
Requires:       gtk4
Requires:       libadwaita >= 1.5
Requires:       systemd-udev

%description
Command line and native GNOME (GTK 4 / libadwaita) app for the AJAZZ AK820 Pro keyboard (wired USB mode): lighting
effects, screen animation upload and clock sync. The protocol was
reverse engineered from the vendor's Windows driver. Includes a udev rule so the logged-in
desktop user can talk to the keyboard without root.

%prep
%autosetup -n %{name}-%{version}

%generate_buildrequires
%pyproject_buildrequires

%build
%pyproject_wheel

%install
%pyproject_install
%pyproject_save_files ak820
install -Dpm 0644 packaging/70-ak820.rules %{buildroot}%{_udevrulesdir}/70-ak820.rules
install -Dpm 0644 packaging/org.ak820linux.Configurator.desktop %{buildroot}%{_datadir}/applications/org.ak820linux.Configurator.desktop
install -Dpm 0644 packaging/org.ak820linux.Configurator.svg %{buildroot}%{_datadir}/icons/hicolor/scalable/apps/org.ak820linux.Configurator.svg

%check
desktop-file-validate %{buildroot}%{_datadir}/applications/org.ak820linux.Configurator.desktop
%{python3} -m unittest discover -s tests -v

%files -f %{pyproject_files}
%license LICENSE
%doc README.md
%{_bindir}/ak820
%{_udevrulesdir}/70-ak820.rules
%{_datadir}/applications/org.ak820linux.Configurator.desktop
%{_datadir}/icons/hicolor/scalable/apps/org.ak820linux.Configurator.svg

%changelog
* Sat Oct 17 2026 no-mine <233317302+no-mine@users.noreply.github.com> - 0.1.0-1
- Initial package
