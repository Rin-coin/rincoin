# Rincoin Core Build & Release Procedure

**Environment**: Ubuntu 24.04 LTS (build host / VirtualBox)
**Target**: rincoin (Core) — full node + Qt GUI, mainnet release binaries
**Canonical source**: <https://github.com/Rin-coin/rincoin> (build releases from a GPG-signed tag)
**Verified (native Linux)**: _pending — stamp after a clean-room reproduction on a fresh OS install_

> **Two build paths.**
>
> - **Native Linux (Steps 1–9)** — the canonical, **verified** release path. Produces the signed x86_64 Linux binaries. Build steps are identical to the verified `rincoin-sim` procedure (verified 2026-05-23) with the GUI enabled and stripping/signing made mandatory.
> - **Multi-platform (Section 10)** — **EXPERIMENTAL**. Cross-compiles **Linux x86_64, Windows x64, and ARM64 (aarch64)** via the upstream `depends` system, automated by the  `contrib/release/` Makefile (`make linux | windows | aarch64 | all | dist | sign | release`). **Not yet verified for Rincoin** — see the checklist in [§10-6](#10-6-rincoin-specific-verification-checklist) before publishing any cross-built binary.
> The `contrib/release/` tooling (`Makefile`, `sign.sh`) is the operational layer; this document is the surrounding process (bump → build → verify → sign → tag → publish). For the Makefile's full option set (GUI `-full` targets, `JOBS`, logging, troubleshooting), see [`contrib/release/README.md`](../contrib/release/README.md).

---

## Table of Contents

**Part I — Native Linux build (verified)**

1. [System Dependencies](#1-system-dependencies)
2. [Obtain the Source (signed tag)](#2-obtain-the-source-signed-tag)
3. [BDB 4.8 Build](#3-bdb-48-build)
4. [Configure](#4-configure)
5. [Make (Build) & Unit Tests](#5-make-build--unit-tests)
6. [Functional Test QA](#6-functional-test-qa)
7. [Troubleshooting](#7-troubleshooting)
8. [Release Packaging](#8-release-packaging)
9. [Verification & GPG Signing](#9-verification--gpg-signing)

**Part II — Multi-platform build (experimental)**

10. [Multi-platform Build (`contrib/release` + depends)](#10-multi-platform-build-contribrelease--depends--experimental)

**Appendices**

- [Appendix A: RinHash Algorithm](#appendix-a-rinhash-algorithm)
- [Appendix B: MWEB Activation by Network](#appendix-b-mweb-activation-by-network)
- [Appendix C: Differences vs rincoin-sim](#appendix-c-differences-vs-rincoin-sim)

---

# Part I — Native Linux build (verified)

## 1. System Dependencies

```bash
sudo apt update

# Build tools + core libraries
sudo apt install -y \
    build-essential libtool autotools-dev automake \
    pkg-config bsdmainutils python3 \
    libssl-dev libevent-dev libboost-all-dev

# Qt5 — REQUIRED for the rincoin-qt GUI.
# A Core release ships the GUI, so (unlike rincoin-sim) these are not optional.
sudo apt install -y \
    qtbase5-dev qttools5-dev-tools

# Optional: QR-code display in the GUI
# sudo apt install -y libqrencode-dev
```

`libevent-dev` is required by the `rincoind` HTTP/RPC server and `libboost-all-dev` covers the Boost components used by the node. The Qt packages are inherited from the
standard Litecoin/Bitcoin Core GUI build set.

> The Python venv + Rust toolchain are only needed to run the functional test suite ([Step 6](#6-functional-test-qa)), not to build the binaries. They are installed there.

---

## 2. Obtain the Source (signed tag)

Official binaries are built from a **GPG-signed release tag in the canonical org**.

```bash
cd ~

# Canonical source
git clone https://github.com/Rin-coin/rincoin.git
cd rincoin

# Check out the target release tag (replace with the actual tag)
git checkout tags/v1.1.0

# Verify the tag signature BEFORE building
git verify-tag v1.1.0
# Expected: "Good signature" from the Core maintainer key (see Step 9)
```

> **Tag vs file naming.** Git tags carry a leading `v` (`v1.1.0`); release candidates use the hyphenated Linux-style `v1.1.0-rc1`. Distributed *files* carry the bare version with **no** `v`, and an RC with **no** hyphen (`rincoin-1.1.0-…`, RC: `rincoin-1.1.0rc1-…`) — see §8-3.

> **Pre-merge development source.** Before a release is merged into the Rin-coin org, the working source lives at [github.com/rincoin-core/rincoin>](https://github.com/rincoin-core/rincoin). Build **official** binaries only from a signed tag in the canonical org; the Aevust repo is for development and review.

---

## 3. BDB 4.8 Build

Rincoin inherits Litecoin's BDB 4.8 requirement for wallet portability. The system ships BDB 5.3, so BDB 4.8 must be built from source.

```bash
cd ~/rincoin

# Build BDB 4.8 into ./db4/
./contrib/install_db4.sh `pwd`

# Export the path (required for every new shell session)
export BDB_PREFIX="$HOME/rincoin/db4"
```

To avoid re-exporting on every session, add it to `~/.bashrc`:

```bash
echo "export BDB_PREFIX=\"$HOME/rincoin/db4\"" >> ~/.bashrc
source ~/.bashrc
```

> **Note.** This manual BDB step applies to the **native** build only. The multi-platform cross-build path (Section 10) builds BDB 4.8 via `depends` and does **not** use
> `install_db4.sh` or the `BDB_*` flags.

---

## 4. Configure

```bash
cd ~/rincoin

./autogen.sh

export BDB_PREFIX="$HOME/rincoin/db4"

./configure \
    --with-gui=qt5 \
    --with-pic \
    --disable-bench \
    --without-miniupnpc \
    BDB_LIBS="-L${BDB_PREFIX}/lib -ldb_cxx-4.8" \
    BDB_CFLAGS="-I${BDB_PREFIX}/include"
```

### Option flags explained

| Flag | Reason |
|------|--------|
| `--with-gui=qt5` | Build the `rincoin-qt` GUI. **This is the key difference from the CLI-only sim build** (`--without-gui`). A Core release ships the GUI. |
| `--with-pic` | **Mandatory (native build).** Required to link the static `libargon2.a` / `libbitcoin_util.a` into the shared `libbitcoinconsensus.la`; omitting it causes an `R_X86_64_PC32 relocation` error. |
| `--disable-bench` | Benchmarks are not shipped in releases; disabling speeds up the build. |
| `--without-miniupnpc` | Optional. Omits UPnP port-mapping. **Drop this flag** if you want UPnP support compiled into the release. |
| `BDB_LIBS` / `BDB_CFLAGS` | Point the wallet at the locally built BDB 4.8 (Step 3). |

### Expected configure output (success indicators)

```
checking for Berkeley DB C++ headers... /home/<user>/rincoin/db4
...
checking whether to build Rincoin Core GUI... yes (Qt5)
...
configure: creating ./config.status
```

---

## 5. Make (Build) & Unit Tests

```bash
# Build with all CPU cores, save a log
make -j$(nproc) 2>&1 | tee build_$(date +%m%d).log

# Run the C++ unit tests (test_rincoin Boost suite + libsecp256k1)
make check 2>&1 | tee test_$(date +%m%d).log
```

### Headless `make check` with the GUI built

Because the GUI is enabled, `make check` also builds and runs the Qt test (`test_rincoin-qt`), which needs a Qt platform plugin. On a headless build VM, run it
with an offscreen platform or under `xvfb`:

```bash
QT_QPA_PLATFORM=offscreen make check
# or:
xvfb-run -a make check
```

### Expected warnings (non-blocking)

```
*** Warning: Linking the shared library libbitcoinconsensus.la against the
*** static library ../src/crypto/argon2/libargon2.a is not portable!
```

These portability warnings are harmless; the build succeeds.

### Built binaries

| File | Role |
|------|------|
| `src/rincoind` | Daemon (main binary) |
| `src/rincoin-cli` | RPC controller |
| `src/rincoin-tx` | Raw transaction tool |
| `src/rincoin-wallet` | Offline wallet maintenance tool |
| `src/qt/rincoin-qt` | GUI (built with `--with-gui=qt5`) |

---

## 6. Functional Test QA

Recommended before publishing a release. The Python functional suite drives the built node end-to-end and uses the same RinHash implementation as Core.

```bash
# venv + Rust are needed only for the functional tests (blake3 builds via Rust)
sudo apt install -y python3-venv python3-dev
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh   # select option 1
source ~/.cargo/env

python3 -m venv ~/rincoin-venv
source ~/rincoin-venv/bin/activate
pip install --upgrade pip
pip install blake3 argon2-cffi
python3 -c "import blake3, argon2; print('OK')"     # Expected: OK

# Run the functional suite
cd ~/rincoin
python3 test/functional/test_runner.py
```

> For the full detail of the test-framework RinHash port (`messages.py` etc.) and the RIN3 / CH boundary tests, see the **rincoin-sim Build & Test Procedure**. Those patches are already committed in the source tree; this step only runs them.

---

## 7. Troubleshooting

| Error | Cause | Fix |
|-------|-------|-----|
| `cannot find -ldb_cxx-4.8` | `BDB_PREFIX` not set | `export BDB_PREFIX=$HOME/rincoin/db4` |
| `R_X86_64_PC32 relocation` (make error) | Missing `--with-pic` | Re-run configure with `--with-pic` |
| `Could not find a configuration for Qt5` / `configure: error: Qt dependencies...` | Qt5 dev packages missing | `sudo apt install qtbase5-dev qttools5-dev-tools` |
| `make check` fails on `test_rincoin-qt` with `xcb`/display error | No display for the Qt test | `QT_QPA_PLATFORM=offscreen make check` or `xvfb-run -a make check` |
| `Text file busy` during `strip` | `rincoind` is running | `pkill -9 rincoind` first |
| `blake3` install fails | Rust not installed | Install Rust first (Step 6) |
| `git pull` blocked with `modified:` warnings | Local edits conflict with remote | `git restore <file>` to discard local changes |

### Re-build from scratch (preserve repo)

```bash
cd ~/rincoin
make distclean
export BDB_PREFIX="$HOME/rincoin/db4"
./configure \
    --with-gui=qt5 \
    --with-pic \
    --disable-bench \
    --without-miniupnpc \
    BDB_LIBS="-L${BDB_PREFIX}/lib -ldb_cxx-4.8" \
    BDB_CFLAGS="-I${BDB_PREFIX}/include"
make -j$(nproc) 2>&1 | tee build_$(date +%m%d).log
```

---

## 8. Release Packaging

### 8-1. Stop the daemon

`strip` cannot modify a running binary (Linux's `Text file busy` protection).

```bash
pkill -9 rincoind
```

### 8-2. Strip binaries (mandatory for release)

```bash
strip src/rincoind src/rincoin-cli src/rincoin-tx src/rincoin-wallet src/qt/rincoin-qt
```

### 8-3. Assemble the release directory

> **Artifact naming.** Distributed files carry the **bare version** — no leading `v` (`rincoin-1.1.0-…`), matching Bitcoin/Litecoin. The `v` belongs to the git tag only (`v1.1.0`; RC tags `v1.1.0-rc1`). RC *files* use the single-token `rincoin-1.1.0rc1-…` (no hyphen) so the version parses unambiguously next to the hyphenated host triple and matches `rincoind -version` / `PACKAGE_VERSION`.

```
rincoin-1.1.0-linux-x86_64/
├── bin/
│   ├── rincoind
│   ├── rincoin-cli
│   ├── rincoin-tx
│   ├── rincoin-wallet
│   └── rincoin-qt
└── README.md
```

```bash
VERSION="1.1.0"                    # bare version — no "v" (the "v" lives on the git tag)
PKG="rincoin-${VERSION}-linux-x86_64"

mkdir -p ${PKG}/bin

cp src/rincoind src/rincoin-cli src/rincoin-tx \
   src/rincoin-wallet src/qt/rincoin-qt \
   ${PKG}/bin/

cp README.md ${PKG}/
```

### 8-4. Create the tarball

```bash
tar -czvf ${PKG}.tar.gz ${PKG}
```

### 8-5. End-user installation (for the README)

```bash
tar xzf rincoin-1.1.0-linux-x86_64.tar.gz
sudo cp rincoin-1.1.0-linux-x86_64/bin/* /usr/local/bin/

rincoind --version
rincoin-cli --help
```

---

## 9. Verification & GPG Signing

Bitcoin Core-level release security (supply-chain attack defense). **Signing is mandatory for official releases**, and applies to **both** the native and the
cross-built artifacts.

### 9-1. Generate SHA256 checksums

```bash
# Cover every artifact you will publish: binaries + the SOURCE tarball
sha256sum \
    rincoin-1.1.0-linux-x86_64.tar.gz \
    rincoin-1.1.0-x86_64-linux-gnu.tar.gz \
    rincoin-1.1.0-aarch64-linux-gnu.tar.gz \
    rincoin-1.1.0-win64.zip \
    rincoin-1.1.0.tar.gz \
    > SHA256SUMS 2>/dev/null

cat SHA256SUMS
```

The source tarball `rincoin-1.1.0.tar.gz` is produced from the signed tag with `git archive` (`make dist` in `contrib/release/`). Like modern Bitcoin Core source releases it contains **no** generated `./configure`; builders run `./autogen.sh` first, same as a git checkout. In the automated flow, `contrib/release/` `make sign` regenerates this manifest over everything present in `release-artifacts/` — the list above is the manual equivalent.

### 9-2. GPG detached signature

A detached, ASCII-armored signature (`--detach-sign --armor`) matches Bitcoin Core / Litecoin release practice: `SHA256SUMS` stays byte-identical to what `sha256sum -c` consumes, and the one-argument `gpg --verify SHA256SUMS.asc` automatically finds and verifies the companion file, with no warnings.

```bash
gpg --detach-sign --armor SHA256SUMS
# Output: SHA256SUMS.asc  — publish BOTH files
```

### 9-3. Signing key

Official Rincoin releases are signed with the Core maintainer key:

```
Fingerprint: ED20 B635 4EE4 526D 01F8 3B53 8B6E 3BF4 5C71 4ECA
```

Published at `keys.openpgp.org`; also committed in-repo as `security/aevust.asc`.

### 9-4. GitHub Releases asset structure

```
rincoin-1.1.0-linux-x86_64.tar.gz         # native x86_64 Linux (verified path)
rincoin-1.1.0-x86_64-linux-gnu.tar.gz     # cross-built Linux   (if published)
rincoin-1.1.0-aarch64-linux-gnu.tar.gz    # cross-built ARM64   (if published)
rincoin-1.1.0-win64.zip                   # cross-built Windows (if published)
rincoin-1.1.0.tar.gz                      # source (git archive of the signed tag)
SHA256SUMS                                # plain-text checksums
SHA256SUMS.asc                            # GPG detached signature over SHA256SUMS
```

### 9-5. End-user verification flow

```bash
# 1. Import the maintainer key (first time only)
gpg --keyserver keys.openpgp.org \
    --recv-keys ED20B6354EE4526D01F83B538B6E3BF45C714ECA
# or: gpg --import security/aevust.asc

# 2. Verify the signature on the checksums.
#    One argument: gpg detects the detached signature and automatically
#    verifies the companion SHA256SUMS in the same directory.
gpg --verify SHA256SUMS.asc
# Expected: "Good signature from <signer>"  (and NO warnings)

# 3. Verify your downloaded file matches the checksum
sha256sum -c SHA256SUMS --ignore-missing
# Expected: <your file>: OK
```

> **Detached vs clear-sign.** Rincoin releases use **detached** signatures (`--detach-sign --armor`), matching Bitcoin Core / Litecoin. With the `.asc` next to `SHA256SUMS`, the one-argument `gpg --verify SHA256SUMS.asc` verifies the companion file automatically; the explicit two-argument form (`gpg --verify SHA256SUMS.asc SHA256SUMS`) is equivalent. Do **not** use `--clear-sign` for release manifests: with a same-named companion file present, gpg verifies only the copy embedded in the `.asc` and warns that the file itself "was NOT verified", even though the signature is good.

---

# Part II — Multi-platform build (experimental)

## 10. Multi-platform Build (`contrib/release` + depends) — EXPERIMENTAL

### 10-1. Build model & status

This path cross-compiles Rincoin for three targets from a single Ubuntu 24.04 host, using the upstream **`depends`** system inherited from Litecoin / Bitcoin Core. `depends` builds **all** dependencies for each target (BDB 4.8, Boost, libevent, and — optionally — Qt), so the manual BDB step from Part I is **not** used here.

It is driven entirely by the **`contrib/release/` Makefile** — no container is required. This section is the *process* wrapper; for the full Makefile interface (GUI `-full` targets, `JOBS`, per-build logging, `git clean` troubleshooting), see [`contrib/release/README.md`](../contrib/release/README.md).

| Aspect | Native (Part I) | Multi-platform (this section) |
|--------|-----------------|-------------------------------|
| Status | **Verified** | **EXPERIMENTAL — verify before publishing** |
| Targets | x86_64 Linux | x86_64 Linux, Windows x64, ARM64 |
| Dependencies | system apt + manual BDB 4.8 | `depends` builds everything |
| GUI | `--with-gui=qt5` | Phase 1: CLI-only → Phase 2: GUI (`-full`) |
| Driver | manual steps | `contrib/release/` Makefile |
| Reproducibility | clean dev VM | controlled toolchain (see [§10-7](#10-7-depends-vs-guix-determinism)) |

> ⚠️ **Verification boundary.** The flow is standard Bitcoin/Litecoin cross-build practice, but the **Rincoin-specific** crypto (RinHash: BLAKE3 → Argon2d → SHA3-256, `libargon2`) and BDB 4.8 cross-builds are **not yet confirmed**. Treat this as a *starting point to validate*, not a finished release flow. Do not publish cross-built binaries until the checklist in [§10-6](#10-6-rincoin-specific-verification-checklist) passes.

### 10-2. Host triples & prerequisites

| Target | `HOST` triple | Cross toolchain (Ubuntu pkg) | Output artifact |
|--------|---------------|------------------------------|-----------------|
| Linux x86_64 | `x86_64-linux-gnu` | native `g++` | `rincoin-1.1.0-x86_64-linux-gnu.tar.gz` |
| Windows x64 | `x86_64-w64-mingw32` | `g++-mingw-w64-x86-64` (POSIX threads) | `rincoin-1.1.0-win64.zip` |
| ARM64 Linux | `aarch64-linux-gnu` | `g++-aarch64-linux-gnu` | `rincoin-1.1.0-aarch64-linux-gnu.tar.gz` |

Install the cross toolchains and select the POSIX threading model MinGW requires:

```bash
sudo apt install -y g++-mingw-w64-x86-64 g++-aarch64-linux-gnu
sudo update-alternatives --config x86_64-w64-mingw32-g++   # choose .../posix
sudo update-alternatives --config x86_64-w64-mingw32-gcc   # choose .../posix
```

`depends` downloads dependency sources on the first build, so the host needs internet access for the first run (or a pre-populated `depends/sources/` cache). Full prerequisite list: [`contrib/release/README.md`](../contrib/release/README.md).

### 10-3. Build (`contrib/release` Makefile)

From the repo root. Builds default to **CLI-only** (validate the core first, per [§10-4](#10-4-phase-1--phase-2-why-split)); add the Qt GUI with the `-full` targets.

```bash
cd contrib/release

make help           # confirm VERSION / TAG and ROOT first
make linux          # -> ../../release-artifacts/rincoin-<VERSION>-x86_64-linux-gnu.tar.gz
make windows        # -> ../../release-artifacts/rincoin-<VERSION>-win64.zip
make aarch64        # -> ../../release-artifacts/rincoin-<VERSION>-aarch64-linux-gnu.tar.gz
make all-cli        # all three, CLI-only, in sequence (always serial)

make linux-full     # same target with the Qt GUI (heavier)
```

The Makefile runs `depends` → `./autogen.sh` → `./configure` → `make` → stage → strip → archive for each target, teeing each build to `~/logs/<target>-<timestamp>.log`. Do **not** pass `-j`; parallelism is internal via `JOBS`, and `.NOTPARALLEL` keeps the three targets from clobbering the shared source tree. `VERSION` (bare, no `v`) and `TAG` (with `v`; RC `v1.1.0-rc1`) are parsed from `configure.ac` — see §8-3 and [`contrib/release/README.md`](../contrib/release/README.md).

Every target is configured `--disable-tests`, so `test_rincoin` and `test_rincoin-qt` are never built into a release artifact — the same binary set §8-3 assembles by hand. This is independent of the native build (Part I), which keeps tests enabled so `make check` (§5) still runs; the two configure invocations do not interact. For a cross build whose test binary you want to run under Wine / qemu-user (§10-6), re-enable it for that run with `EXTRA_CONFIG=--enable-tests`.

### 10-4. Phase 1 → Phase 2 (why split)

Cross-compiling Qt via `depends` for Windows and ARM64 is the slowest and most failure-prone part of the build. Validate the **core** first:

1. **Phase 1 — CLI-only** (`make linux | windows | aarch64`): proves that RinHash,
   `libargon2`, SHA3-256, libsecp256k1, and the BDB 4.8 wallet cross-compile and that
   `rincoind` runs on each target.
2. **Phase 2 — GUI** (`make <target>-full`): add `rincoin-qt` once Phase 1 is green. ARM64
   + Windows Qt are optional — ship a GUI only where it builds cleanly and is tested.

### 10-5. Source tarball, sign & release

`make dist` produces the source tarball (`git archive` of the signed tag; see §9-1), and `make sign` writes the detached-signed manifest over **every** artifact present — the three binaries plus the source tarball — in one `SHA256SUMS` / `.asc` pair (§9). The full Linux-side flow is one command:

```bash
make release        # preflight (HEAD==tag, clean tree) + wipe + dist + all-release + sign
```

Override the key with `make sign KEY=<fingerprint>` (default: the Core maintainer key, §9-3). The Linux build host is the default signing and publishing path; a Windows re-sign path for a hardware-token custody model is documented in [`contrib/release/README.md`](../contrib/release/README.md).

### 10-6. Rincoin-specific verification checklist

⚠️ **Confirm every item against the actual v1.1.0 source before publishing any cross-built binary.** Until this passes, this section is informational only.

- [ ] **RinHash cross-compiles** for each target: `src/crypto/argon2/` (`libargon2`), BLAKE3, and SHA3-256 build cleanly under MinGW and aarch64. Argon2 and BLAKE3 contain SIMD / threading code that may need per-arch configure flags.
- [ ] **BDB 4.8 wallet** is built by `depends` for each target — confirm `depends/<host>/lib/libdb_cxx-4.8.a` exists, i.e. Rincoin's depends tree still includes `bdb.mk` and does not require an extra flag.
- [ ] **`rincoind` runs** and reports correct `getblockchaininfo` / consensus parameters on each platform (Windows under Wine or real hardware; ARM64 on real hardware or `qemu-user`).
- [ ] **Native target relocation:** if `x86_64-linux-gnu` hits `R_X86_64_PC32 relocation`, add `--with-pic` (as in the native build, Step 4) — the `linux` target already sets it; pass `EXTRA_CONFIG=--with-pic` for others if needed.
- [ ] **Functional tests pass** for at least the native target before trusting the cross builds.
- [ ] **Qt (Phase 2)** cross-builds without error for any target you intend to ship with a GUI.
- [ ] **No test binary ships:** confirm each artifact contains no `test_rincoin` / `test_rincoin-qt` (`--disable-tests`). `make check-matrix` asserts this and refuses to sign otherwise; verify with `unzip -l` / `tar -tzf` after a clean `make release` (a partial rebuild can leave a stale artifact that trips the gate).
- [ ] Record results (logs to `~/logs/`, evidence to Zenodo) and only then update the **Verified** line and remove the EXPERIMENTAL markers.

### 10-7. depends vs Guix (determinism)

The `depends` system gives a **controlled, consistent toolchain** and cross-compilation — comparable in spirit to Bitcoin's older **Gitian** system. It does **not** by itself guarantee bit-for-bit deterministic output: timestamps, paths, and build parallelism can introduce variation between independent builders.

Bitcoin Core's current reproducible-build system is **Guix** (`contrib/guix/`), which pins every dependency to a content hash and yields identical binaries across independent builders. **If bit-for-bit reproducibility is the goal, Guix — not plain `depends` — is the upstream path.** Guix support for Rincoin is planned for **v1.1.1**; until then, `depends` via `contrib/release/` is the pragmatic route to multi-platform binaries with a controlled toolchain, and archive-level GPG signatures (§9) carry the integrity guarantee.

---

## Appendix A: RinHash Algorithm

Defined in `src/rinhash.cpp`:

```
80-byte block header
    ↓  BLAKE3
32 bytes
    ↓  Argon2d  (t_cost=2, m_cost=64, lanes=1, salt="RinCoinSalt")
32 bytes
    ↓  SHA3-256
32 bytes  ←  PoW hash (replaces scrypt in Litecoin)
```

---

## Appendix B: MWEB Activation by Network

| Network | MWEB activation |
|---------|-----------------|
| Mainnet | `NEVER_ACTIVE` (sealed) |
| Testnet | `nStartHeight = 840` (height-based) |
| Regtest | `nStartTime = 1601450001` (time-based; already past → activates ~h=432) |

---

## Appendix C: Differences vs rincoin-sim

| Aspect | rincoin-sim | Rincoin Core (this guide) |
|--------|-------------|---------------------------|
| Purpose | Functional testing, 1/1000 scale | Mainnet binary distribution |
| GUI | `--without-gui` (CLI-only) | `--with-gui=qt5` (native) |
| BDB | `BDB_LIBS` / `BDB_CFLAGS` (strict) | Same (native) / `depends` (cross-build) |
| Stripping | Recommended | **Mandatory** |
| Signing | Optional | **Mandatory (GPG detached-sign)** |
| Platforms | Linux x86_64 | x86_64 Linux (verified) + Win/ARM64 (experimental) |
| Chain params | 1/1000-scale heights | Mainnet heights |
