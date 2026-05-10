#!/usr/bin/env python3
"""
Pacekeeper License Key Generator

Setup (once):
  pip install cryptography
  python scripts/keygen.py --generate
    → prints public key bytes for license.rs
    → saves private key to .pacekeeper-private.key  (never commit this)

Issue a key:
  python scripts/keygen.py --issue user@example.com
"""
import sys
import os
import json
import base64
import argparse


def b64e(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def b64d(s: str) -> bytes:
    pad = 4 - len(s) % 4
    if pad != 4:
        s += "=" * pad
    return base64.urlsafe_b64decode(s)


KEY_FILE = ".pacekeeper-private.key"


def cmd_generate():
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from cryptography.hazmat.primitives.serialization import (
        Encoding, PublicFormat, PrivateFormat, NoEncryption,
    )

    priv = Ed25519PrivateKey.generate()
    pub_bytes  = priv.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    priv_bytes = priv.private_bytes(Encoding.Raw, PrivateFormat.Raw, NoEncryption())

    with open(KEY_FILE, "wb") as f:
        f.write(priv_bytes)
    os.chmod(KEY_FILE, 0o600)

    rust_array = "[" + ", ".join(f"0x{b:02x}" for b in pub_bytes) + "]"

    print("Key pair generated.\n")
    print(f"Private key saved to: {KEY_FILE}  ← add to .gitignore, back up securely\n")
    print("Paste this into desktop-app/src-tauri/src/license.rs as PUBLIC_KEY:")
    print(f"  const PUBLIC_KEY: [u8; 32] = {rust_array};")


def cmd_issue(email: str, expires: str | None):
    if not os.path.exists(KEY_FILE):
        sys.exit(f"Error: {KEY_FILE} not found. Run --generate first.")

    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from datetime import date, timedelta

    exp = expires or (date.today() + timedelta(days=365)).isoformat()

    with open(KEY_FILE, "rb") as f:
        priv_bytes = f.read()

    priv = Ed25519PrivateKey.from_private_bytes(priv_bytes)
    payload = json.dumps({"email": email, "expires": exp}, separators=(",", ":")).encode()
    sig = priv.sign(payload)

    license_key = b64e(payload) + "." + b64e(sig)
    print(f"License key for {email} (expires {exp}):\n{license_key}")


def main():
    parser = argparse.ArgumentParser(description="Pacekeeper license key tool")
    group  = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--generate", action="store_true", help="Generate a new key pair (run once)")
    group.add_argument("--issue", metavar="EMAIL",        help="Issue a license key for an email address")
    parser.add_argument("--expires", metavar="YYYY-MM-DD", help="Expiry date (default: 1 year from today)")
    args = parser.parse_args()

    if args.generate:
        cmd_generate()
    else:
        cmd_issue(args.issue, args.expires)


if __name__ == "__main__":
    main()
