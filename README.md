
# RinCoin Core

RinCoin is a decentralized digital currency, based on Bitcoin Core, that introduces a new Proof-of-Work hashing algorithm called **RinHash**. RinHash is a hybrid PoW algorithm designed for both security and ASIC-resistance, combining BLAKE3, Argon2d, and SHA3-256. This README provides an overview of RinCoin’s specifications, the RinHash algorithm, and network parameters.

## Key Specifications

- **Coin Name / Ticker:** RinCoin (**RIN**)  
- **Consensus Mechanism:** Proof-of-Work (PoW) – **RinHash** algorithm (BLAKE3 → Argon2d → SHA3-256)  
- **Block Target Time:** 1 minute (60 seconds per block)  
- **Block Reward:** 50 RIN (initial coinbase reward per block)  
- **Halving Schedule:** Reward halves every 210,000 blocks (~145 days at 1 min blocks)  
- **Difficulty Adjustment:** Every 2016 blocks (~33.6 hours)  
- **Proof-of-Work Hash:** 256-bit output  
- **Address Format:** Base58 addresses start with **R**  
- **Network Ports:** P2P: 9555, RPC: 9556  
- **Network Magic:** 0x52 0x49 0x4E 0x43 ("RINC")  

## Proof-of-Work Algorithm: RinHash

RinHash is a custom proof-of-work algorithm using:

1. **BLAKE3**: Fast initial hashing  
2. **Argon2d**: Memory-hard step to resist ASICs  
3. **SHA3-256**: Final standard cryptographic hash

A valid block satisfies:  
`SHA3-256( Argon2d( BLAKE3(block_header) )) < Target`

This design provides:
- Fast verification
- Memory-hardness to deter ASICs
- Compatibility with existing 256-bit PoW frameworks

## Network and Usage

- **Magic bytes:** `0x52 0x49 0x4E 0x43`  
- **Ports:** 9555 (P2P), 9556 (RPC)  
- **Mining:** CPU/GPU mining supported  
- **Wallet:** Full-node wallet with RIN units

## Building Rincoin

For detailed instructions on building release binaries for Linux and Windows, see [doc/build-release.md](doc/build-release.md).

Quick start for building from source:
- [Linux/Unix Build Notes](doc/build-unix.md)
- [Windows Build Notes](doc/build-windows.md)
- [Release Build Guide](doc/build-release.md)

## Developer Notes

See `chainparams.cpp` for network configuration.  
See `GetPoWHash()` for RinHash implementation.  
See [doc/rinhash-activations.md](doc/rinhash-activations.md) for the
height-indexed RinHash activations table introduced in v1.1.0 and for
items intentionally left out of this release.

## Rincoin Community
[![Discord Banner 2](https://discord.com/api/guilds/1354664874176680017/widget.png?style=banner2)](https://discord.gg/Ap7TUXYRBf)