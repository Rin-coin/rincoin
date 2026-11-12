#!/usr/bin/env python3
# Copyright (c) 2026 The Rincoin Core developers
# Distributed under the MIT software license, see the accompanying
# file COPYING or http://www.opensource.org/licenses/mit-license.php.

"""
feature_rin3_enforcement.py  (v3)

Rincoin RIN3 (nVersion replay protection) — consensus & mempool enforcement tests.

Activation:
    nRinHashForkHeight (regtest) = 840
    At height >= fork, ContextualCheckBlock rejects any non-exempt tx whose
    nVersion != RIN_FORK_TX_VERSION (0x52494e33) with "bad-tx-rinhash-version".
    Exempt: coinbase, HogEx, MWEBOnly.

    Additionally, MemPoolAccept::PreChecks rejects legacy-nVersion txs at
    mempool entry (prevents Mempool Zombie DoS where a bad tx stalls
    CreateNewBlock indefinitely).

Test matrix:
    [01] Pre-fork  : legacy tx in block at h=839             -> ACCEPT
    [02] At  fork  : nVersion=2  block at h=840              -> REJECT (bad-tx-rinhash-version)
    [03] At  fork  : nVersion=1  block at h=840              -> REJECT
    [04] At  fork  : nVersion=3  block at h=840              -> REJECT  (not RIN3)
    [05] At  fork  : mixed (RIN3 + legacy) block at h=840    -> REJECT  (whole block invalid)
    [06] At  fork  : pure RIN3 tx at h=840                   -> ACCEPT  (positive control)
    [07] Post-fork : legacy tx at h=841                      -> REJECT
    [08] Mempool   : nVersion=3 via sendrawtransaction        -> REJECT (IsStandardTx)
    [09] Mempool   : nVersion=2 via sendrawtransaction at h>=840 -> REJECT (PreChecks, Zombie DoS defense)
    [10] Coinbase  : coinbase nVersion != RIN3 at h>=840      -> ACCEPT (exempt)

Out of scope (require MWEB activation):
    - HogEx exemption  (-> feature_rin3_mweb_exemption.py)
    - MWEBOnly exemption
"""

import io
import struct

from test_framework.test_framework import BitcoinTestFramework
from test_framework.messages import (
    CTransaction, CTxIn, CTxOut, COutPoint, COIN,
)
from test_framework.blocktools import create_block, create_coinbase, add_witness_commitment
from test_framework.util import assert_equal, assert_raises_rpc_error

RIN_FORK_TX_VERSION = 0x52494e33   # "RIN3" ASCII = 1380535859
FORK_HEIGHT         = 840          # regtest nRinHashForkHeight
SATOSHI             = 100_000_000


def sat_to_rin(sat: int) -> str:
    return f"{sat / SATOSHI:.2f}"


