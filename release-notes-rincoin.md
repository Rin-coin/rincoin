# Rincoin Core v1.1.0 Release Notes

**Release Date:** *to be set on tag*
**Base Commit:** `b52c87778` (master / v1.0.5 line)
**Branch:** `release-v1.1.0-community-maintenance`

---

## Overview

v1.1.0 is a **community-maintenance and infrastructure release**. It does
not change the consensus rules in force on mainnet today. Instead it lands
the framework that future RinHash and consensus parameter changes will
travel through, ships one narrow forward-looking overlay (a peer-protocol-
version floor at the per-network activation-0 height), and folds in
operational/tooling improvements that have accumulated since v1.0.5.

Highlights:

- **RinHash activations table** — a single JSON consensus table
  (`src/consensus/rinhash_consensus.json`) drives a code-generated header,
  a runtime resolver (`Consensus::Params::GetRinHashEffectiveAt`), and a
  CI guard (`gen_rinhash_consensus.py --check`) preventing JSON↔code
  drift. See `doc/rinhash-activations.md`.
- **Peer-protocol-version floor at activation 0** —
  `min_peer_protocol_version = 70018` becomes effective at heights
  `840000` (mainnet, 4th halving), `4200` (testnet), `600` (regtest), and
  `600` (preview). From those heights onward, v1.1.0 nodes disconnect
  peers that have not advertised at least `nVersion = 70018` during the
  version handshake.
- **`PROTOCOL_VERSION` bump 70017 → 70018** to advertise the activations
  table handshake.
- **Previewnet (`preview` chain)** — a fourth chain dedicated to
  rehearsal, with its own magic, ports, address prefixes, and HRPs but
  reusing testnet's genesis. Activated via `-preview`.
- **HogEx empty-vin fix** — `CheckTransactionInputs` and the MWEB miner
  no longer reject HogEx transactions for having an empty `vin`, the
  required shape for the MWEB peg-out aggregator transaction.
- **Splash and logo** restored to the v1.0.1 assets after a regression
  that landed in the v1.0.4 line.

## Backward Compatibility

v1.1.0 does not change the consensus rules currently in force on mainnet.
Block validation, PoW, transaction format, subsidy rules, chain selection,
existing blocks, wallets, and datadirs remain compatible with the v1.0.x
line. The new peer-protocol floor is scheduled for the activation height
and affects network reachability, not historical block validity.

---

## Major Changes

### 1. RinHash Activations Table

A small, auditable, JSON-driven framework for height-indexed consensus
parameter changes.

- **Authoritative table:** `src/consensus/rinhash_consensus.json` —
  per-network `init` baseline plus an ordered list of `activations[]`
  overlays.
- **Schema:** `src/consensus/rinhash_consensus.schema.json` — validated
  during code generation.
- **Generator:** `python3 src/consensus/gen_rinhash_consensus.py` produces
  `src/consensus/rinhash_consensus_data.h`. CI runs it with `--check`;
  PRs that hand-edit the header without regenerating fail the build.
- **Build wiring:** `src/Makefile.am` invokes `--check` as part of the
  default build target.
- **Runtime resolver:** `Consensus::Params::GetRinHashEffectiveAt(int height)`
  returns the `RinHashEffective` (Argon2d parameters + the
  `min_peer_protocol_version` floor) in force at any height.
- **Last-write-wins per field:** overlays specify only the fields they
  change; everything else inherits from the most recent prior overlay or
  the `init` baseline.

See `doc/rinhash-activations.md` for the full design and a worked example
of adding a new overlay.

### 2. Peer-Protocol-Version Floor at Activation 0

The v1.1.0 activation-0 overlay sets `min_peer_protocol_version = 70018`
at the per-network activation heights below. From those heights forward,
peers advertising `nVersion < 70018` are disconnected during the version
handshake (`net_processing.cpp`, VERSION handler).

| Network  | Activation-0 height | Floor  |
|----------|---------------------|--------|
| mainnet  | 840000              | 70018  |
| testnet  | 4200                | 70018  |
| regtest  | 600                 | 70018  |
| preview  | 600                 | 70018  |

Below the activation height the floor is dormant (`0`); the existing
`MIN_PEER_PROTO_VERSION = 31800` continues to be the only floor enforced.

### 3. `PROTOCOL_VERSION` Bumped to 70018

