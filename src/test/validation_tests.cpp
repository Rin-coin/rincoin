// Copyright (c) 2014-2019 The Bitcoin Core developers
// Distributed under the MIT software license, see the accompanying
// file COPYING or http://www.opensource.org/licenses/mit-license.php.

#include <chainparams.h>
#include <net.h>
#include <signet.h>
#include <validation.h>

#include <test/util/setup_common.h>

#include <boost/test/unit_test.hpp>

BOOST_FIXTURE_TEST_SUITE(validation_tests, TestingSetup)

// Test Customized Halving Schedule (Scenario II)
// Phase 0 (0 ~ 209,999):       50    RIN
// Phase 1 (210,000 ~ 419,999): 25    RIN
// Phase 2 (420,000 ~ 629,999): 12.5  RIN
// Phase 3 (630,000 ~ 839,999):  6.25 RIN
// Phase 4 (840,000 ~ 2,099,999): 4   RIN
// Phase 5 (2,100,000 ~ 4,199,999): 2 RIN
// Phase 6 (4,200,000 ~ 6,299,999): 1 RIN
// Terminal (6,300,000~):         0.6  RIN

BOOST_AUTO_TEST_CASE(block_subsidy_test)
{
    const auto chainParams = CreateChainParams(*m_node.args, CBaseChainParams::MAIN);
    const Consensus::Params& consensusParams = chainParams->GetConsensus();

    // --- Phase 0: 50 RIN ---
    BOOST_CHECK_EQUAL(GetBlockSubsidy(0,      consensusParams), 50 * COIN);
    BOOST_CHECK_EQUAL(GetBlockSubsidy(100000, consensusParams), 50 * COIN);
    BOOST_CHECK_EQUAL(GetBlockSubsidy(209999, consensusParams), 50 * COIN); // last block of Phase 0

    // --- Phase 1: 25 RIN (boundary: 210,000) ---
    BOOST_CHECK_EQUAL(GetBlockSubsidy(210000, consensusParams), 25 * COIN); // first block of Phase 1
    BOOST_CHECK_EQUAL(GetBlockSubsidy(315000, consensusParams), 25 * COIN);
    BOOST_CHECK_EQUAL(GetBlockSubsidy(419999, consensusParams), 25 * COIN); // last block of Phase 1

    // --- Phase 2: 12.5 RIN (boundary: 420,000) ---
    BOOST_CHECK_EQUAL(GetBlockSubsidy(420000, consensusParams), CAmount(1250000000)); // first block of Phase 2
    BOOST_CHECK_EQUAL(GetBlockSubsidy(525000, consensusParams), CAmount(1250000000));
    BOOST_CHECK_EQUAL(GetBlockSubsidy(629999, consensusParams), CAmount(1250000000)); // last block of Phase 2

    // --- Phase 3: 6.25 RIN (boundary: 630,000) ---
    BOOST_CHECK_EQUAL(GetBlockSubsidy(630000, consensusParams), CAmount(625000000)); // first block of Phase 3
    BOOST_CHECK_EQUAL(GetBlockSubsidy(735000, consensusParams), CAmount(625000000));
    BOOST_CHECK_EQUAL(GetBlockSubsidy(839999, consensusParams), CAmount(625000000)); // last block of Phase 3

    // --- Phase 4: 4 RIN (boundary: 840,000) ---
    BOOST_CHECK_EQUAL(GetBlockSubsidy(840000,  consensusParams), 4 * COIN); // first block of Phase 4
    BOOST_CHECK_EQUAL(GetBlockSubsidy(1470000, consensusParams), 4 * COIN);
    BOOST_CHECK_EQUAL(GetBlockSubsidy(2099999, consensusParams), 4 * COIN); // last block of Phase 4

    // --- Phase 5: 2 RIN (boundary: 2,100,000) ---
    BOOST_CHECK_EQUAL(GetBlockSubsidy(2100000, consensusParams), 2 * COIN); // first block of Phase 5
    BOOST_CHECK_EQUAL(GetBlockSubsidy(3150000, consensusParams), 2 * COIN);
    BOOST_CHECK_EQUAL(GetBlockSubsidy(4199999, consensusParams), 2 * COIN); // last block of Phase 5

    // --- Phase 6: 1 RIN (boundary: 4,200,000) ---
    BOOST_CHECK_EQUAL(GetBlockSubsidy(4200000, consensusParams), 1 * COIN); // first block of Phase 6
    BOOST_CHECK_EQUAL(GetBlockSubsidy(5250000, consensusParams), 1 * COIN);
    BOOST_CHECK_EQUAL(GetBlockSubsidy(6299999, consensusParams), 1 * COIN); // last block of Phase 6

    // --- Terminal: 0.6 RIN (boundary: 6,300,000) ---
    BOOST_CHECK_EQUAL(GetBlockSubsidy(6300000,   consensusParams), CAmount(60000000)); // first terminal block
    BOOST_CHECK_EQUAL(GetBlockSubsidy(10000000,  consensusParams), CAmount(60000000));
    BOOST_CHECK_EQUAL(GetBlockSubsidy(100000000, consensusParams), CAmount(60000000));
}

