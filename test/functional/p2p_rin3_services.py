#!/usr/bin/env python3
# Copyright (c) 2026 The Rincoin Core developers
# Distributed under the MIT software license, see the accompanying
# file COPYING or http://www.opensource.org/licenses/mit-license.php.

"""
p2p_rin3_services.py

Rincoin RIN3 (RIP-0009) P2P deployment -- capability signaling tests.

Scope (non-consensus, P2P layer only):
    Step 11  PROTOCOL_VERSION bump 70017 -> 70018 (version.h)
    Step 12  NODE_RIN3 = (1 << 25) service bit, advertised unconditionally
             from the nLocalServices base declaration and rendered via
             serviceFlagToStr (protocol.{h,cpp}, init.cpp)
    Step 13  NODE_RIN3 added to GetDesirableServiceFlags (outbound preference)

    This test does NOT mine blocks and does NOT exercise RinHash, so it needs
    no blake3 / argon2-cffi venv (unlike feature_rin3_enforcement.py).

Assertions:
    [01] RPC   : getnetworkinfo localservices has the NODE_RIN3 bit set and
                 localservicesnames contains "RIN3"
    [02] Wire  : the node advertises protocol version 70018 in its version
                 message, and its advertised nServices includes NODE_RIN3
    [03] Guard : an inbound peer that does NOT advertise NODE_RIN3 is NOT
                 disconnected -- Step 13 adds NODE_RIN3 only to the desirable
                 (automatic-outbound) set, so legacy inbound peers must stay
                 connectable and keep following the canonical chain. This is
                 the permanent regression guard for the soft-fork topology.
"""

from test_framework.test_framework import BitcoinTestFramework
from test_framework.p2p import P2PInterface
from test_framework.messages import (
    NODE_MWEB,
    NODE_NETWORK,
    NODE_RIN3,
    NODE_WITNESS,
)
from test_framework.util import assert_equal

# version.h (Step 11): the RIN3-aware release line. Self-reported in the version
# handshake; MIN_PEER_PROTO_VERSION stays 31800, so no peer is gated by version.
EXPECTED_PROTOCOL_VERSION = 70018

# The pre-RIN3 service set. Matches the framework default (p2p.py peer_connect)
# but is pinned here so subtest [03] keeps modelling a legacy peer even if the
# framework default ever gains NODE_RIN3.
LEGACY_SERVICES = NODE_NETWORK | NODE_WITNESS | NODE_MWEB


class VersionProbe(P2PInterface):
    """Record the node's advertised protocol version and services.

    on_version() receives the *node's* version message. We stash nVersion and
    nServices, then defer to the base class to finish the handshake (verack and
    feature negotiation). The base class already stores self.nServices, but not
    the node's nVersion, which is why this override exists.
    """

    def __init__(self):
        super().__init__()
        self.node_protocol_version = None
        self.node_services = None

    def on_version(self, message):
        super().on_version(message)
        self.node_protocol_version = message.nVersion
        self.node_services = message.nServices


