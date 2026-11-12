# contrib/release — multi-platform build & sign

One-command cross builds of Rincoin Core for **Linux x86_64**, **Windows x64**, and **ARM64 (aarch64)** via the upstream `depends` system, plus a portable signing script that runs on both the Linux build host and a Windows signing machine.

This is the automation layer over Part II (§10) of `release-process.md`. It does **not** replace the verified native Linux build (Part I, §1–9): that remains the canonical x86_64-linux release path until the depends/cross builds clear the §10-6
checklist.

> **Status — EXPERIMENTAL.** RinHash (BLAKE3 → Argon2d → SHA3-256) and BDB-4.8 cross-compilation are not yet confirmed for aarch64. `make` gives you the *flow*; you must still pass the §10-6 verification checklist before publishing any cross-built artifact. *Verification over publication.*

## Files

- `Makefile` — the `make linux | windows | aarch64 | all-cli | all-release | dist | sign | release` interface. Bare targets are CLI-only; add `-full` (`linux-full`, `windows-full`) for the Qt GUI.
- `sign.sh` — SHA256SUMS + GPG detached signature; portable (Linux and Windows Git Bash).

## Prerequisites (build host, Ubuntu 24.04)

Cross toolchains + `depends` prerequisites:

```bash
sudo apt update
sudo apt install -y \
    build-essential autotools-dev automake libtool pkg-config bison \
    curl python3 patch zip \
    g++-mingw-w64-x86-64 g++-aarch64-linux-gnu

# Bitcoin/Litecoin require the POSIX threading model for MinGW:
sudo update-alternatives --config x86_64-w64-mingw32-g++   # choose .../posix
sudo update-alternatives --config x86_64-w64-mingw32-gcc   # choose .../posix
```

`depends` downloads dependency sources on the first build, so the host needs internet access for the first run (or a pre-populated `depends/sources/` cache).

The Rincoin-specific crypto (`src/crypto/argon2/` → `libargon2`, BLAKE3, SHA3-256) is built **in-tree** by the main `make`, not by `depends`; cross-compiling it just needs the cross toolchain to handle its SIMD/threading code. That is exactly the part §10-6 asks you to confirm per target.

## Build

From the repo root:

```bash
cd contrib/release

make windows        # -> ../../release-artifacts/rincoin-<VERSION>-win64.zip
make aarch64        # -> ../../release-artifacts/rincoin-<VERSION>-aarch64-linux-gnu.tar.gz
make linux          # -> ../../release-artifacts/rincoin-<VERSION>-x86_64-linux-gnu.tar.gz
make all-cli        # all three, CLI-only, in sequence (always serial)
```

Bare targets are **CLI-only** (faster; validate the core first, per §10-4). The Qt GUI is selected by the target **name**, not a flag — append `-full` (much heavier; win/aarch64 Qt are the most fragile part):

```bash
make windows-full
```

There is deliberately no `GUI=` flag; passing one is a hard error. `all-release` is the ship matrix — GUI on linux/win, CLI-only on aarch64.

`<VERSION>` is parsed from `configure.ac` (RIP-0001 mapping → e.g. `1.1.0`) and carries **no leading `v`** — the `v` lives only on the git tag (`TAG`, e.g. `v1.1.0`), matching Bitcoin/Litecoin file naming. For a release candidate, the two split on purpose: the tag uses the readable Linux-style hyphen (`v1.1.0-rc1`), while files use the single-token `1.1.0rc1` (`rincoin-1.1.0rc1-win64.zip`) so the version parses unambiguously next to the hyphenated host triple and matches `rincoind -version` / automake's `PACKAGE_VERSION`. Both come from `_CLIENT_VERSION_RC` in `configure.ac`; override with `VERSION=...` / `TAG=...`.
Parallelism is internal via `JOBS` (default `nproc`); do **not** pass `-j` to this Makefile — `.NOTPARALLEL` keeps the three targets from clobbering the shared source tree.

If a target hits `R_X86_64_PC32 relocation`, add PIC for that run:

```bash
EXTRA_CONFIG=--with-pic make linux
```

(`linux` already builds with `--with-pic` by default, matching the native build in Part I. Release artifacts are built `--disable-tests`, so no `test_rincoin` / `test_rincoin-qt` ship — matching the hand-picked binary set in §8-3. To re-add the cross test binary for running under Wine / qemu-user during §10-6 verification, pass `EXTRA_CONFIG=--enable-tests`.)

> **`make linux` ≠ the native verified build.** This produces the *depends*-built, statically linked Linux binary — more portable for distribution, but still experimental. Keep the native Part I build as the blessed x86_64-linux release until depends-linux passes §10-6.

## Source tarball (`make dist`)

Bitcoin/Litecoin releases ship the source next to the binaries, covered by the same signed manifest. `make dist` produces it from the **signed tag** via `git archive`:

```bash
make dist                    # -> ../../release-artifacts/rincoin-<VERSION>.tar.gz
make dist DIST_REF=HEAD      # dry-run before the tag exists
```