`src/version.h` advertises `PROTOCOL_VERSION = 70018` to signal support for
the RinHash activations table. v1.0.x peers (`70017`) remain interoperable
with v1.1.0 peers everywhere except after activation-0, where they will be
disconnected during the version handshake.

### 4. Previewnet (`preview` Chain)

A fourth chain dedicated to rehearsal mining and integration drills,
ported from work originally landed under `customized-halving`:

- `-preview` command-line flag, `[preview]` config section.
- P2P magic `rinp` (`0x72 0x69 0x6E 0x70`); ports `49555` (P2P),
  `49556` (RPC).
- Bech32 HRPs `prin` / `prmweb`; base58 prefixes `56` (PUBKEY),
  `118` (SCRIPT), `219` (SECRET); ext-key prefixes `0x03E25D80` /
  `0x03E25946`.
- Reuses testnet's genesis verbatim — simplifies sync and tooling.
- Activation-0 overlay matches regtest (height `600`, floor `70018`).

### 5. MWEB HogEx Empty-vin Fix

`src/consensus/tx_check.cpp` now exempts HogEx transactions from the
"transaction has no inputs" check, and `src/mweb/mweb_miner.cpp` asserts
the HogEx structural invariant before block assembly so a malformed
HogEx fails fast rather than producing an invalid block. This restores
the ability to mine MWEB blocks that contain a HogEx aggregator
transaction with an empty `vin` (its specified shape).

### 6. Splash and Logo Restored

`src/qt/res/icons/{rincoin.png, rincoin_splash.png, bitcoin.ico,
bitcoin_testnet.ico}` are restored to their v1.0.1 (`5cf3d4a113`) form,
reverting an unintended asset change that landed in the v1.0.4 line.

---

## RPC Changes

- **New:** `getrinhashparams` — returns the `effective` RinHash
  parameters and `min_peer_protocol_version` floor at the current tip,
  plus a `next_change` block describing the next scheduled overlay (if
  any).
- **Extended:** `getblockchaininfo` now contains a top-level `rinhash`
  object with the same `effective` payload, suitable for explorers and
  health dashboards.

## P2P Changes

- `PROTOCOL_VERSION = 70018`. The bump is non-disruptive on its own; the
  associated peer floor is gated on the per-network activation-0 height.

## Testing

- **Unit tests** (`src/test/rinhash_tests.cpp`): canonical PoW vector,
  init-only dormancy, mainnet/testnet/regtest/preview activation-0
  boundaries, height-aware `GetPoWHash` overload, pending-salt rejection.
- **Functional test** (`test/functional/feature_min_peer_proto_floor.py`):
  regtest end-to-end — pre-activation low-version peer accepted, post-
  activation low-version peer disconnected, post-activation peer at the
  floor accepted.
- **Codegen guard** (`gen_rinhash_consensus.py --check`): wired into the
  build; fails PRs whose JSON and generated header are out of sync.

---

## Upgrade Procedure

Node operators, miners, and exchange/explorer integrators should plan a
coordinated upgrade before mainnet block `840000`. From that height
onward, peers still running v1.0.x will be unable to maintain connections
to v1.1.0 peers.

- **Wallet users:** standard upgrade — replace binaries, restart.
  No datadir migration required; no reindex required.
- **Miners:** upgrade ahead of mainnet height `840000`. After activation,
  v1.0.x miners will be unable to maintain peer connections.
- **Pools / explorers / exchanges:** plan a window before mainnet height
  `840000`; consume `getrinhashparams` if you wish to surface the
  upcoming change to users.

## Known Issues

- Customised halving, alternative Argon2d parameter sets, and any new
  transaction-level consensus rules are explicitly out of scope for
  v1.1.0 and remain subjects for separate, community-reviewed proposals.

## Credits

Thanks to everyone who contributed to this release, including the
upstream Litecoin and Bitcoin Core developers whose work this builds on.

---

# Rincoin Core v1.0.4 Release Notes

**Release Date:** February 4, 2026  
**Base Commit:** 5cf3d4a113bbbb7212c289fd474259103999bfb4 (v1.0.1)  
**Release Commit:** 0b8a1599eb13453f1feb5800689588b319887f74

---

## Overview

