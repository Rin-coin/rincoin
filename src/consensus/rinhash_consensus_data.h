// Copyright (c) 2026 The Rincoin developers
// Distributed under the MIT software license, see the accompanying
// file COPYING or http://www.opensource.org/licenses/mit-license.php.
//
// AUTO-GENERATED FILE. DO NOT EDIT.
//
// Source:    src/consensus/rinhash_consensus.json
// Generator: src/consensus/gen_rinhash_consensus.py
//
// To update: edit the JSON file, then run the generator and commit both
// files in a single commit. CI verifies that this header matches the JSON
// on every pull request.

#ifndef BITCOIN_CONSENSUS_RINHASH_CONSENSUS_DATA_H
#define BITCOIN_CONSENSUS_RINHASH_CONSENSUS_DATA_H

#include <consensus/params.h>

#include <cstdint>
#include <string>
#include <vector>

namespace Consensus {
namespace RinHashGen {

// Single overlay record. Each field is an (is_set, value) pair; an unset
// field inherits from the previous overlay (or from the network's init).
// `init` is encoded as the same overlay shape with activation_height = 0.
struct GeneratedOverlay {
    int activation_height;

    bool        has_t_cost;                        uint32_t                  t_cost;
    bool        has_m_cost;                        uint32_t                  m_cost;
    bool        has_lanes;                         uint32_t                  lanes;
    bool        has_salt;                          std::string               salt;
    bool        has_min_peer_protocol_version;     int                       min_peer_protocol_version;
};

struct GeneratedNetwork {
    GeneratedOverlay              init;
    std::vector<GeneratedOverlay> activations;
};

// === Network: mainnet ===

inline const GeneratedNetwork& GetMainnetData() {
    static const GeneratedNetwork data{
        // init
        GeneratedOverlay{
            /* activation_height */ 0,
            /* has_t_cost */ true, /* t_cost */ 2u,
            /* has_m_cost */ true, /* m_cost */ 64u,
            /* has_lanes */ true, /* lanes */ 1u,
            /* has_salt */ true, /* salt */ std::string("RinCoinSalt"),
            /* has_min_peer_protocol_version */ false, /* min_peer_protocol_version */ {},
        },
        // activations
        std::vector<GeneratedOverlay>{
            GeneratedOverlay{
                /* activation_height */ 840000,
                /* has_t_cost */ false, /* t_cost */ {},
                /* has_m_cost */ false, /* m_cost */ {},
                /* has_lanes */ false, /* lanes */ {},
                /* has_salt */ false, /* salt */ {},
                /* has_min_peer_protocol_version */ true, /* min_peer_protocol_version */ 70018,
            },
        },
    };
    return data;
}

// === Network: testnet ===

inline const GeneratedNetwork& GetTestnetData() {
    static const GeneratedNetwork data{
        // init
        GeneratedOverlay{
            /* activation_height */ 0,
            /* has_t_cost */ true, /* t_cost */ 2u,
            /* has_m_cost */ true, /* m_cost */ 64u,
            /* has_lanes */ true, /* lanes */ 1u,
            /* has_salt */ true, /* salt */ std::string("RinCoinSalt"),
            /* has_min_peer_protocol_version */ false, /* min_peer_protocol_version */ {},
        },
        // activations
        std::vector<GeneratedOverlay>{
            GeneratedOverlay{
                /* activation_height */ 4200,
                /* has_t_cost */ false, /* t_cost */ {},
                /* has_m_cost */ false, /* m_cost */ {},
                /* has_lanes */ false, /* lanes */ {},
                /* has_salt */ false, /* salt */ {},
                /* has_min_peer_protocol_version */ true, /* min_peer_protocol_version */ 70018,
            },
        },
    };
    return data;
}

// === Network: regtest ===

inline const GeneratedNetwork& GetRegtestData() {
    static const GeneratedNetwork data{
        // init
        GeneratedOverlay{
            /* activation_height */ 0,
            /* has_t_cost */ true, /* t_cost */ 2u,
            /* has_m_cost */ true, /* m_cost */ 64u,
            /* has_lanes */ true, /* lanes */ 1u,
            /* has_salt */ true, /* salt */ std::string("RinCoinSalt"),
            /* has_min_peer_protocol_version */ false, /* min_peer_protocol_version */ {},
        },
        // activations
        std::vector<GeneratedOverlay>{
            GeneratedOverlay{
                /* activation_height */ 600,
                /* has_t_cost */ false, /* t_cost */ {},
                /* has_m_cost */ false, /* m_cost */ {},
                /* has_lanes */ false, /* lanes */ {},
                /* has_salt */ false, /* salt */ {},
                /* has_min_peer_protocol_version */ true, /* min_peer_protocol_version */ 70018,
            },
        },
    };
    return data;
}

// === Network: preview ===

inline const GeneratedNetwork& GetPreviewData() {
    static const GeneratedNetwork data{
        // init
        GeneratedOverlay{
            /* activation_height */ 0,
            /* has_t_cost */ true, /* t_cost */ 2u,
            /* has_m_cost */ true, /* m_cost */ 64u,
            /* has_lanes */ true, /* lanes */ 1u,
            /* has_salt */ true, /* salt */ std::string("RinCoinSalt"),
            /* has_min_peer_protocol_version */ false, /* min_peer_protocol_version */ {},
        },
        // activations
        std::vector<GeneratedOverlay>{
            GeneratedOverlay{
                /* activation_height */ 600,
                /* has_t_cost */ false, /* t_cost */ {},
                /* has_m_cost */ false, /* m_cost */ {},
                /* has_lanes */ false, /* lanes */ {},
                /* has_salt */ false, /* salt */ {},
                /* has_min_peer_protocol_version */ true, /* min_peer_protocol_version */ 70018,
            },
        },
    };
    return data;
}

} // namespace RinHashGen
} // namespace Consensus

#endif // BITCOIN_CONSENSUS_RINHASH_CONSENSUS_DATA_H
