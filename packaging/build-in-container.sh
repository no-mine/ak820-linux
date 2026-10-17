#!/bin/bash
# Runs INSIDE the Fedora container: tars the source, runs rpmbuild, copies the results to /out.
set -euo pipefail
cd /src
source packaging/common.sh
check_versions

top=$(mktemp -d)
mkdir -p "$top"/{SOURCES,SPECS,BUILD,RPMS,SRPMS,BUILDROOT}
make_tarball "$top/SOURCES/${name}-${version}.tar.gz"
cp packaging/ak820-linux.spec "$top/SPECS/"

rpmbuild --define "_topdir $top" -ba "$top/SPECS/ak820-linux.spec"

mkdir -p /out
cp "$top"/RPMS/*/*.rpm "$top"/SRPMS/*.rpm /out/
echo
rpmlint /out/*.rpm || true          # advisory only
echo
ls -l /out
