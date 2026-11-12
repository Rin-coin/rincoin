// Copyright (c) 2009-2010 Satoshi Nakamoto
// Copyright (c) 2009-2018 The Bitcoin Core developers
// Copyright (c) 2024-2025 The Rincoin developers
// Distributed under the MIT software license, see the accompanying
// file COPYING or http://www.opensource.org/licenses/mit-license.php.

#ifndef BITCOIN_AMOUNT_H
#define BITCOIN_AMOUNT_H

#include <stdint.h>

/** Amount in satoshis (Can be negative) */
typedef int64_t CAmount;

static const CAmount COIN = 100000000;

/** No amount larger than this (in satoshi) is valid.
 *
 * Note that this constant is *not* the total money supply, which in Bitcoin
 * currently happens to be less than 21,000,000 BTC for various reasons, but
 * rather a sanity check. As this sanity check is used by consensus-critical
 * validation code, the exact value of the MAX_MONEY constant is consensus
 * critical; in unusual circumstances like a(nother) overflow bug that allowed
 * for the creation of coins out of thin air modification could lead to a fork.
 *
 * Rincoin: MAX_MONEY is set to 168,000,000 RIN -- 8x the Bitcoin ceiling
 * referenced above, and 2x Litecoin's 84,000,000 -- matching the hard cap
 * defined in the Rincoin whitepaper. Consistent with that note, this
 * value is a consensus-critical sanity bound on individual amounts, not a
 * running check on cumulative issued supply. Emission itself is governed by
 * the Customized Halving schedule in GetBlockSubsidy() (validation.cpp),
 * as specified in RIP-0002.
 */
static const CAmount MAX_MONEY = 168000000 * COIN;
inline bool MoneyRange(const CAmount& nValue) { return (nValue >= 0 && nValue <= MAX_MONEY); }

/** Rincoin supply cap, expressed per halving interval (RIP-0002).
 *  800 RIN * 210,000 = 168,000,000 RIN on mainnet, where the derived
 *  cap equals MAX_MONEY above. Scaled networks (interval = 210) derive
 *  their cap the same way every other CH phase boundary is derived.
 *  Accounting only: no consensus rule reads this constant yet.
 */
static constexpr CAmount SUPPLY_CAP_PER_INTERVAL = 800 * COIN;

#endif //  BITCOIN_AMOUNT_H
