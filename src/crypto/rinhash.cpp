// Copyright (c) 2024-2025 The Rincoin developers
// Distributed under the MIT software license, see the accompanying
// file COPYING or http://www.opensource.org/licenses/mit-license.php.
#include "rinhash.h"
#include "uint256.h"
#include "serialize.h"
#include "crypto/blake3/blake3.h"
#include "crypto/sha3.h"
#include "crypto/argon2/include/argon2.h"
#include <span.h> // MakeUCharSpan を使うなら必要
#include <stdexcept>

uint256 RinHash(const CBlockHeader& block)
{
    CDataStream ss(SER_GETHASH, PROTOCOL_VERSION);
    ss << block;
    std::vector<unsigned char> input(ss.begin(), ss.end());

    uint8_t blake3_out[32];
    blake3_hasher blake_hasher;
    blake3_hasher_init(&blake_hasher);
    blake3_hasher_update(&blake_hasher, input.data(), input.size());
    blake3_hasher_finalize(&blake_hasher, blake3_out, 32);

    const char* salt_str = "RinCoinSalt";
    uint8_t argon2_out[32];
    argon2_context context = {};
    context.out = argon2_out;
    context.outlen = 32;
    context.pwd = blake3_out;
    context.pwdlen = 32;
    context.salt = (uint8_t*)salt_str;
    context.saltlen = strlen(salt_str);
    context.t_cost = 2;
    context.m_cost = 64;
    context.lanes = 1;
    context.threads = 1;
    context.version = ARGON2_VERSION_13;
    context.allocate_cbk = nullptr;
    context.free_cbk = nullptr;
    context.flags = ARGON2_DEFAULT_FLAGS;

    if (argon2d_ctx(&context) != ARGON2_OK) {
        throw std::runtime_error("Argon2d hashing failed");
    }

    uint8_t sha3_out[32];
    SHA3_256().Write(Span<const unsigned char>(argon2_out, 32)).Finalize(sha3_out);

    return uint256(std::vector<unsigned char>(sha3_out, sha3_out + 32));
}
