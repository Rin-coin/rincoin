#!/usr/bin/env python3
# Copyright (c) 2026 The Rincoin Core developers
# Distributed under the MIT software license, see the accompanying
# file COPYING or http://www.opensource.org/licenses/mit-license.php.

"""
mempool_rin3_fork_cleanup.py

Rincoin RIN3 (RIP-0009) -- the mempool cleanup when the block before the
fork height connects (CTxMemPool::removeForRIN3Fork(), called from
ConnectTip() right after removeForBlock()).

From the fork height (regtest 840) on, a block may contain no transaction
other than the coinbase, the HogEx and MWEB-only ones that lacks the
nVersion marker RIN_FORK_TX_VERSION. Once block 839 connects, the mempool
removes every such transaction it holds, together with everything that
spends it; PreChecks() refuses new ones from that tip on.

No wallet is used: the transactions spend P2WSH(OP_TRUE) outputs
(MiniWallet's address), so their version can be set freely.

Four nodes: node0 sends, node1 mines, node2 lags behind (it stays at 836
with a version-2 transaction of its own), node3 mines a competing branch
from 838. node0, node2 and node3 each connect to node1.

    [01] tip 836: node2 is cut off and accepts Y (nVersion 2)
    [02] tip 838: node0 sends L (2), M (marker, spends L), N (2, spends L),
         A (2), D (marker, spends A), E (marker, spends D), B (2),
         C (marker), G (2) and K (2); node1 keeps all but L out of
         block 839; node3 is cut off holding all ten and then, alone,
         gets [09]'s diamond
    [03] block 839 (node1, L only): node0 and node1 remove N, A, B, G, K
         and the descendants D and E; C and M stay. The log names each,
         descendants before ancestors, and gives the counts
    [04] node0 re-creates G from the same input (RG) and K from another
         input (RK2), both with the marker; both are accepted
    [05] node3's branch (839' with all ten, then 840') overtakes: G and K
         confirm in 839'; RG conflicts with G and leaves; RK2 stays and
         confirms in 841 -- K and RK2 are both confirmed, the double
         payment that a re-creation from other inputs allows
    [06] node2 catches up from 836 to 841 in one go and removes Y when
         839' connects
    [07] node1 alone: invalidateblock 839' puts the branch's transactions
         back and reconnects node1's own 839, whose connection removes the
         unmarked ones again; invalidating that 839 too brings L back at tip
         838, where X (2) is accepted; reconsiderblock 839' removes X when
         839' connects again
    [08] at tip 841 a transaction without the marker is refused at entry
         and one with it is accepted and mined
    [09] the diamond, on node3 alone from [02] to [05]: X (marker) and U (2)
         spend coinbases and Y (marker) spends both. node3's 839' removes Y
         and then U ("1 ... and 1 descendant(s)") and keeps X, whose
         descendant state counts X alone again: the one shape here in which
         a removed transaction has an ancestor that stays in the mempool

-checkmempool is on by default on regtest, so CTxMemPool::check(), with its
RIN3 assertion, runs at the end of each ActivateBestChainStep() and after
each transaction accepted from a peer.

[03] checks the order three times: in the cleanup's own log lines, in the
order the removals are queued to the validation interface (the
"Enqueuing TransactionRemovedFromMempool" lines that test nodes log), which
is the order the wallet sees them in, and, when the build has ZMQ, in the
order node1 publishes them on its -zmqpubsequence socket ("zmq: Publish
hashtx mempool removal" lines; no subscriber is needed), where they must all
come before block 839's own "sequence block connect".
"""

from decimal import Decimal
import os

from test_framework.address import ADDRESS_BCRT1_P2WSH_OP_TRUE
from test_framework.messages import (
    COIN,
    COutPoint,
    CTransaction,
    CTxIn,
    CTxInWitness,
    CTxOut,
)
from test_framework.script import CScript, OP_TRUE
from test_framework.test_framework import BitcoinTestFramework
from test_framework.util import (
    assert_equal,
    assert_raises_rpc_error,
    hex_str_to_bytes,
    p2p_port,
    satoshi_round,
)

RIN_FORK_TX_VERSION = 0x52494e33   # "RIN3" = 1380535859
LEGACY_TX_VERSION = 2
FORK_HEIGHT = 840                  # regtest nRinHashForkHeight
FEE = Decimal("0.0001")
MARK = "RIN3 fork: removing "