Version 1.0.4 is a significant maintenance and enhancement release that builds upon v1.0.1 features. This release focuses on:
- **Critical SIMD hash optimizations and fixes** for AVX2, SSSE3, and AVX512 implementations
- **Enhanced Qt wallet usability** with shift+click range selection in coin control
- **Improved cross-platform build system** with automated release tooling
- **Network stability improvements** with updated checkpoints up to block 435,935
- **Build compatibility fixes** for modern toolchains (Ubuntu 24.04, MinGW-w64, Python 3.12)

---

## Major Changes

### 1. Rinhash SIMD Optimizations and Critical Fixes

#### 1.1 Native CPU Optimizations (Commit c0e59cf3f)
**Added multi-platform SIMD acceleration for Argon2d hashing algorithm:**

- **Runtime CPU Dispatch System** (`src/crypto/argon2/argon2_dispatch.c`, `argon2_dispatch.h`):
  - Detects CPU capabilities at runtime using CPUID
  - Automatically selects optimal implementation: AVX512 > AVX2 > SSSE3 > Reference
  - No recompilation needed - single binary adapts to CPU features
  - Thread-safe initialization with atomic operations

- **SIMD Implementations Added**:
  - **SSSE3** (`argon2_ssse3.c`): For older CPUs (2006+, Intel Core 2, AMD K10+)
  - **AVX2** (`argon2_avx2.c`): For modern CPUs (2013+, Intel Haswell+, AMD Excavator+)
  - **AVX512** (`argon2_avx512.c`): For high-end CPUs (2017+, Intel Skylake-X+, AMD Zen 4+)
  - Each implementation provides 2-6x speedup over reference code depending on CPU

- **Build System Integration**:
  - Added CPU feature detection in `configure.ac`
  - Conditional compilation with proper compiler flags per target
  - `-mssse3`, `-mavx2`, `-mavx512f` flags applied only to respective modules
  - Prevents instruction errors on CPUs lacking features

- **Files Modified**:
  - `src/Makefile.am`: Added new SIMD object files with feature flags
  - `src/crypto/argon2/Makefile.am`: Integrated dispatch and SIMD modules
  - `src/crypto/rinhash.cpp`: Switched from `fill_memory_blocks` to `argon2_fill_memory_blocks_dispatch`

#### 1.2 Critical AVX2 and SSSE3 Fixes (Commit a94de3132)
**Fixed serious hashing bugs in SIMD implementations that caused incorrect hash outputs:**

- **AVX2 BLAMKA Round Fix** (`src/crypto/argon2/blake2/blamka-round-avx2.h`):
  - **Problem**: Original implementation used 4-argument `BLAKE2_ROUND_AVX2` macro that only shuffled within single 256-bit registers
  - **Solution**: Implemented 8-argument `BLAKE2_ROUND_1_AVX2` and `BLAKE2_ROUND_2_AVX2` macros
  - **BLAKE2_ROUND_1_AVX2**: Uses `SWAP_HALVES` for row processing (swaps 128-bit lanes)
  - **BLAKE2_ROUND_2_AVX2**: Uses `SWAP_QUARTERS`/`UNSWAP_QUARTERS` for column processing (64-bit element rotation)
  - Matches PHC reference implementation's inter-register shuffle approach

- **SSSE3 BLAMKA Round Fix** (`src/crypto/argon2/blake2/blamka-round-ssse3.h`):
  - **Problem**: Used incorrect single-register 4-argument macros like AVX2
  - **Solution**: Implemented proper 8-argument `BLAKE2_ROUND_1_SSSE3` and `BLAKE2_ROUND_2_SSSE3`
  - Uses `_mm_shuffle_epi32` with correct immediate values for inter-register data movement
  - Row processing: Swaps 64-bit halves between adjacent registers
  - Column processing: Rotates 32-bit elements with proper wrap-around

- **AVX2 Core Fix** (`src/crypto/argon2/argon2_avx2.c`):
  - Updated `fill_block_avx2` to use corrected 8-argument macros
  - Separated row processing (2 iterations with BLAKE2_ROUND_1_AVX2) from column processing (2 iterations with BLAKE2_ROUND_2_AVX2)

- **Impact**: These fixes ensure correct Argon2d hash computation with `-O3 -march=native` optimizations. Without these fixes, SIMD-optimized builds produced wrong hashes.

#### 1.3 Critical AVX512 Fix (Commit 7236807480)
**Fixed AVX512 implementation with same issue as AVX2/SSSE3:**

