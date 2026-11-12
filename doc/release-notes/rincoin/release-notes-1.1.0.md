v1.1.0 Release Notes
====================

Rincoin Core version 1.1.0 is now available from:

  <https://github.com/Rin-coin/rincoin/releases>

This release supersedes the release candidates `v1.1.0-rc1`,
`v1.1.0-rc2` and `v1.1.0-rc3`. Its code is that of `v1.1.0-rc3`; the
two differ in the version and the documentation only (see "Release
candidates" below).

This is a MAJOR release under RIP-0001. It carries RIN3 transaction-
version enforcement, which activates unconditionally at block 840,000,
together with the P2P signalling that lets upgraded nodes find each
other before then, and it restates the Customized Halving schedule
that v1.0.6 already shipped so that mainnet and the 1/1000-scale test
networks share one rule. Every consensus change in this release was
exercised in Rincoin-Sim at 1/1000 scale before being shipped here,
and each change ported from Sim records the Sim commit in the Core
commit that carries it.

**Every node must be running v1.1.0 before block 840,000.** A node on
v1.0.6 or earlier does not enforce RIN3: from that height it accepts
blocks that v1.1.0 rejects, and can end up following a different
chain.

Please report bugs using the issue tracker at GitHub:

  <https://github.com/Rin-coin/rincoin/issues>

To receive release notifications, watch the repository on GitHub or
join the community Discord linked from the README.

How to Upgrade
==============

If you are running an older version, shut it down. Wait until it has
completely shut down (which might take a few minutes in some cases),
then unpack the release archive and copy over `rincoind`,
`rincoin-cli`, `rincoin-tx` and `rincoin-wallet` (and `rincoin-qt`
where the archive includes it). No chain data or wallet migration is
required.

After upgrading, confirm the version and the RIN3 service bit:

```
$ rincoind -version | head -1
Rincoin Core version v1.1.0

$ rincoin-cli getnetworkinfo | grep -A8 localservicesnames
```

`RIN3` must appear in `localservicesnames` and `protocolversion` must
read `70018`.

Compatibility
=============

Rincoin Core v1.1.0 is built and tested on Ubuntu 24.04 (x86_64,
g++ 13.3.0). The Linux x86_64 binaries are the release artifacts this
project builds natively and verifies. Windows x64 and ARM64 builds,
where published, are produced by the
`depends` cross-compilation path and are marked experimental until the
verification checklist in `doc/release-process.md` section 10-6 has been
completed for them.

Release candidates
==================

Commit hashes refer to <https://github.com/Rin-coin/rincoin>.

Three candidates preceded this release. The notes published with the
second and third list what changed since the candidate before, with
corrections to its notes; the changes themselves are also described
under "Notable changes" below.

- `v1.1.0-rc1` (a1b12dc8c) was the first.
- `v1.1.0-rc2` (92f6352c1) fixed the funding of transactions through
  `fundrawtransaction`, `walletcreatefundedpsbt` and `send`, which on
  rc1 kept the caller's legacy version (5709a60b8; merged as 433759964
  via rincoin-core/rincoin#3). See "Funded transactions carry the RIN3
  version" under Wallet.
- `v1.1.0-rc3` (9a1cb9c31) removes legacy-version transactions from
  the mempool when the block before the fork height is connected,
  where on rc2 they stayed; the rule is RIP-0009 section 7 (SHOULD),
  in the revision of 2026-10-23 (5bae46c8a; merged as ec189b863 via
  rincoin-core/rincoin#4). See "Mempool clean-up at the fork height"
  under Mempool policy.
- This release differs from `v1.1.0-rc3` in the version, which
  0abab397c sets to 1.1.0, and in the documentation.

Notable changes
===============

Consensus
---------

### RIN3 transaction-version enforcement at block 840,000 (RIP-0009)

From block 840,000, standard transactions must carry
`nVersion = 0x52494E33` ("RIN3"). Enforcement is dual-layer: at mempool
entry in `PreChecks`, which tests the height of the next block, and at
block connection in `ContextualCheckBlock`, with the reason string
`bad-tx-rinhash-version`. Coinbase, HogEx, and MWEB-only transactions
are exempt. Transactions on the pre-fork chain are unaffected.
(37dd72f00, 51ad19bd9)

The block template refuses legacy-version transactions from the fork
height, and RIN3-version transactions are standard for relay.
(ba6d1415b)

A peer that relays a legacy-version transaction after the fork is not
penalised: the rejection is classified as a recent consensus change
rather than a consensus failure, so nodes that have not upgraded and
still relay such transactions are not disconnected for it. (9426ca366)

`feature_rin3_enforcement.py` exercises all of this end-to-end and
passes its 10 subtests on this tree. (75f7c0746)

### Customized Halving schedule restated as interval scaling (RIP-0002, RIP-0010)

The Scenario II schedule shipped in v1.0.6 as branches on literal
block heights. `GetBlockSubsidy()` now derives every phase boundary
from `nSubsidyHalvingInterval` alone (4x, 10x, 20x, 30x), so mainnet at
interval 210,000 and testnet/regtest at interval 210 run one rule with
proportional timing. Mainnet values are unchanged: 6.25 RIN through
block 839,999, 4.00 RIN from block 840,000, then 2, 1, and 0.6 RIN at
the later phase boundaries. The fork height is
`consensus.nRinHashForkHeight = 840000`. (ebfcaff4e, bf91d99b4)

Measured on this tree: `getblockstats` reports a subsidy of
625,000,000 satoshi at height 839 and 400,000,000 at height 840 on
regtest (1/1000 scale).

### Chain parameter self-checks

Each chain parameter constructor now asserts that the Customized
Halving fork height equals four times the halving interval, and
`CMainParams` additionally asserts that the derived supply cap equals
`MAX_MONEY`. `SetupServerArgs` constructs all networks' parameters at
startup to fill in the help text, so every `rincoind` start checks
every parameter set. Both assertions were verified by breaking them:
a fork height off by one and a cap off by one satoshi each abort
`rincoind` with exit status 134, naming the assertion; reverted, it
starts normally. (c4594f4e3, 9f53e04aa)

### Supply accounting, Stage A (RIP-0002)

`GetTotalSubsidy()` expresses the emission schedule's integral in
closed form over the phase boundaries, and `GetSupplyCap()` derives the
168,000,000 RIN cap from the halving interval. Unit tests pin the
closed form against a brute-force sum of `GetBlockSubsidy()`, including
the height at which cumulative issuance reaches the cap (234,587,500).
(1f388261d, c2bafc878, 9577511dc, bb3a074ff; merged as 70ed956ba via
rincoin-core/rincoin#2)

This is accounting only. `GetBlockSubsidy()` is unchanged, no
consensus rule reads the new constant or calls the new functions, and
emission is not altered. Enforcement of the cap is Stage B and
requires a separate RIP.

### MWEB and Taproot sealed on mainnet (RIP-0004, RIP-0011)

Mainnet MWEB and Taproot deployments are set to `NEVER_ACTIVE`,
replacing the Litecoin-inherited height-based values. MWEB is deferred
pending the SQLite descriptor-wallet migration; Taproot is deferred
because its inherited activation heights are not aligned to Rincoin's
BIP9 window. Testnet and regtest are unaffected: MWEB signals from
block 840 on testnet (`nStartHeight = 840`, `nTimeoutHeight = 1050`,
BIP8) and Taproot is `ALWAYS_ACTIVE` on both. (cd1fae169)

### BIP9 window corrected on mainnet

`nMinerConfirmationWindow` is 7,920 (1,980 x 4) and
`nRuleChangeActivationThreshold` is 5,940 (75%), replacing the
upstream 8,064 / 6,048. The sealing above and this change land in the
same commit, so no live deployment observes the new window
retroactively. (cd1fae169)

### `-vbparams` parser fix (Litecoin #1095)

The parser zero-initialises `nStartHeight` / `nTimeoutHeight`, which
were previously uninitialised on the legacy three-argument form. This
is the Rincoin-side application of the fix reported upstream as
litecoin-project/litecoin#1095. (37dd72f00)

### HogEx with no inputs (RIP-0004 section 4)

The first HogEx transaction of an MWEB block has no inputs when the
activation block carries no peg-ins. Context-free validation in
`consensus/tx_check.cpp` rejected it as `bad-txns-vin-empty`; HogEx is
now exempt from that check, and its inputs are validated contextually
while MWEB is active. This is a deliberate fork-local divergence from
upstream Litecoin, which retains the rejection. RIP-0004 section 4.4
records the audited consequences of the exemption on a mainnet where
MWEB is sealed, and condition S-7 schedules its retirement, bundled
with any MWEB re-activation, as a consensus tightening. (e68cf8fe5)

P2P and network
---------------

### NODE_RIN3 service bit and protocol version 70018 (RIP-0009)

Nodes advertise `NODE_RIN3` (service bit 25) and `PROTOCOL_VERSION`
70018. `MIN_PEER_PROTO_VERSION` is unchanged, so RIN3 support is a
capability rather than a version floor: peers that do not signal it
are still connected and served. (fae242216, cac01210e)

Automatic outbound connections prefer peers that advertise the bit
(`GetDesirableServiceFlags`), which gives every upgraded node a
connected relay subgraph for RIN3 transactions, which legacy nodes drop
as non-standard. Inbound connections from legacy peers are accepted,
and manual connections (`-addnode`, `-connect`) are exempt from the
preference. This mirrors the outbound preference Bitcoin applied to
`NODE_WITNESS` at the SegWit rollout and is what preserves soft-fork
topology up to the activation height. (6f7b056ba)

`GetDesirableServiceFlags` now includes `NODE_RIN3`, so a v1.1.0 node
queries its DNS seeds with the filter prefix `x3000009`
(`NODE_NETWORK | NODE_WITNESS | NODE_MWEB | NODE_RIN3`). The project's
seeder was given that whitelist entry on 2026-08-28 (Aevust/seeder#2);
before it, the default whitelist rejected the filter and such queries
returned empty. Anyone running a DNS seeder for this network needs the
same entry. Until nodes advertising RIN3 appear, the filtered query
answers with nothing, which is expected rather than a failure. The
seeds are `seed.rincoin.org` and `seed.rincoin.net`. (b0966f7fe)

Measured on this tree: `localservices` reports `0000000003800449`
with `RIN3` among the names, and the version message on the wire
carries 70018 and the same service mask. `p2p_rin3_services.py`
passes its 3 subtests. (7445cf336)

### Fixed seed list

The fixed seed list (`src/chainparamsseeds.h`) is regenerated from
`contrib/seeds/nodes_main.txt` and `nodes_test.txt`, which now name
the two nodes this project operates. The previous list was
hand-written: its input files still held Litecoin's node lists, and
the testnet entries encoded port 19539 where `nDefaultPort` is 19555.
Entries that operated outside the project, and one that no longer answers
on any port, were removed. Fixed seeds are the fallback used when DNS
seeds are unavailable. (b8f2b0597)

Mempool policy
--------------

### Mempool clean-up at the fork height (RIP-0009 section 7)

From the fork height, a block may contain no transaction without the
RIN3 version other than the coinbase, the HogEx, and MWEB-only
transactions, and `PreChecks()` refuses such transactions once the next
block is at or above the fork height. On `v1.1.0-rc2`, transactions
accepted before that stayed in the mempool: they could be mined only
after a reorg below the fork height, and `abandontransaction` refused
them while they were there. Now, when `ConnectTip()` connects the
block before the fork height, right after `removeForBlock()`,
`CTxMemPool::removeForRIN3Fork()` removes every transaction that is not
MWEB-only and lacks the version, with all of its in-mempool descendants,
with the new reason `MemPoolRemovalReason::RIN3_FORK`. Descendants are
removed and notified before their ancestors, so a wallet never sees an
ancestor leave while a descendant still counts as in the mempool; an
MWEB-only child of a legacy peg-in leaves with the peg-in. The clean-up
runs each time that height is connected, including after a reorg or
`invalidateblock`; a node in initial block download or reindex runs it
once when it passes that height. (5bae46c8a)

One count line is always logged, even when nothing is removed:

```
RIN3 fork: removed N transaction(s) without the nVersion marker and M descendant(s) of them from the mempool (V vbytes, T ms)
```

One line per removed transaction is logged under `-debug=mempool`.
Prioritisation (`mapDeltas`) is kept, and fee estimation counts the
removed transactions as failures, as it does for expired ones.
`CTxMemPool::check()` asserts the invariant once the next block is at or
above the fork height; the check is on by default on regtest and on
mainnet only with a nonzero `-checkmempool`. Consensus, `PreChecks()`
and the block assembler are unchanged, and nodes on earlier versions
keep the stale transactions. (5bae46c8a)

The wallet handles `RIN3_FORK` like `CONFLICT`: the transaction is
unconfirmed and no longer in the mempool, its change is no longer
trusted, `abandontransaction` succeeds at once, a re-creation from the
same inputs is accepted, and `-walletnotify` fires once for each wallet
transaction removed. Unlike in a conflict, no block spends the inputs of
such a transaction: it stays unconfirmed, and its inputs stay spent,
until it is abandoned, until a transaction spending one of the same
inputs confirms, or until a reorg below the fork height confirms it.
(a06b704e4)

The clean-up changes nothing in ZMQ, which publishes each removal on
the `sequence` topic (`-zmqpubsequence`); `hashtx` and `rawtx` do not
announce removals.

`UpdateForRemoveFromMempool()` skips the re-indexing of ancestors that
are in the set being removed; ancestors that stay are updated as before,
which `mempool_rin3_fork_cleanup.py` [09] checks. The change applies to
every `RemoveStaged()` path; the state of the transactions that stay is
unchanged. (aa9454ffb)

Measured on 2026-10-25 for rincoin-core/rincoin#4 on the tree of
2ad3d9e57, built through the `depends` `config.site` with wallet and
ZMQ, on an Intel Core i5-10500 (6 vCPUs), regtest, `-maxmempool=300`,
`-checkmempool=0`: removing 227,000 legacy-version transactions in
chains of 25 (285 MB) took 6529.5, 6742.0 and 6812.9 ms (n=3), during
which RPC calls that need the chain state or the mempool wait (the
longest wait 6.792 s); about 20 MB (17,000 transactions) took 163.3 ms
(n=1). In Rincoin-Sim the 285 MB case took a median of 8.8 s with this
change and 10.3 s without the re-indexing skip and with every removed
transaction logged (n=5 each).

Wallet
------

### Taproot wallet guard (RIP-0011)

While the Taproot deployment is sealed, `CWallet::CreateTransaction`
refuses to create outputs paying to witness version 1 or later.
Without the guard such outputs would be anyone-can-spend at the
consensus level on mainnet, and the hazard is reachable from
`sendtoaddress`. The refusal surfaces as RPC error -6. MWEB recipients
are exempt. `feature_taproot_wallet_guard.py` covers both branches of
the guard and passes its 3 subtests on this tree. (56843e34d,
80d5d831a)

### RIN3 version emitted one block early

The wallet switches to the RIN3 transaction version once the last
block it has processed is one block below the fork height, so a
transaction created at the boundary is not left with a legacy version
when the block that includes it lands on or after 840,000. The wallet
RPCs that create, fund or bump a transaction first wait for the wallet
to process the blocks connected, or being connected, when they are
called; the GUI does not (see "Known issues"). (7e95083bd)

### Funded transactions carry the RIN3 version

On v1.1.0-rc1 the caller's default `nVersion` of 2 survived funding
through `fundrawtransaction`, `walletcreatefundedpsbt` and `send` at
any height, so once block 839,999 has connected, the node rejects the
result with `bad-tx-rinhash-version`; `send` returned a txid for a
transaction the node had not accepted into its mempool (measured on
the published rc1 binaries, 2026-09-25). `CWallet::FundTransaction()`
copied the output amounts and the inputs of the transaction
`CreateTransaction()` built, but not its version. It now copies the
version as well when the caller's transaction has
`CTransaction::CURRENT_VERSION`, so these RPCs switch to the RIN3
marker one block below the fork height, where `txassembler.cpp`
switches the wallet's own transactions. Any other version the caller
set is kept, so the workaround published on the rc1 release page,
setting the marker before funding, keeps working; a caller that sets
2 itself cannot be told apart from one that left the default and gets
the wallet's version too. Ported from Rincoin-Sim v1.1.0.2, released
2026-10-05. (5709a60b8)

Two functional tests cover it. `wallet_rin3_fund_version.py` pins the
version each of the three RPCs gives on both sides of the switch.
`wallet_rin3_boundary_rescue.py` follows a legacy-version transaction
broadcast before the fork height that did not confirm: on
`v1.1.0-rc2`, a mempool that held it kept it, and a restart was the
way out; from `v1.1.0-rc3` on it leaves the mempool when the block
before the fork height connects, and the test checks the
notification, that its change is not spent, and that abandon,
`bumpfee` and re-creation work without a restart (see "Mempool
clean-up at the fork height").
(1634eb6d2, 106f0b73e, 5bae46c8a)

### `-walletdir` with a trailing separator

Since Boost 1.78, `fs::canonical()` no longer strips a trailing path
separator, so a user-supplied trailing slash in `-walletdir` was
retained in the stored path. It is now removed after
canonicalisation, mirroring Bitcoin Core PR 24104. Wallet operation
was unaffected; the walletinit unit tests that check the stored path
pass again. (07e6bef0a)

Logging
-------

### Header-sync timing moved behind `-debug=bench`

Two per-batch header-sync timing lines (`HEADERSYNC-PERF`) were
written unconditionally and accounted for the large majority of log
volume on a synced v1.0.6 node (197 of the last 200 lines on one
production node, about 8 MB per day). They now use the `bench`
category, which this tree already uses for comparable timing output
elsewhere. Output is unchanged with `-debug=bench`; without it the
lines are suppressed. Operators who relied on these lines should add
`-debug=bench`. (2515fc659)

Tests
-----

### Functional test framework synchronised with the chain

The functional test framework now matches `chainparams.cpp`: message
magic bytes on all three networks, Rincoin address encodings (except
that for P2SH it took `SCRIPT_ADDRESS`, where the node encodes with
`SCRIPT_ADDRESS2`; see "Functional tests") and `RIN` fee-rate units in
place of inherited Litecoin values, the `indexes/` directory preserved
in the cached datadir (tests that use the 199-block cache previously
crashed in setup because `-blockfilterindex` defaults to on in this
tree), and the `rin_` test prefix accepted by `test_runner.py`.
(065898039 through 646715055)

Eight tests written for Rincoin are registered:
`feature_rin3_enforcement.py` (10 subtests),
`feature_taproot_wallet_guard.py` (3), `p2p_rin3_services.py` (3),
`wallet_rin3_fund_version.py` (7), `wallet_rin3_boundary_rescue.py`
(12), `mempool_rin3_fork_cleanup.py` (9), `mempool_rin3_fork_reorg.py`
(3) and `mempool_rin3_fork_mweb.py` (5). The Qt RPC console test uses
the Rincoin mainnet Merkle root. (75f7c0746, 80d5d831a, 7445cf336,
e09a447fb, 1634eb6d2, 106f0b73e, 5bae46c8a, 2ad3d9e57)

### Unit tests

`validation_tests` gains a full regtest-scale sweep pinning
`GetTotalSubsidy()` against `GetBlockSubsidy()` for every height in
[0, 240000] and mainnet-scale boundary checks at S_fix and the cap
height. The unit suite now runs 500 cases. (bb3a074ff)

Build and release
-----------------

- The test, bench and Qt executables are named `test_rincoin`,
  `bench_rincoin` and `rincoin-qt`. (1488c8729, 11dc913a9,
  6a8534447)
- `contrib/release/` provides the multi-platform build Makefile and
  the signing script; `doc/release-process.md` describes the release
  procedure around them. (e2b753cc7, 6e361434d, fd201f357,
  929c130f2, adb43eb54, b6cfc0a34)
- The version is 1.1.0 (`_CLIENT_VERSION_RC = 0` in `configure.ac`;
  the three candidates carried 1, 2 and 3). `contrib/release/` derives
  artifact names and the git tag from `configure.ac`: distributed
  files carry `1.1.0` and the tag is `v1.1.0`. (c92864c64, 2bdf74061,
  126d21d36, 4b3ae145b, 0abab397c)
- `chainparams.cpp` includes `<stdexcept>` explicitly. (30d4da632)

Documentation and policy
------------------------

- `SECURITY.md` describes how to report vulnerabilities and the GPG
  policy for releases. The release signing key is no longer bundled in
  the tree and is published as `SECURITY.md` describes. (7096d0a57,
  456c6a29d, dbb667d16, e80a700ea, cb9bde370, 524138cfb)
- The README describes the release contents, the emission schedule, and
  the test-suite state as measured. (d27d8074e, 0f70caace, de22a42fc)

Verification
============

All measurements below were taken on the tree of the third
candidate's version bump (4b3ae145b), on Ubuntu 24.04 (x86_64), built
through the `depends` `config.site` without the GUI, except where
another tree or build is named, as for the mined testnet chain, which
was measured on v1.1.0-rc1 (a1b12dc8c); the consensus code is
unchanged since then. This release's tree differs from 4b3ae145b in
`configure.ac`, where 0abab397c sets the version, and in the
documentation; `src/` and `test/` are the same. Every commit from
c1020be63 on was verified against the release signing key; e68cf8fe5
and earlier commits are not signed with it. The Linux x86_64 release
binaries are built natively, as `doc/release-process.md` describes;
no native build of this tree was measured, and on the second
candidate's native build the functional suite also failed the two
`wallet_multiwallet.py` runs (see "Functional tests").

### Unit tests

```
$ ./src/test/test_rincoin
Running 500 test cases...
*** No errors detected

$ make check
exit status 0: the unit suite run per source file (121 files), the
util tests, libsecp256k1 2/2, univalue 3/3
```

Of the 500 cases, `script_assets_test` reports a warning and skips its
body because `DIR_UNIT_TEST_DATA` is unset, as it does upstream; the
other 499 pass without one.

### Functional tests

```
$ test/functional/test_runner.py --exclude feature_loadblock.py
  214 scripts: 121 passed, 51 failed, 42 skipped     (runtime 963 s)
```

The 51 failures are the set measured at v1.1.0-rc2 less
`wallet_multiwallet.py` and `wallet_multiwallet.py --usecli`, which fail
on a native build and pass on one built through `depends`, compared as
sets rather than counts, and the three scripts added in rc3
pass, as do the two added in rc2. Every one of them also fails
in the Rincoin-Sim baseline of 2026-09-03, which has three further
failures of its own: `feature_config_args.py`, which passes here, and
the two `wallet_multiwallet.py` runs. None points to a defect in the
node; the classes below say why. 50 were present in the first baseline
of this repository, taken on a native build on 2026-09-03 as soon as
the framework repairs let the suite run, and `p2p_addr_relay.py` was
intermittent when rc1 was measured and failed in every run taken since.
The set has been re-measured after every group of changes. They fall
into these classes:

- Address vectors and message-signing prefixes in older tests, and the
  framework's own keys on testnet and signet, still carry Litecoin
  values (`rltc1`, `tmweb`, WIF bytes, `Litecoin Signed Message:`); the
  tests fail on the encoding, not on the node.
- Other upstream values in the tests: the framework's `MAX_MONEY` is
  Litecoin's (`mempool_accept.py`); `rpc_blockchain.py`,
  `mining_basic.py` and `wallet_create_tx.py` set the mock time to the
  framework's `TIME_GENESIS_BLOCK`, upstream's regtest genesis time of
  2011, so the first block they ask the node to mine, which it dates
  after this regtest's genesis of 2025, is refused as `time-too-new`;
  `rpc_getblockstats.py` submits a pre-generated upstream regtest
  chain; and `rpc_dumptxoutset.py` expects an upstream block hash.
- Test-framework helpers derive block identity from SHA256d, where
  this chain uses RinHash for `GetHash()` and `GetPoWHash()`; tests
  that wait on a block by hash time out.
- `p2p_blockfilters.py` assumes upstream's regtest block spacing: at
  this regtest's 3,000 seconds per block, its stale block 1,000 blocks
  behind the tip counts as older than the 30 days within which the
  node serves stale blocks, and the node disconnects the peer that
  asks for that block's filter checkpoint (`getcfcheckpt`).
- `feature_dersig.py` and `feature_cltv.py` run into the RIN3 rule: the
  block each sends at height 1250 or 1350 carries a version-2
  transaction from `createpsbt`, which the node refuses in blocks from
  regtest height 840, so their buried-deployment checks fail. Were that
  transaction to carry the RIN3 version, each would fail next where it
  compares the node's tip with the block's SHA256d hash.
- Test values this tree changed that the node does not match: the
  framework encodes regtest P2SH addresses with version 196 since
  b3a6056f8, where the node uses 58 (three scripts), and two scripts
  expect `Invalid Rincoin address` where the node says `Invalid
  rincoin address`.
- `p2p_addr_relay.py`: for its rate-limit checks the test asks the node
  for an outbound connection to a mock peer that advertises
  `NODE_NETWORK | NODE_WITNESS | NODE_MWEB`; the node expects
  `NODE_RIN3` of outbound peers as well and closes the connection. A
  framework default, to be corrected in Sim first; intermittent when
  rc1 was measured, in every run for the second and third candidates.

Each class is tracked for a 1.1.x maintenance release.

`feature_loadblock.py` is excluded because `contrib/linearize`
identifies blocks by SHA256d and never matches on a RinHash chain, so
the test hangs rather than fails.

### Individual runs

| Test | Result |
| ---- | ------ |
| `feature_rin3_enforcement.py` | 10 subtests PASS |
| `feature_taproot_wallet_guard.py` | 3 subtests PASS |
| `p2p_rin3_services.py` | 3 subtests PASS |
| `wallet_rin3_fund_version.py` | 7 subtests PASS |
| `wallet_rin3_boundary_rescue.py` | 12 subtests PASS |
| `mempool_rin3_fork_cleanup.py` | 9 subtests PASS |
| `mempool_rin3_fork_reorg.py` | 3 subtests PASS |
| `mempool_rin3_fork_mweb.py` | 5 subtests PASS |
| `validation_tests` | 4 cases PASS (sweep included) |

### Fork boundary script

`scripts/sim-rin3-boundary.sh` from Rincoin-Sim at commit
`492b8f7fe1b637cda1103c77b1eea7ada9d8d388` (sha256 `5cecf09d`...), run
with `EXPECT_FUND_MARKER=1`, drives two nodes across the regtest fork
height and checks the transaction version on both sides, the subsidy at
the boundary, relay of legacy transactions, the funding RPCs
`fundrawtransaction` and `walletcreatefundedpsbt` and, since the
third candidate, the clean-up at the block before the fork height,
the abandon and the re-creation. Against this tree's binaries: PASS 19,
FAIL 0, INCONCLUSIVE 0. In mixed mode the second node runs an older
release, which keeps the legacy transaction, mines block 841 without
it, has its relay of it rejected without being disconnected or
discouraged, and follows three more blocks of this node: against the
published v1.1.0-rc2 binaries PASS 29, FAIL 0, INCONCLUSIVE 0, and
against Rincoin-Sim v1.1.0.2 PASS 29, FAIL 0, INCONCLUSIVE 0. Against
the published v1.1.0-rc2 binaries alone, single mode gives PASS 15,
FAIL 4, the four being the clean-up checks that rc2 lacks. The
script is not part of this tree. In single mode, the script of
492b8f7fe1 has 19 checks where the v1.1.0.2 script had 24: its mining
and relay checks now run in mixed mode only, and the four clean-up
checks are new.

### Consensus behaviour on regtest

```
$ rincoin-cli -regtest getblockstats 839 | grep subsidy
  "subsidy": 625000000,
$ rincoin-cli -regtest getblockstats 840 | grep subsidy
  "subsidy": 400000000,
$ rincoin-cli -regtest getblockstats 841 | grep subsidy
  "subsidy": 400000000,
```

### Consensus behaviour on a mined testnet chain

The same rules were exercised on v1.1.0-rc1 (a1b12dc8c) on a testnet
chain mined from genesis, where the difficulty adjustment is live
rather than pinned at the regtest minimum; the consensus code is
unchanged in the later candidates and in this release. The chain is
private: it was mined solely by this node with `generatetoaddress`
and had no peers at any point.

Every Customized Halving phase boundary, in satoshi:

| boundary | subsidy before | subsidy at and after |
| ---- | ---- | ---- |
| 210 | 5000000000 | 2500000000 |
| 420 | 2500000000 | 1250000000 |
| 630 | 1250000000 | 625000000 |
| **840** | **625000000** | **400000000** |

The MWEB deployment, as observed while the chain was being mined.
`getblockchaininfo` reports the state that applies to the next block,
so a tip of 839 already reports `started` with `since` 840:

| tip | bip8 status | since |
| ---- | ---- | ---- |
| 18 | defined | 0 |
| 839 | started | 840 |
| 1049 | locked_in | 1050 |
| 1260 | active | 1260 |

RIN3 enforcement, both directions, at a tip well above the testnet
fork height of 840:

- A wallet transaction was created with `sendtoaddress` and mined. Its
  version is `0x52494e33`.
- A transaction built with `createrawtransaction`, which emits version
  2, was signed and submitted with `sendrawtransaction`. The node
  answered with error -26 `bad-tx-rinhash-version`, and the
  transaction is absent from the mempool afterwards.

A record of this run, listing the commit, the digests of the binaries
that produced it, the chain's genesis hash and peer count, and every
value above, is published with the release together with the script
that produces it.

### Relation to Rincoin-Sim

The reference tree for the second candidate is Rincoin-Sim v1.1.0.2 at
commit `7d07316439428c29ec4ace6c56754b2ec932584d`, the tree that release
was verified on; `src/protocol.h`, `src/protocol.cpp`, `src/init.cpp`,
`src/amount.h`, `src/validation.h` and `src/test/validation_tests.cpp`
are byte-identical to it. The reference tree for the mempool clean-up is
Rincoin-Sim at commit `7dca6c412892b063b257148c771941b8e8e10b51`, merged
into its master as `492b8f7fe1b637cda1103c77b1eea7ada9d8d388`
(Aevust/rincoin-sim#7); the four commits of the third candidate apply
the changes of Sim's commits unchanged, and `src/txmempool.cpp`,
`src/txmempool.h`, `src/validationinterface.h`, `src/wallet/wallet.cpp`
and every file under `test/` are byte-identical to that commit.
`src/validation.cpp` differs from the clean-up's reference tree in one
line, the header-sync timing line, which is behind `-debug=bench` here
(2515fc659) and unconditional in Sim; from v1.1.0.2 it differs in that
line and the clean-up call. The rc1 notes listed that file as
byte-identical; it was not, for the same line. `src/chainparams.cpp`
differs in comments, whitespace, and the order of two assignments only;
the simulator's chain guard is in its `src/bitcoind.cpp`. Each Core
commit that ports a Sim change records the Sim commit hash in its
message. The Sim v1.1.0.2 release is at
<https://github.com/Aevust/rincoin-sim/releases/tag/v1.1.0.2>; the
archived build and test evidence of Sim v1.1.0 is at
<https://doi.org/10.5281/zenodo.21805345>.

Known issues
============

- The 51 functional test failures listed above. None affects node
  operation; they are defects in the tests, most of them inherited
  from upstream, and are tracked for 1.1.x.
- `p2p_node_network_limited.py` passes the service-mask check added
  in this release but still fails later at `wait_for_block`, for the
  SHA256d reason above.
- The man pages under `doc/man/` are the inherited Litecoin 0.21.4
  pages and do not describe this release. The third candidate's notes
  said they would be regenerated as part of the final release build;
  they are not, because that renames the pages and their entries in
  `doc/man/Makefile.am`, a build file, and this release changes only
  the version and the documentation after the last candidate.
  Regenerating them is tracked for 1.1.x.
- `build_msvc/` is the inherited Bitcoin 0.21.3 tree and is not a
  supported build path for this release. Windows binaries, where
  published, come from the `depends` cross-compilation path.
- MWEB and Taproot remain `NEVER_ACTIVE` on mainnet; see RIP-0004 and
  RIP-0011 for the conditions under which either is revisited.
- The mempool refuses replacements by default (`-mempoolreplacement`,
  inherited from Litecoin). Below the fork height, a legacy-version
  transaction a node holds still blocks its re-creation on that node;
  from the block before the fork height the clean-up removes it, and
  re-creation, `bumpfee` and `abandontransaction` work at once
  (`wallet_rin3_boundary_rescue.py`).
- At the block before the fork height, almost every unconfirmed
  transaction leaves the mempool of a node on this release, including
  unconfirmed payments to receivers. The sender's balance looks short by
  the change until the removed transaction is abandoned or re-created;
  its inputs stay spent meanwhile.
- A one-block reorg across the fork height can lead to a double payment
  if the sender re-creates a removed transaction from other inputs.
  Re-create it from the same inputs instead; `bumpfee` does this for a
  transaction that signals BIP 125. A transaction removed by a reorg
  across the fork height, rather than by the clean-up, leaves with
  reason `REORG`, for which `-walletnotify` does not fire; this follows
  from the code, and no test covers it. The same transaction can be
  removed with reason `RIN3_FORK` more than once across reorgs
  (`mempool_rin3_fork_cleanup.py` [07], without a wallet), so a wallet
  can be notified of it more than once; that is not tested.
- A node that starts with its tip at or above the block before the fork
  height loads no legacy-version transaction from `mempool.dat` and gets
  no `RIN3_FORK` notification for them (`wallet_rin3_boundary_rescue.py`
  [12]); this is the case for a node upgraded from an earlier version
  after that block. Find them with `gettransaction` (`confirmations` 0
  and `trusted` false) and release them with `abandontransaction`. A
  node stopped below that block loads them at its old tip and removes
  them, with the notification, when it connects that block ([11]).
- RPC calls that need the chain state or the mempool are not answered
  while the removal runs (it holds `cs_main` and the mempool lock): up
  to 6.8 s with 285 MB of legacy-version transactions under
  `-maxmempool=300` on the machine measured (see Mempool policy).
  Nodes on earlier versions keep the stale transactions, and a
  transaction without the RIN3 version, other than an MWEB-only one,
  that is still unconfirmed when the block before the fork height
  connects, or that is submitted once that block has connected, has to
  be re-created, and so do its descendants.
- For about a minute after the block before the fork height connects,
  avoid sending and abandoning from the GUI: the GUI can create a
  transaction without the RIN3 version before the wallet has caught up,
  and abandoning during a reorg has a pre-existing assert window.
  Neither was introduced by the third candidate; both follow from the
  code and are not tested, and the minute is a margin, not a
  measurement.
- A wallet RPC that is already under way when the node starts
  connecting the block before the fork height can still give a
  transaction version 2: the RPCs wait only for the blocks connected,
  or being connected, when they were called. `sendtoaddress`,
  `sendmany`, `send` and `bumpfee` then still return its txid, although
  the node refuses the transaction at entry or, if it got in first,
  removes it when that block connects; a refused one gets no
  `RIN3_FORK` notification. Find it with `gettransaction`
  (`confirmations` 0, `trusted` false) and release it with
  `abandontransaction`; after `bumpfee`, abandon the transaction it
  replaced as well, which still spends the same inputs and can no
  longer be bumped. This follows from the code and is not tested.
- Not tested: passing the fork height in `-reindex` or
  initial block download (the hook is in `ConnectTip()`, which both
  use); `testmempoolaccept` (the same `PreChecks()` as rc2); re-applying
  `mapDeltas` after a reorg. Between the 20 MB loads and the 285 MB
  loads, the only measurement is a 96 MB case in Rincoin-Sim, so no
  `-maxmempool` advice is given.
- The funding defect fixed in the second candidate was present in
  v1.1.0-rc1, measured on its published binaries. The rc1 release page
  carries the workaround for nodes still on rc1.

Node operator checklist
=======================

1. Upgrade every node to v1.1.0 before block 840,000.
2. Confirm `RIN3` in `localservicesnames` and `protocolversion` 70018.
3. If you operate a DNS seeder, give it the whitelist entry for the
   filter v1.1.0 sends, `x3000009` (Aevust/seeder#2); a seeder without
   it answers such queries with nothing.
4. If you relied on `HEADERSYNC-PERF` log lines, add `-debug=bench`.
5. Mining pools and exchanges: transactions you create once block
   839,999 has connected, other than the coinbase, must carry
   `nVersion = 0x52494E33`. The bundled wallet does this, except in
   the GUI before the wallet has caught up with that block and in a
   wallet RPC already under way when the node starts connecting that
   block (see "Known issues"); `v1.1.0-rc1` did not for
   `fundrawtransaction`, `walletcreatefundedpsbt` and `send` (see
   "Release candidates"). `createrawtransaction` and
   `createpsbt` give version 2, and `rincoin-tx` gives 2 with
   `-create`, 1 or 2 with `nversion=` (it takes no other value), and
   otherwise the version of the transaction it is given; none of them
   can set the RIN3 version, and funding through `fundrawtransaction`
   replaces version 2 with the wallet's version, the RIN3 one once the
   wallet has processed block 839,999, but keeps any other. External
   transaction builders must be updated.
   Anything without that version that is still unconfirmed when block
   839,999 connects leaves the mempool then, with all of its in-mempool
   descendants whatever their version, and from that tip on such
   transactions are refused at entry, so either way they have to be
   re-created.
6. Expect almost every unconfirmed transaction to leave the mempool when
   block 839,999 connects. `-walletnotify` fires once per removed wallet
   transaction, ZMQ publishes each removal on the `sequence` topic
   (`-zmqpubsequence`), and `debug.log` gets one count line. To keep
   the removed txids in the log, set `debug=mempool` in the
   configuration around the fork height.
7. If you upgrade a node from an earlier version after block 839,999
   has connected on it, its legacy-version wallet transactions do not
   load from `mempool.dat` and get no notification: after the restart,
   find them with `gettransaction` (`confirmations` 0, `trusted` false)
   and release them with `abandontransaction`. A node on this version
   that is stopped below block 839,999 loads them again and is notified
   when it connects that block.

Credits
=======

Thanks to everyone who directly contributed to this release:

- Aevust
- ysmreg

And to the developers of Litecoin Core and Bitcoin Core, on whose work
this tree is built.
