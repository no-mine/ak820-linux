#!/bin/bash
# Runs INSIDE the Debian/Ubuntu container: copies the tree, adds debian/, builds the .deb, copies it to /out.
set -euo pipefail
cd /src
source packaging/common.sh
check_versions

work=$(mktemp -d)
src="$work/${name}-${version}"
export_tree "$src"
cp -a packaging/debian "$src/debian"
chmod +x "$src/debian/rules"
(cd "$src" && dpkg-buildpackage -us -uc -b)

mkdir -p /out
cp "$work"/*.deb /out/
echo
lintian --no-tag-display-limit "$work"/*.changes || true      # advisory only
echo
ls -l /out
