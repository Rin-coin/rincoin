// Copyright (c) 2024-2025 The Rincoin developers
// Distributed under the MIT software license, see the accompanying
// file COPYING or http://www.opensource.org/licenses/mit-license.php.
#include "rinhash.h"
#include "uint256.h"
#include "serialize.h"
#include "crypto/blake3/blake3.h"
#include "crypto/sha3.h"
#include "crypto/argon2/argon2.h"

uint256 RinHash(const CBlockHeader& block)
{
    // Step 1: Serialize block header
    CDataStream ss(SER_GETHASH, PROTOCOL_VERSION);
    ss << block;
    std::vector<unsigned char> input(ss.begin(), ss.end());

    // Step 2: BLAKE3 hash
    uint8_t blake3_out[32];
    blake3_hasher blake_hasher;
    blake3_hasher_init(&blake_hasher);
    blake3_hasher_update(&blake_hasher, input.data(), input.size());
    blake3_hasher_finalize(&blake_hasher, blake3_out, 32);

    // Step 3: Argon2d hash
    uint8_t argon2_out[32];
    argon2_context context;
    memset(&context, 0, sizeof(context));

    context.out = argon2_out;
    context.outlen = 32;
    context.pwd = blake3_out;
    context.pwdlen = 32;
    context.salt = blake3_out;  // reuse blake3 as salt (for simplicity)
    context.saltlen = 32;
    context.t_cost = 2;     // iterations
    context.m_cost = 64;    // KB
    context.lanes = 1;
    context.threads = 1;
    context.version = ARGON2_VERSION_13;
    context.allocate_cbk = nullptr;
    context.free_cbk = nullptr;
    context.flags = ARGON2_DEFAULT_FLAGS;

    int result = argon2d_ctx(&context);
    if (result != ARGON2_OK) {
        throw std::runtime_error("Argon2d hashing failed: " + std::string(argon2_error_message(result)));
    }

    // Step 4: SHA3-256 final hash
    uint8_t sha3_out[32];
    sha3_256(sha3_out, argon2_out, 32);

    return uint256(sha3_out);
}
