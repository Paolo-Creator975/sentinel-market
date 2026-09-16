#!/usr/bin/env python3
"""Read-only integrity verifier for Sentinel's frozen 90-day demo."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path


AUDIT_DIR = Path(__file__).resolve().parent
DEFAULT_ROOT = AUDIT_DIR.parent


def git_blob_sha(data: bytes) -> str:
    header = f"blob {len(data)}\0".encode("ascii")
    return hashlib.sha1(header + data).hexdigest()


def load_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def verify(root: Path = DEFAULT_ROOT, manifest_path: Path | None = None) -> list[str]:
    manifest_path = manifest_path or AUDIT_DIR / "frozen_demo_manifest.json"
    manifest = load_json(manifest_path)
    errors: list[str] = []

    for relative, expected in manifest["protected_git_blobs"].items():
        path = root / relative
        if not path.is_file():
            errors.append(f"missing protected file: {relative}")
            continue
        actual = git_blob_sha(path.read_bytes())
        if actual != expected:
            errors.append(
                f"protected file changed: {relative} expected={expected} actual={actual}"
            )

    config_path = root / "cloud/config/crypto_24h_demo_v1.json"
    if config_path.is_file():
        config = load_json(config_path)
        for key, expected in manifest["required_config_assertions"].items():
            actual = config.get(key)
            if actual != expected:
                errors.append(
                    f"frozen config assertion failed: {key} expected={expected!r} actual={actual!r}"
                )

    commandments = load_json(AUDIT_DIR / "ten_commandments.json")
    if commandments.get("decision_authority") is not False:
        errors.append("audit must have no decision authority")
    if commandments.get("may_modify_frozen_demo") is not False:
        errors.append("audit must not modify the frozen demo")
    if [rule.get("id") for rule in commandments.get("rules", [])] != list(range(1, 11)):
        errors.append("the methodological audit must contain exactly commandments 1 through 10")

    return errors


def main() -> int:
    errors = verify()
    if errors:
        print("SENTINEL_NEUTRAL_AUDIT FAIL")
        for error in errors:
            print(f"- {error}")
        return 1
    print("SENTINEL_NEUTRAL_AUDIT OK")
    print("Protected demo files and paper-only assertions are unchanged.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