- **AVX512 BLAMKA Round Fix** (`src/crypto/argon2/blake2/blamka-round-avx512.h`):
  - **Problem**: Used 4-argument `BLAKE2_ROUND_AVX512` macro, only shuffling within 512-bit registers
  - **Solution**: Implemented 8-argument `BLAKE2_ROUND_1_AVX512` and `BLAKE2_ROUND_2_AVX512`
  - Uses `SWAP_HALVES` (256-bit lane swaps) for row processing
  - Uses `SWAP_QUARTERS`/`UNSWAP_QUARTERS` (128-bit element rotation) for column processing
  - Proper inter-register shuffles using `_mm512_shuffle_i64x2` with correct immediate values

- **AVX512 Core Fix** (`src/crypto/argon2/argon2_avx512.c`):
  - Updated `fill_block_avx512` to use corrected 8-argument macros
  - Removed unnecessary `__AVX512DQ__` requirement (only needs `__AVX512F__`)
  - Matches PHC Argon2 reference implementation structure

- **Documentation**: Added detailed fix explanation in commit message referencing the original buggy commit (c0e59cf3f)

---

### 2. Qt Wallet Enhancements

#### 2.1 Shift+Click Range Selection in Coin Control (Commits 29acf92db, b5c48afc9)
**Implemented efficient UTXO selection with shift+click functionality:**

- **New Feature** (`src/qt/coincontroltreewidget.cpp`, `coincontroltreewidget.h`):
  - **Shift+Click Behavior**: Select/deselect range of UTXOs between last clicked item and shift+clicked item
  - **Smart State Toggle**: If previously clicked item was checked, range is unchecked; if unchecked, range is checked
  - **Visual Feedback**: Blue cursor line moves to shift+clicked item
  - **Real-time Updates**: Coin control totals (quantity, bytes, amount, fee) update immediately
  - **Works in Both Modes**: Tree mode (grouped by address) and list mode (flat UTXO list)

- **Implementation Details**:
  - Added `QTreeWidgetItem* m_lastClickedItem` member to track reference point
  - `mousePressEvent` override detects shift modifier and handles range logic
  - Uses `QTreeWidgetItemIterator` to build ordered list of visible items
  - Handles bidirectional ranges (shift+click above or below last clicked item)
  - Signal blocking prevents redundant updates during batch state changes
  - Emits `itemChanged` signals after range update for proper coin control synchronization

- **User Benefit**: Dramatically improves workflow when selecting many UTXOs for consolidation or specific transaction requirements

#### 2.2 Qt Wallet Performance Improvements (Commit 3bb8c83ae)
**Enhanced synchronization and dialog responsiveness:**

- **Modal Overlay Optimization** (`src/qt/modaloverlay.cpp`):
  - Reduced update frequency during IBD (Initial Block Download)
  - Updates progress every 250ms instead of every block
  - Significantly reduces GUI thread load during sync

- **Coin Control Dialog Optimization** (`src/qt/coincontroldialog.cpp`, `coincontroldialog.h`):
  - Implements caching for coin control tree model data
  - Reduces redundant UTXO queries during dialog operations
  - Added `QTimer` for deferred updates to batch changes

- **Node Interface Improvements** (`src/interfaces/node.cpp`):
  - Optimized `getUnspentOutputs` query with better filtering
  - Reduced lock contention for wallet UTXO access

---

### 3. Cross-Platform Build System Improvements

#### 3.1 Comprehensive Release Build Tooling (Commits 8429a5555, 92a5059b3, 0b8a1599e)
**Added automated multi-platform release build system:**

- **Release Build Script** (`contrib/build_release.sh`):
  - **Multi-variant Linux Builds**:
    - Ubuntu 20.04 build: Maximum compatibility (glibc 2.31, Ubuntu 18.04+, Debian 10+, RHEL 8+)
    - Ubuntu 24.04 build: Modern performance (glibc 2.39, GCC 13, 5-15% faster Argon2)
  - **Windows Cross-Compilation**: MinGW-w64 on Ubuntu 24.04 for Win10/Win11 x64
  - **Docker-Based Builds**: Isolated, reproducible build environments
  - **Features**:
    - Git tag-based version detection
    - Automatic source tarball creation (`.tar.gz` and `.zip`)
    - Binary package generation with proper naming conventions
    - SHA256 checksum generation for all artifacts
    - Build caching for faster incremental builds
    - Support for local builds (`--local` flag) and clean builds (`--clean`, `--clean-all`)
    - Comprehensive release documentation auto-generation

