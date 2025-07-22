// Copyright (c) 2024-2025 The Rincoin developers
// Distributed under the MIT software license, see the accompanying
// file COPYING or http://www.opensource.org/licenses/mit-license.php.
#ifndef RINHASH_H
#define RINHASH_H

#include "uint256.h"
#include "primitives/block.h"

uint256 RinHash(const CBlockHeader& block);

#endif // RINHASH_H
