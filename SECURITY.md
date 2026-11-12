# Security Policy

## Official Rincoin Core Team

The following individuals are the current Core Role holders of the Rincoin protocol. **Only individuals listed here are authorized to represent the Rincoin Core Team.**

| Name | Role | Fingerprint |
|------|------|-------------|
| @ysmreg | Founder / Core Technical Lead | (to be added) |
| @Aevust | Core Authority Lead / Core Research Lead / Principal Architect | ED20 B635 4EE4 526D 01F8 3B53 8B6E 3BF4 5C71 4ECA |

Individuals not listed above are **not** members of the Rincoin Core Team, regardless of any claims made elsewhere.

---

## Reporting a Vulnerability

To report security issues, send an email to **info@rincoin.org** (not for general support).

Please do **not** open a public GitHub issue for security-sensitive reports.

Sensitive information may be encrypted using the key identified above.

### How to obtain our public key

Key material is not bundled in this repository. Import it from a live channel and check the fingerprint.

From the public keyserver:

```
gpg --keyserver hkps://keys.openpgp.org --recv-keys ED20B6354EE4526D01F83B538B6E3BF45C714ECA
```

Or, when rincoin.org is reachable, via WKD:

```
gpg --auto-key-locate clear,wkd --locate-keys info@rincoin.org
```

The key is also viewable at
- [keys.openpgp.org/vks/v1/by-fingerprint/ED20B6354EE4526D01F83B538B6E3BF45C714ECA](https://keys.openpgp.org/vks/v1/by-fingerprint/ED20B6354EE4526D01F83B538B6E3BF45C714ECA)

After import, verify the fingerprint matches the table above:

```
gpg --fingerprint ED20B6354EE4526D01F83B538B6E3BF45C714ECA
```

Signatures made since 2026-06-26 come from a signing subkey (0ED9 9C46 B219 2E37 5381 EF4A C5BE F8A9 FA06 C16F); gpg resolves this automatically once the primary key is imported.

The two channels may serve byte-different copies of the same key (the keyserver retains superseded self-signatures); verify the fingerprint, not a file digest. The same fingerprint is also pinned in the signed provenance certificate and in llms.txt on rincoin.org.

---

## Verifying Official Communications

Official Rincoin communications are characterized by:

- Signatures from keys listed in this document
- Publication via the official Discord server (owner: @Aevust)
- Publication on **rincoin.org** and **rincoin.com** (operated by @Aevust)
- For protocol-level changes: approval by the Founder (@ysmreg) and Core Strategic Authority as defined in GOVERNANCE.md §Version Authority

For full governance details, canonical sources, and independent DNS verification, see the [RIPs Security Policy](https://github.com/Aevust/rincoin-rips/blob/main/SECURITY.md).
