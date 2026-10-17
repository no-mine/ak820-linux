#!/bin/bash
# Sourced by the in-container build scripts. Run from the source root (/src in the containers).
name=ak820-linux
version=$(sed -n 's/^version = "\(.*\)"/\1/p' pyproject.toml)

# All packaging formats must carry the same version as pyproject.toml.
check_versions() {
    local label value bad=0
    while IFS='|' read -r label value; do
        if [ "$value" != "$version" ]; then
            echo "version mismatch: $label=$value, pyproject.toml=$version" >&2
            bad=1
        fi
    done <<EOF
ak820/__init__.py|$(sed -n "s/^__version__ = '\(.*\)'/\1/p" ak820/__init__.py)
rpm spec|$(sed -n 's/^Version:[[:space:]]*//p' packaging/ak820-linux.spec)
PKGBUILD|$(sed -n 's/^pkgver=//p' packaging/arch/PKGBUILD)
debian/changelog|$(sed -n '1s/^[^(]*(\([^)]*\)).*/\1/p' packaging/debian/changelog)
EOF
    return $bad
}

_tar_excludes=(--exclude=dist --exclude=__pycache__ '--exclude=*.pyc' --exclude=.git --exclude=build '--exclude=*.egg-info')

# export_tree DIR: copy the source tree to DIR without build leftovers.
export_tree() {
    mkdir -p "$1"
    tar "${_tar_excludes[@]}" -cf - . | tar -xf - -C "$1"
}

# make_tarball FILE: source tarball with a ${name}-${version}/ top directory.
make_tarball() {
    tar "${_tar_excludes[@]}" --transform "s,^\.,${name}-${version}," -czf "$1" .
}
