#!/usr/bin/env python3
# Copyright (c) 2026 The Rincoin Core developers
# Distributed under the MIT software license, see the accompanying
# file COPYING or http://www.opensource.org/licenses/mit-license.php.

"""
mempool_rin3_fork_reorg.py

Rincoin RIN3 (RIP-0009) -- the mempool cleanup at the fork height in the
middle of a reorg that crosses it.

CTxMemPool::removeForRIN3Fork() runs when ConnectTip() connects the block
before the fork height (regtest 839). In a reorg, ActivateBestChainStep()
first disconnects the old branch into a DisconnectedBlockTransactions pool,
then connects the new one, and only afterwards puts the disconnected
transactions back through UpdateMempoolForReorg(). So the cleanup can run
while some of the mempool's parents sit in that pool, outside the mempool.

No wallet: the transactions spend P2WSH(OP_TRUE) outputs. -checkmempool is
on by default on regtest, so CTxMemPool::check() runs at the end of every
step; a node that hit an assertion would stop answering.

Six nodes, three pairs; each pair shares the chain to 836 and then splits:
  [01] node0 vs node1: node0 mines 837a (T, 2) and 838a and holds P (2),
       Q (marker, spends P) and S (marker, spends T). node1's 837b..840b
       wins. The cleanup runs at 839b with T in the disconnect pool: it
       removes Q then P; S leaves later with T (reason REORG), outside the
       cleanup's log. Mempool empty.
  [02] node2 vs node3: node2 is at 838 (P2' confirmed in 837) with a
       legacy chain U1 -> U2 -> U3, W (marker, spends U3), V (marker, spends
       P2') and Z (2, spends V). node3's 837..839 wins. The cleanup removes
       W, U3, then U2 and Z in txid order, then U1 (4 unmarked, 1
       descendant); V is not in its log (its parent is in the disconnect
       pool) and leaves later with P2'. Mempool empty.
  [03] node4 vs node5: node4 is at 841 holding Q2 (marker, spends the legacy
       P2 of 837) and G3 (marker, spends the marker M3 of 839, which spends
       the legacy L3 of 838). node5's 837..842 wins: a five-block reorg. The
       cleanup runs exactly once, at 839, and removes nothing; Q2 and G3
       leave later with their ancestors. Mempool empty.
Which reason the later removals carry (REORG) is read from the code
(UpdateMempoolForReorg() -> removeRecursive(..., REORG)); the log does not
show it.
"""

from decimal import Decimal
import os

from test_framework.address import ADDRESS_BCRT1_P2WSH_OP_TRUE
from test_framework.messages import COIN, COutPoint, CTransaction, CTxIn, CTxInWitness, CTxOut
from test_framework.script import CScript, OP_TRUE
from test_framework.test_framework import BitcoinTestFramework
from test_framework.util import assert_equal, hex_str_to_bytes, satoshi_round

RIN_FORK_TX_VERSION = 0x52494e33
LEGACY_TX_VERSION = 2
FORK_HEIGHT = 840
FEE = Decimal("0.0001")
MARK = "RIN3 fork: removing "
COUNT = "RIN3 fork: removed "


