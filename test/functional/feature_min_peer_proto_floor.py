#!/usr/bin/env python3
# Copyright (c) 2026 The Rincoin developers
# Distributed under the MIT software license, see the accompanying
# file COPYING or http://www.opensource.org/licenses/mit-license.php.
"""Test the RinHash overlay's `min_peer_protocol_version` floor.

The RinHash activations table exposes a height-indexed peer-protocol-version
floor via Consensus::Params::GetRinHashEffectiveAt(height). Before the active
chain reaches the overlay's activation_height, the floor is dormant and any
peer that satisfies MIN_PEER_PROTO_VERSION (31800) is accepted. From
activation_height onward, peers below the configured floor must be
disconnected during the version handshake.

On regtest the activation 0 overlay activates at height 600 with floor 70018.
"""

from test_framework.messages import msg_version, NODE_NETWORK, NODE_WITNESS, NODE_MWEB
from test_framework.p2p import P2PInterface
from test_framework.test_framework import BitcoinTestFramework
from test_framework.util import assert_equal


REGTEST_ACTIVATION0_HEIGHT = 600
REGTEST_FLOOR = 70018
LOW_VERSION = 70017  # one below the floor; was the previous PROTOCOL_VERSION
HIGH_VERSION = 70018  # at the floor


class FixedVersionPeer(P2PInterface):
    """P2P peer that advertises a specific nVersion in its version message."""

    def __init__(self, version):
        super().__init__()
        self._wanted_version = version

    def peer_connect_send_version(self, services):
        vt = msg_version()
        vt.nVersion = self._wanted_version
        vt.nServices = services
        vt.addrTo.ip = self.dstaddr
        vt.addrTo.port = self.dstport
        vt.addrFrom.ip = "0.0.0.0"
        vt.addrFrom.port = 0
        self.on_connection_send_msg = vt


class MinPeerProtoFloorTest(BitcoinTestFramework):
    def set_test_params(self):
        self.num_nodes = 1
        self.setup_clean_chain = True

    def run_test(self):
        node = self.nodes[0]

        self.log.info("Sanity-check the overlay schedule via getrinhashparams")
        params = node.getrinhashparams()
        # Effective floor is dormant at genesis on regtest.
        assert_equal(params["effective"]["min_peer_protocol_version"], 0)
        # Activation 0 is the scheduled change.
        assert len(params["activations"]) >= 1, params
        assert_equal(params["activations"][0]["activation_height"], REGTEST_ACTIVATION0_HEIGHT)
        assert_equal(params["activations"][0]["min_peer_protocol_version"], REGTEST_FLOOR)

        self.log.info("Below activation: a low-version peer is accepted")
        # Chain is at genesis (height 0) -> floor dormant.
        peer_pre = node.add_p2p_connection(FixedVersionPeer(LOW_VERSION))
        # If we got here without timing out, the node accepted the version
        # handshake. Confirm via getpeerinfo.
        peers = node.getpeerinfo()
        assert_equal(len(peers), 1)
        assert_equal(peers[0]["version"], LOW_VERSION)
        node.disconnect_p2ps()

        self.log.info("Mine to one block before activation_height; floor still dormant")
        addr = node.getnewaddress()
        node.generatetoaddress(REGTEST_ACTIVATION0_HEIGHT - 1, addr)
        assert_equal(node.getblockcount(), REGTEST_ACTIVATION0_HEIGHT - 1)
        params = node.getrinhashparams()
        assert_equal(params["effective"]["min_peer_protocol_version"], 0)

        peer_pre2 = node.add_p2p_connection(FixedVersionPeer(LOW_VERSION))
        assert_equal(node.getpeerinfo()[0]["version"], LOW_VERSION)
        node.disconnect_p2ps()

        self.log.info("Mine the activation block; floor now %d", REGTEST_FLOOR)
        node.generatetoaddress(1, addr)
        assert_equal(node.getblockcount(), REGTEST_ACTIVATION0_HEIGHT)
        params = node.getrinhashparams()
        assert_equal(params["effective"]["min_peer_protocol_version"], REGTEST_FLOOR)

        self.log.info("At/above activation: low-version peer is disconnected")
        # We expect the node to drop the connection during the handshake;
        # add_p2p_connection waits for verack with wait_for_verack=True by
        # default, which would deadlock, so disable it and watch the socket.
        peer_low = node.add_p2p_connection(FixedVersionPeer(LOW_VERSION),
                                           wait_for_verack=False)
        peer_low.wait_for_disconnect()

        self.log.info("At/above activation: high-version peer is accepted")
        peer_hi = node.add_p2p_connection(FixedVersionPeer(HIGH_VERSION))
        peers = node.getpeerinfo()
        # Only the accepted peer should be present.
        assert_equal(len(peers), 1)
        assert_equal(peers[0]["version"], HIGH_VERSION)


if __name__ == '__main__':
    MinPeerProtoFloorTest().main()
