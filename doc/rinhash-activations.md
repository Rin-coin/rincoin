# RinHash Activations Table

> Status: introduced in **Rincoin Core v1.1.0** (release branch
> `release-v1.1.0-community-maintenance`). Forward-looking infrastructure:
> the v1.1.0 release ships a single dormant overlay; it does **not** change
> consensus rules already in force on mainnet.

## Motivation

Rincoin's PoW (RinHash: BLAKE3 → Argon2d → SHA3-256) and a small set of
consensus-adjacent network parameters need to be evolvable without scattering
ad-hoc `if (height >= X)` branches across the codebase. The RinHash
activations table provides a single, auditable, height-indexed structure
that:

- holds an `init` baseline and an ordered list of `activations[]` overlays
  per network (`mainnet`, `testnet`, `regtest`, `preview`);
- is the **single source of truth** — a code-generated header
  (`src/consensus/rinhash_consensus_data.h`) is produced from the JSON file
  and a CI guard (`gen_rinhash_consensus.py --check`) blocks merges that
  desynchronise the two;
- is queryable at runtime through `Consensus::Params::GetRinHashEffectiveAt(int height)`
  and exposed via the `getrinhashparams` RPC and the `rinhash.effective`
  block in `getblockchaininfo`.

The first overlay deployed on this infrastructure is intentionally narrow —
a peer-protocol-version floor — so the framework can be exercised end-to-end
on real networks before any more invasive consensus change is proposed.

## Files of record

| File | Role |
|------|------|
| `src/consensus/rinhash_consensus.json` | Authoritative table (`init` + `activations[]` per network) |
| `src/consensus/rinhash_consensus.schema.json` | JSON Schema; validates the table |
| `src/consensus/gen_rinhash_consensus.py` | Generator + `--check` CI guard |
| `src/consensus/rinhash_consensus_data.h` | Generated header consumed by `chainparams.cpp` |
| `src/consensus/params.h` | `Argon2dParams`, `RinHashOverlay`, `RinHashActivation`, `RinHashEffective`, `GetRinHashEffectiveAt()` |
| `src/chainparams.cpp` | Applies overlays via `ApplyRinHashConsensus()` per network |
| `src/Makefile.am` | Wires the codegen + `--check` into the build |

## JSON layout

```jsonc
{
  "networks": {
    "mainnet": {
      "init":  { "t_cost": 2, "m_cost": 64, "lanes": 1, "salt": "RinCoinSalt" },
      "activations":  [
        { "activation_height": 840000, "min_peer_protocol_version": 70018 }
      ]
    },
    "testnet": { "init": { "t_cost": 2, "m_cost": 64, "lanes": 1, "salt": "RinCoinSalt" },
                  "activations": [ { "activation_height": 4200, "min_peer_protocol_version": 70018 } ] },
    "regtest": { "init": { "t_cost": 2, "m_cost": 64, "lanes": 1, "salt": "RinCoinSalt" },
                  "activations": [ { "activation_height": 600,  "min_peer_protocol_version": 70018 } ] },
    "preview": { "init": { "t_cost": 2, "m_cost": 64, "lanes": 1, "salt": "RinCoinSalt" },
                  "activations": [ { "activation_height": 600,  "min_peer_protocol_version": 70018 } ] }
  }
}
```

`m_cost` is in MiB (matches the in-memory `Argon2dParams::m_cost` field).

Semantics:

- The `init` block defines the baseline that is in force from height 0.
- Each entry in `activations[]` is an **overlay**: only the fields it
  specifies are updated; unspecified fields inherit their last-effective
  value (last-write-wins per field).
- Heights in `activations[]` MUST be strictly ascending.
- Adding a new field requires an additive change in three places only: the
  schema, the generator's `SET_FIELDS` list, and the `RinHashOverlay` /
  `RinHashEffective` structs in `params.h`. The generator and CI guard
  ensure the C++ side stays in lockstep.

## Runtime resolution