BOOST_AUTO_TEST_CASE(subsidy_limit_test)
{
    const auto chainParams = CreateChainParams(*m_node.args, CBaseChainParams::MAIN);
    CAmount nSum = 0;
    for (int nHeight = 0; nHeight < 56000000; nHeight += 1000) {
        CAmount nSubsidy = GetBlockSubsidy(nHeight, chainParams->GetConsensus());
        BOOST_CHECK(nSubsidy <= 50 * COIN);
        nSum += nSubsidy * 1000;
        BOOST_CHECK(MoneyRange(nSum));
    }
    // Expected total for heights 0~55,999,000 (step 1000) under Scenario II:
    //   Phase 0 (210 steps x 50 RIN x 1000):      1,050,000,000,000,000
    //   Phase 1 (210 steps x 25 RIN x 1000):        525,000,000,000,000
    //   Phase 2 (210 steps x 12.5 RIN x 1000):      262,500,000,000,000
    //   Phase 3 (210 steps x 6.25 RIN x 1000):      131,250,000,000,000
    //   Phase 4 (1260 steps x 4 RIN x 1000):        504,000,000,000,000
    //   Phase 5 (2100 steps x 2 RIN x 1000):        420,000,000,000,000
    //   Phase 6 (2100 steps x 1 RIN x 1000):        210,000,000,000,000
    //   Terminal (49700 steps x 0.6 RIN x 1000):  2,982,000,000,000,000
    //   Total:                                     6,084,750,000,000,000
    BOOST_CHECK_EQUAL(nSum, CAmount{6084750000000000});
}

// Supply accounting (RIP-0002, Stage A). GetTotalSubsidy() is the closed
// form of the running sum of GetBlockSubsidy(), clamped at the cap derived
// from nSubsidyHalvingInterval. Accounting only: emission is unchanged.

BOOST_AUTO_TEST_CASE(total_subsidy_sweep_test)
{
    // Regtest scales the schedule by 1/1000 (interval 210), so the whole
    // emission curve including the cap fits in one sweep. At mainnet scale
    // the same sweep would need 234,587,500 iterations.
    const auto chainParams = CreateChainParams(*m_node.args, CBaseChainParams::REGTEST);
    const Consensus::Params& consensusParams = chainParams->GetConsensus();
    const CAmount cap = GetSupplyCap(consensusParams);
    BOOST_CHECK_EQUAL(cap, 168000 * COIN);

    // One assertion for the whole sweep: report the first mismatching
    // height rather than recording 240,001 individual checks.
    int nFirstMismatch = -1;
    CAmount nRunning = 0;
    for (int nHeight = 0; nHeight <= 240000; ++nHeight) {
        const CAmount nExpected = (nRunning < cap) ? nRunning : cap;
        if (GetTotalSubsidy(nHeight, consensusParams) != nExpected) {
            nFirstMismatch = nHeight;
            break;
        }
        nRunning += GetBlockSubsidy(nHeight, consensusParams);
    }
    BOOST_CHECK_EQUAL(nFirstMismatch, -1);

    // 12 does not divide 210, so the integral reaches the cap mid-block:
    // the residual before height 234,587 is 0.3 RIN, i.e. a partial final
    // block once the cap is enforced. Scaled networks only; mainnet
    // (210,000 = 12 x 17,500) lands exactly on a block boundary.
    BOOST_CHECK_EQUAL(GetTotalSubsidy(234587, consensusParams), cap - CAmount(30000000));
    BOOST_CHECK_EQUAL(GetTotalSubsidy(234588, consensusParams), cap);
}

BOOST_AUTO_TEST_CASE(supply_cap_boundary_test)
{
    const auto chainParams = CreateChainParams(*m_node.args, CBaseChainParams::MAIN);
    const Consensus::Params& consensusParams = chainParams->GetConsensus();
    const CAmount cap = GetSupplyCap(consensusParams);
    BOOST_CHECK_EQUAL(cap, MAX_MONEY);

    BOOST_CHECK_EQUAL(GetTotalSubsidy(0, consensusParams), 0);
    BOOST_CHECK_EQUAL(GetTotalSubsidy(1, consensusParams), 50 * COIN);

    // Whitepaper v1.6.4 Sec.3 Scenario II: S_fix at the terminal phase start.
    BOOST_CHECK_EQUAL(GetTotalSubsidy(6300000, consensusParams), CAmount(31027500) * COIN);

    // Cap height = 13405 * interval / 12. int64 is mandatory here:
    // 13405 * 210000 = 2,815,050,000 overflows int32.
    // 234,587,500 / 525,600 = 446.3232 years = t_trans, "mining ends".
    const int64_t nCapHeight = (int64_t)13405 * consensusParams.nSubsidyHalvingInterval / 12;
    BOOST_CHECK_EQUAL(nCapHeight, 234587500);

    BOOST_CHECK_EQUAL(GetTotalSubsidy((int)nCapHeight - 1, consensusParams), cap - CAmount(60000000));
    BOOST_CHECK_EQUAL(GetTotalSubsidy((int)nCapHeight,     consensusParams), cap);
    BOOST_CHECK_EQUAL(GetTotalSubsidy((int)nCapHeight + 1000000, consensusParams), cap);
}

BOOST_AUTO_TEST_SUITE_END()
