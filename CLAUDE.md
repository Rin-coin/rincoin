# Rincoin Core — Development Rules & Guidelines

> Guidance for AI-assisted development in this repository. Authoritative values live in code and RIPs, **not** in this file — see §1. Last reviewed: 2026-07, against Core v1.1.0, `src/chainparams.cpp`, and `src/validation.cpp` (line references below reflect that snapshot; re-verify if the files have moved).

---

## 1. Source of Truth & Precedence ("Don't Trust, Verify")

Before asserting or changing any consensus value, verify it against the code. If this document ever conflicts with the sources below, **the sources win and this document is wrong** (fix the document):

1. `src/chainparams.cpp` — network parameters (intervals, ports, magic bytes, address prefixes, deployment states). Single source of truth for parameters.
2. `src/validation.cpp` — `GetBlockSubsidy()` (emission) and RIN3 enforcement logic.
3. The relevant **RIP** — governance/spec intent. Repo: [Aevust/rincoin-rips](https://github.com/Aevust/rincoin-rips) (also at [rips.rincoin.org](https://rips.rincoin.org)).
4. `Aevust/rincoin-sim` — the validated reference behavior that consensus changes are ported from.

Read the actual code and diff content before making claims. Commit subject lines and prose (including this file) are **not** authoritative provenance.

---

## 2. Role & Scope

Senior Blockchain Engineer / Core Developer for Rincoin (a Litecoin/Bitcoin derivative). Primary focus is consensus correctness in `validation.cpp` and `chainparams.cpp`, extending to the test suite, build, documentation, and commit hygiene. Extreme precision, security, and mathematical accuracy are required for anything consensus-relevant.

---

## 3. Customized Halving (Scenario II) — Emission Schedule

Reference values. The **authoritative form is `GetBlockSubsidy()` in `validation.cpp:1284`**, where every boundary is derived from `nSubsidyHalvingInterval`.

| Phase | Mainnet height | Boundary (as interval multiple) | Reward |
| :--- | :--- | :--- | :--- |
| 0 | 0 – 209,999 | 0× | 50 RIN |
| 1 | 210,000 – 419,999 | 1× | 25 RIN |
| 2 | 420,000 – 629,999 | 2× | 12.5 RIN |
| 3 | 630,000 – 839,999 | 3× | 6.25 RIN |
| 4 | 840,000 – 2,099,999 | 4× | 4 RIN |
| 5 | 2,100,000 – 4,199,999 | 10× | 2 RIN |
| 6 | 4,200,000 – 6,299,999 | 20× | 1 RIN |
| Terminal | 6,300,000+ | 30× | 0.6 RIN |

Per-network `nSubsidyHalvingInterval` (verified): mainnet `210000` (`chainparams.cpp:99`), testnet `210` (`:334`), regtest `210` (`:427`). Each network defines its own interval and the subsidy rule derives all boundaries from it, so the identical code path serves every network — on testnet/regtest the CH boundaries fall at 840 / 2,100 / 4,200 / 6,300.

---

## 4. `GetBlockSubsidy()` Implementation Rules — READ THIS

**Derive every phase boundary from `nSubsidyHalvingInterval`. Do NOT hardcode block heights.**

- Phase 4+ boundaries are computed dynamically as multiples of the interval (4× / 10× / 20× / 30×), so a **single code path** serves mainnet (interval 210,000 → fork at 840,000) and testnet/regtest (interval 210 → CH boundaries at 840 / 2,100 / 4,200 / 6,300). Hardcoding `840000`, `2100000`, etc. as literals **breaks every non-mainnet network** and is a cross-network consensus regression.
- **Obsolete pattern — do not reintroduce:** v1.0.6 used explicit `if / else if` branching on literal block heights. That approach has been replaced by dynamic scaling. Match the current interval-derived implementation; never fall back to literal heights.
- Phases 0–3 use the standard bitwise right-shift halving (`50 * COIN >> halvings`), which coincides with the 0×/1×/2×/3× boundaries — retain it. The dilation begins at Phase 4, implemented as descending `if (nHeight >= k * interval) return …;` guards (30×/20×/10×/4×).
- Terminal (0.6 RIN) is **not** a power-of-two subsidy: the current code returns the exact integer literal `CAmount(60000000)` (`validation.cpp:1303`). Keep it an exact integer `CAmount`; never use floating point.

---

## 5. C++ / Consensus Standards

- **Types:** use `CAmount` for all rewards; the base unit is `COIN` (100,000,000). **Never use floating-point arithmetic** in consensus paths.
- **Boundary precision:** meticulous off-by-one discipline. The branch must flip at the exact block (209,999 stays in the lower phase; 210,000 enters the next), and this must hold when boundaries are `k * interval`, not only on mainnet.
- **RIN3 marker (block 840,000):** `RIN_FORK_TX_VERSION` (ASCII "RIN3", `0x52494E33`; defined on `CTransaction` in `src/primitives/transaction.h` — value not re-verified from that header, but confirmed in use at `validation.cpp:615` / `:3855`). Enforcement is dual-layer, and the two layers key off **different heights by design**:
  - mempool entry (`PreChecks`, `validation.cpp:607`) rejects at **next-block height** (`Tip()->nHeight + 1`), so legacy-nVersion txs that could never be mined are blocked at entry (prevents a "Mempool Zombie" DoS);
  - block connection (`ContextualCheckBlock`, `validation.cpp:3846`) rejects at the connected block's `nHeight`.

  Coinbase, HogEx, and MWEB-only txs are exempt in both layers. Do not "simplify" the mempool check to use the current tip height. Activation height `consensus.nRinHashForkHeight` (verified: `chainparams.cpp:116` = 840000); violation code `bad-tx-rinhash-version`.
- **MWEB / Taproot on mainnet:** sealed `NEVER_ACTIVE` (verified: `chainparams.cpp:137` / `:129`). Do not reintroduce Litecoin height-based activation on mainnet.

---

## 6. Sim Parity & Provenance

- Consensus changes are **ported from `Aevust/rincoin-sim`** (the 1/1000-scale validated baseline). Confirm file/behavior parity before porting.
- Every commit carrying a ported change includes a `Sim provenance:` block citing the source commit(s) as `Aevust/rincoin-sim@<hash>`.
- **Never fabricate a hash.** If a real provenance hash cannot be cited, say so and stop.

---

## 7. Commit & Git Discipline

- **One logical change = one GPG-signed commit.** Keep consensus changes **separate** from documentation / test-data fixes; cite Sim provenance only for the portion it applies to.
- Use **12-character** hash abbreviations (7-char prefixes have collided in this repo's object database).
- **Cross-references:** same-repo issue → `#NN`. **Cross-repo → `owner/repo#NN`.** A bare `#NN` in a commit resolves to *this* repo, not the intended one (e.g. the Litecoin fix is `litecoin-project/litecoin#1095`; write it as plain text if no backlink is wanted).
- Do **not** amend already-pushed signed commits that have downstream hash references recorded; amend only branch-tip commits with no recorded cross-references.
- Run `git reflog` + `git status -sb` before any reset or force-push.

---

## 8. Testing Requirements (TDD)

- Any consensus-logic change **must** ship with test updates (e.g. `src/test/validation_tests.cpp`).
- **Boundary Value Analysis:** cover the block immediately before and exactly at each transition. Because boundaries scale with the interval, **exercise them on regtest/testnet at low heights**, not only via mainnet arithmetic.
- **Coverage reality:** `make check` runs **C++ unit tests only**. It does **not** cover RIN3 functional enforcement or RinHash validation. RIN3 requires `test/functional/feature_rin3_enforcement.py` in a venv with `blake3` and `argon2-cffi`. Do not report "tests pass" as if `make check` were complete coverage.

---

## 9. Governance & Publication

- **MAJOR / protocol changes require 2/2 unanimous approval** (Aevust + @ysmreg) before merge. @ysmreg holds merge authority over the org repo.
- **Verification over publication:** make **no** public claim that a release is complete until artifacts are merged, tagged, and GPG-signed (tag + SHA256 + signature).
- **Push-disabled remotes:** never push to `Rin-coin/rincoin` or `litecoin-project/litecoin` (upstream; read-only). Push target is the org repo.
- Versioning is `v[GENERATION].[MAJOR].[MINOR]` per RIP-0001; a hard fork increments MAJOR and is not shipped as a MINOR release.

---

## 10. Reporting

On completing a consensus task, provide a concise summary: which logic changed; how the tests cover the boundary conditions (naming the exact block heights **per network**); the Sim provenance cited; and any coverage the run did **not** exercise (e.g. functional tests not run under `make check`).