```cpp
const Consensus::Params& cp = Params().GetConsensus();
const Consensus::RinHashEffective& eff = cp.GetRinHashEffectiveAt(height);

// Argon2d parameters in force at `height`:
eff.pow.t_cost; eff.pow.m_cost; eff.pow.lanes; eff.pow.salt;
// Networking floor in force at `height`:
eff.min_peer_protocol_version;
```

`GetRinHashEffectiveAt()` is a pure function of the chain table and the
supplied height: it walks `activations[]` in order, applying overlays whose
`activation_height <= height`. It is safe to call from any thread and from
both validation and RPC paths.

## v1.1.0 overlay: peer-protocol-version floor

The single overlay shipped in v1.1.0 sets `min_peer_protocol_version = 70018`
at each network's first activation height. Below that height the field is
`0` (dormant) and the existing `MIN_PEER_PROTO_VERSION` (`31800`) is the only
floor enforced.

From the activation height onward, peers offering a `nVersion` strictly less
than the effective floor are disconnected during the version handshake (see
`net_processing.cpp`, `ProcessMessage` VERSION handler). Once activation 0
is in force, only nodes advertising `nVersion ≥ 70018` remain reachable;
this provides a clean handshake-level boundary that any subsequent rule
change can opt into without re-implementing version-gating logic.

Activation heights:

| Network  | Height | Approx. timing               |
|----------|--------|------------------------------|
| mainnet  | 840000 | scheduled (4th halving)      |
| testnet  | 4200   | early activation for staging |
| regtest  | 600    | for unit/functional tests    |
| preview  | 600    | for rehearsal mining         |

## Adding a future overlay

1. Append a new entry to the relevant network's `activations[]` array in
   `rinhash_consensus.json`. Make sure heights remain strictly ascending.
2. If a new consensus field is needed, add it (a) in the schema, (b) in
   `SET_FIELDS` in `gen_rinhash_consensus.py`, and (c) as `has_X` / `value_X`
   on `RinHashOverlay` plus the matching field on `RinHashEffective` in
   `params.h`. Extend the `apply` lambda in `GetRinHashEffectiveAt`.
3. Run `python3 src/consensus/gen_rinhash_consensus.py` to regenerate
   `rinhash_consensus_data.h`.
4. Verify with `python3 src/consensus/gen_rinhash_consensus.py --check` —
   this same command runs in CI; PRs that omit the regenerated header are
   rejected.
5. Add a unit test asserting the new effective value at the relevant
   boundary heights (see `src/test/rinhash_tests.cpp` for examples).

## Inspecting effective parameters

```bash
$ rincoin-cli getrinhashparams
{
  "chain": "main",
  "height": 612345,
  "init": { "t_cost": 2, "m_cost": 64, "lanes": 1, "salt": "RinCoinSalt" },
  "activations": [
    { "activation_height": 840000, "min_peer_protocol_version": 70018 }
  ],
  "effective": {
    "t_cost": 2,
    "m_cost": 64,
    "lanes": 1,
    "salt": "RinCoinSalt",
    "min_peer_protocol_version": 0
  }
}
```

The `effective` object is the fully-resolved table at the requested height
(or active tip if no `height` argument is supplied). The same `effective`
payload is also exposed under `getblockchaininfo` → `rinhash.effective` so
dashboards and explorers can surface the active overlay without an extra
RPC. The `getblockchaininfo.rinhash` block additionally carries `height`
and a `next_change` object (`activation_height`, `blocks_until`) for the
first future activation past the tip, or `null` once no further overlays
remain.

## Testing

- `src/test/rinhash_tests.cpp` — unit tests covering the canonical PoW
  vector, init-only dormancy, mainnet activation at 840000, height-aware
  PoW overload, pending-salt rejection, and the testnet/regtest/preview
  activation-0 boundaries.
- `test/functional/feature_min_peer_proto_floor.py` — regtest end-to-end:
  asserts that a peer advertising `nVersion = 70017` is accepted before
  height 600 and disconnected at/after height 600, while a peer at the
  effective floor (`70018`) connects in either window.

## Out of scope for v1.1.0

Customised halving, alternative Argon2d parameter sets, and any new
transaction-level consensus rules are explicitly out of scope for v1.1.0
and remain subjects for separate, community-reviewed proposals.
