#!/usr/bin/env python3
# Copyright (c) 2026 The Rincoin Core developers
# Distributed under the MIT software license, see the accompanying
# file COPYING or http://www.opensource.org/licenses/mit-license.php.

"""
wallet_rin3_boundary_rescue.py

Rincoin RIN3 (nVersion replay protection) -- wallet transactions without the
nVersion marker that are still unconfirmed when the block before the fork
height is connected.

In a block at or above the fork height, RIN3 requires nVersion
RIN_FORK_TX_VERSION (the marker) on every transaction except the coinbase,
the HogEx and MWEB-only ones (validation.cpp, ContextualCheckBlock()), and
the mempool refuses such a transaction once the tip is one block below the
fork height (PreChecks()). When that block is connected,
CTxMemPool::removeForRIN3Fork() removes every unmarked transaction still in
the mempool, with its in-mempool descendants, and notifies the removal with
MemPoolRemovalReason::RIN3_FORK. The wallet handles that reason as it
handles CONFLICT: the transaction stays UNCONFIRMED with its inputs counted
as spent, and -walletnotify fires for it.

From then on, until the user abandons it or a transaction spending one of
the same inputs confirms:
  - its change is not trusted, so no funding RPC selects it;
  - abandontransaction succeeds at once, without a restart;
  - bumpfee builds a marker replacement that the mempool accepts, as long
    as the transaction signals BIP 125 and has no child in the wallet;
  - a re-creation from the same inputs is accepted.

Five nodes. node0 holds the sending wallets (the default one and w2), node1
mines, node2 lags behind, node3 and node4 are stopped across the fork. Each
node appends "<wallet>:<txid>" to its own notify.log through -walletnotify,
and the test counts lines per txid: AddToWallet() runs the command on a
detached thread without waiting (wallet.cpp), so a late line from an earlier
event must not be mistaken for the one under test.

Test matrix (regtest fork height 840):
  [01] fund w2 and node2-4; node2, cut off at tip 836, sends Y (nVersion 2)
  [02] tip 838: node3 and node4, cut off, send Z1 and Z2 and stop; node0
       sends A (BIP 125), B (not), D (BIP 125) and E (spends D's change);
       w2 sends T from its 10 RIN coin. All carry nVersion 2.
  [03] block 839 (node1, without them): A, B, D, E and T leave both
       mempools, E before D; the log names each; -walletnotify fires for
       exactly those wallet transactions
  [04] w2: T is not trusted and its change is in no balance; the five
       funding RPCs refuse an amount only that change would cover, and fund
       one the confirmed coins cover without T's outputs, with the marker
  [05] bumpfee: D -> refused (a descendant in the wallet); B -> refused
       (not BIP 125); A -> replacement R_A with the marker, accepted
  [06] abandontransaction at once: D (and its child E), and B
  [07] B re-created from its inputs (fundrawtransaction) -> R_B with the
       marker, accepted
  [08] node0 restarts: every transaction in mempool.dat loads again
  [09] blocks 840 and 841: R_A, R_B and w2's payments confirm; A and B show
       as conflicted, D and E stay abandoned
  [10] node2 catches up from 836: Y leaves at block 839; -walletnotify
  [11] node3 restarts at tip 838 (Z1 loads from mempool.dat) and catches
       up: Z1 leaves at block 839; -walletnotify
  [12] node4 reaches 841 with its mempool off, then restarts with it: Z2
       fails to load, no notification, Z2 stays unconfirmed and abandonable
"""

import os
import re
import time
from collections import Counter
from decimal import Decimal

from test_framework.messages import COIN
from test_framework.test_framework import BitcoinTestFramework
from test_framework.util import assert_equal, assert_raises_rpc_error

RIN_FORK_TX_VERSION = 0x52494e33   # "RIN3" ASCII = 1380535859
LEGACY_TX_VERSION   = 2            # CTransaction::CURRENT_VERSION
FORK_HEIGHT         = 840          # regtest nRinHashForkHeight
MARK                = "RIN3 fork: removing "
IMPORTED            = re.compile(r"Imported mempool transactions from disk: (\d+) succeeded, (\d+) failed, "
                                 r"(\d+) expired, (\d+) already there")


