# Package builds run inside containers (podman); no build tools needed on the host.
#   make rpm                      Fedora RPM            (make rpm FEDORA=43 for another release)
#   make deb                      Debian/Ubuntu .deb    (make deb BASE=ubuntu:24.04, default debian:13)
#   make arch                     Arch Linux package
#   make test                     unit tests (no hardware needed)

PODMAN ?= podman
FEDORA ?= 44
BASE   ?= docker.io/library/debian:13

# Unqualified image names (ubuntu:24.04) live on Docker Hub; podman would otherwise ask which registry to use.
DEB_BASE := $(if $(findstring /,$(BASE)),$(BASE),docker.io/library/$(BASE))
DEB_TAG  := $(subst :,-,$(notdir $(DEB_BASE)))

PYTHON ?= python3

.DEFAULT_GOAL := help
.PHONY: help test rpm deb arch packages clean

help:
	@sed -n "s/^#   //p" $(MAKEFILE_LIST) | head -5

test:
	$(PYTHON) -m unittest discover -s tests

rpm:
	mkdir -p dist/rpm
	$(PODMAN) build --build-arg FEDORA=$(FEDORA) -t ak820-rpm-build:f$(FEDORA) -f packaging/Containerfile.rpm .
	$(PODMAN) run --rm -v "$(CURDIR)/dist/rpm:/out:Z" ak820-rpm-build:f$(FEDORA)
	@echo; echo "Install with:  sudo dnf install ./dist/rpm/ak820-linux-*.noarch.rpm"

deb:
	mkdir -p dist/deb/$(DEB_TAG)
	$(PODMAN) build --build-arg BASE=$(DEB_BASE) -t ak820-deb-build:$(DEB_TAG) -f packaging/Containerfile.deb .
	$(PODMAN) run --rm -v "$(CURDIR)/dist/deb/$(DEB_TAG):/out:Z" ak820-deb-build:$(DEB_TAG)
	@echo; echo "Install with:  sudo apt install ./dist/deb/$(DEB_TAG)/ak820-linux_*_all.deb"

arch:
	mkdir -p dist/arch
	$(PODMAN) build -t ak820-arch-build -f packaging/Containerfile.arch .
	$(PODMAN) run --rm -v "$(CURDIR)/dist/arch:/out:Z" ak820-arch-build
	@echo; echo "Install with:  sudo pacman -U dist/arch/ak820-linux-*.pkg.tar.zst"

packages: rpm deb arch

clean:
	rm -rf dist build *.egg-info
