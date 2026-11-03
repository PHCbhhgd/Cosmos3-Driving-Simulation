"""Stream a release archive to verify file inventories and public JSON metadata."""

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import tarfile

from audit_public_repo import LOCAL_PATH, SECRET
from build_release import digest


def audit(path):
    hashes, manifests, errors = {}, {}, []
    json_count = 0
    with tarfile.open(path, "r|gz") as archive:
        names = set()
        for member in archive:
            name = PurePosixPath(member.name)
            if name.is_absolute() or ".." in name.parts or member.name in names:
                errors.append(f"Unsafe or duplicate archive member: {member.name}")
            names.add(member.name)
            if member.isdir():
                continue
            if not member.isfile():
                errors.append(f"Non-regular archive member: {member.name}")
                continue
            handle = archive.extractfile(member)
            if name.name == "SHA256SUMS" or name.suffix == ".json":
                data = handle.read()
                checksum = hashlib.sha256(data).hexdigest()
                text = data.decode("utf-8")
                if name.name == "SHA256SUMS":
                    manifests[name] = text
                else:
                    json.loads(text)
                    json_count += 1
                    if LOCAL_PATH.search(text) or SECRET.search(text):
                        errors.append(f"Private path or credential-like content: {name}")
            else:
                checksum = hashlib.file_digest(handle, "sha256").hexdigest()
            hashes[name] = checksum
    checked = 0
    covered = set()
    for manifest, text in manifests.items():
        declared = set()
        for line in text.splitlines():
            expected, relative = line.split("  ", 1)
            relative_path = PurePosixPath(relative)
            name = manifest.parent / relative_path
            if relative_path.is_absolute() or ".." in relative_path.parts or name in declared:
                errors.append(f"Unsafe or duplicate checksum entry: {manifest}: {relative}")
            declared.add(name)
            if hashes.get(name) != expected:
                errors.append(f"Checksum mismatch: {name}")
            covered.add(name)
            checked += 1
        actual = {
            name for name in hashes if name.is_relative_to(manifest.parent) and name != manifest
        }
        if declared != actual:
            errors.append(f"Incomplete checksum inventory: {manifest}")
    # Business archives have a root README outside the individually verified bundles.
    unchecked = {name for name in hashes if name not in covered and name not in manifests}
    if not manifests:
        errors.append("No checksum manifest")
    if any(len(name.parts) != 2 or name.name != "README.md" for name in unchecked):
        errors.append("Unchecksummed files outside bundle inventories")
    return dict(
        archive=path.name,
        bytes=path.stat().st_size,
        sha256=digest(path),
        metadata_json_checked=json_count,
        checksum_entries_checked=checked,
        status="passed" if not errors else "failed",
        errors=errors,
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = audit(args.archive)
    text = json.dumps(report, indent=2) + "\n"
    if args.output:
        args.output.write_text(text)
    print(text, end="")
    return int(bool(report["errors"]))


if __name__ == "__main__":
    raise SystemExit(main())
