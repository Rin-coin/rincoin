#!/usr/bin/env python3
# Copyright (c) 2026 The Rincoin Core developers
# Distributed under the MIT software license, see the accompanying
# file COPYING or http://www.opensource.org/licenses/mit-license.php.

"""
mempool_rin3_fork_mweb.py

Rincoin RIN3 (RIP-0009) -- the mempool cleanup at the fork height with MWEB
active (the regtest default: BIP9, first MWEB block 432; this test does not
pass -vbparams). Blocks are mined with generatetoaddress: generateblock
does not build the HogEx.

MWEB-only transactions (no canonical inputs or outputs) are exempt from
RIN3, as are the coinbase and the HogEx. A pegin is not MWEB-only: it spends
canonical inputs, so it needs the marker like any other transaction. The
mempool links an MWEB input to the transaction that created the output
(mapTxOutputs_MWEB), so an MWEB-only child of a legacy pegin is that
pegin's in-mempool descendant and leaves with it.

Two nodes: node0 holds the wallets c and u, node1 mines.
  [01] MWEB active; c holds one canonical coin (10), u one MWEB coin (3)
  [02] tip 838: c pegs in P (nVersion 2, canonical input, MWEB outputs) and
       then sends M from P's MWEB outputs (MWEB-only, P's child); u sends U
       from its confirmed MWEB coin (MWEB-only, unrelated); node1 keeps them
       out of block 839
  [03] block 839: P and M leave both mempools, M first; U stays
  [04] c abandons P at once (M with it) and pegs in again: P2 carries the
       marker and is accepted
  [05] block 840 holds P2 and U, and a HogEx that spends the previous one;
       block 841 follows
"""

from decimal import Decimal
import os

from test_framework.messages import COIN
from test_framework.rin_util import get_hogex_tx, setup_mweb_chain
from test_framework.test_framework import BitcoinTestFramework
from test_framework.util import assert_equal

RIN_FORK_TX_VERSION = 0x52494e33
LEGACY_TX_VERSION = 2
FORK_HEIGHT = 840
MARK = "RIN3 fork: removing "
MWEB_HRP = "rrmweb"                # regtest mweb_hrp (chainparams.cpp)