Like modern Bitcoin Core source tarballs, it is a snapshot of the tag and does **not** contain a generated `./configure` — builders run `./autogen.sh` first, exactly as with a git checkout. The output is deterministic for a given tag (`git archive` pins entry mtimes to the commit; `gzip -n` drops the stream timestamp), and the name matches `sign.sh`'s glob, so the next `make sign` includes it automatically.

## Sign (Linux build host)

Signing covers **all** artifacts together in one manifest (the Bitcoin model — one `SHA256SUMS.asc` per release, not one per binary), including the source tarball. The `.asc` is a **detached**, armored signature over `SHA256SUMS`; publish both files. Sign after the targets you intend to ship are built:

```bash
make sign           # -> ../../release-artifacts/SHA256SUMS(.asc)
# or, the full Linux-side flow in one command:
make release        # preflight (HEAD==tag, clean tree) + wipe + dist + all-release + sign
```

Override the key with `make sign KEY=<fingerprint>`. Default is the Core maintainer key from §9-3: `ED20 B635 4EE4 526D 01F8 3B53 8B6E 3BF4 5C71 4ECA`.

> **This is the default release path.** The release signing key lives in the Linux build host's keyring, so the output of `make sign` here — `SHA256SUMS` + `SHA256SUMS.asc` — is exactly what gets published.
> The next two sections (transfer + re-sign on Windows) are an **optional alternative** for a key-custody model where the release key lives on a Windows machine instead (e.g. on a hardware token plugged in there); skip them if you sign on Linux. If the key is on **both** hosts, whichever host produces the published `.asc` is the authoritative seal — both verify under the same key.

## Optional: transfer to Windows

> Skip this section and the next if you sign on the Linux build host (the default). They apply only when the release key lives on a Windows machine.

Copy the **archives** (and optionally the manifest) to the Windows signing machine in **binary mode** — do not let any tool rewrite line endings on the `.tar.gz` /
`.zip`:

```bash
scp release-artifacts/rincoin-*.tar.gz \
    release-artifacts/rincoin-*.zip \
    user@windows:/c/rincoin/release-artifacts/
```

A VirtualBox shared folder or `rsync` works too. The only requirement is that the archive bytes are identical on both sides — their SHA256 is the source of truth.

## Optional: re-sign on Windows

If the release key lives on the Windows machine, run the **same** `sign.sh` under **Git Bash** there. It re-hashes the artifacts that actually landed on that machine and signs the manifest with the release key (detached, armored) — in this custody model, the Windows-produced `.asc` is the one you publish:

```bash
# Git Bash on Windows. Gpg4win provides gpg; the release key lives in this
# machine's GnuPG keyring (or on a hardware token plugged in here).
bash contrib/release/sign.sh /c/rincoin/release-artifacts \
    ED20B6354EE4526D01F83B538B6E3BF45C714ECA
```

**Why re-hash + re-sign instead of copying the `.asc`:** in a binary-safe transfer the archives do not change, but the *text* manifest (and its detached signature) is fragile to line-ending conversion. Regenerating `SHA256SUMS` from the real files on the machine that holds the release key removes every transit ambiguity and lets the final signature come from a token on that machine.

### PowerShell alternative (mind the encoding)

If you sign from PowerShell instead of Git Bash, do **not** use `>` — it writes UTF-16 and will corrupt the manifest. Force ASCII:

```powershell
cd C:\rincoin\release-artifacts
Get-ChildItem rincoin-*.tar.gz, rincoin-*.zip | Sort-Object Name | ForEach-Object {
    '{0}  {1}' -f (Get-FileHash $_ -Algorithm SHA256).Hash.ToLower(), $_.Name
} | Out-File -Encoding ascii SHA256SUMS
gpg --local-user <fpr> --detach-sign --armor --output SHA256SUMS.asc SHA256SUMS
gpg --verify SHA256SUMS.asc
```

GPG's `sha256sum`-style line format is `<hash><two spaces><filename>` — the two spaces matter for `sha256sum -c` interoperability.

## Verify before publishing

```bash
make verify         # lists artifacts + the §10-6 reminder
```

Then walk `release-process.md` §10-6 per target: `rincoind -version` and `getblockchaininfo` (wine / qemu-user / real hardware), and confirm `depends/<host>/lib/libdb_cxx-4.8.a` exists for each host. Only then publish.

End-user verification stays as documented in §9-5:

```bash
gpg --verify SHA256SUMS.asc            # one argument — gpg auto-verifies the
                                       # companion SHA256SUMS (detached sig)
sha256sum -c SHA256SUMS --ignore-missing
```

## .gitignore

Add the staging/output dirs:

```
/release/
/release-artifacts/
```

## Reproducibility

Plain `depends` gives a controlled toolchain, not bit-for-bit determinism (timestamps, paths, parallelism vary). For reproducible builds, **Guix** (`contrib/guix/`) is the upstream path — but that tree is still the upstream Bitcoin one and needs adapting for Rincoin's RinHash/argon2 inputs, planned for v1.1.1. This wrapper is the pragmatic route to multi-platform binaries now.
