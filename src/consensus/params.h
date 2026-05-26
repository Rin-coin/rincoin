// Copyright (c) 2009-2010 Satoshi Nakamoto
// Copyright (c) 2009-2019 The Bitcoin Core developers
// Distributed under the MIT software license, see the accompanying
// file COPYING or http://www.opensource.org/licenses/mit-license.php.

#ifndef BITCOIN_CONSENSUS_PARAMS_H
#define BITCOIN_CONSENSUS_PARAMS_H

#include <uint256.h>
#include <cstdint>
#include <limits>
#include <string>
#include <vector>

namespace Consensus {

enum DeploymentPos
{
    DEPLOYMENT_TESTDUMMY,
    DEPLOYMENT_TAPROOT, // Deployment of Schnorr/Taproot (BIPs 340-342)
    DEPLOYMENT_MWEB, // Deployment of MWEB (LIPs 0002-0004)
    // NOTE: Also add new deployments to VersionBitsDeploymentInfo in versionbits.cpp
    MAX_VERSION_BITS_DEPLOYMENTS
};

/**
 * Struct for each individual consensus rule change using BIP9.
 */
struct BIP9Deployment {
    /** Bit position to select the particular bit in nVersion. */
    int bit;
    /** Start MedianTime for version bits miner confirmation. Can be a date in the past */
    int64_t nStartTime = 0;
    /** Timeout/expiry MedianTime for the deployment attempt. */
    int64_t nTimeout = 0;
    /** Start block height for version bits miner confirmation. Should be a retarget block, can be in the past */
    int64_t nStartHeight = 0;
    /** Timeout/expiry block height for the deployment attempt. Should be a retarget block. */
    int64_t nTimeoutHeight = 0;

    /** Constant for nTimeout very far in the future. */
    static constexpr int64_t NO_TIMEOUT = std::numeric_limits<int64_t>::max();

    /** Special value for nStartTime indicating that the deployment is always active.
     *  This is useful for testing, as it means tests don't need to deal with the activation
     *  process (which takes at least 3 BIP9 intervals). Only tests that specifically test the
     *  behaviour during activation cannot use this. */
    static constexpr int64_t ALWAYS_ACTIVE = -1;

    /** Special value for nStartTime indicating that the deployment is never active.
     *  This is useful for integrating the code changes for a new feature
     *  prior to deploying it on some or all networks. */
    static constexpr int64_t NEVER_ACTIVE = -2;
};

/**
 * Parameters that influence chain consensus.
 */
struct Params {
    uint256 hashGenesisBlock;
    int nSubsidyHalvingInterval;
    /** Block height at which BIP16 becomes active */
    int BIP16Height;
    /** Block height and hash at which BIP34 becomes active */
    int BIP34Height;
    uint256 BIP34Hash;
    /** Block height at which BIP65 becomes active */
    int BIP65Height;
    /** Block height at which BIP66 becomes active */
    int BIP66Height;
    /** Block height at which CSV (BIP68, BIP112 and BIP113) becomes active */
    int CSVHeight;
    /** Block height at which Segwit (BIP141, BIP143 and BIP147) becomes active.
     * Note that segwit v0 script rules are enforced on all blocks except the
     * BIP 16 exception blocks. */
    int SegwitHeight;
    /** Don't warn about unknown BIP 9 activations below this height.
     * This prevents us from warning about the CSV and segwit activations. */
    int MinBIP9WarningHeight;
    /**
     * Minimum blocks including miner confirmation of the total of 2016 blocks in a retargeting period,
     * (nPowTargetTimespan / nPowTargetSpacing) which is also used for BIP9 deployments.
     * Examples: 1916 for 95%, 1512 for testchains.
     */
    uint32_t nRuleChangeActivationThreshold;
    uint32_t nMinerConfirmationWindow;
    BIP9Deployment vDeployments[MAX_VERSION_BITS_DEPLOYMENTS];
    /** Proof of work parameters */
    uint256 powLimit;
    bool fPowAllowMinDifficultyBlocks;
    bool fPowNoRetargeting;
    int64_t nPowTargetSpacing;
    int64_t nPowTargetTimespan;
    int64_t DifficultyAdjustmentInterval() const { return nPowTargetTimespan / nPowTargetSpacing; }
    /** The best chain should have at least this much work */
    uint256 nMinimumChainWork;
    /** By default assume that the signatures in ancestors of this block are valid */
    uint256 defaultAssumeValid;

    /**
     * If true, witness commitments contain a payload equal to a Bitcoin Script solution
     * to the signet challenge. See BIP325.
     */
    bool signet_blocks{false};
    std::vector<uint8_t> signet_challenge;
    int DGWHeight;

    /**
     * RinHash consensus parameters.
     *
     * The chain has always used RinHash for proof of work. Consensus is
     * organised as an `init` (the values applicable from genesis) plus a
     * height-ordered list of `activations` (overlays). At any height H, the
     * effective parameters are obtained by starting from `init` and applying
     * every activation whose activation_height <= H, last-write-wins per
     * field.
     *
     * A rule is enforced iff its corresponding field is present (non-empty
     * for byte vectors, non-zero for integers) in the effective parameters.
     * In particular, mainnet's init has no coinbase marker, no fork tx
     * version, and no extra peer protocol floor; those rules become active
     * only when an activation introduces them.
     */
    struct Argon2dParams {
        uint32_t    t_cost;
        uint32_t    m_cost;
        uint32_t    lanes;
        std::string salt;
    };

    struct RinHashOverlay {
        bool        has_t_cost{false};                     uint32_t                  t_cost{0};
        bool        has_m_cost{false};                     uint32_t                  m_cost{0};
        bool        has_lanes{false};                      uint32_t                  lanes{0};
        bool        has_salt{false};                       std::string               salt;
        bool        has_min_peer_protocol_version{false};  int                       min_peer_protocol_version{0};
    };

    struct RinHashActivation {
        int            activation_height;
        RinHashOverlay overlay;
    };

    /** Fully resolved RinHash consensus parameters at a particular height. */
    struct RinHashEffective {
        Argon2dParams              pow;
        int                        min_peer_protocol_version{0}; //!< 0 => no extra floor
    };

    struct RinHashConsensusData {
        RinHashOverlay                 init;        //!< activation_height implicitly 0
        std::vector<RinHashActivation> activations; //!< strictly height-ascending
    };

    /** Per-network RinHash consensus table. */
    RinHashConsensusData rinhash;

    /** Resolve the effective RinHash parameters at the given block height. */
    RinHashEffective GetRinHashEffectiveAt(int height) const;
};

inline Params::RinHashEffective Params::GetRinHashEffectiveAt(int height) const
{
    auto apply = [](RinHashEffective& e, const RinHashOverlay& o) {
        if (o.has_t_cost)                    e.pow.t_cost = o.t_cost;
        if (o.has_m_cost)                    e.pow.m_cost = o.m_cost;
        if (o.has_lanes)                     e.pow.lanes  = o.lanes;
        if (o.has_salt)                      e.pow.salt   = o.salt;
        if (o.has_min_peer_protocol_version) e.min_peer_protocol_version  = o.min_peer_protocol_version;
    };
    RinHashEffective effective{};
    apply(effective, rinhash.init);
    for (const auto& activation : rinhash.activations) {
        if (activation.activation_height > height) break;
        apply(effective, activation.overlay);
    }
    return effective;
}

} // namespace Consensus

#endif // BITCOIN_CONSENSUS_PARAMS_H
