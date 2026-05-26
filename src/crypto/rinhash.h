// Copyright (c) 2024-2025 The Rincoin developers
// Distributed under the MIT software license, see the accompanying
// file COPYING or http://www.opensource.org/licenses/mit-license.php.
#ifndef RINHASH_H
#define RINHASH_H

#include "uint256.h"
#include "primitives/block.h"
#include <consensus/params.h>

//! Compute RinHash with the network's pre-activations (init) parameters. Provided
//! for call sites that have no block-height context (e.g. legacy benchmarks
//! and parallel header-batch verification helpers).
uint256 RinHash(const CBlockHeader& block);

//! Compute RinHash using the supplied Argon2d parameters. Use
//! Consensus::Params::GetRinHashEffectiveAt(height).pow to obtain the
//! correct overlay-resolved values for a given block height.
uint256 RinHash(const CBlockHeader& block, const Consensus::Params::Argon2dParams& pow);

#endif // RINHASH_H
