#!/usr/bin/env python3
"""Restore historical evidence commit objects after Issue #164; never move refs."""
import base64
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]

def git(*args, data=None):
    return subprocess.check_output(["git", "-C", str(ROOT), *args], input=data)

def main():
    manifest = json.loads((ROOT / "docs/maintenance/ai-coauthor-2026-10-12.json").read_text())
    reverse = {r["new"]: r["old"] for r in manifest["mapping"]}
    for row in manifest["mapping"]:
        raw = git("cat-file", "commit", row["new"])
        headers, message = raw.split(b"\n\n", 1)
        lines = message.splitlines(keepends=True)
        for position, encoded in row["removed"]:
            lines.insert(position, base64.b64decode(encoded, validate=True))
        restored_headers = []
        for line in headers.split(b"\n"):
            if line.startswith(b"parent "):
                line = b"parent " + reverse[line[7:].decode()].encode()
            restored_headers.append(line)
        restored = b"\n".join(restored_headers) + b"\n\n" + b"".join(lines)
        computed = git("hash-object", "-t", "commit", "--stdin", data=restored).decode().strip()
        if computed != row["old"]:
            raise RuntimeError(f"Recovery mismatch: {row['old']} != {computed}; no object written")
        git("hash-object", "-t", "commit", "-w", "--stdin", data=restored)
    print(f"Verified/restored {len(manifest['mapping'])} historical commit objects; refs unchanged")

if __name__ == "__main__":
    main()