class Rin3EnforcementTest(BitcoinTestFramework):

    def set_test_params(self):
        self.num_nodes = 1
        self.setup_clean_chain = True
        self.extra_args = [[
            "-fallbackfee=0.001",
            "-acceptnonstdtxn=0",
            # Disable MWEB for this test: MWEB+RIN3 interaction is covered by
            # feature_rin3_mweb_exemption.py. Use far-future timestamp (~2286)
            # as a practical equivalent of NEVER_ACTIVE.
            "-vbparams=mweb:9999999999:9999999999",
        ]]

    def skip_test_if_missing_module(self):
        self.skip_if_no_wallet()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _log_blockstats(self, height: int, expected_sat: int):
        """Print getblockstats subsidy line — same style as sim-ch.sh grep subsidy."""
        node = self.nodes[0]
        stats = node.getblockstats(height)
        actual = stats["subsidy"]
        self.log.info(
            f"  getblockstats[{height}] | subsidy = {actual:>12} sat"
            f"  ({sat_to_rin(actual)} RIN)"
            f"  expect {sat_to_rin(expected_sat)} RIN"
        )
        return actual

    def _pick_utxo(self):
        utxos = self.nodes[0].listunspent()
        assert len(utxos) > 0, "no mature UTXOs available"
        return utxos[0]

    def _build_signed_tx(self, nversion: int, utxo=None, fee_sat: int = 1000):
        """
        Build and sign a tx with an explicit nVersion.

        signrawtransactionwithwallet does NOT invoke txassembler and therefore
        does NOT overwrite nVersion. We assert this post-sign.
        """
        node  = self.nodes[0]
        utxo  = utxo or self._pick_utxo()

        tx = CTransaction()
        tx.nVersion = nversion
        tx.vin.append(CTxIn(COutPoint(int(utxo["txid"], 16), utxo["vout"]), b""))
        tx.vout.append(CTxOut(
            int(utxo["amount"] * COIN) - fee_sat,
            bytes.fromhex("0014" + "00" * 20),  # P2WPKH burn address
        ))

        signed_hex = node.signrawtransactionwithwallet(tx.serialize().hex())["hex"]

        # Verify wallet did not overwrite nVersion
        check = CTransaction()
        check.deserialize(io.BytesIO(bytes.fromhex(signed_hex)))
        assert check.nVersion == nversion, (
            f"wallet overwrote nVersion: {nversion:#x} -> {check.nVersion:#x}"
        )
        self.log.info(f"  Built tx: nVersion={nversion:#x} ({nversion}), "
                      f"txid={check.rehash()}")
        return check

    def _build_block(self, extra_txs):
        """Build a candidate block at current_tip + 1."""
        node       = self.nodes[0]
        tip_hash   = node.getbestblockhash()
        tip_height = node.getblockcount()
        block_time = node.getblock(tip_hash)["time"] + 1

        # Ask rincoind for the correct block version via getblocktemplate.
        # Hardcoding nVersion (e.g. 4) is insufficient: Rincoin requires
        # BIP9-style version (0x20000000+). getblocktemplate always returns
        # the correct value for the current chain state.
        tmpl    = node.getblocktemplate({"rules": ["mweb", "segwit"]})
        version = tmpl["version"]

        block = create_block(
            int(tip_hash, 16),
            create_coinbase(tip_height + 1),
            block_time,
            version=version,
        )
        for tx in extra_txs:
            block.vtx.append(tx)
        # add_witness_commitment inserts the SegWit witness commitment into the
        # coinbase output and recalculates the coinbase hash. Required for all
        # SegWit-active blocks; omitting it causes "unexpected-witness" rejection.
        add_witness_commitment(block)
        block.hashMerkleRoot = block.calc_merkle_root()
        block.solve()
        self.log.info(f"  Built block at h={tip_height + 1}, nVersion={version:#010x}, "
                      f"vtx={len(block.vtx)} (coinbase + {len(extra_txs)} user txs)")
        return block

    def _submit_expect_reject(self, block, label: str, expected_substring: str = "rinhash"):
        node     = self.nodes[0]
        h_before = node.getblockcount()
        result   = node.submitblock(block.serialize().hex())
        self.log.info(f"  submitblock -> {result!r}")

        assert result is not None, f"{label}: block unexpectedly ACCEPTED"
        assert expected_substring in str(result).lower(), (
            f"{label}: unexpected reject reason: {result}"
        )
        assert_equal(node.getblockcount(), h_before)
        self.log.info(f"  [PASS] {label} -> REJECTED as expected")

    def _submit_expect_accept(self, block, label: str):
        node     = self.nodes[0]
        h_before = node.getblockcount()
        result   = node.submitblock(block.serialize().hex())
        self.log.info(f"  submitblock -> {result!r}")

        assert result is None, f"{label}: block unexpectedly REJECTED: {result}"
        assert_equal(node.getblockcount(), h_before + 1)
        self.log.info(f"  [PASS] {label} -> ACCEPTED, chain advanced to h={h_before + 1}")

    def _mine_to(self, target: int):
        """Advance chain to `target` height with progress logging every 100 blocks."""
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
            self.log.info(f"    -> Height: {node.getblockcount()} / {target}")

    # ------------------------------------------------------------------
    # Subtests
    # ------------------------------------------------------------------

    def subtest_01_pre_fork_legacy_accepted(self):
        self.log.info("-" * 55)
        self.log.info("[01] Pre-fork: legacy tx in block at h=839 -> ACCEPT")
        self.log.info("-" * 55)
        node = self.nodes[0]
        addr = node.getnewaddress()

        # Advance to h=838 (coinbase at h=1 is mature after 100 confs, i.e. h>=101)
        self._mine_to(838)

        # Show subsidy at h=838 (still Phase 3: 6.25 RIN)
        self._log_blockstats(838, 625_000_000)

        self.log.info(f"  Building block at h=839 with legacy nVersion=2...")
        legacy_tx = self._build_signed_tx(nversion=2)
        block     = self._build_block([legacy_tx])
        self._submit_expect_accept(block, "legacy nVersion=2 at h=839")
        self._log_blockstats(839, 625_000_000)

    def subtest_02_at_fork_v2_rejected(self):
        self.log.info("-" * 55)
        self.log.info("[02] At-fork: nVersion=2 block at h=840 -> REJECT")
        self.log.info("-" * 55)
        assert_equal(self.nodes[0].getblockcount(), 839)
        self.log.info(f"  Building block at h=840 (FORK) with legacy nVersion=2...")
        bad_tx = self._build_signed_tx(nversion=2)
        block  = self._build_block([bad_tx])
        self._submit_expect_reject(block, "nVersion=2 at h=840")

    def subtest_03_at_fork_v1_rejected(self):
        self.log.info("-" * 55)
        self.log.info("[03] At-fork: nVersion=1 block at h=840 -> REJECT")
        self.log.info("-" * 55)
        self.log.info(f"  Building block at h=840 with nVersion=1...")
        bad_tx = self._build_signed_tx(nversion=1)
        block  = self._build_block([bad_tx])
        self._submit_expect_reject(block, "nVersion=1 at h=840")

    def subtest_04_at_fork_v3_rejected(self):
        self.log.info("-" * 55)
        self.log.info("[04] At-fork: nVersion=3 block at h=840 -> REJECT (not RIN3)")
        self.log.info("-" * 55)
        self.log.info(f"  Note: RIN_FORK_TX_VERSION = {RIN_FORK_TX_VERSION:#x} = {RIN_FORK_TX_VERSION}")
        self.log.info(f"  nVersion=3 is NOT RIN3 and must be rejected...")
        bad_tx = self._build_signed_tx(nversion=3)
        block  = self._build_block([bad_tx])
        self._submit_expect_reject(block, "nVersion=3 at h=840")

    def subtest_05_at_fork_mixed_block_rejected(self):
        self.log.info("-" * 55)
        self.log.info("[05] At-fork: mixed block (RIN3 + legacy) at h=840 -> REJECT")
        self.log.info("-" * 55)
        utxos = self.nodes[0].listunspent()
        assert len(utxos) >= 2, "need two UTXOs for mixed block test"
        self.log.info(f"  Available UTXOs: {len(utxos)}")

        self.log.info(f"  Building good tx (RIN3) and bad tx (nVersion=2)...")
        good_tx = self._build_signed_tx(nversion=RIN_FORK_TX_VERSION, utxo=utxos[0])
        bad_tx  = self._build_signed_tx(nversion=2,                   utxo=utxos[1])

        self.log.info(f"  Block contains 2 user txs: 1 RIN3 + 1 legacy")
        self.log.info(f"  Entire block must be rejected (one bad tx poisons the block)...")
        block = self._build_block([good_tx, bad_tx])
        self._submit_expect_reject(block, "mixed RIN3+legacy at h=840")

    def subtest_06_at_fork_rin3_accepted(self):
        self.log.info("-" * 55)
        self.log.info("[06] At-fork: pure RIN3 block at h=840 -> ACCEPT (positive control)")
        self.log.info("-" * 55)
        self.log.info(f"  Building block with RIN_FORK_TX_VERSION={RIN_FORK_TX_VERSION:#x}...")
        good_tx = self._build_signed_tx(nversion=RIN_FORK_TX_VERSION)
        block   = self._build_block([good_tx])
        self._submit_expect_accept(block, "pure RIN3 at h=840")
        assert_equal(self.nodes[0].getblockcount(), 840)

        # Show subsidy at fork block — CH dilation: 4.00 RIN
        self.log.info(f"  Subsidy at fork block:")
        self._log_blockstats(840, 400_000_000)

    def subtest_07_post_fork_legacy_rejected(self):
        self.log.info("-" * 55)
        self.log.info("[07] Post-fork: nVersion=2 block at h=841 -> REJECT")
        self.log.info("-" * 55)
        assert_equal(self.nodes[0].getblockcount(), 840)
        self.log.info(f"  Enforcement must persist beyond the fork block itself...")
        bad_tx = self._build_signed_tx(nversion=2)
        block  = self._build_block([bad_tx])
        self._submit_expect_reject(block, "nVersion=2 at h=841")

    def subtest_08_mempool_rejects_nversion3(self):
        self.log.info("-" * 55)
        self.log.info("[08] Mempool: nVersion=3 via sendrawtransaction -> REJECT (IsStandardTx)")
        self.log.info("-" * 55)
        self.log.info(f"  nVersion=3 exceeds MAX_STANDARD_VERSION and is unknown.")
        self.log.info(f"  IsStandardTx must reject it regardless of fork height...")
        bad_tx = self._build_signed_tx(nversion=3)
        assert_raises_rpc_error(
            -26, "version",
            self.nodes[0].sendrawtransaction, bad_tx.serialize().hex()
        )
        self.log.info(f"  [PASS] mempool rejected nVersion=3 with 'version' reason (IsStandardTx)")

    def subtest_09_mempool_zombie_defense(self):
        self.log.info("-" * 55)
        self.log.info("[09] Mempool Zombie DoS defense: nVersion=2 at h>=840 -> REJECT (PreChecks)")
        self.log.info("-" * 55)
        node = self.nodes[0]
        h_before = node.getblockcount()
        self.log.info(f"  Current height: {h_before}")

        # Precondition: mempool must be empty so the rejection is unambiguous.
        # Any lingering tx from a prior subtest would mask the actual defense. (B)
        mempool_before = node.getmempoolinfo()["size"]
        assert_equal(mempool_before, 0)
        self.log.info(f"  Mempool size (before): {mempool_before} -- clean, precondition OK")

        self.log.info(f"  Attack scenario:")
        self.log.info(f"    A high-fee legacy-nVersion=2 tx enters the mempool.")
        self.log.info(f"    BlockAssembler picks it up, TestBlockValidity throws,")
        self.log.info(f"    CreateNewBlock fails => miner cannot produce blocks.")
        self.log.info(f"  Defense (MemPoolAccept::PreChecks): reject at entry.")
        bad_tx = self._build_signed_tx(nversion=2)
        assert_raises_rpc_error(
            -26, "bad-tx-rinhash-version",
            node.sendrawtransaction, bad_tx.serialize().hex()
        )
        # Verify mempool is still clean and miner can still produce blocks
        assert_equal(node.getmempoolinfo()["size"], 0)
        addr = node.getnewaddress()
        node.generatetoaddress(1, addr)
        # Note: chain height is now h_before + 1 (e.g. 842 if subtest_08 left h=841).
        # subtest_10 uses getblockcount() dynamically so this is safe. (A)
        self.log.info(f"  Mempool size after rejection: 0 (clean)")
        self.log.info(f"  generatetoaddress succeeded -> miner unaffected")
        self.log.info(f"  Chain height after subtest_09: {node.getblockcount()}")
        self.log.info(f"  [PASS] Mempool Zombie DoS defense confirmed")

    def subtest_10_coinbase_exemption(self):
        self.log.info("-" * 55)
        self.log.info("[10] Coinbase exemption: non-RIN3 coinbase at h>=840 -> ACCEPT")
        self.log.info("-" * 55)
        node       = self.nodes[0]
        tip_hash   = node.getbestblockhash()
        tip_height = node.getblockcount()
        block_time = node.getblock(tip_hash)["time"] + 1

        self.log.info(f"  Building block at h={tip_height + 1}")
        self.log.info(f"  Coinbase nVersion will be set by create_coinbase() (not RIN3).")
        self.log.info(f"  ContextualCheckBlock exempts coinbase from RIN3 check.")

        # Use getblocktemplate for correct version (same reason as _build_block).
        tmpl = node.getblocktemplate({"rules": ["mweb", "segwit"]})

        block = create_block(
            int(tip_hash, 16),
            create_coinbase(tip_height + 1),
            block_time,
            version=tmpl["version"],
        )
        # No extra user txs — coinbase-only block.
        # add_witness_commitment is still required to satisfy SegWit validation.
        add_witness_commitment(block)
        block.hashMerkleRoot = block.calc_merkle_root()
        block.solve()

        # Inspect the coinbase's nVersion before submit
        cb_nver = block.vtx[0].nVersion
        self.log.info(f"  Coinbase nVersion = {cb_nver:#x} ({cb_nver})")
        assert cb_nver != RIN_FORK_TX_VERSION, (
            f"create_coinbase unexpectedly produced RIN3 nVersion: {cb_nver:#x}"
        )
        self.log.info(f"  Submitting coinbase-only block (expect ACCEPT)...")
        self._submit_expect_accept(block, f"coinbase-only block at h={tip_height + 1}")
        self.log.info(f"  [PASS] Coinbase exemption confirmed: nVersion={cb_nver:#x} accepted at h>={FORK_HEIGHT}")

    # ------------------------------------------------------------------
    # Driver
    # ------------------------------------------------------------------

    def run_test(self):
        self.log.info("=" * 55)
        self.log.info("  RIN3 nVersion enforcement -- consensus & mempool")
        self.log.info(f"  nRinHashForkHeight (regtest) = {FORK_HEIGHT}")
        self.log.info(f"  RIN_FORK_TX_VERSION = {RIN_FORK_TX_VERSION:#010x} = {RIN_FORK_TX_VERSION}")
        self.log.info("=" * 55)

        self.subtest_01_pre_fork_legacy_accepted()
        self.subtest_02_at_fork_v2_rejected()
        self.subtest_03_at_fork_v1_rejected()
        self.subtest_04_at_fork_v3_rejected()
        self.subtest_05_at_fork_mixed_block_rejected()
        self.subtest_06_at_fork_rin3_accepted()
        self.subtest_07_post_fork_legacy_rejected()
        self.subtest_08_mempool_rejects_nversion3()
        self.subtest_09_mempool_zombie_defense()
        self.subtest_10_coinbase_exemption()

        self.log.info("=" * 55)
        self.log.info("  ALL 10 SUBTESTS PASSED")
        self.log.info("  RIN3 consensus & mempool defense verified end-to-end")
        self.log.info("=" * 55)


if __name__ == "__main__":
    Rin3EnforcementTest().main()
