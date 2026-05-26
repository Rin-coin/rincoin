// Copyright (c) 2026 The Rincoin developers
// Distributed under the MIT software license, see the accompanying
// file COPYING or http://www.opensource.org/licenses/mit-license.php.

#include <boost/test/unit_test.hpp>

#include <chainparams.h>
#include <consensus/params.h>
#include <crypto/rinhash.h>
#include <primitives/block.h>
#include <primitives/transaction.h>
#include <test/util/setup_common.h>
#include <uint256.h>
#include <util/strencodings.h>

#include <stdexcept>
#include <string>
#include <vector>

BOOST_FIXTURE_TEST_SUITE(rinhash_tests, BasicTestingSetup)

namespace {

// Pre-activations (init) header used to pin the canonical RinHash output. The
// activation-0 PoW parameters are unchanged from the historical hardcoded
// values, so this vector remains valid after the introduction of the
// activations table.
CBlockHeader MakeFixedHeader()
{
    CBlockHeader h;
    h.nVersion = 0x20000000;
    h.hashPrevBlock.SetNull();
    h.hashMerkleRoot = uint256S("0102030405060708090a0b0c0d0e0f10111213141516171819202122232425fe");
    h.nTime  = 1750000000;
    h.nBits  = 0x1e0fffff;
    h.nNonce = 0xdeadbeef;
    return h;
}

const Consensus::Params& MainConsensus()
{
    SelectParams(CBaseChainParams::MAIN);
    return Params().GetConsensus();
}

} // namespace

BOOST_AUTO_TEST_CASE(rinhash_canonical_pow_vector)
{
    const uint256 expected = uint256S(
        "02b229adf0a67d35cfd176d5ee46b750ca698b97e1edc479787090856ca33222");
    BOOST_CHECK_EQUAL(RinHash(MakeFixedHeader()).GetHex(), expected.GetHex());
}

BOOST_AUTO_TEST_CASE(rinhash_init_overlay_height_zero_dormant_rules)
{
    const auto& consensus = MainConsensus();
    const auto eff = consensus.GetRinHashEffectiveAt(0);

    // Init PoW parameters are present from genesis.
    BOOST_CHECK_EQUAL(eff.pow.t_cost, 2u);
    BOOST_CHECK_EQUAL(eff.pow.m_cost, 64u);
    BOOST_CHECK_EQUAL(eff.pow.lanes,  1u);
    BOOST_CHECK_EQUAL(eff.pow.salt,   std::string("RinCoinSalt"));

    // Activation-0 rules are dormant before activation_height.
    BOOST_CHECK_EQUAL(eff.min_peer_protocol_version, 0);
}

BOOST_AUTO_TEST_CASE(rinhash_mainnet_activation0_height_840000)
{
    const auto& consensus = MainConsensus();
    BOOST_REQUIRE_GE(consensus.rinhash.activations.size(), 1u);
    BOOST_CHECK_EQUAL(consensus.rinhash.activations[0].activation_height, 840000);

    // One block before activation: rule still dormant.
    {
        const auto eff = consensus.GetRinHashEffectiveAt(839999);
        BOOST_CHECK_EQUAL(eff.min_peer_protocol_version, 0);
    }

    // At activation: peer protocol version floor present.
    {
        const auto eff = consensus.GetRinHashEffectiveAt(840000);
        BOOST_CHECK_EQUAL(eff.min_peer_protocol_version, 70018);
    }
}

BOOST_AUTO_TEST_CASE(rinhash_height_aware_overload_matches_default)
{
    // PoW parameters do not change across the current set of activations, so
    // the height-aware overload must produce the same hash at any height.
    const auto& consensus = MainConsensus();
    const CBlockHeader h = MakeFixedHeader();

    const uint256 base = RinHash(h);
    BOOST_CHECK_EQUAL(h.GetPoWHashAt(0,        consensus).GetHex(), base.GetHex());
    BOOST_CHECK_EQUAL(h.GetPoWHashAt(839999,   consensus).GetHex(), base.GetHex());
    BOOST_CHECK_EQUAL(h.GetPoWHashAt(840000,   consensus).GetHex(), base.GetHex());
}

BOOST_AUTO_TEST_CASE(rinhash_pending_salt_is_rejected)
{
    Consensus::Params::Argon2dParams pending{2u, 64u, 1u, std::string("PENDING")};
    BOOST_CHECK_THROW(RinHash(MakeFixedHeader(), pending), std::runtime_error);
}

BOOST_AUTO_TEST_CASE(rinhash_testnet_and_regtest_activation0_heights)
{
    SelectParams(CBaseChainParams::TESTNET);
    {
        const auto& c = Params().GetConsensus();
        BOOST_REQUIRE_GE(c.rinhash.activations.size(), 1u);
        BOOST_CHECK_EQUAL(c.rinhash.activations[0].activation_height, 4200);
    }
    SelectParams(CBaseChainParams::REGTEST);
    {
        const auto& c = Params().GetConsensus();
        BOOST_REQUIRE_GE(c.rinhash.activations.size(), 1u);
        BOOST_CHECK_EQUAL(c.rinhash.activations[0].activation_height, 600);
    }
}

BOOST_AUTO_TEST_CASE(rinhash_preview_activation0_height_and_floor)
{
    SelectParams(CBaseChainParams::PREVIEW);
    const auto& c = Params().GetConsensus();
    BOOST_REQUIRE_GE(c.rinhash.activations.size(), 1u);
    // Preview mirrors regtest's activation schedule by design.
    BOOST_CHECK_EQUAL(c.rinhash.activations[0].activation_height, 600);
    BOOST_CHECK_EQUAL(c.GetRinHashEffectiveAt(599).min_peer_protocol_version, 0);
    BOOST_CHECK_EQUAL(c.GetRinHashEffectiveAt(600).min_peer_protocol_version, 70018);
}

BOOST_AUTO_TEST_SUITE_END()
