#!/usr/bin/env python3
# Copyright (c) 2026 The Rincoin Core developers
# Distributed under the MIT software license, see the accompanying
# file COPYING or http://www.opensource.org/licenses/mit-license.php.

"""
feature_taproot_wallet_guard.py

RIP-0011 wallet guard -- refuse to create outputs paying to witness v1
(Taproot) or any later witness version while that deployment is sealed.

Why the guard exists:
    Taproot is NEVER_ACTIVE on mainnet (CMainParams), so an
    OP_1 <32-byte> output is anyone-can-spend at the consensus level there.
    The hazard is reachable from sendtoaddress, not only from the raw
    transaction APIs: DecodeDestination accepts genuine bech32m v1
    addresses -- it enforces the BIP350 rule that a non-zero witness
    version must be bech32m and a zero version must not be -- and maps
    them to WitnessUnknown, which GetScriptForDestination renders as
    OP_1 <program>.

Why this test can exercise both branches:
    regtest ships Taproot as ALWAYS_ACTIVE (CRegTestParams), so the
    guard is off by default here. It is switched on with
        -vbparams=taproot:-2:9223372036854775807
    where -2 == Consensus::BIP9Deployment::NEVER_ACTIVE. The -vbparams
    parser in CRegTestParams::UpdateActivationParametersFromArgs applies
    ParseInt64 with no range check, which is what makes the negative
    sentinel injectable. The 3-argument form zero-initialises the height
    fields; the guard reads nStartTime only, so that is immaterial here.

    The guard reads the deployment parameter directly rather than querying
    activation state, because VersionBitsState requires cs_main while
    cs_wallet is already held in CreateTransaction (the same lock-order
    constraint that shaped the RIN3 nVersion emission in txassembler).

Subtests:
    [01] guard off : a witness v1 recipient is accepted -- proves the guard
                     does not over-block when the deployment is live.
    [02] guard on  : the same recipient is refused, and the message names
                     the witness version.
    [03] guard on  : an MWEB recipient does not reach the guard's
                     GetScript() call. DestinationAddr::GetScript() asserts
                     on !IsMWEB(), so a guard that drops its IsMWEB()
                     early-continue would abort the node rather than fail
                     an RPC. This subtest is the permanent regression
                     guard for that failure mode. An abort would
                     surface first as a transport-level failure of the send
                     itself, since the node dies mid-request; the
                     getblockcount that follows confirms the node is still
                     serving.
"""

from test_framework.test_framework import BitcoinTestFramework
from test_framework.authproxy import JSONRPCException
from test_framework.segwit_addr import encode_segwit_address
from test_framework.util import assert_equal, assert_raises_rpc_error

# Consensus::BIP9Deployment sentinels, from src/consensus/params.h.
NEVER_ACTIVE = -2
NO_TIMEOUT = 9223372036854775807

# Deterministic 32-byte witness program. WITNESS_V1_TAPROOT_SIZE is 32, so
# Solver() classifies this as WITNESS_V1_TAPROOT.
# The value is never spent, so it need not be a valid x-only pubkey.
TAPROOT_PROGRAM = bytes(range(32))

# Substring of the guard's error message. Kept narrow on purpose: matching the
# whole sentence would make the test brittle against wording changes, while
# matching "witness" alone could match an unrelated wallet error.
GUARD_ERROR_FRAGMENT = "witness version"

# CWallet::CreateTransaction failures surface through SendMoney(), which maps
# every failure to RPC_WALLET_INSUFFICIENT_FUNDS regardless of cause:
#
#   const bool fCreated = pwallet->CreateTransaction(..., error, ...);
#   if (!fCreated) {
#       throw JSONRPCError(RPC_WALLET_INSUFFICIENT_FUNDS, error.original);
#   }                              -- SendMoney(), src/wallet/rpcwallet.cpp
#
# The code is therefore -6, not RPC_WALLET_ERROR. Every other throw in that
# file uses RPC_WALLET_ERROR, so -6 is specific to this path. error is a
# bilingual_str and .original is the untranslated text, so the English
# fragment above matches whatever locale the node runs under.
GUARD_ERROR_CODE = -6

