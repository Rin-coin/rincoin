# contrib/release/Makefile — Rincoin Core multi-platform build & sign wrapper
#
# Per-host builds, via the upstream `depends` system:
#
#   make linux        # x86_64 Linux, CLI-only   -> rincoin-<VERSION>-x86_64-linux-gnu.tar.gz
#   make windows      # x86_64 Windows, CLI-only -> rincoin-<VERSION>-win64.zip
#   make aarch64      # ARM64 Linux, CLI-only    -> rincoin-<VERSION>-aarch64-linux-gnu.tar.gz
#   make linux-full   # same host WITH the Qt GUI; also windows-full / aarch64-full
#
# Matrices (serial — see .NOTPARALLEL):
#
#   make all-cli      # linux + windows + aarch64, all CLI-only      (dev / CI smoke)
#   make all-release  # linux-full + windows-full + aarch64          (SHIP MATRIX)
#   make all-full     # + the aarch64 Qt GUI — needs ARM64_GUI=1, NOT release-blessed
#
# Flows:
#
#   make release      # release-preflight (HEAD==TAG, clean tree) + artifacts-clean
#                     #   + dist + all-release + sign; sign itself runs check-matrix
#   make release-full # DEFERRED until release-process.md §10-6 passes on ARM64 hw
#   make dist         # source tarball via git archive -> rincoin-<VERSION>.tar.gz
#   make sign         # check-matrix, then SHA256SUMS + GPG detached-sign. The
#                     #   signed set is always the FULL artifact matrix; signing a
#                     #   source tarball alone is deliberately unsupported.
#   make check-matrix # assert the GUI/CLI shape of the built artifacts
#   make verify       # list artifacts + the §10-6 verification reminder
#   make clean        # remove staging (keeps the depends/ cache)
#   make distclean    # also wipe the three depends/<host> build dirs
#   make help         # this list (default goal)
#
# GUI POLICY LIVES IN THE TARGET NAME, NOT IN A FLAG:
#     bare name  ("linux")       = forced CLI-only, no rincoin-qt in the artifact
#     -full name ("linux-full")  = forced Qt GUI
# There is deliberately NO `GUI=` toggle. Two ways to say the same thing is how an
# unverified binary ends up under the release signature. Each engine target below
# has its Qt decision baked in at parse time, so no runtime variable can flip it.
#
# Every build is captured to a timestamped log under $(LOGDIR) (default ~/logs)
# and the wrapper exits with the build's real status (bash PIPESTATUS[0]), so a
# failed compile is never masked by `tee`.
#
# NOTE on `make -n`: flow targets (release, all-*) are built from recursive
# $(MAKE) lines, which GNU make EXECUTES even under -n — the sub-makes inherit
# -n so nothing destructive runs, but the flow is walked, not merely printed.
#
# Toggles (make VAR=value target):
#   JOBS=8            # parallel jobs INSIDE each build (default: nproc)
#   VERSION=1.1.0     # file version, no "v"   (default: parsed from configure.ac)
#   TAG=v1.1.0-rc1    # git tag / git-archive ref (default from configure.ac; RC uses -rcN)
#   KEY=<fpr>         # GPG signing key (default: the Core maintainer fingerprint below)
#   LOGDIR=<dir>      # where per-build logs are written (default: ~/logs)
#   ARM64_GUI=1       # unlock `aarch64-full` FOR TESTING ONLY (see the gate below)
#   EXTRA_CONFIG=...  # extra ./configure flags, e.g. --with-pic on R_X86_64_PC32,
#                     #   --without-miniupnpc, or --enable-tests to re-add the cross
#                     #   test binary for running under wine / qemu-user (§10-6).
#                     #   (--disable-tests is applied by default; release artifacts
#                     #   never ship test binaries. `make check` is unaffected -- it
#                     #   runs on the native Part I build, not this wrapper.)
#
# STATUS: cross-built binaries are EXPERIMENTAL for Rincoin. RinHash
# (BLAKE3 -> Argon2d -> SHA3-256) and BDB-4.8 cross-builds are NOT yet confirmed
# for win64/aarch64 — see release-process.md §10-6. This wrapper automates the
# *flow*; it does not by itself bless the output for release.

