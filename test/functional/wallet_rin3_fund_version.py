#!/usr/bin/env python3
# Copyright (c) 2026 The Rincoin Core developers
# Distributed under the MIT software license, see the accompanying
# file COPYING or http://www.opensource.org/licenses/mit-license.php.

"""
wallet_rin3_fund_version.py

Rincoin RIN3 (nVersion replay protection) -- the version the wallet puts on
transactions it funds for a caller.

CWallet::FundTransaction() copies the amounts and the inputs of the
transaction CreateTransaction() built, and also its version when the
caller's transaction has CTransaction::CURRENT_VERSION (2), the value
rawtransaction_util.cpp gives a transaction it constructs.
CreateTransaction() reaches wallet/txassembler.cpp, which switches to
RIN_FORK_TX_VERSION when the wallet's last processed block is at
nRinHashForkHeight - 1 or above, so a transaction with that version funded
through fundrawtransaction, walletcreatefundedpsbt or send switches at the
same block as transactions the wallet builds itself.

Any other version the caller set is kept. The workaround published with the
v1.1.0-rc1 release notes -- setting the marker before funding -- depends on
that and is exercised here. A caller that set 2 itself cannot be told apart
from one that left the default, and gets the wallet's version.

Test matrix:
    [01] tip 838 : fundrawtransaction, walletcreatefundedpsbt and send
                                                      -> nVersion 2
    [02] tip 838 : caller set the marker, then fund   -> marker kept
    [03] tip 839 : fundrawtransaction, walletcreatefundedpsbt and send
                                                      -> marker; the PSBT is
                   processed, finalized and sent, and all three
                   transactions are mined into block 840
    [04] tip 840 : walletcreatefundedpsbt             -> marker
    [05] tip 840 : caller set nVersion 2, then fund   -> marker (not kept:
                   2 is the default and cannot be told apart from it);
                   setting 2 after funding gives a transaction the
                   mempool rejects with bad-tx-rinhash-version
    [06] tip 840 : sendtoaddress                      -> marker (control)
    [07] tip 840 : send                               -> marker, and it is in
                   the mempool

Not covered here: the enforcement rules themselves, which
feature_rin3_enforcement.py covers, and the boundary behaviour of a node
pair, which scripts/sim-rin3-boundary.sh measures.
"""

from test_framework.test_framework import BitcoinTestFramework
from test_framework.util import assert_equal, assert_raises_rpc_error

RIN_FORK_TX_VERSION = 0x52494e33   # "RIN3" ASCII = 1380535859
LEGACY_TX_VERSION   = 2            # CTransaction::CURRENT_VERSION
FORK_HEIGHT         = 840          # regtest nRinHashForkHeight