- **Release Build Documentation** (`doc/build-rincoin-release.md`):
  - 524 lines of comprehensive build instructions
  - Platform selection guide (Ubuntu 20.04 vs 24.04)
  - Prerequisite installation for Debian 13, Ubuntu 24.04, RHEL 9
  - Berkeley DB 4.8 setup instructions
  - Docker configuration and troubleshooting
  - Build flags and optimization details
  - Package verification instructions

- **Fixes** (Commit 0b8a1599e):
  - Corrected build script logic for version detection
  - Fixed cache directory handling
  - Improved error messages and validation
  - Fixed Docker volume mount paths

#### 3.2 Modern Toolchain Compatibility

**Python 3.12 Support** (Commit 75d07d944):
- **Problem**: Old `xcb_proto 1.10` used deprecated Python `imp` module, removed in Python 3.12
- **Solution**: Upgraded dependencies for Ubuntu 24.04 compatibility:
  - `xcb_proto`: 1.10 → 1.17.0
  - `libxcb`: 1.10 → 1.17.0
- **Files**: `depends/packages/xcb_proto.mk`, `depends/packages/libxcb.mk`
- **Build System**: Updated archive format from `.tar.bz2` to `.tar.gz`

**MinGW-w64 / Qt 5.9.8 Compatibility** (Commits b68adf088, 29acf92db):
- **Problem**: Qt 5.9.8 redefines `TOUCHINPUT` structures already present in newer MinGW-w64 headers (Ubuntu 24.04)
- **Solution**: Added conditional compilation check in Qt patch
- **New Patch** (`depends/patches/qt/fix-mingw-touchinput.patch`):
  - Checks if `TOUCHEVENTF_MOVE` already defined before redefining structures
  - Prevents redefinition errors in `qwindowsmousehandler.cpp`
  - Allows Windows builds with modern MinGW-w64 toolchain

**Windows Build C++ Header Fix** (Commit 85ffc0f5f):
- **Problem**: `src/fs.cpp` used `std::numeric_limits` without including `<limits>` header
- **Solution**: Added `#include <limits>` to `src/fs.cpp`
- **Impact**: Fixed Windows cross-compilation errors

#### 3.3 Docker Build System Updates
- **Removed `sudo` from Docker Commands** (Commit 398fe7205):
  - Build script now assumes user is in `docker` group
  - Cleaner script logic without privilege elevation
  - Better practice for CI/CD integration

---

### 4. Network and Blockchain Updates

#### 4.1 Checkpoint Data Update (Commit 0ea66328c)
**Added 125 new checkpoints to accelerate initial sync:**

- **Block Range**: Extended checkpoints from ~310,000 to **block 435,935**
- **File Modified**: `src/chainparams.cpp`
- **Checkpoint Interval**: Approximately every 1,000-2,000 blocks
- **Purpose**: 
  - Speeds up initial blockchain download by skipping full validation for old blocks
  - Provides additional security against chain reorganization attacks
  - Reduces CPU load during sync for blocks before checkpoint height

#### 4.2 Checkpoint Generation Tool (Commit 973663a10)
**Added developer tool for automated checkpoint generation:**

- **New Tool**: `contrib/devtools/generate_checkpoints.py` (239 lines)
- **Functionality**:
  - Connects to local Rincoin RPC node
  - Queries block hashes at specified intervals
  - Generates C++ code for `chainparams.cpp` checkpoint array
  - Supports custom start/end block and interval parameters
- **Usage**: `python3 generate_checkpoints.py --start 1000 --end 435935 --interval 2000`

#### 4.3 Network Parameters (Commits de08fd440, 07571879c)
**Complete testnet and regtest network configuration:**

- **DNS Seeds Updated**: New DNS seed nodes for improved peer discovery
- **IP Seeds**: Updated hardcoded peer addresses for fallback connectivity
- **Testnet Genesis Block**: New testnet genesis block with proper difficulty and timestamp
- **Regtest Parameters**: Full regtest configuration for development environments
- **Base58 Prefixes**: Corrected address prefixes for testnet and regtest networks

---

### 5. Developer Tools

#### 5.1 Genesis Block Miner (Commit 0d87d0313)
**Added tool for mining genesis blocks for new networks:**

