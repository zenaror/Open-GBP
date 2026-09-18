#!/usr/bin/env python3
"""swiss_export.py - export the built DOLs into a numbered, short-named tree.

    tools/swiss_export.py [--root DIR] [--out DIR] [--check]

WHAT THIS IS FOR. Swiss lists directories. The build tree is named for the
source, and `gbp-init-irq-program-probe` next to `gbp-init-irq-deliver-probe` in
a truncated list is how a physical run gets spent on the wrong DOL. This copies
each launchable DOL into `build/swiss/NN-short/boot.dol`, where the numbers come
from the versioned manifest `tools/swiss-layout.tsv` and never move.

WHAT THIS IS NOT. It is not a build step and it is not an identity. The copy is
byte for byte and the hash is verified after it; the build id, the commit and
every byte of the image stay exactly what the POC produced. If a physical run is
ever attributed to something, it is attributed to `build/poc/<out_dir>/<dol>`,
which is the authority. `build/swiss` is presentation.

`--check` exports nothing and only validates the manifest, which is what the
host test uses.
"""
import argparse
import hashlib
import os
import shutil
import sys

MANIFEST = os.path.join("tools", "swiss-layout.tsv")
FIELDS = ("number", "short_name", "source_poc", "dol", "out_dir", "make_target", "enabled")
# NN- plus the short name. Swiss truncates, so this is a hard limit, not advice.
MAX_DIR_NAME = 14


def load(path):
    """Parses the manifest and enforces every rule a number-as-interface needs."""
    rows, seen_num, seen_name = [], {}, {}
    with open(path) as f:
        for lineno, raw in enumerate(f, 1):
            line = raw.rstrip("\n")
            if not line.strip() or line.lstrip().startswith("#"):
                continue
            parts = line.split("\t")
            if len(parts) != len(FIELDS):
                raise ValueError("%s:%d: %d fields, expected %d" % (path, lineno, len(parts), len(FIELDS)))
            row = dict(zip(FIELDS, parts))
            n = row["number"]
            if len(n) != 2 or not n.isdigit():
                raise ValueError("%s:%d: number %r must be exactly two digits" % (path, lineno, n))
            if n in seen_num:
                raise ValueError("%s:%d: number %s already used on line %d" % (path, lineno, n, seen_num[n]))
            seen_num[n] = lineno
            if row["short_name"] in seen_name:
                raise ValueError("%s:%d: short name %r already used on line %d"
                                 % (path, lineno, row["short_name"], seen_name[row["short_name"]]))
            seen_name[row["short_name"]] = lineno
            row["dir"] = "%s-%s" % (n, row["short_name"])
            if len(row["dir"]) > MAX_DIR_NAME:
                raise ValueError("%s:%d: %r is %d characters; Swiss truncates, the limit is %d"
                                 % (path, lineno, row["dir"], len(row["dir"]), MAX_DIR_NAME))
            if row["enabled"] not in ("0", "1"):
                raise ValueError("%s:%d: enabled must be 0 or 1" % (path, lineno))
            rows.append(row)
    if not rows:
        raise ValueError("%s: no entries" % path)
    return rows


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def build_info(root, row):
    """Build id and commit as the POC itself recorded them, or '-' when absent."""
    p = os.path.join(root, "build", "poc", row["out_dir"], "build-info.txt")
    out = {"build_id": "-", "commit": "-", "test_id": "-"}
    if os.path.exists(p):
        for line in open(p):
            k, _, v = line.partition("=")
            if k.strip() in ("build_id", "commit"):
                out[k.strip()] = v.strip()
    src = os.path.join(root, "poc", row["source_poc"], "source", "main.c")
    if os.path.exists(src):
        for line in open(src):
            if line.startswith("#define TEST_ID"):
                out["test_id"] = line.split('"')[1]
                break
    return out


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    ap.add_argument("--out", default=None, help="default: <root>/build/swiss")
    ap.add_argument("--manifest", default=None)
    ap.add_argument("--check", action="store_true", help="validate the manifest and exit")
    args = ap.parse_args(argv)

    root = os.path.abspath(args.root)
    manifest = args.manifest or os.path.join(root, MANIFEST)
    rows = load(manifest)
    if args.check:
        print("swiss_export: manifest OK, %d entries, %d enabled"
              % (len(rows), sum(1 for r in rows if r["enabled"] == "1")))
        return 0

    out = os.path.abspath(args.out or os.path.join(root, "build", "swiss"))
    # ONLY this directory is removed, and only when it is the one we own.
    if os.path.exists(out):
        if os.path.basename(out) != "swiss":
            print("refusing to clear %s: not a swiss export directory" % out, file=sys.stderr)
            return 2
        shutil.rmtree(out)
    os.makedirs(out)

    index, missing = [], []
    for row in rows:
        if row["enabled"] != "1":
            continue
        src = os.path.join(root, "build", "poc", row["out_dir"], row["dol"])
        if not os.path.exists(src):
            missing.append((row["dir"], os.path.relpath(src, root), row["make_target"]))
            continue
        dst_dir = os.path.join(out, row["dir"])
        os.makedirs(dst_dir)
        dst = os.path.join(dst_dir, "boot.dol")
        shutil.copyfile(src, dst)
        a, b = sha256(src), sha256(dst)
        if a != b:                      # the copy is the whole job; verify it did nothing else
            print("HASH MISMATCH after copying %s" % src, file=sys.stderr)
            return 3
        bi = build_info(root, row)
        index.append({"dir": row["dir"], "test_id": bi["test_id"], "build_id": bi["build_id"],
                      "commit": bi["commit"], "source": os.path.relpath(src, root),
                      "size": os.path.getsize(dst), "sha256": a})

    lines = [
        "Open-GBP - Swiss launch layout",
        "",
        "Each directory holds one boot.dol, copied byte for byte from build/poc.",
        "The AUTHORITY is the source path below, never this copy. Numbers are stable:",
        "a new build takes the next free number and nothing is renumbered.",
        "",
        "%-12s | %-18s | %-22s | %-9s | %10s | %-64s | %s"
        % ("DIR", "TEST ID", "BUILD ID", "COMMIT", "SIZE", "SHA-256", "SOURCE"),
    ]
    for e in index:
        lines.append("%-12s | %-18s | %-22s | %-9s | %10d | %s | %s"
                     % (e["dir"], e["test_id"], e["build_id"], e["commit"], e["size"], e["sha256"], e["source"]))
    if missing:
        lines += ["", "NOT EXPORTED (not built):"]
        for d, p, tgt in missing:
            lines.append("  %-12s %s   (run: make %s)" % (d, p, tgt))
    text = "\n".join(lines) + "\n"
    with open(os.path.join(out, "INDEX.txt"), "w") as f:
        f.write(text)
    print(text, end="")
    print("swiss_export: %d exported, %d missing -> %s" % (len(index), len(missing), os.path.relpath(out, root)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
