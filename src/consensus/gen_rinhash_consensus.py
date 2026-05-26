#!/usr/bin/env python3
# Copyright (c) 2026 The Rincoin developers
# Distributed under the MIT software license, see the accompanying
# file COPYING or http://www.opensource.org/licenses/mit-license.php.
"""Generate src/consensus/rinhash_consensus_data.h from rinhash_consensus.json.

The generated header is consumed by chainparams.cpp to populate the per-network
RinHash consensus table. JSON is the human-edited source of truth; the
generated header is committed alongside the JSON so the project can be built
without Python at hand. CI re-runs this script with --check.

Each network is emitted as a (init, activations[]) pair where every overlay-able
field is encoded as an "(is_set, value)" tuple. The C++ side consumes them via
GeneratedOverlay records that also carry the same is_set markers, and performs
the height-based overlay at lookup time.
"""
import argparse
import json
import os
import sys
from pathlib import Path

try:
    import jsonschema  # type: ignore
    HAVE_JSONSCHEMA = True
except ImportError:
    HAVE_JSONSCHEMA = False


def strip_comments(node):
    if isinstance(node, dict):
        return {k: strip_comments(v) for k, v in node.items()
                if not (isinstance(k, str) and k.startswith("_comment"))}
    if isinstance(node, list):
        return [strip_comments(v) for v in node]
    return node


def cpp_string_literal(s: str) -> str:
    out = ['"']
    for ch in s:
        b = ord(ch)
        if ch == "\\":
            out.append("\\\\")
        elif ch == '"':
            out.append('\\"')
        elif 0x20 <= b < 0x7f:
            out.append(ch)
        else:
            out.append("\\x{:02x}".format(b))
    out.append('"')
    return "".join(out)


# Field name -> (cpp_type, default_when_unset, encoder)
def encode_uint(v):  return "{}u".format(v)
def encode_int(v):   return "{}".format(v)
def encode_str(v):   return "std::string({})".format(cpp_string_literal(v))


SET_FIELDS = [
    # (json_key,                       cpp_setter)
    ("t_cost",                          ("t_cost",                          encode_uint)),
    ("m_cost",                          ("m_cost",                          encode_uint)),
    ("lanes",                           ("lanes",                           encode_uint)),
    ("salt",                            ("salt",                            encode_str)),
    ("min_peer_protocol_version",       ("min_peer_protocol_version",       encode_int)),
]


def emit_overlay_initializer(node: dict, indent: str) -> str:
    """Emit a brace-initializer for a RinHashOverlay. The struct on the C++
    side uses optional<T>-style flags so unset fields cleanly inherit."""
    pairs = []
    for jk, (member, encoder) in SET_FIELDS:
        if jk in node:
            pairs.append("/* has_{m} */ true, /* {m} */ {v}"
                         .format(m=member, v=encoder(node[jk])))
        else:
            pairs.append("/* has_{m} */ false, /* {m} */ {{}}".format(m=member))
    body = (",\n" + indent + "    ").join(pairs)
    return "{\n" + indent + "    " + body + "\n" + indent + "}"


HEADER = """\
// Copyright (c) 2026 The Rincoin developers
// Distributed under the MIT software license, see the accompanying
// file COPYING or http://www.opensource.org/licenses/mit-license.php.
//
// AUTO-GENERATED FILE. DO NOT EDIT.
//
// Source:    src/consensus/rinhash_consensus.json
// Generator: src/consensus/gen_rinhash_consensus.py
//
// To update: edit the JSON file, then run the generator and commit both
// files in a single commit. CI verifies that this header matches the JSON
// on every pull request.

#ifndef BITCOIN_CONSENSUS_RINHASH_CONSENSUS_DATA_H
#define BITCOIN_CONSENSUS_RINHASH_CONSENSUS_DATA_H

#include <consensus/params.h>

#include <cstdint>
#include <string>
#include <vector>

namespace Consensus {
namespace RinHashGen {

// Single overlay record. Each field is an (is_set, value) pair; an unset
// field inherits from the previous overlay (or from the network's init).
// `init` is encoded as the same overlay shape with activation_height = 0.
struct GeneratedOverlay {
    int activation_height;

    bool        has_t_cost;                        uint32_t                  t_cost;
    bool        has_m_cost;                        uint32_t                  m_cost;
    bool        has_lanes;                         uint32_t                  lanes;
    bool        has_salt;                          std::string               salt;
    bool        has_min_peer_protocol_version;     int                       min_peer_protocol_version;
};

struct GeneratedNetwork {
    GeneratedOverlay              init;
    std::vector<GeneratedOverlay> activations;
};

__NETWORK_BLOCKS__

} // namespace RinHashGen
} // namespace Consensus

#endif // BITCOIN_CONSENSUS_RINHASH_CONSENSUS_DATA_H
"""