SHELL := /bin/bash

# `GUI=` was removed in favour of the target name. Reject it loudly rather than
# silently ignoring it — a maintainer typing `make release GUI=1` from muscle
# memory must not get a different artifact set than the one he thinks he asked for.
ifdef GUI
$(error GUI= is no longer a toggle (origin here: $(origin GUI)). The target name \
carries the policy: `make linux` = CLI-only, `make linux-full` = Qt GUI. If the \
origin above says "environment", unset the stray GUI env var. See the header)
endif

# Never build two targets concurrently in the same source tree (they share src/
# and we distclean between them). Each build still uses -jJOBS internally.
.NOTPARALLEL:

# Repo root = two levels up from this Makefile.
ROOT  := $(abspath $(dir $(lastword $(MAKEFILE_LIST)))../..)

JOBS  ?= $(shell nproc 2>/dev/null || echo 4)

# Qt GUI binary, as renamed in Makefile.qt.include (qt/litecoin-qt -> qt/rincoin-qt).
# check-matrix greps the packaged listing for this exact path.
QT_BIN := bin/rincoin-qt

# Test binaries. --disable-tests keeps both test_rincoin and test_rincoin-qt out
# of every artifact (configure.ac: use_gui_tests defaults to use_tests, and the
# qt-test build gates on use_gui_tests). The substring 'bin/test_rincoin' matches
# both names, so one grep asserts neither shipped. check-matrix treats any hit as
# fail-closed, so a future EXTRA_CONFIG=--enable-tests cannot quietly re-inflate
# the release by ~59 MB without tripping the signing gate.
TEST_BIN := bin/test_rincoin

# Version assembled from configure.ac (RIP-0001: GENERATION.MAJOR.MINOR + RC).
# Parsed with paren-free greps: a literal ')' inside a $(shell ...) would close
# the make function early, so we avoid awk field classes / sed capture groups.
V_MAJ := $(shell grep -o '_CLIENT_VERSION_MAJOR, *[0-9][0-9]*' "$(ROOT)/configure.ac" | grep -o '[0-9][0-9]*')
V_MIN := $(shell grep -o '_CLIENT_VERSION_MINOR, *[0-9][0-9]*' "$(ROOT)/configure.ac" | grep -o '[0-9][0-9]*')
V_REV := $(shell grep -o '_CLIENT_VERSION_REVISION, *[0-9][0-9]*' "$(ROOT)/configure.ac" | grep -o '[0-9][0-9]*')
V_RC  := $(shell grep -o '_CLIENT_VERSION_RC, *[0-9][0-9]*' "$(ROOT)/configure.ac" | grep -o '[0-9][0-9]*')

# Refuse to continue if the parse failed (Makefile copied out of the tree, or
# configure.ac restructured). Silent failure here names artifacts "rincoin-..-*",
# and a failed RC grep ALONE would give a release candidate FINAL-release
# filenames. help/clean/distclean don't consume VERSION and stay usable anywhere.
ifneq ($(filter-out help clean distclean,$(or $(MAKECMDGOALS),help)),)
  ifeq ($(and $(V_MAJ),$(V_MIN),$(V_REV),$(V_RC)),)
    $(error cannot parse _CLIENT_VERSION_{MAJOR,MINOR,REVISION,RC} from \
$(ROOT)/configure.ac — is this Makefile at contrib/release/ inside the Rincoin tree?)
  endif
endif

# The leading "v" lives ONLY on the git tag; distributed files carry the bare
# version (no "v"). RC handling is intentionally SPLIT between the two:
#   - files / package version use rcN with NO hyphen, so the version stays a
#     single token and rincoin-<ver>-<host>.tar.gz parses unambiguously; this
#     also matches `rincoind -version` and automake's PACKAGE_VERSION.
#   - the git TAG uses the readable Linux-style -rcN (hyphen).
#   release :  VERSION = 1.1.0     TAG = v1.1.0      files rincoin-1.1.0-*
#   candidate: VERSION = 1.1.0rc1  TAG = v1.1.0-rc1  files rincoin-1.1.0rc1-*
BASE    := $(V_MAJ).$(V_MIN).$(V_REV)
VERSION ?= $(BASE)$(if $(filter-out 0,$(V_RC)),rc$(V_RC),)
TAG     ?= v$(BASE)$(if $(filter-out 0,$(V_RC)),-rc$(V_RC),)