class MempoolRin3ForkReorgTest(BitcoinTestFramework):

    def set_test_params(self):
        self.num_nodes = 6
        self.setup_clean_chain = True
        args = [
            "-acceptnonstdtxn=0",
            "-vbparams=mweb:9999999999:9999999999",
            "-whitelist=noban@127.0.0.1",
            # The tests read the cleanup's per-transaction log lines; keep
            # the mempool category on (the framework passes -debug as well).
            "-debug=mempool",
        ]
        self.extra_args = [args] * self.num_nodes

    def setup_network(self):
        self.setup_nodes()
        for i in range(1, self.num_nodes):
            self.connect_nodes(i, 0)
        self.sync_all()

    # ------------------------------------------------------------------

    def cb(self, node, height):
        c = node.getblock(node.getblockhash(height), 2)["tx"][0]
        return (c["txid"], 0, c["vout"][0]["value"])

    def send(self, node, inputs, version, deprioritise=False):
        tx = CTransaction()
        tx.nVersion = version
        tx.vin = [CTxIn(COutPoint(int(txid, 16), n)) for txid, n, _ in inputs]
        each = satoshi_round(sum(v for _, _, v in inputs) - FEE)
        tx.vout = [CTxOut(int(each * COIN), self.spk)]
        for _ in inputs:
            wit = CTxInWitness()
            wit.scriptWitness.stack = [CScript([OP_TRUE])]
            tx.wit.vtxinwit.append(wit)
        txid = node.sendrawtransaction(tx.serialize().hex())
        if deprioritise:
            node.prioritisetransaction(txid=txid, fee_delta=-COIN)
        return txid, (txid, 0, each)

    def log_size(self, node):
        return os.path.getsize(os.path.join(node.datadir, node.chain, "debug.log"))

    def cleanup_lines(self, node, since):
        with open(os.path.join(node.datadir, node.chain, "debug.log"), "rb") as f:
            f.seek(since)
            text = f.read().decode("utf-8", "replace")
        return [line for line in text.splitlines() if "RIN3 fork: " in line]

    def report(self, label, lines, names):
        removed = [line.split(MARK, 1)[1].split(" ", 1)[0] for line in lines if MARK in line]
        counts = [line.split(COUNT, 1)[1] for line in lines if COUNT in line]
        self.log.info(f"  {label} removal order {[names.get(x, x[:8]) for x in removed]}")
        for c in counts:
            self.log.info(f"  {label} count line: removed {c}")
        return removed, counts

    # ------------------------------------------------------------------

    def subtest_01_cleanup_with_parent_in_disconnect_pool(self):
        self.log.info("[01] node1's 837b..840b replaces 837a/838a: the cleanup runs at 839b with T "
                      "in the disconnect pool")
        n0, n1 = self.nodes[0], self.nodes[1]
        t, t_out = self.send(n0, [self.cb(n0, 1)], LEGACY_TX_VERSION)
        h837a = n0.generatetoaddress(1, ADDRESS_BCRT1_P2WSH_OP_TRUE)[0]
        assert t in n0.getblock(h837a)["tx"]
        n0.generatetoaddress(1, ADDRESS_BCRT1_P2WSH_OP_TRUE)                     # 838a
        p, p_out = self.send(n0, [self.cb(n0, 2)], LEGACY_TX_VERSION)
        q, _ = self.send(n0, [p_out], RIN_FORK_TX_VERSION)
        s, _ = self.send(n0, [t_out], RIN_FORK_TX_VERSION)
        assert_equal(set(n0.getrawmempool()), {p, q, s})
        hb = n1.generatetoaddress(4, ADDRESS_BCRT1_P2WSH_OP_TRUE)                # 837b..840b
        since = self.log_size(n0)
        self.connect_nodes(0, 1)
        self.sync_blocks([n0, n1])
        assert_equal(n0.getbestblockhash(), hb[-1])
        assert_equal(n0.getrawmempool(), [])
        removed, counts = self.report("node0", self.cleanup_lines(n0, since), {p: "P", q: "Q", s: "S", t: "T"})
        assert_equal(removed, [q, p])
        assert_equal(len(counts), 1)
        assert counts[0].startswith("1 transaction(s) without the nVersion marker and 1 descendant(s) of them"), counts
        assert_equal(n0.getblockcount(), FORK_HEIGHT)                            # still answering

    def subtest_02_cleanup_before_mempool_update(self):
        self.log.info("[02] node3's 837..839 replaces node2's 837/838: removal order W, U3, (U2, Z), U1; "
                      "V leaves later with its parent")
        n2, n3 = self.nodes[2], self.nodes[3]
        p2, p2_out = self.send(n2, [self.cb(n2, 10)], LEGACY_TX_VERSION)
        n2.generatetoaddress(1, ADDRESS_BCRT1_P2WSH_OP_TRUE)                     # 837 (P2')
        assert p2 in n2.getblock(n2.getbestblockhash())["tx"]
        u1, o = self.send(n2, [self.cb(n2, 11)], LEGACY_TX_VERSION, deprioritise=True)
        u2, o = self.send(n2, [o], LEGACY_TX_VERSION, deprioritise=True)
        u3, o = self.send(n2, [o], LEGACY_TX_VERSION, deprioritise=True)
        w, _ = self.send(n2, [o], RIN_FORK_TX_VERSION, deprioritise=True)
        v, v_out = self.send(n2, [p2_out], RIN_FORK_TX_VERSION, deprioritise=True)
        z, _ = self.send(n2, [v_out], LEGACY_TX_VERSION, deprioritise=True)
        n2.generatetoaddress(1, ADDRESS_BCRT1_P2WSH_OP_TRUE)                     # 838 (none of them)
        assert_equal(n2.getblockcount(), FORK_HEIGHT - 2)
        assert_equal(set(n2.getrawmempool()), {u1, u2, u3, w, v, z})
        hb = n3.generatetoaddress(3, ADDRESS_BCRT1_P2WSH_OP_TRUE)                # 837..839
        since = self.log_size(n2)
        self.connect_nodes(2, 3)
        self.sync_blocks([n2, n3])
        assert_equal(n2.getbestblockhash(), hb[-1])
        assert_equal(n2.getrawmempool(), [])
        names = {u1: "U1", u2: "U2", u3: "U3", w: "W", v: "V", z: "Z"}
        removed, counts = self.report("node2", self.cleanup_lines(n2, since), names)
        assert v not in removed
        assert_equal(removed[:2], [w, u3])
        assert_equal(removed[2:4], sorted([u2, z], key=lambda h: bytes.fromhex(h)[::-1]))
        assert_equal(removed[4:], [u1])
        assert_equal(len(counts), 1)
        assert counts[0].startswith("4 transaction(s) without the nVersion marker and 1 descendant(s) of them"), counts
        assert_equal(n2.getblockcount(), FORK_HEIGHT - 1)

    def subtest_03_five_block_reorg(self):
        self.log.info("[03] node5's 837..842 replaces node4's 837..841: the cleanup runs once, at 839, "
                      "and removes nothing")
        n4, n5 = self.nodes[4], self.nodes[5]
        p2, p2_out = self.send(n4, [self.cb(n4, 20)], LEGACY_TX_VERSION)
        n4.generatetoaddress(1, ADDRESS_BCRT1_P2WSH_OP_TRUE)                     # 837 (P2)
        q2, _ = self.send(n4, [p2_out], RIN_FORK_TX_VERSION, deprioritise=True)
        l3, l3_out = self.send(n4, [self.cb(n4, 21)], LEGACY_TX_VERSION)
        n4.generatetoaddress(1, ADDRESS_BCRT1_P2WSH_OP_TRUE)                     # 838 (L3)
        m3, m3_out = self.send(n4, [l3_out], RIN_FORK_TX_VERSION)
        n4.generatetoaddress(1, ADDRESS_BCRT1_P2WSH_OP_TRUE)                     # 839 (M3)
        assert m3 in n4.getblock(n4.getbestblockhash())["tx"]
        g3, _ = self.send(n4, [m3_out], RIN_FORK_TX_VERSION, deprioritise=True)
        n4.generatetoaddress(2, ADDRESS_BCRT1_P2WSH_OP_TRUE)                     # 840, 841
        assert_equal(n4.getblockcount(), FORK_HEIGHT + 1)
        assert_equal(set(n4.getrawmempool()), {q2, g3})
        hb = n5.generatetoaddress(6, ADDRESS_BCRT1_P2WSH_OP_TRUE)                # 837..842
        since = self.log_size(n4)
        self.connect_nodes(4, 5)
        self.sync_blocks([n4, n5])
        assert_equal(n4.getbestblockhash(), hb[-1])
        assert_equal(n4.getrawmempool(), [])
        removed, counts = self.report("node4", self.cleanup_lines(n4, since), {q2: "Q2", g3: "G3"})
        assert_equal(removed, [])
        assert_equal(len(counts), 1)
        assert counts[0].startswith("0 transaction(s) without the nVersion marker and 0 descendant(s) of them"), counts
        assert_equal(n4.getblockcount(), FORK_HEIGHT + 2)

    def run_test(self):
        self.spk = hex_str_to_bytes(self.nodes[0].validateaddress(ADDRESS_BCRT1_P2WSH_OP_TRUE)["scriptPubKey"])
        self.nodes[0].generatetoaddress(FORK_HEIGHT - 4, ADDRESS_BCRT1_P2WSH_OP_TRUE)
        self.sync_all()
        for i in range(1, self.num_nodes):
            self.disconnect_nodes(i, 0)
        self.subtest_01_cleanup_with_parent_in_disconnect_pool()
        self.subtest_02_cleanup_before_mempool_update()
        self.subtest_03_five_block_reorg()
        self.log.info("ALL 3 SUBTESTS PASSED")


if __name__ == "__main__":
    MempoolRin3ForkReorgTest().main()