class Rin3ServicesTest(BitcoinTestFramework):

    def set_test_params(self):
        self.num_nodes = 1
        self.setup_clean_chain = True
        # No wallet, no mining, no MWEB tuning: a pure service-advertising and
        # connection-policy test. NODE_RIN3 advertising is unconditional, so the
        # default regtest node exposes it regardless of chain state.

    # ------------------------------------------------------------------
    # [01] RPC surface (Step 12: nLocalServices bit + serviceFlagToStr)
    # ------------------------------------------------------------------
    def subtest_01_rpc_advertises_rin3(self):
        self.log.info("-" * 55)
        self.log.info("[01] RPC: localservices bit and localservicesnames RIN3")
        self.log.info("-" * 55)
        node = self.nodes[0]
        info = node.getnetworkinfo()
        services = int(info["localservices"], 16)
        names = info["localservicesnames"]
        self.log.info(f"  localservices      = {info['localservices']}")
        self.log.info(f"  localservicesnames = {names}")
        self.log.info(f"  protocolversion    = {info['protocolversion']}")
        # The raw bit (init.cpp nLocalServices base declaration, Step 12.3) and
        # its RPC rendering (protocol.cpp serviceFlagToStr, Step 12.2) are
        # separate failure modes; assert both independently.
        assert services & NODE_RIN3, (
            f"node does not set NODE_RIN3 in localservices: "
            f"{info['localservices']}"
        )
        assert "RIN3" in names, (
            f"node does not advertise RIN3 in localservicesnames: {names}"
        )
        self.log.info("  [PASS] NODE_RIN3 bit set and rendered as RIN3")

    # ------------------------------------------------------------------
    # [02] Wire: version handshake (Step 11 version + Step 12 service bit)
    # ------------------------------------------------------------------
    def subtest_02_handshake_version_and_services(self):
        self.log.info("-" * 55)
        self.log.info("[02] Wire: node advertises version 70018 + NODE_RIN3 bit")
        self.log.info("-" * 55)
        node = self.nodes[0]

        # add_p2p_connection completes the version/verack handshake before it
        # returns, so on_version() has already recorded the node's values.
        probe = node.add_p2p_connection(VersionProbe())
        self.log.info(f"  node version   advertised = {probe.node_protocol_version}")
        self.log.info(f"  node nServices advertised = {probe.node_services:#x}")

        assert_equal(probe.node_protocol_version, EXPECTED_PROTOCOL_VERSION)
        # The wire value must agree with the RPC-reported protocol version.
        assert_equal(node.getnetworkinfo()["protocolversion"],
                     EXPECTED_PROTOCOL_VERSION)

        # The node's advertised services must include NODE_RIN3 (Step 12's
        # nLocalServices base-declaration advertising), confirmed on the wire.
        assert probe.node_services & NODE_RIN3, (
            f"node version message omits NODE_RIN3 "
            f"(nServices={probe.node_services:#x}, NODE_RIN3={NODE_RIN3:#x})"
        )

        probe.peer_disconnect()
        probe.wait_for_disconnect()
        self.wait_until(lambda: len(node.getpeerinfo()) == 0)
        self.log.info("  [PASS] version=70018 and NODE_RIN3 advertised on the wire")

    # ------------------------------------------------------------------
    # [03] Soft-fork topology guard (Step 13 must not touch inbound)
    # ------------------------------------------------------------------
    def subtest_03_legacy_inbound_not_disconnected(self):
        self.log.info("-" * 55)
        self.log.info("[03] Guard: inbound peer without NODE_RIN3 stays connected")
        self.log.info("-" * 55)
        node = self.nodes[0]

        # Explicitly advertise the pre-RIN3 service set (see LEGACY_SERVICES;
        # effective default lives in p2p.py peer_connect, not messages.py).
        # Step 13 adds NODE_RIN3 only to GetDesirableServiceFlags, which
        # governs AUTOMATIC OUTBOUND selection (ExpectServicesFromConn); it
        # must never drop an INBOUND peer.
        peer = node.add_p2p_connection(P2PInterface(), services=LEGACY_SERVICES)
        # A completed ping round-trip proves the connection is live post-handshake.
        peer.sync_with_ping()
        assert peer.is_connected, (
            "inbound peer without NODE_RIN3 was disconnected by the node"
        )

        self.wait_until(lambda: len(node.getpeerinfo()) == 1)
        info = node.getpeerinfo()[0]
        self.log.info(f"  peer inbound        = {info['inbound']}")
        self.log.info(f"  peer servicesnames  = {info['servicesnames']} (node's view)")
        assert info["inbound"] is True, "connection is not inbound as expected"
        assert "RIN3" not in info["servicesnames"], (
            f"test premise broken: inbound peer advertised RIN3: "
            f"{info['servicesnames']}"
        )

        # Persistence: still connected after a second round-trip.
        peer.sync_with_ping()
        assert peer.is_connected, "inbound peer was dropped while idle-connected"
        self.log.info("  [PASS] legacy inbound peer retained (soft-fork topology preserved)")

    # ------------------------------------------------------------------
    # Driver
    # ------------------------------------------------------------------
    def run_test(self):
        self.log.info("=" * 55)
        self.log.info("  RIN3 P2P capability signaling (RIP-0009, non-consensus)")
        self.log.info(f"  expected protocol version = {EXPECTED_PROTOCOL_VERSION}")
        self.log.info(f"  NODE_RIN3 = {NODE_RIN3:#x} (1 << 25)")
        self.log.info("=" * 55)

        self.subtest_01_rpc_advertises_rin3()
        self.subtest_02_handshake_version_and_services()
        self.subtest_03_legacy_inbound_not_disconnected()

        self.log.info("=" * 55)
        self.log.info("  ALL 3 SUBTESTS PASSED")
        self.log.info("  RIN3 advertised (RPC + wire); legacy inbound preserved")
        self.log.info("=" * 55)


if __name__ == "__main__":
    Rin3ServicesTest().main()
