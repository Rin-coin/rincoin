#!/usr/bin/env bash
# contrib/release/sign.sh
#
# Generate SHA256SUMS over the Rincoin release artifacts in a directory and
# GPG-sign it with a DETACHED, armored signature (SHA256SUMS.asc). Runs on BOTH:
#   - the Linux build host (`make sign` calls this), and
#   - a Windows signing machine under Git Bash (the "re-sign" step).
#
# It always RE-HASHES whatever artifacts are actually present in the target dir,
# so on Windows it re-hashes the transferred binaries and the signature is
# guaranteed to match the distributed bytes — no transit / line-ending ambiguity.
#
# Usage:
#   bash sign.sh <artifacts-dir> [gpg-key-fingerprint]
#
# Examples:
#   bash sign.sh ./release-artifacts
#   bash sign.sh /c/rincoin/release-artifacts ED20B6354EE4526D01F83B538B6E3BF45C714ECA

set -euo pipefail

DIR="${1:-.}"
KEY="${2:-ED20B6354EE4526D01F83B538B6E3BF45C714ECA}"

# Output names (no .txt suffix; matches Bitcoin Core / Litecoin and rincoin-sim).
MANIFEST=SHA256SUMS
SIG=SHA256SUMS.asc

cd "$DIR"

# Collect artifacts (bash pathname expansion is already sorted).
shopt -s nullglob
FILES=( rincoin-*.tar.gz rincoin-*.zip )
if (( ${#FILES[@]} == 0 )); then
    echo "error: no rincoin-*.{tar.gz,zip} artifacts found in $(pwd)" >&2
    exit 1
fi

# Need a sha256 tool. coreutils sha256sum on Linux and in Git Bash; fall back to
# `shasum -a 256` if only that is present.
if command -v sha256sum >/dev/null 2>&1; then
    HASH() { sha256sum "$@"; }
elif command -v shasum >/dev/null 2>&1; then
    HASH() { shasum -a 256 "$@"; }
else
    echo "error: neither sha256sum nor shasum found on PATH" >&2
    exit 1
fi

echo "==> hashing ${#FILES[@]} artifact(s) in $(pwd)"
# Regenerate the manifest from the real bytes in this directory (LF newlines).
HASH "${FILES[@]}" > "$MANIFEST"

echo "==> $MANIFEST"
cat "$MANIFEST"
echo

echo "==> detached-signing $MANIFEST with key $KEY"
rm -f "$SIG"
gpg --local-user "$KEY" --detach-sign --armor --output "$SIG" "$MANIFEST"

echo "==> verifying $SIG"
gpg --verify "$SIG" "$MANIFEST"

echo
echo "==> OK"
echo "    $(pwd)/$MANIFEST       <- publish (the file 'sha256sum -c' checks against)"
echo "    $(pwd)/$SIG   <- publish (detached signature over the file above)"