- **New Tool**: `src/tools/genesis_miner.cpp` (111 lines)
- **Build Integration**: `src/tools/Makefile.am` with standalone compilation
- **Functionality**:
  - Mines genesis block with configurable parameters (timestamp, bits, nonce range)
  - Supports custom block messages and timestamps
  - Uses Rinhash algorithm for block header hashing
  - Outputs block hash, nonce, and genesis block C++ initialization code
- **Use Case**: Creating genesis blocks for testnet, regtest, or new forks

#### 5.2 Base58 Prefix Test Utility (Commit de08fd440)
**Added testing utility for address encoding:**

- **New Tool**: `test/util/base58prefixes-wallet-test.py` (49 lines)
- **Purpose**: Verify Base58 address prefix encoding for different network types
- **Tests**: Validates address generation for mainnet, testnet, and regtest

---

### 6. Visual Updates

#### 6.1 New Application Icons (Commit bd5a96a0f)
**Refreshed application iconography:**

- **Updated Files**:
  - `src/qt/res/icons/bitcoin.ico`: 60KB → 205KB (higher resolution, multiple sizes)
  - `src/qt/res/icons/bitcoin_testnet.ico`: 60KB → 205KB
  - `src/qt/res/icons/rincoin.png`: 1.15MB → 82KB (optimized)
  - `src/qt/res/icons/rincoin_splash.png`: 1.15MB → 82KB (optimized)

- **Improvements**:
  - Higher quality icons for modern high-DPI displays
  - Optimized PNG files reduce binary size by ~2MB
  - Multi-resolution ICO files for better Windows integration

---

### 7. Version Updates

#### 7.1 Version Configuration
**File Modified**: `configure.ac`
```
_CLIENT_VERSION_MAJOR: 1
_CLIENT_VERSION_MINOR: 0
_CLIENT_VERSION_REVISION: 4
_CLIENT_VERSION_BUILD: 0
_CLIENT_VERSION_IS_RELEASE: true
_COPYRIGHT_YEAR: 2026
```

---

### 8. Performance Enhancements

#### 8.1 Sequential Blockfile Reading (Commit bc6f40bfc)
**Optimized block file I/O for faster sync:**

- **New Feature** (`src/flatfile.cpp`, `src/flatfile.h`):
  - Added sequential read hint system for block files
  - Advises OS to prefetch sequential data (Linux: `posix_fadvise` with `POSIX_FADV_SEQUENTIAL`)
  - Reduces I/O latency during IBD by optimizing read-ahead behavior

- **Integration** (`src/validation.cpp`, `src/init.cpp`):
  - Applied to block file reading during chain validation
  - Automatically enabled during initial sync operations
  - Improves disk throughput for spinning drives and SSDs

---

## Commit History Summary

### Critical Fixes
- **7236807** Fix AVX512 Argon2d: use proper 8-argument macros with SWAP_HALVES/QUARTERS
- **a94de31** Fixed versions of some hashing structures (AVX2/SSSE3 BLAMKA fixes)
- **85ffc0f** Add missing `<limits>` header for Windows build
- **75d07d9** Build: upgrade xcb_proto and libxcb to 1.17.0 for Python 3.12 support
- **b68adf0** Build: fix Qt 5.9.8 compatibility with newer MinGW-w64

### New Features
- **b5c48af** Qt: Add shift+click range selection to coin control dialog
- **29acf92** Qt shift+click correction (implementation)
- **8429a55** Release build tools
- **973663a** Generate checkpoints for chainparams.cpp
- **0d87d03** Genesis block miner tool

### Network/Data Updates
- **0ea6632** New checkpointData up to block 435935
- **de08fd4** Chainparams: new dns+ip seeds, complete new testnet+regtest params incl. genesis

### Build System
- **0b8a159** Release build correction
- **92a5059** Release build tool update (documentation)
- **398fe72** Removing sudo in the docker calls
- **92ef0f1** Version changed to 1.0.4

### Visual Updates
- **bd5a96a** New icons

### Core Optimizations
- **c0e59cf** Rinhash: add native CPU optimizations (SSSE3, AVX2, AVX512 with dispatch)
- **3bb8c83** Speed up Qt sync and payment dialogs
- **bc6f40b** Sequential blockfile read
- **0757187** TestNet chainparams + version update

### Rolled Back
- **a75de64** Argon2 mempool rollback (unstable) - removed memory pooling implementation (see Appendix D)

---

## Files Changed Summary

**Total Modified**: 47 files  
**Total Additions**: +3,847 lines  
**Total Deletions**: -882 lines