def emit_network_block(json_name: str, cpp_name: str, net: dict) -> str:
    init_obj = dict(net["init"])
    activations = net["activations"]

    # Validate strict ascending activation heights, all > 0.
    last_h = 0
    for e in activations:
        if e["activation_height"] <= last_h:
            raise ValueError("{}: activation_height not strictly ascending: {} after {}"
                             .format(json_name, e["activation_height"], last_h))
        last_h = e["activation_height"]

    out = []
    out.append("inline const GeneratedNetwork& Get{}Data() {{".format(cpp_name))
    out.append("    static const GeneratedNetwork data{")
    out.append("        // init")
    out.append("        GeneratedOverlay{")
    out.append("            /* activation_height */ 0,")
    for jk, (member, encoder) in SET_FIELDS:
        if jk in init_obj:
            out.append("            /* has_{m} */ true, /* {m} */ {v},"
                       .format(m=member, v=encoder(init_obj[jk])))
        else:
            out.append("            /* has_{m} */ false, /* {m} */ {{}},".format(m=member))
    out.append("        },")
    out.append("        // activations")
    out.append("        std::vector<GeneratedOverlay>{")
    for e in activations:
        out.append("            GeneratedOverlay{")
        out.append("                /* activation_height */ {},".format(e["activation_height"]))
        for jk, (member, encoder) in SET_FIELDS:
            if jk in e:
                out.append("                /* has_{m} */ true, /* {m} */ {v},"
                           .format(m=member, v=encoder(e[jk])))
            else:
                out.append("                /* has_{m} */ false, /* {m} */ {{}},".format(m=member))
        out.append("            },")
    out.append("        },")
    out.append("    };")
    out.append("    return data;")
    out.append("}")
    return "\n".join(out)


NETWORK_NAME_MAP = [
    # (json_name, cpp_name)
    ("mainnet", "Mainnet"),
    ("testnet", "Testnet"),
    ("regtest", "Regtest"),
    ("preview", "Preview"),
]


def main():
    ap = argparse.ArgumentParser()
    here = Path(__file__).resolve().parent
    ap.add_argument("--json",   default=str(here / "rinhash_consensus.json"))
    ap.add_argument("--schema", default=str(here / "rinhash_consensus.schema.json"))
    ap.add_argument("--out",    default=str(here / "rinhash_consensus_data.h"))
    ap.add_argument("--check",  action="store_true",
                    help="Do not write; fail with non-zero exit if regeneration would change --out.")
    args = ap.parse_args()

    with open(args.json, "r", encoding="utf-8") as f:
        raw = json.load(f)

    if HAVE_JSONSCHEMA and os.path.isfile(args.schema):
        with open(args.schema, "r", encoding="utf-8") as f:
            schema = json.load(f)
        try:
            jsonschema.validate(instance=raw, schema=schema)
        except jsonschema.ValidationError as e:
            print("JSON schema validation failed: {}".format(e), file=sys.stderr)
            return 2

    data = strip_comments(raw)
    networks = data["networks"]
    blocks = []
    for json_name, cpp_name in NETWORK_NAME_MAP:
        blocks.append("// === Network: {} ===".format(json_name))
        blocks.append(emit_network_block(json_name, cpp_name, networks[json_name]))
    network_blocks = "\n\n".join(blocks)
    output = HEADER.replace("__NETWORK_BLOCKS__", network_blocks)

    if args.check:
        try:
            with open(args.out, "r", encoding="utf-8") as f:
                existing = f.read()
        except FileNotFoundError:
            print("ERROR: generated header missing: {}".format(args.out), file=sys.stderr)
            return 3
        if existing != output:
            print("ERROR: {} is out of date with {}.".format(args.out, args.json), file=sys.stderr)
            print("Re-run: python3 {}".format(__file__), file=sys.stderr)
            return 1
        print("OK: {} matches {}".format(args.out, args.json))
        return 0

    with open(args.out, "w", encoding="utf-8") as f:
        f.write(output)
    print("Wrote {}".format(args.out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