# Default release signing key (release-process.md §9-3).
KEY   ?= ED20B6354EE4526D01F83B538B6E3BF45C714ECA

# DESTDIR staging (one subdir per engine target) and the final output dir.
RELEASE ?= $(ROOT)/release
OUTDIR  ?= $(ROOT)/release-artifacts

EXTRA_CONFIG ?=

LOGDIR ?= $(HOME)/logs

.DEFAULT_GOAL := help

# --- per-target build engine ---------------------------------------------------
# $(call BUILD,<name>,<HOST triple>,<strip program>,<PIC 0|1>,<qt 0|1>,<preflight tools>)
#
# $(1)..$(6) and every $(if ...) expand at $(eval) time, so each engine target
# has its Qt decision BAKED INTO THE RECIPE TEXT. There is no runtime variable to
# override, and therefore no command-line/MAKEFLAGS precedence question about
# whether `_aarch64` might somehow acquire a GUI.
# $$(VAR) stays deferred and expands when the recipe runs.
#
# WARNING: $(call) does NOT strip whitespace from its arguments. Writing
# `$(call BUILD,_aarch64, aarch64-linux-gnu,...)` — i.e. aligning the columns —
# yields HOST=" aarch64-linux-gnu", which the depends sub-make reads as an EMPTY
# HOST= plus a stray goal: you silently get a NATIVE build under a cross-host
# filename. Keep the $(call) arguments comma-tight; $(strip) below is a second
# line of defence, and check-matrix is the third.
define BUILD
.PHONY: $(strip $(1))
$(strip $(1)):
	@echo "==> [$(strip $(1))] HOST=$(strip $(2))  VERSION=$$(VERSION)  QT=$(strip $(5))  JOBS=$$(JOBS)"
	@for t in $(strip $(3)) $(strip $(6)); do \
	    command -v "$$$$t" >/dev/null 2>&1 || { \
	      echo "==> [$(strip $(1))] preflight FAIL: '$$$$t' not in PATH" >&2; \
	      echo "    Failing NOW rather than hours into depends. Note in particular" >&2; \
	      echo "    that a missing strip tool would otherwise ship UNSTRIPPED" >&2; \
	      echo "    binaries in silence (the strip step below is '-' prefixed)." >&2; \
	      exit 1; }; \
	 done
	@mkdir -p "$$(OUTDIR)"
	@echo "==> [$(strip $(1))] depends (slowest step; first run needs network)"
	$$(MAKE) -C "$$(ROOT)/depends" HOST=$(strip $(2)) $(if $(filter 0,$(5)),NO_QT=1,) -j$$(JOBS)
	@echo "==> [$(strip $(1))] autogen + configure"
	cd "$$(ROOT)" && ./autogen.sh
	cd "$$(ROOT)" && CONFIG_SITE="$$(ROOT)/depends/$(strip $(2))/share/config.site" \
	    ./configure --prefix=/ $(if $(filter 1,$(5)),--with-gui=qt5,--without-gui) \
	        --disable-bench --disable-tests $(if $(filter 1,$(4)),--with-pic,) $$(EXTRA_CONFIG)
	@echo "==> [$(strip $(1))] make -j$$(JOBS)"
	$$(MAKE) -C "$$(ROOT)" -j$$(JOBS)
	@echo "==> [$(strip $(1))] install into staging"
	rm -rf "$$(RELEASE)/$(strip $(1))"
	$$(MAKE) -C "$$(ROOT)" DESTDIR="$$(RELEASE)/$(strip $(1))" install
	@echo "==> [$(strip $(1))] strip with $(strip $(3))"
	-$(strip $(3)) "$$(RELEASE)/$(strip $(1))"/bin/* 2>/dev/null
	@echo "==> [$(strip $(1))] package"
	@if [ "$(strip $(2))" = "x86_64-w64-mingw32" ]; then \
	    rm -f "$$(OUTDIR)/rincoin-$$(VERSION)-win64.zip"; \
	    ( cd "$$(RELEASE)/$(strip $(1))" && zip -qr "$$(OUTDIR)/rincoin-$$(VERSION)-win64.zip" bin ); \
	 else \
	    tar -C "$$(RELEASE)/$(strip $(1))" -czf "$$(OUTDIR)/rincoin-$$(VERSION)-$(strip $(2)).tar.gz" bin; \
	 fi
	@echo "==> [$(strip $(1))] distclean source tree for next target (depends/ kept)"
	-cd "$$(ROOT)" && $$(MAKE) distclean >/dev/null 2>&1
	@echo "==> [$(strip $(1))] DONE -> $$(OUTDIR)"
endef

# Raw build engines (underscore = internal). Users call the logged wrappers below.
# Args:               name,HOST triple,strip program,PIC,QT,preflight tools   <- comma-tight, see WARNING
$(eval $(call BUILD,_linux,x86_64-linux-gnu,strip,1,0,g++))
$(eval $(call BUILD,_linux_qt,x86_64-linux-gnu,strip,1,1,g++))
$(eval $(call BUILD,_windows,x86_64-w64-mingw32,x86_64-w64-mingw32-strip,0,0,x86_64-w64-mingw32-g++ zip))
$(eval $(call BUILD,_windows_qt,x86_64-w64-mingw32,x86_64-w64-mingw32-strip,0,1,x86_64-w64-mingw32-g++ zip))
$(eval $(call BUILD,_aarch64,aarch64-linux-gnu,aarch64-linux-gnu-strip,0,0,aarch64-linux-gnu-g++))
$(eval $(call BUILD,_aarch64_qt,aarch64-linux-gnu,aarch64-linux-gnu-strip,0,1,aarch64-linux-gnu-g++))

# --- logged public targets ----------------------------------------------------
CLI_TARGETS  := linux windows aarch64
FULL_TARGETS := linux-full windows-full aarch64-full
.PHONY: $(CLI_TARGETS) $(FULL_TARGETS)

$(CLI_TARGETS):
	@mkdir -p "$(LOGDIR)"
	@log="$(LOGDIR)/$@-$$(date +%F-%H%M%S).log"; \
	 echo "==> [$@] logging to $$log"; \
	 set -o pipefail; \
	 $(MAKE) _$@ 2>&1 | tee "$$log"; \
	 rc=$${PIPESTATUS[0]}; \
	 echo "==> [$@] build exit: $$rc"; \
	 echo "    log: $$log"; \
	 exit $$rc

$(FULL_TARGETS):
	@mkdir -p "$(LOGDIR)"
	@log="$(LOGDIR)/$@-$$(date +%F-%H%M%S).log"; \
	 echo "==> [$@] logging to $$log"; \
	 set -o pipefail; \
	 $(MAKE) _$(patsubst %-full,%,$@)_qt 2>&1 | tee "$$log"; \
	 rc=$${PIPESTATUS[0]}; \
	 echo "==> [$@] build exit: $$rc"; \
	 echo "    log: $$log"; \
	 exit $$rc

# --- aarch64 Qt GUI: DEFERRED -------------------------------------------------
# Not deferred because ARM64 desktops don't exist — upstream does ship an ARM64
# GUI (Bitcoin Core's aarch64-linux-gnu tarball carries bitcoin-qt; Arch Linux ARM
# packages it). Deferred because we cannot VERIFY it:
#
#   * Bitcoin Core and Litecoin both still label their ARM builds experimental,
#     and they have Guix/Gitian determinism behind them. Rincoin has neither yet
#     (Guix + the aarch64 cross environment are v1.1.1 roadmap items).
#   * Litecoin's own doc/build-unix.md cross-compiles ARM with NO_QT=1. The real
#     ARM population for a coin is overwhelmingly headless (Pi / ARM VPS nodes).
#   * qemu-user cannot exercise a Qt binary (platform plugin, fontconfig, X11),
#     so with no real ARM64 hardware there is no way to satisfy §10-6.
#
# We do not sign what we have never run. The TARGET is kept — it is how the
# binary to test on hardware gets produced — but it must be opted into, and it
# can never reach `sign` (release-full is a tripwire, and check-matrix asserts
# the ARM tarball is GUI-less before `release` hands anything to the key).
#
# TO LIFT, once §10-6 passes on real aarch64 hardware:
#   1. delete arm64-gui-gate and both `arm64-gui-gate` prerequisites
#   2. in all-release, change `aarch64` -> `aarch64-full`
#   3. flip the single knob: `EXPECT_ARM_GUI ?= 0` -> `?= 1`
#   4. replace the release-full tripwire with the real flow
ARM64_GUI ?= 0

.PHONY: arm64-gui-gate
arm64-gui-gate:
	@if [ "$(ARM64_GUI)" != "1" ]; then \
	   echo ""                                                                  >&2; \
	   echo "  aarch64 Qt GUI is DEFERRED — never verified on real hardware."   >&2; \
	   echo "  (release-process.md §10-6; qemu-user cannot validate a Qt bin)"  >&2; \
	   echo ""                                                                  >&2; \
	   echo "  ship matrix (ARM = CLI-only):  make release"                     >&2; \
	   echo "  build it FOR TESTING ONLY:     make aarch64-full ARM64_GUI=1"    >&2; \
	   echo ""                                                                  >&2; \
	   exit 1; \
	 fi; \
	 echo "==> [aarch64-full] ARM64_GUI=1 — UNVERIFIED build. Do NOT distribute."

aarch64-full: arm64-gui-gate

# --- build matrices -----------------------------------------------------------
#   all-cli      dev / CI smoke — three hosts, CLI-only, fastest path
#   all-release  SHIP MATRIX — Qt GUI where a desktop user actually runs it and
#                where we can verify it (native x86_64 run / wine); CLI on ARM
#   all-full     everything incl. the ARM64 GUI — gated, NOT release-blessed
#
# all-full lists the gate FIRST: prerequisites run in order (serial tree, see
# .NOTPARALLEL), so a forgotten ARM64_GUI=1 fails in one second — not after the
# hours of linux-full + windows-full it would otherwise burn before aarch64-full.
.PHONY: all-cli all-release all-full
all-cli:     linux       windows       aarch64
all-release: linux-full  windows-full  aarch64
all-full:    arm64-gui-gate  linux-full  windows-full  aarch64-full

# `all` is deliberately left undefined: the old name never said whether the GUI
# was in the artifacts, and that ambiguity is exactly what could get an unverified
# binary signed. Fail with the replacement rather than "No rule to make target".
# (Removable once release-process.md and CI no longer mention `make all`.)
.PHONY: all
all:
	@echo "\`make all\` was renamed. Name the matrix explicitly:"              >&2
	@echo "  make all-cli      three hosts, CLI-only         (dev / CI smoke)" >&2
	@echo "  make all-release  linux+win Qt GUI, ARM CLI     (what release builds)" >&2
	@echo "  make all-full     + ARM64 GUI (ARM64_GUI=1)     (unverified)"     >&2
	@exit 1

# --- artifact hygiene ---------------------------------------------------------
# sign.sh globs OUTDIR, and the artifact NAMES do not encode CLI vs GUI:
# rincoin-1.1.0-aarch64-linux-gnu.tar.gz is the same filename either way. A
# leftover from a previous `all-full` run would therefore be picked up and signed
# in silence. Every release flow starts from an empty OUTDIR.
.PHONY: artifacts-clean
artifacts-clean:
	@case "$(abspath $(OUTDIR))" in \
	   ""|"/") echo "artifacts-clean: refusing to rm -rf OUTDIR='$(OUTDIR)'" >&2; exit 1;; \
	 esac
	@echo "==> [artifacts] wiping $(OUTDIR)"
	rm -rf "$(OUTDIR)"

# Assert the built artifacts match the intended matrix BEFORE the signing key
# touches anything. EXPECT_ARM_GUI is THE single deferral knob (see TO LIFT):
#   0 = ship matrix (ARM tarball must be GUI-less)   1 = post-§10-6 flow
# Overriding it on the command line is deliberate and fail-closed: a mismatch in
# EITHER direction (GUI present when 0 expected, absent when 1 expected) refuses.
EXPECT_ARM_GUI ?= 0

.PHONY: check-matrix
check-matrix:
	@l="$(OUTDIR)/rincoin-$(VERSION)-x86_64-linux-gnu.tar.gz"; \
	 w="$(OUTDIR)/rincoin-$(VERSION)-win64.zip"; \
	 a="$(OUTDIR)/rincoin-$(VERSION)-aarch64-linux-gnu.tar.gz"; \
	 for f in "$$l" "$$w" "$$a"; do \
	   [ -f "$$f" ] || { echo "check-matrix: missing artifact: $$f" >&2; exit 1; }; \
	 done; \
	 tar -tzf "$$l" | grep -qx '$(QT_BIN)' \
	   || { echo "check-matrix: FAIL — linux tarball has no $(QT_BIN)" >&2; exit 1; }; \
	 echo "==> [check-matrix] linux  : $(QT_BIN) present"; \
	 if   command -v unzip   >/dev/null 2>&1; then zl="unzip -l"; \
	 elif command -v python3 >/dev/null 2>&1; then zl="python3 -m zipfile -l"; \
	 else echo "check-matrix: need unzip or python3 to inspect $$w" >&2; exit 1; fi; \
	 $$zl "$$w" | grep -q '$(QT_BIN)\.exe' \
	   || { echo "check-matrix: FAIL — win64 zip has no $(QT_BIN).exe" >&2; exit 1; }; \
	 echo "==> [check-matrix] win64  : $(QT_BIN).exe present"; \
	 if tar -tzf "$$a" | grep -q '$(QT_BIN)'; then has=1; else has=0; fi; \
	 if [ "$$has" != "$(EXPECT_ARM_GUI)" ]; then \
	   echo "check-matrix: FAIL — aarch64 rincoin-qt=$$has, this flow expects $(EXPECT_ARM_GUI)" >&2; \
	   echo "  refusing to hand an unverified ARM64 GUI binary to the signing key" >&2; \
	   exit 1; \
	 fi; \
	 echo "==> [check-matrix] aarch64: rincoin-qt=$$has (expected $(EXPECT_ARM_GUI)) — OK"; \
	 for pair in "linux:$$l" "aarch64:$$a"; do \
	   host=$${pair%%:*}; arc=$${pair#*:}; \
	   tar -tzf "$$arc" | grep -q '$(TEST_BIN)' && { \
	     echo "check-matrix: FAIL — $$host tarball ships a $(TEST_BIN)* binary" >&2; \
	     echo "  release artifacts must not contain test binaries (--disable-tests)" >&2; \
	     exit 1; }; \
	 done; \
	 $$zl "$$w" | grep -q '$(TEST_BIN)' && { \
	   echo "check-matrix: FAIL — win64 zip ships a $(TEST_BIN)*.exe binary" >&2; \
	   echo "  release artifacts must not contain test binaries (--disable-tests)" >&2; \
	   exit 1; }; \
	 echo "==> [check-matrix] no test_rincoin* binary in any artifact"
# grep anchoring above is asymmetric ON PURPOSE:
#   presence checks are exact (-x / \.exe) so a stray rincoin-qt_test can't fake
#   a GUI; the ARM ABSENCE check is an unanchored substring so that ANY qt-ish
#   file in the CLI artifact fails closed.

# --- sign / dist / release ----------------------------------------------------
# sign VERIFIES BEFORE IT SIGNS: check-matrix is a hard prerequisite, so even a
# standalone `make sign` after a stray `make all-full ARM64_GUI=1` cannot put the
# release key on an ARM64 GUI binary. Consequence: signing a source tarball alone
# (dist without binaries) is deliberately unsupported — the signed set is always
# the full matrix, matching the release-process.md file list.
.PHONY: sign
sign: check-matrix
	@bash "$(ROOT)/contrib/release/sign.sh" "$(OUTDIR)" "$(KEY)"

# Source tarball via `git archive` — a snapshot of the signed tag, matching
# modern Bitcoin Core's source release: the generated ./configure is NOT
# included, so the builder runs ./autogen.sh first (same as a git checkout).
# Named rincoin-<VERSION>.tar.gz to match the binary artifacts, so sign.sh's glob
# (rincoin-*.tar.gz) picks it up automatically — no sign.sh change needed.
# gzip -n drops the archive's embedded timestamp for a reproducible byte stream;
# git archive already fixes entry mtimes to the commit, so the same tag yields
# the same tarball. Dry-run before tagging with:  make dist DIST_REF=HEAD
DIST_REF ?= $(TAG)

.PHONY: dist
dist:
	@mkdir -p "$(OUTDIR)"
	@git -C "$(ROOT)" rev-parse -q --verify "$(DIST_REF)^{commit}" >/dev/null || { \
	    echo "error: git ref '$(DIST_REF)' not found in $(ROOT)" >&2; \
	    echo "       tag the release first, or dry-run with: make dist DIST_REF=HEAD" >&2; \
	    exit 1; \
	 }
	@echo "==> [dist] git archive $(DIST_REF) -> rincoin-$(VERSION).tar.gz"
	@git -C "$(ROOT)" archive --format=tar --prefix="rincoin-$(VERSION)/" "$(DIST_REF)" \
	    | gzip -9n > "$(OUTDIR)/rincoin-$(VERSION).tar.gz"
	@echo "    -> $(OUTDIR)/rincoin-$(VERSION).tar.gz ($$(du -h "$(OUTDIR)/rincoin-$(VERSION).tar.gz" | cut -f1))"

# The release key must never sign a source tarball and binaries that disagree:
# dist archives $(DIST_REF) while the engines compile HEAD. Assert they are the
# same commit and that no TRACKED file is locally modified — before the hours of
# building, and before artifacts-clean wipes the previous artifact set.
# (Untracked files are ignored: builds legitimately generate configure etc.)
.PHONY: release-preflight
release-preflight:
	@git -C "$(ROOT)" rev-parse -q --verify "$(DIST_REF)^{commit}" >/dev/null || { \
	    echo "release: git ref '$(DIST_REF)' not found in $(ROOT)" >&2; \
	    echo "         tag the release first, or dry-run with: make release DIST_REF=HEAD" >&2; \
	    exit 1; }
	@h="$$(git -C "$(ROOT)" rev-parse HEAD)"; \
	 t="$$(git -C "$(ROOT)" rev-parse "$(DIST_REF)^{commit}")"; \
	 [ "$$h" = "$$t" ] || { \
	    echo "release: HEAD          $$h" >&2; \
	    echo "         $(DIST_REF) is  $$t" >&2; \
	    echo "         The binaries would NOT match the signed source tarball." >&2; \
	    echo "         Checkout the tag, or dry-run with DIST_REF=HEAD." >&2; \
	    exit 1; }
	@[ -z "$$(git -C "$(ROOT)" status --porcelain --untracked-files=no)" ] || { \
	    echo "release: tracked files are locally modified — the binaries would" >&2; \
	    echo "         not match the signed source tarball. Commit or stash:" >&2; \
	    git -C "$(ROOT)" status --porcelain --untracked-files=no >&2; \
	    exit 1; }
	@echo "==> [release] preflight OK: HEAD == $(DIST_REF), tracked tree clean"

# CANONICAL publish flow: Qt GUI on x86_64 Linux + win64, CLI-only on aarch64.
# Order is fail-fast: the two git assertions and the tag check cost seconds and
# run before anything is built or wiped; dist (seconds) precedes the multi-hour
# all-release; and `sign` re-runs check-matrix as its own prerequisite, so the
# matrix is asserted against the actual packaged bytes immediately before the
# key touches them — not against the target names we believe we invoked.
.PHONY: release
release:
	@$(MAKE) release-preflight
	@$(MAKE) artifacts-clean
	@$(MAKE) dist
	@$(MAKE) all-release
	@$(MAKE) sign

# DEFERRED. Kept as a named tripwire rather than deleted, so that the deferral is
# recorded in executable form and cannot be undone by muscle memory: this is the
# only flow that would put the release key on an aarch64 rincoin-qt that no one
# has ever executed. Re-enable per the "TO LIFT" checklist above.
.PHONY: release-full
release-full:
	@echo ""                                                                    >&2
	@echo "  release-full is DEFERRED."                                          >&2
	@echo "  It would GPG-sign an aarch64 rincoin-qt that has never run on real" >&2
	@echo "  hardware (release-process.md §10-6)."                               >&2
	@echo ""                                                                     >&2
	@echo "    ship:  make release                       (ARM = CLI-only)"       >&2
	@echo "    test:  make aarch64-full ARM64_GUI=1      (never distribute)"     >&2
	@echo ""                                                                     >&2
	@exit 1

.PHONY: verify
verify:
	@echo "Artifacts in $(OUTDIR):"
	@ls -l "$(OUTDIR)"/rincoin-$(VERSION)* 2>/dev/null || echo "  (none — run 'make all-release' first)"
	@echo
	@echo "Cross-built binaries are NOT release-blessed until release-process.md"
	@echo "§10-6 passes. Confirm, per target (wine / qemu-user / real hardware):"
	@echo "  - ./rincoind -version runs and reports the $(TAG) version"
	@echo "  - getblockchaininfo shows the correct consensus params (CH 840k, RIN3)"
	@echo "  - depends/<host>/lib/libdb_cxx-4.8.a exists for each host"
	@echo "  - rincoin-qt starts and shows the correct version (x86_64 native, win64 via wine)"

.PHONY: clean
clean:
	rm -rf "$(RELEASE)"
	-cd "$(ROOT)" && $(MAKE) distclean >/dev/null 2>&1

.PHONY: distclean
distclean: clean
	rm -rf "$(ROOT)/depends/x86_64-linux-gnu" \
	       "$(ROOT)/depends/x86_64-w64-mingw32" \
	       "$(ROOT)/depends/aarch64-linux-gnu"

.PHONY: help
help:
	@echo "Rincoin Core — multi-platform build & sign"
	@echo
	@echo "  make linux | windows | aarch64        one host, CLI-only (logged)"
	@echo "  make linux-full | windows-full        one host, WITH the Qt GUI (logged)"
	@echo "  make aarch64-full                     DEFERRED — needs ARM64_GUI=1, unverified"
	@echo
	@echo "  make all-cli                          three hosts, CLI-only   (dev / CI smoke)"
	@echo "  make all-release                      linux+win Qt GUI, ARM CLI  (SHIP MATRIX)"
	@echo "  make all-full                         + ARM64 GUI (gated, not release-blessed)"
	@echo
	@echo "  make release                          preflight + clean + dist + all-release + sign"
	@echo "  make release-full                     DEFERRED until §10-6 passes on ARM64 hardware"
	@echo "  make dist                             source tarball via git archive"
	@echo "  make sign                             check-matrix, then SHA256SUMS + GPG detached-sign"
	@echo "  make check-matrix                     assert the CLI/GUI shape of the artifacts"
	@echo "  make verify                           list artifacts + §10-6 checklist"
	@echo "  make clean | distclean                remove staging [ + depends build dirs ]"
	@echo
	@echo "  GUI policy is the TARGET NAME: bare = CLI-only, -full = Qt GUI. There is no GUI= flag."
	@echo "  each build tees to LOGDIR/<target>-<timestamp>.log"
	@echo "  toggles: JOBS=N  VERSION=X.Y.Z  KEY=<fpr>  LOGDIR=<dir>  ARM64_GUI=1  EXTRA_CONFIG='--with-pic'"
	@echo
	@echo "  ROOT   = $(ROOT)"
	@echo "  VERSION= $(VERSION)   (files, no v)      TAG = $(TAG)   (git tag)"
	@echo "  LOGDIR = $(LOGDIR)"
	@echo "  OUTDIR = $(OUTDIR)"