### Core Crypto/Hashing (15 files)
- `src/crypto/argon2/*`: SIMD implementations and fixes
- `src/crypto/rinhash.cpp`: Dispatch integration

### Qt Interface (4 files)
- `src/qt/coincontroltreewidget.{cpp,h}`: Shift+click selection
- `src/qt/coincontroldialog.{cpp,h}`: Performance optimizations
- `src/qt/modaloverlay.cpp`: Sync dialog updates

### Build System (9 files)
- `configure.ac`: Version and CPU feature detection
- `src/Makefile.am`: SIMD module integration
- `depends/packages/{qt.mk,libxcb.mk,xcb_proto.mk}`: Dependency updates
- `depends/patches/qt/*.patch`: Qt compatibility patches
- `contrib/build_release.sh`: Release automation
- `doc/build-rincoin-release.md`: Build documentation

### Network/Blockchain (3 files)
- `src/chainparams.cpp`: Checkpoints and network parameters
- `src/chainparamsseeds.h`: IP seeds
- `src/fs.cpp`: Header fix

### Developer Tools (4 files)
- `contrib/devtools/generate_checkpoints.py`: Checkpoint generator
- `src/tools/{Makefile.am,genesis_miner.cpp}`: Genesis miner
- `test/util/base58prefixes-wallet-test.py`: Address testing

### Validation/Storage (4 files)
- `src/validation.{cpp,h}`: Sequential read integration
- `src/flatfile.{cpp,h}`: Sequential read hint system
- `src/init.cpp`: Initialization logic

### Visual Assets (4 files)
- `src/qt/res/icons/*.{ico,png}`: Updated icons

### Documentation (1 file)
- `README.md`: Updated build information

---

## Testing Recommendations

### Critical Testing Areas

1. **Hash Verification**:
   - Verify block hash consistency across different CPU types
   - Test SIMD dispatch correctly selects AVX512/AVX2/SSSE3/Reference
   - Compare hashes from v1.0.1 (reference only) vs v1.0.4 (SIMD) on same blocks

2. **Cross-Platform Builds**:
   - Test Ubuntu 20.04 build on Ubuntu 18.04, 20.04, 22.04, 24.04
   - Test Ubuntu 24.04 build on Ubuntu 24.04 and Debian 12
   - Test Windows build on Windows 10 and Windows 11

3. **Qt Wallet Features**:
   - Test shift+click selection in coin control (tree and list modes)
   - Verify correct amount calculation with range selection
   - Test edge cases: selecting ranges with disabled items, hidden items

4. **Network Synchronization**:
   - Verify checkpoint validation up to block 435,935
   - Test initial blockchain download speed improvement
   - Verify testnet connectivity and genesis block

5. **Performance Benchmarks**:
   - Compare block validation speed vs v1.0.1
   - Measure Argon2 hashing performance improvement per CPU type
   - Benchmark Qt dialog responsiveness during sync

---

## Known Issues & Limitations

1. **Memory Pooling Disabled**: Argon2 memory pooling proved unstable and was removed. Standard allocation is used instead.

2. **AVX512 Requirement**: AVX512 builds require only `AVX512F`, not `AVX512DQ`. Most Skylake-X and later CPUs support this.

3. **Qt 5.9.8**: Using older Qt version for compatibility. Qt 6.x migration planned for future release.

4. **Checkpoint Centralization**: Hardcoded checkpoints reduce decentralization but improve sync speed. Critical security assumption: checkpointed blocks are trusted.

---

## Upgrade Notes

### From v1.0.1 or Earlier
- **Mandatory Upgrade**: No consensus changes, but highly recommended for performance improvements
- **Backup Wallet**: Always backup `wallet.dat` before upgrading
- **Clean Shutdown**: Stop old version cleanly with `rincoin-cli stop`
- **Binary Replacement**: Replace binaries and restart
- **No Reindex Required**: Blockchain data is compatible

---

## Credits

**Lead Developer**: takologi (takologi@users.noreply.github.com)

**Upstream References**:
- Bitcoin Core project for base codebase
- PHC Argon2 reference implementation for SIMD algorithm guidance

---

## Appendix: Technical Deep Dive

### A. SIMD Optimization Architecture

The dispatch system uses a three-tier approach:

1. **Runtime Detection** (`argon2_dispatch.c`):
   - CPUID instruction queries CPU features (EAX=1, EAX=7)
   - Atomic initialization ensures thread-safe single detection
   - Feature flags: `SSSE3` (bit 9 in ECX), `AVX2` (bit 5 in EBX), `AVX512F` (bit 16 in EBX)

2. **Function Pointer Selection**:
   ```c
   if (cpu_features.has_avx512f)
       fill_memory_blocks_ptr = fill_segment_avx512;
   else if (cpu_features.has_avx2)
       fill_memory_blocks_ptr = fill_segment_avx2;
   else if (cpu_features.has_ssse3)
       fill_memory_blocks_ptr = fill_segment_ssse3;
   else
       fill_memory_blocks_ptr = fill_segment_ref;
   ```

3. **SIMD Register Usage**:
   - **SSSE3**: 128-bit `__m128i` (XMM registers) - processes 2x 64-bit words
   - **AVX2**: 256-bit `__m256i` (YMM registers) - processes 4x 64-bit words
   - **AVX512**: 512-bit `__m512i` (ZMM registers) - processes 8x 64-bit words

### B. BLAKE2b Round Transformation

The BLAMKA (BLAKE2b Modified) compression function uses:

**Row Processing** (BLAKE2_ROUND_1):
- Operates on consecutive state elements: `(S[0],S[1],S[2],S[3],S[4],S[5],S[6],S[7])`
- Requires `SWAP_HALVES`: Swaps lower/upper halves of SIMD vectors for inter-element mixing
- Without proper swaps: data stays isolated within register boundaries → wrong hash

**Column Processing** (BLAKE2_ROUND_2):
- Operates on strided state elements: `(S[0],S[2],S[4],S[6],S[8],S[10],S[12],S[14])`
- Requires `SWAP_QUARTERS`/`UNSWAP_QUARTERS`: Rotates elements cyclically for column mixing
- Without proper rotations: columns don't mix correctly → wrong hash

### C. Build System Cache Strategy

The build script implements three-level caching:

1. **Source Downloads** (`DEPENDS_SOURCES_CACHE`):
   - Caches downloaded dependency tarballs (Qt, OpenSSL, BDB, etc.)
   - Shared across all builds to avoid redundant downloads
   - Persistent across clean builds

2. **Built Dependencies** (`DEPENDS_BUILT_CACHE`):
   - Caches compiled dependencies per target (linux/win64)
   - Dramatically speeds up rebuilds (20 minutes → 5 minutes)
   - Invalidated by `--clean` flag

3. **Docker Images**:
   - Base OS images cached by Docker
   - Custom build images rebuilt when Dockerfile changes
   - Removed with `--clean-all` flag

### D. Argon2 Memory Pool Implementation (Rolled Back)

**Context**: During development, a memory pooling system was implemented for Argon2 hash calculations to reduce allocation overhead.

**Implementation Details** (Commit c0e59cf3f - original, reverted in a75de64fa):
- Created `src/crypto/argon2/argon2_mempool.c` (219 lines) and `argon2_mempool.h` (81 lines)
- Implemented a pre-allocated memory pool for Argon2 block allocations
- Goal: Reduce malloc/free overhead during repeated hash operations
- Used thread-local storage to maintain per-thread memory pools
- Automatic pool growth when additional memory needed

**Why It Was Rolled Back** (Commit a75de64fa):
- **Instability**: Memory pooling caused intermittent crashes under heavy load
- **Thread Safety Issues**: Complex interaction with multi-threaded mining operations
- **Minimal Performance Gain**: Standard allocation proved sufficiently fast
- **Complexity**: Added significant code complexity for negligible benefit
- **Memory Pressure**: Pools held memory longer than necessary, increasing RSS

**Decision**: Complete removal of memory pooling code
- Reverted to standard `malloc`/`free` for Argon2 allocations
- System allocator optimization (jemalloc/tcmalloc) provides better results
- Simpler code is more maintainable and reliable
- Memory allocation is not the bottleneck - computation time dominates

**Files Removed**:
- `src/crypto/argon2/argon2_mempool.c`
- `src/crypto/argon2/argon2_mempool.h`
- References in `src/crypto/argon2/Makefile.am`
- Usage in `src/crypto/rinhash.cpp`

**Lesson Learned**: Premature optimization. Profile before optimizing, and measure the actual impact. In this case, the complexity cost outweighed any theoretical performance benefit.

---

**End of Release Notes**