class WalletRin3FundVersionTest(BitcoinTestFramework):

    def set_test_params(self):
        self.num_nodes = 1
        self.setup_clean_chain = True
        self.extra_args = [[
            "-fallbackfee=0.001",
            "-acceptnonstdtxn=0",
            # Disable MWEB for this test, as feature_rin3_enforcement.py does:
            # a far-future timestamp (~2286) stands in for NEVER_ACTIVE.
            "-vbparams=mweb:9999999999:9999999999",
        ]]

    def skip_test_if_missing_module(self):
        self.skip_if_no_wallet()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _mine_to(self, target: int):
        """Advance chain to `target` height with progress logging."""
        node    = self.nodes[0]
        addr    = node.getnewaddress()
        current = node.getblockcount()
        if current >= target:
            return

        self.log.info(f"  Mining from h={current} to h={target} ...")
        remaining = target - current
        while remaining > 0:
            batch = min(remaining, 100)
            node.generatetoaddress(batch, addr)
            remaining -= batch
        assert_equal(node.getblockcount(), target)

    def _skeleton(self, version: int = None) -> str:
        """An unfunded one-output transaction, optionally with a set version."""
        node = self.nodes[0]
        raw  = node.createrawtransaction([], [{node.getnewaddress(): 1}])
        assert_equal(node.decoderawtransaction(raw)["version"], LEGACY_TX_VERSION)
        if version is None:
            return raw
        # nVersion is the first four bytes of the serialization, little-endian.
        return version.to_bytes(4, "little").hex() + raw[8:]

    def _fund(self, raw: str) -> tuple:
        """Fund a skeleton; return (hex, version)."""
        node   = self.nodes[0]
        funded = node.fundrawtransaction(raw)["hex"]
        return funded, node.decoderawtransaction(funded)["version"]

    def _sign_and_send(self, funded: str) -> str:
        node   = self.nodes[0]
        signed = node.signrawtransactionwithwallet(funded)
        assert_equal(signed["complete"], True)
        # The signature commits to nVersion, so signing must not change it.
        assert_equal(
            node.decoderawtransaction(signed["hex"])["version"],
            node.decoderawtransaction(funded)["version"],
        )
        return node.sendrawtransaction(signed["hex"])

    def _psbt(self) -> tuple:
        """walletcreatefundedpsbt for one output; return (psbt, version)."""
        node = self.nodes[0]
        psbt = node.walletcreatefundedpsbt([], [{node.getnewaddress(): 1}])["psbt"]
        return psbt, node.decodepsbt(psbt)["tx"]["version"]

    def _psbt_version(self) -> int:
        return self._psbt()[1]

    def _psbt_process_and_send(self, psbt: str) -> str:
        """Sign, finalize and broadcast a funded PSBT; return the txid.
        The version must survive every step, as the signature commits to it."""
        node      = self.nodes[0]
        version   = node.decodepsbt(psbt)["tx"]["version"]
        processed = node.walletprocesspsbt(psbt)
        assert_equal(processed["complete"], True)
        finalized = node.finalizepsbt(processed["psbt"])
        assert_equal(finalized["complete"], True)
        assert_equal(node.decoderawtransaction(finalized["hex"])["version"], version)
        txid = node.sendrawtransaction(finalized["hex"])
        assert txid in node.getrawmempool()
        return txid

    def _send(self) -> tuple:
        """send with its defaults, which funds, signs and broadcasts;
        return (txid, version)."""
        node = self.nodes[0]
        # send funds through CWallet::FundTransaction() as well
        # (rpcwallet.cpp).
        res = node.send({node.getnewaddress(): 1})
        assert_equal(res["complete"], True)
        txid = res["txid"]
        assert txid in node.getrawmempool()
        return txid, node.decoderawtransaction(node.gettransaction(txid)["hex"])["version"]

    # ------------------------------------------------------------------
    # Subtests
    # ------------------------------------------------------------------

    def subtest_01_before_boundary_legacy(self):
        self.log.info("[01] tip 838: the three funding RPCs emit the legacy version")
        node = self.nodes[0]
        self._mine_to(FORK_HEIGHT - 2)

        funded, version = self._fund(self._skeleton())
        self.log.info(f"  fundrawtransaction     nVersion = {version}")
        assert_equal(version, LEGACY_TX_VERSION)
        # Spendable here: the next block is still before the fork height.
        self._sign_and_send(funded)

        version = self._psbt_version()
        self.log.info(f"  walletcreatefundedpsbt nVersion = {version}")
        assert_equal(version, LEGACY_TX_VERSION)

        _, version = self._send()
        self.log.info(f"  send                   nVersion = {version}")
        assert_equal(version, LEGACY_TX_VERSION)

        # The funded transaction and the one send broadcast.
        assert_equal(node.getmempoolinfo()["size"], 2)

    def subtest_02_before_boundary_caller_version_kept(self):
        self.log.info("[02] tip 838: a marker set by the caller survives funding")
        node = self.nodes[0]
        assert_equal(node.getblockcount(), FORK_HEIGHT - 2)

        funded, version = self._fund(self._skeleton(RIN_FORK_TX_VERSION))
        self.log.info(f"  nVersion = {version} ({version:#010x})")
        assert_equal(version, RIN_FORK_TX_VERSION)
        # Standard at any height (policy.cpp), so it reaches the mempool here.
        self._sign_and_send(funded)

    def subtest_03_at_boundary_marker(self):
        self.log.info("[03] tip 839: the three funding RPCs emit the marker")
        node = self.nodes[0]
        self._mine_to(FORK_HEIGHT - 1)
        # Block 839 took everything the tip-838 subtests left in the mempool.
        assert_equal(node.getmempoolinfo()["size"], 0)

        funded, version = self._fund(self._skeleton())
        self.log.info(f"  fundrawtransaction     nVersion = {version} ({version:#010x})")
        assert_equal(version, RIN_FORK_TX_VERSION)
        txid = self._sign_and_send(funded)
        assert txid in node.getrawmempool()

        psbt, version = self._psbt()
        self.log.info(f"  walletcreatefundedpsbt nVersion = {version} ({version:#010x})")
        assert_equal(version, RIN_FORK_TX_VERSION)
        # The PSBT path end to end: the marker survives signing and finalizing.
        psbt_txid = self._psbt_process_and_send(psbt)

        send_txid, version = self._send()
        self.log.info(f"  send                   nVersion = {version} ({version:#010x})")
        assert_equal(version, RIN_FORK_TX_VERSION)

        # All three are mineable into the fork block, which the legacy version
        # is not.
        block_hash = node.generatetoaddress(1, node.getnewaddress())[0]
        assert_equal(node.getblockcount(), FORK_HEIGHT)
        block_txs = node.getblock(block_hash)["tx"]
        assert txid in block_txs
        assert psbt_txid in block_txs
        assert send_txid in block_txs
        assert_equal(node.gettransaction(txid)["confirmations"], 1)
        assert_equal(node.getblockstats(FORK_HEIGHT)["subsidy"], 400000000)

    def subtest_04_at_boundary_psbt(self):
        self.log.info("[04] tip 840: walletcreatefundedpsbt emits the marker as well")
        node = self.nodes[0]
        assert_equal(node.getblockcount(), FORK_HEIGHT)

        version = self._psbt_version()
        self.log.info(f"  nVersion = {version} ({version:#010x})")
        assert_equal(version, RIN_FORK_TX_VERSION)

    def subtest_05_at_boundary_explicit_legacy_not_kept(self):
        self.log.info("[05] tip 840: a caller version of 2 is not told apart from the default")
        node = self.nodes[0]
        funded, version = self._fund(self._skeleton(LEGACY_TX_VERSION))
        self.log.info(f"  nVersion = {version} ({version:#010x})")
        # Documented consequence: after the fork height this path no longer
        # funds a legacy-version transaction from a default skeleton.
        assert_equal(version, RIN_FORK_TX_VERSION)

        # A caller that wants one sets the version after funding and before
        # signing. The result is well-formed, but this node does not accept
        # it: the mempool rejects a legacy version from the fork height on.
        legacy = LEGACY_TX_VERSION.to_bytes(4, "little").hex() + funded[8:]
        signed = node.signrawtransactionwithwallet(legacy)
        assert_equal(signed["complete"], True)
        assert_equal(node.decoderawtransaction(signed["hex"])["version"], LEGACY_TX_VERSION)
        assert_raises_rpc_error(-26, "bad-tx-rinhash-version",
                                node.sendrawtransaction, signed["hex"])

    def subtest_06_at_boundary_sendtoaddress_control(self):
        self.log.info("[06] tip 840, control: sendtoaddress emits the marker")
        node = self.nodes[0]
        txid = node.sendtoaddress(node.getnewaddress(), 1)
        version = node.decoderawtransaction(node.gettransaction(txid)["hex"])["version"]
        self.log.info(f"  nVersion = {version} ({version:#010x})")
        assert_equal(version, RIN_FORK_TX_VERSION)

    def subtest_07_at_boundary_send_rpc(self):
        self.log.info("[07] tip 840: the send RPC emits the marker")
        _, version = self._send()
        self.log.info(f"  nVersion = {version} ({version:#010x})")
        assert_equal(version, RIN_FORK_TX_VERSION)

    # ------------------------------------------------------------------

    def run_test(self):
        self.log.info("=" * 55)
        self.log.info("  RIN3 nVersion -- transactions the wallet funds")
        self.log.info(f"  nRinHashForkHeight (regtest) = {FORK_HEIGHT}")
        self.log.info(f"  RIN_FORK_TX_VERSION = {RIN_FORK_TX_VERSION:#010x}"
                      f" = {RIN_FORK_TX_VERSION}")
        self.log.info("=" * 55)

        self.subtest_01_before_boundary_legacy()
        self.subtest_02_before_boundary_caller_version_kept()
        self.subtest_03_at_boundary_marker()
        self.subtest_04_at_boundary_psbt()
        self.subtest_05_at_boundary_explicit_legacy_not_kept()
        self.subtest_06_at_boundary_sendtoaddress_control()
        self.subtest_07_at_boundary_send_rpc()

        self.log.info("=" * 55)
        self.log.info("  ALL 7 SUBTESTS PASSED")
        self.log.info("  from a default skeleton, fundrawtransaction,")
        self.log.info("  walletcreatefundedpsbt and send give the version")
        self.log.info("  the wallet gives its own transactions")
        self.log.info("=" * 55)


if __name__ == "__main__":
    WalletRin3FundVersionTest().main()