class MempoolRin3ForkCleanupTest(BitcoinTestFramework):

    def set_test_params(self):
        self.num_nodes = 4
        self.setup_clean_chain = True
        args = [
            "-acceptnonstdtxn=0",
            # As in feature_rin3_enforcement.py: MWEB stays inactive.
            "-vbparams=mweb:9999999999:9999999999",
            "-whitelist=noban@127.0.0.1",
            # The tests read the cleanup's per-transaction log lines; keep
            # the mempool category on (the framework passes -debug as well).
            "-debug=mempool",
        ]
        self.extra_args = [args] * self.num_nodes

    def setup_network(self):
        # node1 publishes the mempool sequence over ZMQ when the build has it.
        # The PUB socket binds without a subscriber; -debug (set by the test
        # framework) makes it log each message.
        self.zmq = self.is_zmq_compiled()
        if self.zmq:
            self.extra_args = [list(a) for a in self.extra_args]
            self.extra_args[1].append("-zmqpubsequence=tcp://127.0.0.1:{}".format(p2p_port(self.num_nodes)))
        self.setup_nodes()
        for i in (0, 2, 3):
            self.connect_nodes(i, 1)
        self.sync_all()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def coinbase_utxo(self, height):
        node = self.nodes[1]
        cb = node.getblock(node.getblockhash(height), 2)["tx"][0]
        assert_equal(cb["vout"][0]["scriptPubKey"]["hex"], self.spk.hex())
        return (cb["txid"], 0, cb["vout"][0]["value"])

    def send(self, node, inputs, version, n_out=1):
        """Spend `inputs` [(txid, vout, value)] to n_out P2WSH(OP_TRUE)
        outputs with the given nVersion; return (txid, outputs)."""
        tx = CTransaction()
        tx.nVersion = version
        tx.vin = [CTxIn(COutPoint(int(txid, 16), vout)) for txid, vout, _ in inputs]
        each = satoshi_round((sum(v for _, _, v in inputs) - FEE) / n_out)
        tx.vout = [CTxOut(int(each * COIN), self.spk) for _ in range(n_out)]
        for _ in inputs:
            wit = CTxInWitness()
            wit.scriptWitness.stack = [CScript([OP_TRUE])]
            tx.wit.vtxinwit.append(wit)
        txid = node.sendrawtransaction(tx.serialize().hex())
        return txid, [(txid, i, each) for i in range(n_out)]

    def mempool(self, i):
        return set(self.nodes[i].getrawmempool())

    def log_lines(self, i, since):
        """node i's debug.log lines written after byte offset `since`."""
        path = os.path.join(self.nodes[i].datadir, "regtest", "debug.log")
        with open(path, "rb") as f:
            f.seek(since)
            text = f.read().decode("utf-8", "replace")
        return text.splitlines()

    def removal_lines(self, i, since):
        """The cleanup's log lines on node i written after byte offset `since`."""
        return [line for line in self.log_lines(i, since) if "RIN3 fork: " in line]

    def enqueued_removals(self, i, since):
        """txids of the TransactionRemovedFromMempool notifications queued on
        node i after byte offset `since`, in queue order."""
        tag = "Enqueuing TransactionRemovedFromMempool: txid="
        return [line.split(tag, 1)[1].split(" ", 1)[0]
                for line in self.log_lines(i, since) if tag in line]

    def log_size(self, i):
        return os.path.getsize(os.path.join(self.nodes[i].datadir, "regtest", "debug.log"))

    # ------------------------------------------------------------------
    # Subtests
    # ------------------------------------------------------------------

    def subtest_01_lagging_node(self):
        self.log.info("[01] tip 836: node2 is cut off and accepts Y (nVersion 2)")
        node1, node2 = self.nodes[1], self.nodes[2]
        node1.generatetoaddress(FORK_HEIGHT - 4, ADDRESS_BCRT1_P2WSH_OP_TRUE)
        self.sync_all()
        self.disconnect_nodes(2, 1)
        self.y, _ = self.send(node2, [self.coinbase_utxo(1)], LEGACY_TX_VERSION)
        assert_equal(self.mempool(2), {self.y})

    def subtest_02_tip_838(self):
        self.log.info("[02] tip 838: node0 sends ten transactions; node3 is cut off holding them")
        node0, node1, node3 = self.nodes[0], self.nodes[1], self.nodes[3]
        main = [node0, node1, node3]
        node1.generatetoaddress(2, ADDRESS_BCRT1_P2WSH_OP_TRUE)
        self.sync_blocks(main)
        assert_equal(node0.getblockcount(), FORK_HEIGHT - 2)

        t = {}
        t["L"], l_out = self.send(node0, [self.coinbase_utxo(2)], LEGACY_TX_VERSION, n_out=2)
        t["M"], _ = self.send(node0, [l_out[0]], RIN_FORK_TX_VERSION)
        t["N"], _ = self.send(node0, [l_out[1]], LEGACY_TX_VERSION)
        t["A"], a_out = self.send(node0, [self.coinbase_utxo(3)], LEGACY_TX_VERSION)
        t["D"], d_out = self.send(node0, a_out, RIN_FORK_TX_VERSION)
        t["E"], _ = self.send(node0, d_out, RIN_FORK_TX_VERSION)
        t["B"], _ = self.send(node0, [self.coinbase_utxo(4)], LEGACY_TX_VERSION)
        t["C"], _ = self.send(node0, [self.coinbase_utxo(5)], RIN_FORK_TX_VERSION)
        t["G"], _ = self.send(node0, [self.coinbase_utxo(6)], LEGACY_TX_VERSION)
        t["K"], _ = self.send(node0, [self.coinbase_utxo(7)], LEGACY_TX_VERSION)
        self.t = t
        self.sync_mempools(main)
        for i in (0, 1, 3):
            assert_equal(self.mempool(i), set(t.values()))
        # Keep all but L out of block 839 on the miner: a large negative fee
        # delta puts them below the block assembler's minimum fee rate.
        for name, txid in t.items():
            if name != "L":
                node1.prioritisetransaction(txid=txid, fee_delta=-COIN)
        self.disconnect_nodes(3, 1)
        # [09]'s diamond, on node3 alone: X (marker) and U (2) spend coinbases
        # 11 and 12, Y (marker) spends both. node3 keeps the three out of its
        # 839' in [05], so 839' connects with exactly these in its mempool.
        d = {}
        d["X"], x_out = self.send(node3, [self.coinbase_utxo(11)], RIN_FORK_TX_VERSION)
        d["U"], u_out = self.send(node3, [self.coinbase_utxo(12)], LEGACY_TX_VERSION)
        d["Y"], _ = self.send(node3, x_out + u_out, RIN_FORK_TX_VERSION)
        for txid in d.values():
            node3.prioritisetransaction(txid=txid, fee_delta=-COIN)
        self.d = d
        assert_equal(self.mempool(3), set(t.values()) | set(d.values()))
        assert_equal(self.mempool(1), set(t.values()))

    def subtest_03_block_839(self):
        self.log.info("[03] block 839 (L only): N, A, B, G, K and their descendants D, E leave; C, M stay")
        node0, node1 = self.nodes[0], self.nodes[1]
        t = self.t
        before = [self.log_size(0), self.log_size(1)]
        h839 = node1.generatetoaddress(1, ADDRESS_BCRT1_P2WSH_OP_TRUE)[0]
        self.h839 = h839
        self.sync_blocks([node0, node1])
        assert_equal(node1.getblock(h839)["tx"][1:], [t["L"]])
        for i in (0, 1):
            assert_equal(self.mempool(i), {t["C"], t["M"]})

        unmarked = sorted([t["N"], t["A"], t["B"], t["G"], t["K"]], key=lambda h: bytes.fromhex(h)[::-1])
        for i in (0, 1):
            lines = self.removal_lines(i, before[i])
            removed = [line.split(MARK, 1)[1].split(" ", 1)[0] for line in lines if MARK in line]
            self.log.info(f"  node{i}: removal order {[k for x in removed for k, v in t.items() if v == x]}")
            # Descendants first (E counts three ancestors, D two), then the
            # five without the marker in txid order.
            assert_equal(removed, [t["E"], t["D"]] + unmarked)
            # The notifications are queued in the same order. Block 839's own
            # transaction (L) leaves with reason BLOCK, which is not notified.
            assert_equal(self.enqueued_removals(i, before[i]), [t["E"], t["D"]] + unmarked)
            for line in lines:
                if t["D"] in line or t["E"] in line:
                    assert "(nVersion 0x52494e33, spends a removed transaction)" in line, line
                elif MARK in line:
                    assert "(nVersion 0x00000002)" in line, line
            assert any("RIN3 fork: removed 5 transaction(s) without the nVersion marker and "
                       "2 descendant(s) of them from the mempool" in line for line in lines), lines
            name = {v: k for k, v in t.items()}
            self.log.info(f"  node{i}: queued notifications {[name[x] for x in self.enqueued_removals(i, before[i])]}")
            for line in lines:
                if "RIN3 fork: removed " in line:
                    self.log.info(f"  node{i}: {line.split('RIN3 fork: ', 1)[1]}")
        if self.zmq:
            # The ZMQ notifier runs on the scheduler thread: drain the queue
            # before reading what it logged.
            node1.syncwithvalidationinterfacequeue()
            tag = "zmq: Publish hashtx mempool removal "
            lines = self.log_lines(1, before[1])
            published = [(n, line.split(tag, 1)[1].split(" ", 1)[0]) for n, line in enumerate(lines) if tag in line]
            connect = [n for n, line in enumerate(lines) if f"zmq: Publish sequence block connect {h839}" in line]
            self.log.info(f"  node1: ZMQ removals published {[k for _, x in published for k, v in t.items() if v == x]}")
            assert_equal([x for _, x in published], [t["E"], t["D"]] + unmarked)
            assert_equal(len(connect), 1)
            assert max(n for n, _ in published) < connect[0], "a removal was published after block 839's connect"
        else:
            self.log.info("  node1: built without ZMQ; the ZMQ order is not checked")
        # node3 is still at 838 and holds all ten, and the diamond.
        assert_equal(self.nodes[3].getblockcount(), FORK_HEIGHT - 2)
        assert_equal(self.mempool(3), set(t.values()) | set(self.d.values()))

    def subtest_04_recreate(self):
        self.log.info("[04] node0 re-creates G from its own input (RG) and K from another input (RK2)")
        node0, node1 = self.nodes[0], self.nodes[1]
        self.rg, _ = self.send(node0, [self.coinbase_utxo(6)], RIN_FORK_TX_VERSION)
        self.rk2, _ = self.send(node0, [self.coinbase_utxo(8)], RIN_FORK_TX_VERSION)
        self.sync_mempools([node0, node1])
        assert_equal(self.mempool(1), {self.t["C"], self.t["M"], self.rg, self.rk2})

    def subtest_05_one_block_reorg(self):
        self.log.info("[05] node3's 839' (all ten) and 840' overtake block 839")
        node0, node1, node3 = self.nodes[0], self.nodes[1], self.nodes[3]
        t = self.t
        self.before3 = self.log_size(3)                 # for [09]
        h839b, h840b = node3.generatetoaddress(2, ADDRESS_BCRT1_P2WSH_OP_TRUE)
        assert_equal(set(node3.getblock(h839b)["tx"][1:]), set(t.values()))
        # For [09], taken while node3 still has no peer: later, X stays in its
        # mempool only because the unbroadcast rebroadcast first runs 10-15
        # minutes after startup (ReattemptInitialBroadcast).
        self.d_mempool = self.mempool(3)
        self.d_entry = node3.getmempoolentry(self.d["X"])
        assert_equal(self.d_mempool, {self.d["X"]})
        self.connect_nodes(3, 1)
        self.sync_blocks([node0, node1, node3])
        assert_equal(node0.getbestblockhash(), h840b)
        for i in (0, 1):
            mp = self.mempool(i)
            assert self.rg not in mp, "RG spends G's input and must leave when 839' confirms G"
            assert self.rk2 in mp
            assert_equal(mp, {self.rk2})
        h841 = node1.generatetoaddress(1, ADDRESS_BCRT1_P2WSH_OP_TRUE)[0]
        self.sync_blocks([node0, node1, node3])
        assert self.rk2 in node1.getblock(h841)["tx"]
        assert t["K"] in node1.getblock(h839b)["tx"]
        self.log.info("  K (839') and RK2 (841) are both confirmed: a re-creation from other inputs pays twice")
        self.h839b = h839b

    def subtest_06_lagging_node_catches_up(self):
        self.log.info("[06] node2 catches up from 836 to 841 and removes Y at 839'")
        node2 = self.nodes[2]
        with node2.assert_debug_log([f"{MARK}{self.y} (nVersion 0x00000002)"], timeout=60):
            self.connect_nodes(2, 1)
            self.sync_blocks()
        assert_equal(node2.getblockcount(), FORK_HEIGHT + 1)
        assert self.y not in self.mempool(2)

    def subtest_07_invalidate_reconsider(self):
        self.log.info("[07] node1 alone: invalidating 839' reconnects its own 839, which removes the "
                      "branch's unmarked transactions again; at 838, X (2) is accepted and "
                      "reconsiderblock 839' removes it")
        node1 = self.nodes[1]
        t = self.t
        for i in (0, 2, 3):
            self.disconnect_nodes(i, 1)
        # node1 still holds the block 839 it mined in [03] (L only). Invalidating
        # 839' puts the branch's transactions back into the mempool at tip 838
        # and then reconnects that block 839, so the cleanup runs again.
        before = self.log_size(1)
        node1.invalidateblock(self.h839b)
        assert_equal(node1.getbestblockhash(), self.h839)
        assert_equal(self.mempool(1), {t["C"], t["M"], self.rk2})
        lines = self.removal_lines(1, before)
        removed = {line.split(MARK, 1)[1].split(" ", 1)[0] for line in lines if MARK in line}
        assert_equal(removed, {t["N"], t["A"], t["B"], t["G"], t["K"], t["D"], t["E"]})
        assert any("removed 5 transaction(s) without the nVersion marker and 2 descendant(s)" in line
                   for line in lines), lines
        # Down to 838: L, confirmed only in node1's 839, comes back too.
        node1.invalidateblock(self.h839)
        assert_equal(node1.getblockcount(), FORK_HEIGHT - 2)
        assert_equal(self.mempool(1), {t["L"], t["C"], t["M"], self.rk2})
        x, _ = self.send(node1, [self.coinbase_utxo(9)], LEGACY_TX_VERSION)
        with node1.assert_debug_log([f"{MARK}{x} (nVersion 0x00000002)"], timeout=30):
            node1.reconsiderblock(self.h839b)
        assert_equal(node1.getblockcount(), FORK_HEIGHT + 1)
        assert_equal(self.mempool(1), set())
        node1.reconsiderblock(self.h839)          # valid again, less work: no reorg
        assert_equal(node1.getblockcount(), FORK_HEIGHT + 1)
        for i in (0, 2, 3):
            self.connect_nodes(i, 1)
        self.sync_blocks()

    def subtest_08_after_the_fork(self):
        self.log.info("[08] tip 841: nVersion 2 is refused at entry; the marker is accepted and mined")
        node0, node1 = self.nodes[0], self.nodes[1]
        assert_raises_rpc_error(-26, "bad-tx-rinhash-version",
                                self.send, node0, [self.coinbase_utxo(10)], LEGACY_TX_VERSION)
        z, _ = self.send(node0, [self.coinbase_utxo(10)], RIN_FORK_TX_VERSION)
        self.sync_mempools([node0, node1])
        h = node1.generatetoaddress(1, ADDRESS_BCRT1_P2WSH_OP_TRUE)[0]
        assert z in node1.getblock(h)["tx"]
        self.sync_blocks()

    def subtest_09_diamond(self):
        self.log.info("[09] node3's 839' removed the diamond's Y and U and kept X, whose descendant state counts X alone")
        node3 = self.nodes[3]
        d = self.d
        lines = self.removal_lines(3, self.before3)
        removed = [line.split(MARK, 1)[1].split(" ", 1)[0] for line in lines if MARK in line]
        self.log.info(f"  node3: removal order {[k for x in removed for k, v in d.items() if v == x]}")
        # Y counts two ancestors (X, U), U none: Y leaves first.
        assert_equal(removed, [d["Y"], d["U"]])
        assert any(f"{MARK}{d['Y']} (nVersion 0x52494e33, spends a removed transaction)" in line for line in lines), lines
        assert any(f"{MARK}{d['U']} (nVersion 0x00000002)" in line for line in lines), lines
        assert any("RIN3 fork: removed 1 transaction(s) without the nVersion marker and "
                   "1 descendant(s) of them from the mempool" in line for line in lines), lines
        # X stays outside the removed set, so Y's removal must still take Y
        # out of X's descendant state (the update U32 must not skip). The
        # values are the ones [05] took right after 839', before node3 had a
        # peer again.
        assert_equal(self.d_mempool, {d["X"]})
        e = self.d_entry
        self.log.info(f"  node3 now (not asserted): X {'still' if d['X'] in self.mempool(3) else 'no longer'} in its mempool")
        self.log.info(f"  node3: X descendantcount {e['descendantcount']}, descendantsize {e['descendantsize']} "
                      f"(vsize {e['vsize']}), ancestorcount {e['ancestorcount']}")
        assert_equal(e["descendantcount"], 1)
        assert_equal(e["descendantsize"], e["vsize"])
        assert_equal(e["fees"]["descendant"], e["fees"]["modified"])
        assert_equal(e["ancestorcount"], 1)

    # ------------------------------------------------------------------

    def run_test(self):
        self.spk = hex_str_to_bytes(self.nodes[0].validateaddress(ADDRESS_BCRT1_P2WSH_OP_TRUE)["scriptPubKey"])
        self.subtest_01_lagging_node()
        self.subtest_02_tip_838()
        self.subtest_03_block_839()
        self.subtest_04_recreate()
        self.subtest_05_one_block_reorg()
        self.subtest_06_lagging_node_catches_up()
        self.subtest_07_invalidate_reconsider()
        self.subtest_08_after_the_fork()
        self.subtest_09_diamond()
        self.log.info("ALL 9 SUBTESTS PASSED")


if __name__ == "__main__":
    MempoolRin3ForkCleanupTest().main()