SEAL_TAPROOT_ARG = f"-vbparams=taproot:{NEVER_ACTIVE}:{NO_TIMEOUT}"


class TaprootWalletGuardTest(BitcoinTestFramework):

    def set_test_params(self):
        self.num_nodes = 1
        self.setup_clean_chain = True
        # Start with regtest defaults so subtest [01] sees the guard off.
        # -fallbackfee lets sendtoaddress work without fee estimation data.
        self.extra_args = [["-fallbackfee=0.001"]]

    def skip_test_if_missing_module(self):
        self.skip_if_no_wallet()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def taproot_address(self):
        """Build a bech32m witness-v1 address for this node's HRP.

        The HRP is read back from a wallet address instead of being hardcoded,
        so the test follows chainparams rather than duplicating it. The bech32
        data charset excludes '1', so the last '1' is the separator (BIP173).
        """
        reference = self.nodes[0].getnewaddress("", "bech32")
        hrp = reference.rsplit("1", 1)[0]
        return encode_segwit_address(hrp, 1, TAPROOT_PROGRAM)

    def fund_wallet(self):
        node = self.nodes[0]
        addr = node.getnewaddress()
        # 101 blocks: one mature coinbase to spend. Well below the regtest
        # CH/RIN3 activation height (840 at 1/1000 scale), so no RIN3
        # nVersion interaction is in play.
        node.generatetoaddress(101, addr)
        assert_equal(node.getblockcount(), 101)
        self.log.info(f"  wallet balance = {node.getbalance()}")

    # ------------------------------------------------------------------
    # [01] Guard off -- must not over-block
    # ------------------------------------------------------------------
    def subtest_01_guard_off_accepts_witness_v1(self):
        self.log.info("-" * 60)
        self.log.info("[01] Taproot ALWAYS_ACTIVE (regtest default): v1 accepted")
        self.log.info("-" * 60)
        node = self.nodes[0]

        taproot_addr = self.taproot_address()
        self.log.info(f"  witness v1 address = {taproot_addr}")

        # Sanity: the node must recognise the address at all, otherwise [02]
        # would "pass" for the wrong reason (rejected at decode, not by the
        # guard).
        info = node.validateaddress(taproot_addr)
        self.log.info(f"  validateaddress isvalid = {info['isvalid']}")
        assert info["isvalid"], (
            f"node rejected the bech32m v1 address at decode: {info}"
        )

        txid = node.sendtoaddress(taproot_addr, 1)
        self.log.info(f"  sendtoaddress txid = {txid}")

        # Confirm the created output really is witness v1, so [02] is testing
        # the same script type this subtest just allowed.
        raw = node.getrawtransaction(txid, True)
        types = [o["scriptPubKey"]["type"] for o in raw["vout"]]
        self.log.info(f"  output types = {types}")
        assert "witness_v1_taproot" in types, (
            f"expected a witness_v1_taproot output, got {types}"
        )
        self.log.info("  [PASS] guard is off while the deployment is live")

    # ------------------------------------------------------------------
    # [02] Guard on -- must refuse
    # ------------------------------------------------------------------
    def subtest_02_guard_on_refuses_witness_v1(self):
        self.log.info("-" * 60)
        self.log.info("[02] Taproot NEVER_ACTIVE: v1 refused by the guard")
        self.log.info("-" * 60)
        node = self.nodes[0]

        taproot_addr = self.taproot_address()
        self.log.info(f"  witness v1 address = {taproot_addr}")
        # Still decodable: the seal changes consensus deployment state, not
        # address parsing. This keeps the refusal attributable to the guard.
        assert node.validateaddress(taproot_addr)["isvalid"], (
            "the sealed node no longer decodes the bech32m v1 address, so a "
            "refusal below would not be attributable to the guard"
        )

        assert_raises_rpc_error(GUARD_ERROR_CODE, GUARD_ERROR_FRAGMENT,
                                node.sendtoaddress, taproot_addr, 1)
        self.log.info("  [PASS] refused, and the message names the witness version")

    # ------------------------------------------------------------------
    # [03] Guard on + MWEB recipient -- must not abort the node
    # ------------------------------------------------------------------
    def subtest_03_guard_on_mweb_recipient_survives(self):
        self.log.info("-" * 60)
        self.log.info("[03] Taproot NEVER_ACTIVE: MWEB recipient must not abort")
        self.log.info("-" * 60)
        node = self.nodes[0]
        height_before = node.getblockcount()

        try:
            mweb_addr = node.getnewaddress("", "mweb")
        except JSONRPCException as e:
            # Not a skippable condition. MWEB has an address type on every
            # network in this tree, so failing to produce one means this
            # subtest -- the only runtime check that the guard does not
            # abort the node -- did not run at all. Returning quietly here
            # would leave run_test() printing ALL SUBTESTS PASSED for a
            # guard that was never exercised.
            raise AssertionError(
                "could not create an MWEB address, so [03] never ran: "
                f"{e.error['message']}"
            ) from e

        self.log.info(f"  MWEB address = {mweb_addr}")
        # The send has to reach CreateTransaction for this subtest to mean
        # anything, because the IsMWEB() continue lives there. sendtoaddress
        # returns a txid for an MWEB recipient even before MWEB activates:
        # the transaction is built and recorded, it just does not enter the
        # mempool. So a failure here is not an acceptable variation, it means
        # the guard was never reached and this subtest proved nothing. The
        # send therefore has to succeed, and this test now enforces that.
        try:
            txid = node.sendtoaddress(mweb_addr, 1)
        except JSONRPCException as e:
            message = e.error["message"]
            if GUARD_ERROR_FRAGMENT in message:
                raise AssertionError(
                    f"guard rejected an MWEB recipient: {message}"
                ) from e
            raise AssertionError(
                "the MWEB send failed before reaching the guard, so [03] "
                f"exercised nothing: {message}"
            ) from e
        self.log.info(f"  sendtoaddress txid = {txid}")

        # Confirmation. If the guard had called GetScript() on a
        # StealthAddress, the assert in DestinationAddr::GetScript()
        # would have aborted the node -- which would already have broken
        # the send above at the transport layer, since the node dies
        # mid-request and never returns a JSON error. This call proves
        # the node is still serving afterwards.
        assert_equal(node.getblockcount(), height_before)
        self.log.info("  [PASS] node still answering RPCs; no assert reached")

    # ------------------------------------------------------------------
    # Driver
    # ------------------------------------------------------------------
    def run_test(self):
        self.log.info("=" * 60)
        self.log.info("  RIP-0011 Taproot wallet guard")
        self.log.info(f"  seal argument = {SEAL_TAPROOT_ARG}")
        self.log.info("=" * 60)

        self.fund_wallet()
        self.subtest_01_guard_off_accepts_witness_v1()

        self.log.info(f"  restarting node with {SEAL_TAPROOT_ARG}")
        # Sealing a deployment only loosens consensus rules, so the chain built
        # under ALWAYS_ACTIVE stays valid across the restart; no reorg occurs.
        self.restart_node(0, extra_args=["-fallbackfee=0.001", SEAL_TAPROOT_ARG])

        self.subtest_02_guard_on_refuses_witness_v1()
        self.subtest_03_guard_on_mweb_recipient_survives()

        self.log.info("=" * 60)
        self.log.info("  ALL SUBTESTS PASSED")
        self.log.info("  guard off: v1 accepted / on: v1 refused, MWEB safe")
        self.log.info("=" * 60)


if __name__ == "__main__":
    TaprootWalletGuardTest().main()
