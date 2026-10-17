#!/bin/bash
# Runs INSIDE the Arch container: makepkg refuses to run as root, so build as the 'builder' user.
set -euo pipefail
cd /src
source packaging/common.sh
check_versions

build=/home/builder/build
mkdir -p "$build"
make_tarball "$build/${name}-${version}.tar.gz"
cp packaging/arch/PKGBUILD "$build/"
chown -R builder:builder /home/builder
su builder -c "cd $build && makepkg -f --noconfirm"

mkdir -p /out
cp "$build"/*.pkg.tar.zst /out/
echo
namcap /out/*.pkg.tar.zst || true      # advisory only
echo
ls -l /out