def nkey(wallet, txid):
    # A line of notify.log: -walletnotify=echo %w:%s >> notify.log. %w is the
    # shell-escaped wallet name, so the default wallet ("") gives ":<txid>".
    return "{}:{}".format(wallet, txid)


class WalletRin3BoundaryRescueTest(BitcoinTestFramework):

    def set_test_params(self):
        self.num_nodes = 5
        self.setup_clean_chain = True

    def skip_test_if_missing_module(self):
        self.skip_if_no_wallet()

    def setup_network(self):
        self.notify_logs = []
        self.extra_args = []
        for i in range(self.num_nodes):
            d = os.path.join(self.options.tmpdir, "walletnotify{}".format(i))
            os.mkdir(d)
            self.notify_logs.append(os.path.join(d, "notify.log"))
            self.extra_args.append([
                "-fallbackfee=0.001",
                "-acceptnonstdtxn=0",
                # Disable MWEB for this test, as feature_rin3_enforcement.py does:
                # a far-future timestamp (~2286) stands in for NEVER_ACTIVE.
                "-vbparams=mweb:9999999999:9999999999",
                # Relay without the trickle delay (inbound peers; every node
                # connects to node0).
                "-whitelist=noban@127.0.0.1",
                "-walletnotify=echo %w:%s >> {}".format(self.notify_logs[i]),
                # The cleanup's per-transaction log lines (assert_debug_log);
                # the framework passes -debug as well.
                "-debug=mempool",
            ])
        self.setup_nodes()
        for i in range(1, self.num_nodes):
            self.connect_nodes(i, 0)
        self.sync_all()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def notify_counts(self, i):
        """Lines per "<wallet>:<txid>" in node i's notify.log."""
        try:
            with open(self.notify_logs[i], encoding="utf-8") as f:
                return Counter(line.strip() for line in f if line.strip())
        except FileNotFoundError:
            return Counter()

    def settle(self, i, timeout=30):
        """Wait until node i has drained its validation queue and its
        notify.log has stopped growing for a second; return the counts."""
        if self.nodes[i].running:
            self.nodes[i].syncwithvalidationinterfacequeue()
        prev = self.notify_counts(i)
        deadline = time.time() + timeout
        while time.time() < deadline:
            time.sleep(1)
            cur = self.notify_counts(i)
            if cur == prev:
                return cur
            prev = cur
        raise AssertionError("notify.log of node{} kept growing".format(i))

    def expect_delta(self, i, base, delta, timeout=30):
        """Wait until the counts of node i reach base + delta, then require
        that nothing else changed."""
        self.wait_until(lambda: all(self.notify_counts(i)[k] >= base[k] + v for k, v in delta.items()),
                        timeout=timeout)
        cur = self.settle(i)
        got = {k: cur[k] - base[k] for k in set(cur) | set(base) if cur[k] != base[k]}
        self.log.info(f"  node{i} -walletnotify lines added: {len(got)} txid(s), {sum(got.values())} line(s)")
        assert_equal(got, dict(delta))
        return cur

    def debug_log(self, i):
        node = self.nodes[i]
        return os.path.join(node.datadir, node.chain, "debug.log")

    def log_size(self, i):
        return os.path.getsize(self.debug_log(i))

    def log_lines_since(self, i, offset):
        with open(self.debug_log(i), encoding="utf-8") as f:
            f.seek(offset)
            return f.read().splitlines()

    @staticmethod
    def version_of(rpc, txid):
        return rpc.decoderawtransaction(rpc.gettransaction(txid)["hex"])["version"]

    @staticmethod
    def vin_txids(vin):
        return {i["txid"] for i in vin}

    @staticmethod
    def is_abandoned(rpc, txid):
        """gettransaction reports "abandoned" only on its "send" details
        (rpcwallet.cpp, ListTransactions()), not at the top level."""
        sends = [d for d in rpc.gettransaction(txid)["details"] if d["category"] == "send"]
        assert sends, txid
        flags = {d["abandoned"] for d in sends}
        assert_equal(len(flags), 1)
        return flags.pop()

    def wallets(self):
        node0 = self.nodes[0]
        self.w0 = node0.get_wallet_rpc(self.default_wallet_name)
        self.w2 = node0.get_wallet_rpc("w2")

    def mine(self, i, n):
        node = self.nodes[i]
        return node.generatetoaddress(n, node.get_wallet_rpc(self.default_wallet_name).getnewaddress()
                                      if i == 0 else node.getnewaddress())

    # ------------------------------------------------------------------
    # Subtests
    # ------------------------------------------------------------------

    def subtest_01_setup(self):
        self.log.info("[01] fund w2 and node2-4; node2, cut off at tip 836, sends Y (nVersion 2)")
        node0, node1, node2 = self.nodes[0], self.nodes[1], self.nodes[2]
        node0.createwallet("w2")
        self.wallets()
        self.log.info(f"  Mining from h=0 to h={FORK_HEIGHT - 10} on node0 ...")
        self.mine(0, FORK_HEIGHT - 10)
        self.sync_blocks()

        self.w0.sendtoaddress(self.w2.getnewaddress(), 10)
        self.w0.sendmany("", {self.w2.getnewaddress(): 1 for _ in range(5)})
        for i in (2, 3, 4):
            self.w0.sendtoaddress(self.nodes[i].getnewaddress(), 5)
        self.mine(0, 6)                                    # tip 836
        self.sync_blocks()
        assert_equal(node2.getblockcount(), FORK_HEIGHT - 4)
        self.x_coin = next(u for u in self.w2.listunspent() if u["amount"] == Decimal("10"))
        assert_equal(len([u for u in self.w2.listunspent() if u["amount"] == Decimal("1")]), 5)

        self.disconnect_nodes(2, 0)
        self.tx_y = node2.sendtoaddress(node2.getnewaddress(), 1)
        assert_equal(self.version_of(node2, self.tx_y), LEGACY_TX_VERSION)
        assert self.tx_y in node2.getrawmempool()
        assert self.tx_y not in node1.getrawmempool()

    def subtest_02_legacy_at_838(self):
        self.log.info("[02] tip 838: node3 and node4 send Z1 and Z2 cut off and stop; node0 sends A, B, D, E; "
                      "w2 sends T")
        node0, node1, node3, node4 = self.nodes[0], self.nodes[1], self.nodes[3], self.nodes[4]
        self.mine(0, 2)                                    # tip 838
        self.sync_blocks([node0, node1, node3, node4])
        assert_equal(node0.getblockcount(), FORK_HEIGHT - 2)

        self.disconnect_nodes(3, 0)
        self.disconnect_nodes(4, 0)
        self.tx_z1 = node3.sendtoaddress(node3.getnewaddress(), 1)
        self.tx_z2 = node4.sendtoaddress(node4.getnewaddress(), 1)
        for node, txid in ((node3, self.tx_z1), (node4, self.tx_z2)):
            assert_equal(self.version_of(node, txid), LEGACY_TX_VERSION)
            assert txid in node.getrawmempool()
        self.stop_node(3)                                  # mempool.dat holds Z1
        self.stop_node(4)                                  # mempool.dat holds Z2

        w0, w2 = self.w0, self.w2
        base = self.settle(0)
        self.tx_a = w0.sendtoaddress(w0.getnewaddress(), 1, "", "", False, True)
        self.tx_b = w0.sendtoaddress(w0.getnewaddress(), 1, "", "", False, False)
        self.tx_d = w0.sendtoaddress(w0.getnewaddress(), 1, "", "", False, True)
        d = w0.decoderawtransaction(w0.gettransaction(self.tx_d)["hex"])
        change_n, change_value = None, None
        for v in d["vout"]:
            spk = v["scriptPubKey"]
            addr = spk["address"] if "address" in spk else spk["addresses"][0]
            if w0.getaddressinfo(addr)["ischange"]:
                change_n, change_value = v["n"], v["value"]
        assert change_n is not None
        # Half of D's change: coin selection decides how large that change is.
        e_amount = (change_value / 2).quantize(Decimal("0.00000001"))
        self.log.info(f"  D's change {change_value}, E pays {e_amount}")
        assert change_value > e_amount > 0
        raw = w0.createrawtransaction([{"txid": self.tx_d, "vout": change_n}], [{w0.getnewaddress(): e_amount}])
        funded = w0.fundrawtransaction(raw, {"add_inputs": False})
        self.tx_e = w0.sendrawtransaction(w0.signrawtransactionwithwallet(funded["hex"])["hex"])

        raw = w2.createrawtransaction([{"txid": self.x_coin["txid"], "vout": self.x_coin["vout"]}],
                                      [{node1.getnewaddress(): 3}])
        funded = w2.fundrawtransaction(raw, {"add_inputs": False})
        self.tx_t = w2.sendrawtransaction(w2.signrawtransactionwithwallet(funded["hex"])["hex"])

        self.removed = {"A": self.tx_a, "B": self.tx_b, "D": self.tx_d, "E": self.tx_e, "T": self.tx_t}
        for name, txid in self.removed.items():
            rpc = w2 if name == "T" else w0
            version = self.version_of(rpc, txid)
            self.log.info(f"  {name} {txid[:16]}...  nVersion = {version}")
            assert_equal(version, LEGACY_TX_VERSION)
        for name in ("B", "D"):
            vin = w0.decoderawtransaction(w0.gettransaction(self.removed[name])["hex"])["vin"]
            assert self.tx_a not in self.vin_txids(vin)
        # sendtoaddress: two lines (AddToWallet in CommitTransaction, then the
        # mempool acceptance through SyncTransaction); sendrawtransaction: one.
        self.notify_base0 = self.expect_delta(0, base, {
            nkey(self.default_wallet_name, self.tx_a): 2, nkey(self.default_wallet_name, self.tx_b): 2,
            nkey(self.default_wallet_name, self.tx_d): 2, nkey(self.default_wallet_name, self.tx_e): 1,
            nkey("w2", self.tx_t): 1})
        self.sync_mempools([node0, node1])
        assert_equal(set(node1.getrawmempool()), set(self.removed.values()))
        # Keep all of them out of block 839 on the miner.
        for txid in self.removed.values():
            node1.prioritisetransaction(txid=txid, fee_delta=-COIN)

    def subtest_03_block_839(self):
        self.log.info("[03] block 839 (node1, without them): A, B, D, E and T leave both mempools; "
                      "-walletnotify fires for each")
        node0, node1 = self.nodes[0], self.nodes[1]
        base = self.settle(0)
        assert_equal(base, self.notify_base0)
        offsets = [self.log_size(0), self.log_size(1)]
        expected = [MARK + txid for txid in self.removed.values()]
        with node0.assert_debug_log(expected, timeout=30), node1.assert_debug_log(expected, timeout=30):
            block = node1.generatetoaddress(1, node1.getnewaddress())[0]
            self.sync_blocks([node0, node1])
        assert_equal(node0.getblockcount(), FORK_HEIGHT - 1)
        assert_equal(node1.getblock(block)["tx"][1:], [])
        for node in (node0, node1):
            assert_equal(node.getmempoolinfo()["size"], 0)
        for i in (0, 1):
            lines = [line for line in self.log_lines_since(i, offsets[i]) if "RIN3 fork: " in line]
            order = [line.split(MARK, 1)[1].split(" ", 1)[0] for line in lines if MARK in line]
            names = [k for x in order for k, v in self.removed.items() if v == x]
            self.log.info(f"  node{i}: removal order {names}")
            assert order.index(self.tx_e) < order.index(self.tx_d)
            assert any("RIN3 fork: removed 5 transaction(s) without the nVersion marker and "
                       "0 descendant(s) of them from the mempool" in line for line in lines), lines

        # One more line for each removed wallet transaction, and nothing else.
        delta = {nkey(self.default_wallet_name, self.removed[k]): 1 for k in ("A", "B", "D", "E")}
        delta[nkey("w2", self.tx_t)] = 1
        self.expect_delta(0, base, delta)
        for name, txid in self.removed.items():
            info = (self.w2 if name == "T" else self.w0).gettransaction(txid)
            assert_equal(info["confirmations"], 0)
            assert_equal(info["trusted"], False)

    def subtest_04_change_not_spent(self):
        self.log.info("[04] w2: T's change is not trusted; the funding RPCs neither spend it nor fall back on it")
        w2 = self.w2
        bal = w2.getbalances()["mine"]
        self.log.info(f"  w2 balances {bal}")
        assert_equal(bal["trusted"], Decimal("5.00000000"))
        assert_equal(bal["untrusted_pending"], Decimal("0"))
        assert self.tx_t not in {u["txid"] for u in w2.listunspent(0)}
        dest = self.w0.getnewaddress()
        big = Decimal("6")                                  # only T's change would cover it
        assert_raises_rpc_error(-6, "Insufficient funds", w2.sendtoaddress, dest, big)
        assert_raises_rpc_error(-6, "Insufficient funds", w2.sendmany, "", {dest: big})
        assert_raises_rpc_error(-4, "Insufficient funds", w2.send, [{dest: big}])
        assert_raises_rpc_error(-4, "Insufficient funds", w2.fundrawtransaction,
                                w2.createrawtransaction([], [{dest: big}]))
        assert_raises_rpc_error(-4, "Insufficient funds", w2.walletcreatefundedpsbt, [], [{dest: big}])

        small = Decimal("0.5")                              # the confirmed coins cover it
        funded = []
        self.w2_sent = []
        for txid in (w2.sendtoaddress(dest, small), w2.sendmany("", {dest: small}),
                     w2.send([{dest: small}])["txid"]):
            self.w2_sent.append(txid)
            funded.append(("sent " + txid[:16], w2.decoderawtransaction(w2.gettransaction(txid)["hex"])))
        funded.append(("fundrawtransaction",
                       w2.decoderawtransaction(w2.fundrawtransaction(w2.createrawtransaction([], [{dest: small}]))["hex"])))
        funded.append(("walletcreatefundedpsbt",
                       w2.decodepsbt(w2.walletcreatefundedpsbt([], [{dest: small}])["psbt"])["tx"]))
        for what, tx in funded:
            assert self.tx_t not in self.vin_txids(tx["vin"]), what
            assert_equal(tx["version"], RIN_FORK_TX_VERSION)
        self.sync_mempools([self.nodes[0], self.nodes[1]])

    def subtest_05_bumpfee(self):
        self.log.info("[05] bumpfee: D has a child in the wallet, B does not signal; A's replacement is accepted")
        w0 = self.w0
        assert_raises_rpc_error(-8, "Transaction has descendants in the wallet", w0.bumpfee, self.tx_d)
        assert_raises_rpc_error(-4, "Transaction is not BIP 125 replaceable", w0.bumpfee, self.tx_b)
        res = w0.bumpfee(self.tx_a)
        assert_equal(res["errors"], [])
        self.tx_ra = res["txid"]
        version = self.version_of(w0, self.tx_ra)
        self.log.info(f"  R_A {self.tx_ra[:16]}...  nVersion = {version} ({version:#010x})")
        assert_equal(version, RIN_FORK_TX_VERSION)
        self.wait_until(lambda: all(self.tx_ra in n.getrawmempool() for n in self.nodes[:2]), timeout=30)

    def subtest_06_abandon(self):
        self.log.info("[06] abandontransaction at once: D (and its child E), and B")
        w0 = self.w0
        for txid in (self.tx_d, self.tx_e, self.tx_b):
            assert_equal(self.is_abandoned(w0, txid), False)
        w0.abandontransaction(self.tx_d)
        for txid in (self.tx_d, self.tx_e):
            assert_equal(self.is_abandoned(w0, txid), True)
        w0.abandontransaction(self.tx_b)
        assert_equal(self.is_abandoned(w0, self.tx_b), True)

    def subtest_07_recreate_b(self):
        self.log.info("[07] B re-created from its inputs: R_B carries the marker and is accepted")
        w0 = self.w0
        b_vin = w0.decoderawtransaction(w0.gettransaction(self.tx_b)["hex"])["vin"]
        inputs = [{"txid": i["txid"], "vout": i["vout"]} for i in b_vin]
        funded = w0.fundrawtransaction(w0.createrawtransaction(inputs, [{w0.getnewaddress(): 1}]))["hex"]
        assert_equal(w0.decoderawtransaction(funded)["version"], RIN_FORK_TX_VERSION)
        signed = w0.signrawtransactionwithwallet(funded)
        assert_equal(signed["complete"], True)
        self.tx_rb = w0.sendrawtransaction(signed["hex"])
        self.wait_until(lambda: all(self.tx_rb in n.getrawmempool() for n in self.nodes[:2]), timeout=30)

    def subtest_08_restart_node0(self):
        self.log.info("[08] node0 restarts: every transaction in mempool.dat loads again")
        node0 = self.nodes[0]
        saved = set(node0.getrawmempool())
        assert {self.tx_ra, self.tx_rb} | set(self.w2_sent) <= saved
        offset = self.log_size(0)
        self.restart_node(0)
        self.wait_until(lambda: node0.getmempoolinfo()["loaded"], timeout=30)
        lines = [m for m in map(IMPORTED.search, self.log_lines_since(0, offset)) if m]
        assert_equal(len(lines), 1)
        succeeded, failed, expired, already = map(int, lines[0].groups())
        self.log.info(f"  LoadMempool: {succeeded} succeeded, {failed} failed, {expired} expired, "
                      f"{already} already there ({len(saved)} saved)")
        assert_equal(failed, 0)
        assert_equal(succeeded + already, len(saved))
        assert saved <= set(node0.getrawmempool())
        node0.loadwallet("w2")
        self.wallets()
        self.connect_nodes(1, 0)

    def subtest_09_blocks_840_841(self):
        self.log.info("[09] blocks 840 and 841: the replacements and w2's payments confirm; A and B are conflicted")
        node0, node1 = self.nodes[0], self.nodes[1]
        self.sync_mempools([node0, node1])
        block = node1.generatetoaddress(1, node1.getnewaddress())[0]
        self.sync_blocks([node0, node1])
        assert_equal(node1.getblockstats(FORK_HEIGHT)["subsidy"], 400000000)
        txs = node1.getblock(block)["tx"]
        for txid in [self.tx_ra, self.tx_rb] + self.w2_sent:
            assert txid in txs
        node1.generatetoaddress(1, node1.getnewaddress())
        self.sync_blocks([node0, node1])
        assert_equal(node0.getblockcount(), FORK_HEIGHT + 1)
        for node in (node0, node1):
            assert_equal(node.getmempoolinfo()["size"], 0)

        w0 = self.w0
        a, b = w0.gettransaction(self.tx_a), w0.gettransaction(self.tx_b)
        # A conflicted transaction reports minus the depth of the block that
        # conflicts with it (CWalletTx::GetDepthInMainChain()): R_A and R_B
        # are in block 840 and the tip is 841, so -2.
        for info, rtxid in ((a, self.tx_ra), (b, self.tx_rb)):
            r = w0.gettransaction(rtxid)
            assert_equal(r["blockheight"], FORK_HEIGHT)
            assert_equal(r["confirmations"], 2)
            assert_equal(info["confirmations"], -r["confirmations"])
        assert self.tx_ra in a["walletconflicts"]
        assert self.tx_rb in b["walletconflicts"]
        assert_equal(a["replaced_by_txid"], self.tx_ra)
        assert_equal(w0.gettransaction(self.tx_ra)["replaces_txid"], self.tx_a)
        for txid in (self.tx_d, self.tx_e):
            assert_equal(self.is_abandoned(w0, txid), True)
            assert_equal(w0.gettransaction(txid)["confirmations"], 0)

    def subtest_10_lagging_node(self):
        self.log.info("[10] node2 catches up from 836: Y leaves at block 839; -walletnotify fires")
        node2 = self.nodes[2]
        base = self.settle(2)
        with node2.assert_debug_log([MARK + self.tx_y], timeout=60):
            self.connect_nodes(2, 0)
            self.sync_blocks([self.nodes[0], node2])
        assert self.tx_y not in node2.getrawmempool()
        self.expect_delta(2, base, {nkey(self.default_wallet_name, self.tx_y): 1})
        assert_equal(node2.gettransaction(self.tx_y)["trusted"], False)

    def subtest_11_stopped_at_838(self):
        self.log.info("[11] node3 restarts at tip 838, Z1 loads from mempool.dat; catching up removes it at 839")
        node3 = self.nodes[3]
        self.start_node(3)
        self.wait_until(lambda: node3.getmempoolinfo()["loaded"], timeout=30)
        assert_equal(node3.getblockcount(), FORK_HEIGHT - 2)
        assert self.tx_z1 in node3.getrawmempool()
        base = self.settle(3)
        with node3.assert_debug_log([MARK + self.tx_z1], timeout=60):
            self.connect_nodes(3, 0)
            self.sync_blocks([self.nodes[0], node3])
        assert self.tx_z1 not in node3.getrawmempool()
        self.expect_delta(3, base, {nkey(self.default_wallet_name, self.tx_z1): 1})

    def subtest_12_stopped_and_loaded_after_839(self):
        self.log.info("[12] node4 reaches 841 with its mempool off, then restarts with it: Z2 fails to load, "
                      "no notification")
        node4 = self.nodes[4]
        self.start_node(4, extra_args=self.extra_args[4] + ["-persistmempool=0", "-walletbroadcast=0"])
        assert self.tx_z2 not in node4.getrawmempool()
        self.connect_nodes(4, 0)
        self.sync_blocks([self.nodes[0], node4])
        assert self.tx_z2 not in node4.getrawmempool()
        self.stop_node(4)                 # -persistmempool=0: the mempool.dat holding Z2 is left as it was
        base = self.settle(4)             # node4 is stopped: the file no longer changes
        with node4.assert_debug_log(["Imported mempool transactions from disk: 0 succeeded, 1 failed"], timeout=30):
            self.start_node(4)
            self.wait_until(lambda: node4.getmempoolinfo()["loaded"], timeout=30)
        assert_equal(node4.getblockcount(), FORK_HEIGHT + 1)
        assert self.tx_z2 not in node4.getrawmempool()
        cur = self.settle(4)
        z2 = nkey(self.default_wallet_name, self.tx_z2)
        self.log.info(f"  node4 -walletnotify lines for Z2: {base[z2]} before the restart, {cur[z2]} after; "
                      f"other changes {dict((k, cur[k] - base[k]) for k in cur if cur[k] != base[k] and k != z2)}")
        assert_equal(cur[z2], base[z2])
        info = node4.gettransaction(self.tx_z2)
        assert_equal(info["confirmations"], 0)
        assert_equal(info["trusted"], False)
        assert_equal(self.is_abandoned(node4, self.tx_z2), False)
        node4.abandontransaction(self.tx_z2)
        assert_equal(self.is_abandoned(node4, self.tx_z2), True)

    # ------------------------------------------------------------------

    def run_test(self):
        self.log.info("=" * 60)
        self.log.info("  RIN3 boundary -- unmarked wallet transactions at the fork")
        self.log.info(f"  nRinHashForkHeight (regtest) = {FORK_HEIGHT}")
        self.log.info(f"  RIN_FORK_TX_VERSION = {RIN_FORK_TX_VERSION:#010x} = {RIN_FORK_TX_VERSION}")
        self.log.info("=" * 60)

        self.subtest_01_setup()
        self.subtest_02_legacy_at_838()
        self.subtest_03_block_839()
        self.subtest_04_change_not_spent()
        self.subtest_05_bumpfee()
        self.subtest_06_abandon()
        self.subtest_07_recreate_b()
        self.subtest_08_restart_node0()
        self.subtest_09_blocks_840_841()
        self.subtest_10_lagging_node()
        self.subtest_11_stopped_at_838()
        self.subtest_12_stopped_and_loaded_after_839()

        self.log.info("=" * 60)
        self.log.info("  ALL 12 SUBTESTS PASSED")
        self.log.info("  unmarked wallet transactions leave the mempool at block 839 and are")
        self.log.info("  notified; their change is not spent; abandon, bumpfee and re-creation")
        self.log.info("  work without a restart")
        self.log.info("=" * 60)


if __name__ == "__main__":
    WalletRin3BoundaryRescueTest().main()
