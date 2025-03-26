#ifndef RINHASH_H
#define RINHASH_H

#include "uint256.h"
#include "primitives/block.h"

uint256 RinHash(const CBlockHeader& block);

#endif // RINHASH_H
