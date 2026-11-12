Rincoin Core
=============

Setup
---------------------
Rincoin Core is the reference Rincoin client and forms the backbone of the network. It downloads and, by default, stores the entire history of Rincoin transactions.

Rincoin is derived from Bitcoin via Litecoin, with the following key differences:

- **Proof-of-Work**: RinHash (BLAKE3 → Argon2d → SHA3-256) — CPU-friendly
- **Block time**: 60 seconds
- **Hard cap**: 168,000,000 RIN
- **Customized Halving (CH)**: Block 840,000 dilation (6.25 → 4.00 RIN)
- **MWEB**: Mainnet `NEVER_ACTIVE` (sealed until preconditions are met)

To download Rincoin Core, visit [rincoin.org](https://rincoin.org/) or the [GitHub Releases](https://github.com/Rin-coin/rincoin/releases) page.

Running
---------------------
The following are notes on how to run Rincoin Core on your native platform.

### Unix

Unpack the files into a directory and run:

- `bin/rincoin-qt` (GUI) or
- `bin/rincoind` (headless)

### Windows

Unpack the files into a directory, and then run `rincoin-qt.exe`.

### macOS

Drag Rincoin Core to your Applications folder, and then run Rincoin Core.

### Need Help?

- See the [Rincoin Whitepaper](https://doi.org/10.5281/zenodo.17141922)
  for protocol specifications.
- Open an issue on the [GitHub repository](https://github.com/Rin-coin/rincoin/issues).
- Join the discussion on the [Rincoin Discord](https://discord.gg/H4Du5YuqFa)
  (community-operated).

Building
---------------------
The following are developer notes on how to build Rincoin Core on your native platform. They are not complete guides, but include notes on necessary libraries, compile flags, etc.

- [Dependencies](dependencies.md)
- [macOS Build Notes](build-osx.md)
- [Unix Build Notes](build-unix.md)
- [Windows Build Notes](build-windows.md)
- [FreeBSD Build Notes](build-freebsd.md)
- [OpenBSD Build Notes](build-openbsd.md)
- [NetBSD Build Notes](build-netbsd.md)

Development
---------------------
The Rincoin repo's [root README](/README.md) contains relevant
information on the development process and automated testing.

- [Developer Notes](developer-notes.md)
- [Productivity Notes](productivity.md)
- [Release Notes](release-notes/README.md)
- [Release Process](release-process.md)
- [Source Code Documentation (External)](https://doxygen.bitcoincore.org/)
- [Translation Process](translation_process.md)
- [Translation Strings Policy](translation_strings_policy.md)
- [JSON-RPC Interface](JSON-RPC-interface.md)
- [Unauthenticated REST Interface](REST-interface.md)
- [Shared Libraries](shared-libraries.md)
- [BIPs](bips.md)
- [RIPs (Rincoin Improvement Proposals)](https://github.com/Rin-coin/rips)
- [DNS Seed Policy](dnsseed-policy.md)
- [Benchmarking](benchmarking.md)

### Rincoin-Sim (1/1000-scale test environment)

- [Build & Test Guide (v1.0.7)](release-notes/rincoin-sim/v1.0.7-build-guide.md)
- [Test Evidence Archive](release-notes/rincoin-sim/EVIDENCE.md)

### Resources

- [Rincoin Whitepaper](https://doi.org/10.5281/zenodo.17141922)
- [RIPs Repository](https://github.com/Rin-coin/rips)
- [GitHub Discussions](https://github.com/Rin-coin/rincoin/discussions)

Miscellaneous
---------------------
- [Assets Attribution](assets-attribution.md)
- [rincoin.conf Configuration File](rincoin-conf.md)
- [Files](files.md)
- [Fuzz-testing](fuzzing.md)
- [Reduce Memory](reduce-memory.md)
- [Reduce Traffic](reduce-traffic.md)
- [Tor Support](tor.md)
- [Init Scripts (systemd/upstart/openrc)](init.md)
- [ZMQ](zmq.md)
- [PSBT support](psbt.md)
- [MWEB (Privacy Layer, currently sealed)](mweb.md)

License
---------------------
Distributed under the [MIT software license](/COPYING).