class MempoolRin3ForkMwebTest(BitcoinTestFramework):

    def set_test_params(self):
        self.num_nodes = 2
        self.setup_clean_chain = True
        # -debug=mempool: the tests read the cleanup's per-transaction log
        # lines (the framework passes -debug as well).
        args = ["-fallbackfee=0.001", "-acceptnonstdtxn=0", "-whitelist=noban@127.0.0.1", "-debug=mempool"]
        self.extra_args = [args, args]

    def skip_test_if_missing_module(self):
        self.skip_if_no_wallet()

    def log_size(self, i):
        node = self.nodes[i]
        return os.path.getsize(os.path.join(node.datadir, node.chain, "debug.log"))

    def cleanup_lines(self, i, since):
        node = self.nodes[i]
        with open(os.path.join(node.datadir, node.chain, "debug.log"), "rb") as f:
            f.seek(since)
            text = f.read().decode("utf-8", "replace")
        return [line for line in text.splitlines() if "RIN3 fork: " in line]

    def mine(self, n):
        node1 = self.nodes[1]
        hashes = node1.generatetoaddress(n, node1.getnewaddress())
        self.sync_blocks()
        return hashes

    @staticmethod
    def decoded(rpc, txid):
        return rpc.decoderawtransaction(rpc.gettransaction(txid)["hex"])

    @staticmethod
    def is_abandoned(rpc, txid):
        """gettransaction reports "abandoned" only on its "send" details
        (as in wallet_rin3_boundary_rescue.py)."""
        sends = [d for d in rpc.gettransaction(txid)["details"] if d["category"] == "send"]
        assert sends, txid
        flags = {d["abandoned"] for d in sends}
        assert_equal(len(flags), 1)
        return flags.pop()

    @staticmethod
    def shape(d):
        """(canonical vin, canonical vout, MWEB vin, MWEB vout): decoderawtransaction
        lists MWEB inputs and outputs in vin/vout too, flagged "ismweb"."""
        cv = [x for x in d["vin"] if not x["ismweb"]]
        co = [x for x in d["vout"] if not x["ismweb"]]
        return len(cv), len(co), len(d["vin"]) - len(cv), len(d["vout"]) - len(co)

    def subtest_01_setup(self):
        self.log.info("[01] MWEB active; c holds one canonical coin, u one MWEB coin")
        node0, node1 = self.nodes
        setup_mweb_chain(node1)
        self.sync_blocks()
        node0.createwallet("c")
        node0.createwallet("u")
        self.c = node0.get_wallet_rpc("c")
        self.u = node0.get_wallet_rpc("u")
        self.mine(FORK_HEIGHT - 10 - node1.getblockcount())               # tip 830
        node1.sendtoaddress(self.c.getnewaddress(), 10)
        node1.sendtoaddress(self.u.getnewaddress(address_type="mweb"), 3)
        self.mine(1)
        self.mine(FORK_HEIGHT - 2 - node1.getblockcount())                # tip 838
        assert_equal(node0.getblockcount(), FORK_HEIGHT - 2)
        c_utxos = self.c.listunspent()
        u_utxos = self.u.listunspent()
        self.log.info(f"  c: {[(x['amount'], x['address'][:6]) for x in c_utxos]}  "
                      f"u: {[(x['amount'], x['address'][:6]) for x in u_utxos]}")
        assert_equal([x["amount"] for x in c_utxos], [Decimal("10")])
        assert not c_utxos[0]["address"].startswith(MWEB_HRP)
        assert_equal([x["amount"] for x in u_utxos], [Decimal("3")])
        assert u_utxos[0]["address"].startswith(MWEB_HRP)

    def subtest_02_tip_838(self):
        self.log.info("[02] tip 838: c pegs in P (2) and sends M from P's MWEB outputs; u sends U")
        node0, node1 = self.nodes
        c, u = self.c, self.u
        self.p = c.sendtoaddress(c.getnewaddress(address_type="mweb"), 5)
        p = self.decoded(c, self.p)
        sp = self.shape(p)
        self.log.info(f"  P {self.p[:16]}...  nVersion {p['version']}  canonical vin/vout {sp[:2]}  MWEB vin/vout {sp[2:]}")
        assert_equal(p["version"], LEGACY_TX_VERSION)
        assert sp[0] > 0 and sp[3] > 0, "a pegin spends canonical inputs into MWEB outputs"
        self.m = c.sendtoaddress(u.getnewaddress(address_type="mweb"), 1)
        sm = self.shape(self.decoded(c, self.m))
        self.log.info(f"  M {self.m[:16]}...  canonical vin/vout {sm[:2]}  MWEB vin/vout {sm[2:]}")
        assert_equal(sm[:2], (0, 0))                       # MWEB-only
        assert sm[2] > 0
        self.uu = u.sendtoaddress(node1.getnewaddress(address_type="mweb"), 1)
        su = self.shape(self.decoded(u, self.uu))
        self.log.info(f"  U {self.uu[:16]}...  canonical vin/vout {su[:2]}  MWEB vin/vout {su[2:]}")
        assert_equal(su[:2], (0, 0))                       # MWEB-only
        assert su[2] > 0
        self.sync_mempools()
        for node in self.nodes:
            assert_equal(set(node.getrawmempool()), {self.p, self.m, self.uu})
        assert self.p in node0.getmempoolentry(self.m)["depends"], "M must depend on P in the mempool"
        assert_equal(node0.getmempoolentry(self.uu)["depends"], [])
        for txid in (self.p, self.m, self.uu):
            node1.prioritisetransaction(txid=txid, fee_delta=-COIN)

    def subtest_03_block_839(self):
        self.log.info("[03] block 839: P and M leave, M first; U stays")
        node0, node1 = self.nodes
        before = [self.log_size(0), self.log_size(1)]
        h839 = self.mine(1)[0]
        assert_equal(node1.getblockcount(), FORK_HEIGHT - 1)
        assert self.p not in node1.getblock(h839)["tx"]
        for i, node in enumerate(self.nodes):
            assert_equal(set(node.getrawmempool()), {self.uu})
            lines = self.cleanup_lines(i, before[i])
            removed = [line.split(MARK, 1)[1].split(" ", 1)[0] for line in lines if MARK in line]
            names = {self.p: "P", self.m: "M", self.uu: "U"}
            self.log.info(f"  node{i}: removal order {[names.get(x, x[:8]) for x in removed]}")
            assert_equal(removed, [self.m, self.p])
            assert any(f"{MARK}{self.m} " in line and "spends a removed transaction" in line for line in lines)
            counts = [line.split("RIN3 fork: ", 1)[1] for line in lines if "RIN3 fork: removed " in line]
            self.log.info(f"  node{i}: {counts}")
            assert_equal(len(counts), 1)
            assert counts[0].startswith("removed 1 transaction(s) without the nVersion marker and "
                                        "1 descendant(s) of them"), counts

    def subtest_04_abandon_and_pegin_again(self):
        self.log.info("[04] c abandons P (and M) and pegs in again with the marker")
        c = self.c
        c.abandontransaction(self.p)
        # M spends P's MWEB outputs: abandoning P abandons M with it.
        assert self.is_abandoned(c, self.m), "M is not abandoned with P"
        assert_equal(c.gettransaction(self.m)["trusted"], False)
        self.log.info("  M is abandoned with P and not trusted")
        self.p2 = c.sendtoaddress(c.getnewaddress(address_type="mweb"), 5)
        p2 = self.decoded(c, self.p2)
        self.log.info(f"  P2 {self.p2[:16]}...  nVersion {p2['version']:#010x}")
        assert_equal(p2["version"], RIN_FORK_TX_VERSION)
        self.sync_mempools()
        for node in self.nodes:
            assert_equal(set(node.getrawmempool()), {self.uu, self.p2})
        self.nodes[1].prioritisetransaction(txid=self.uu, fee_delta=COIN)

    def subtest_05_blocks_840_841(self):
        self.log.info("[05] block 840 holds P2, U and a HogEx; block 841 follows")
        node0, node1 = self.nodes
        h839 = node1.getbestblockhash()
        h840 = self.mine(1)[0]
        block = node1.getblock(h840)
        assert self.p2 in block["tx"]
        hogex = get_hogex_tx(node1, h840)
        prev_hogex = get_hogex_tx(node1, h839)
        self.log.info(f"  block 840: {len(block['tx'])} canonical txs; HogEx {hogex.hash[:16]}... "
                      f"spends {hogex.vin[0].prevout.hash:064x}"[:120])
        assert_equal(block["tx"][-1], hogex.hash)
        assert_equal(hogex.vin[0].prevout.hash, prev_hogex.sha256)
        assert_equal(self.u.gettransaction(self.uu)["confirmations"], 1)
        assert_equal(self.c.gettransaction(self.p2)["confirmations"], 1)
        for node in self.nodes:
            assert_equal(node.getrawmempool(), [])
        self.mine(1)
        assert_equal(node0.getblockcount(), FORK_HEIGHT + 1)

    def run_test(self):
        self.subtest_01_setup()
        self.subtest_02_tip_838()
        self.subtest_03_block_839()
        self.subtest_04_abandon_and_pegin_again()
        self.subtest_05_blocks_840_841()
        self.log.info("ALL 5 SUBTESTS PASSED")


if __name__ == "__main__":
    MempoolRin3ForkMwebTest().main()
