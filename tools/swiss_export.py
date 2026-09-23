#!/usr/bin/env python3
"""swiss_export.py - export the built DOLs into a numbered, short-named tree.

    tools/swiss_export.py [--root DIR] [--out DIR] [--only SLOT ...] [--index-only] [--check]

WHAT THIS IS FOR. Swiss lists directories. The build tree is named for the
source, and `gbp-init-irq-program-probe` next to `gbp-init-irq-deliver-probe` in
a truncated list is how a physical run gets spent on the wrong DOL. This copies
each launchable DOL into `build/swiss/NN-short/boot.dol`, where the numbers come
from the versioned manifest `tools/swiss-layout.tsv` and never move.

WHAT THIS IS NOT. It is not a build step and it is not an identity. The copy is
byte for byte and the hash is verified after it.

WHERE THE AUTHORITY IS -- corrected by GitHub Issue #88 (2026-09-23). This
docstring and INDEX.txt used to say that `build/poc/<out_dir>/<dol>` was the
authority. It never was: `build/poc` is a BUILD OUTPUT and holds whatever the tree
last built, and once `make build` works (Issue #87) it moves with HEAD. On
2026-09-23 eleven of fourteen staged slots (01 to 11) held rebuilds made at
7d7a6d8 under the build ids of images that had run at other commits. What a
physical run executed is identified by the SHA-256 and the commit the RECORDS
carry (EVIDENCE.md, HARDWARE_TESTS.md, HANDOFF.md). A staged slot is those bytes
only when its manifest row is FROZEN, because only then does this tool verify the
bytes against the pinned hash. Every other staged row is a copy of whatever
`build/poc` held at export time: its build id and commit name that build, and it
carries no physical status.

`--check` exports nothing and only validates the manifest, which is what the
host test uses.

`--index-only` (Issue #88) copies nothing and removes nothing. It rewrites
INDEX.txt from the slots already staged, carrying each row over by RULE 3, so a
correction to the index's own text reaches the index without restaging anything.

FROZEN SLOTS (GitHub Issue #44, after the near-miss of Hardware Issue #43).
A slot that holds an image a physical run executed, or one staged for a run
that has not happened yet, is FROZEN: the manifest's `frozen_sha256` column
carries its pinned hash. Three rules follow, and all three are refusals with a
non-zero exit rather than warnings, because the thing they protect exists in
two places and one of them is a card in a drawer:

  1. A frozen slot is never written with bytes whose hash is not its pinned
     one. The export REFUSES before copying anything.
  2. A frozen slot's directory is never removed. In particular there is NO
     unconditional `rmtree` of the export tree while any frozen slot is staged
     in it: the tree is cleaned slot by slot, and only for slots being written.
  3. `INDEX.txt` NEVER silently re-describes a frozen slot. A row for a slot
     this run did not write is CARRIED OVER from the previous INDEX when the
     bytes on disk still hash to what that row recorded, and is otherwise
     written with `-` in the columns that came from `build/poc`. The index may
     not learn a new identity for a file it did not copy.

`--only <slot>` exports the named slots (repeatable; `12-stream` or `12`) and
touches no other slot's directory. It is how a single new slot is staged
without re-exporting a tree whose sources have moved on -- which is exactly the
state that made `make swiss` dangerous on 2026-09-21: `build/poc`'s stream
probe was a rebuild at another commit, and a full export would have replaced
the frozen `12-stream`, rewritten its INDEX row to agree, and left the
Operator's SD as the only copy of the image three physical runs executed.
"""
import argparse
import hashlib
import os
import re
import shutil
import sys

MANIFEST = os.path.join("tools", "swiss-layout.tsv")
FIELDS = ("number", "short_name", "source_poc", "dol", "out_dir", "make_target", "enabled", "frozen_sha256")
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
            fz = row["frozen_sha256"]
            if fz != "-" and not re.fullmatch(r"[0-9a-f]{64}", fz):
                raise ValueError("%s:%d: frozen_sha256 must be 64 lowercase hex digits or '-', not %r"
                                 % (path, lineno, fz))
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


def index_path(out):
    return os.path.join(out, "INDEX.txt")


def parse_index(out):
    """The previous INDEX's rows, by slot. Used to CARRY OVER a row for a slot this run does not write."""
    p = index_path(out)
    rows = {}
    if not os.path.exists(p):
        return rows
    for line in open(p):
        m = INDEX_ROW_RE.match(line)
        if m:
            rows[m.group(1)] = {"dir": m.group(1), "test_id": m.group(2), "build_id": m.group(3),
                                "commit": m.group(4), "size": int(m.group(5)), "sha256": m.group(6),
                                "source": m.group(8)}
    return rows


# One INDEX row. The STATUS column is Issue #88's; an INDEX written before it has none,
# and its rows must still be carried over, so the column is optional when READING.
# It is never carried over when WRITING: the status is recomputed every time, from the
# manifest's pins and the bytes on disk, because a status copied from an old file would be
# a record certifying itself (Issue #83, pattern H).
STATUS_PINNED = "PINNED-VERIFIED"
STATUS_COPY = "UNPINNED-COPY"
INDEX_ROW_RE = re.compile(r"^(\S+)\s+\|\s+(\S+)\s+\|\s+(\S+)\s+\|\s+(\S+)\s+\|\s+(\d+)\s+\|\s+([0-9a-f]{64})\s+\|"
                          r"\s+(?:(%s|%s)\s+\|\s+)?(.+?)\s*$" % (STATUS_PINNED, STATUS_COPY))


def row_status(frozen, entry):
    """PINNED-VERIFIED only when the slot is frozen AND its bytes are the pin; otherwise a copy."""
    pin = frozen.get(entry["dir"])
    return STATUS_PINNED if pin and pin == entry["sha256"] else STATUS_COPY


def staged_hash(out, slot):
    p = os.path.join(out, slot, "boot.dol")
    return sha256(p) if os.path.exists(p) else None


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    ap.add_argument("--out", default=None, help="default: <root>/build/swiss")
    ap.add_argument("--manifest", default=None)
    ap.add_argument("--check", action="store_true", help="validate the manifest and exit")
    ap.add_argument("--only", action="append", default=[], metavar="SLOT",
                    help="export only this slot (repeatable): '12-stream' or '12'. No other slot is touched.")
    ap.add_argument("--index-only", action="store_true",
                    help="copy and remove NOTHING; rewrite INDEX.txt from the staged slots (RULE 3's carry-over)")
    args = ap.parse_args(argv)

    root = os.path.abspath(args.root)
    manifest = args.manifest or os.path.join(root, MANIFEST)
    rows = load(manifest)
    frozen = {r["dir"]: r["frozen_sha256"] for r in rows if r["frozen_sha256"] != "-"}
    if args.check:
        print("swiss_export: manifest OK, %d entries, %d enabled, %d frozen"
              % (len(rows), sum(1 for r in rows if r["enabled"] == "1"), len(frozen)))
        return 0

    out = os.path.abspath(args.out or os.path.join(root, "build", "swiss"))
    if os.path.exists(out) and os.path.basename(out) != "swiss":
        print("refusing to touch %s: not a swiss export directory" % out, file=sys.stderr)
        return 2

    # which slots this run writes
    selected = [r for r in rows if r["enabled"] == "1"]
    if args.index_only:
        if args.only:
            print("--index-only writes no slot, so it takes no --only", file=sys.stderr)
            return 2
        if not os.path.isdir(out):
            print("--index-only: nothing is staged under %s" % out, file=sys.stderr)
            return 2
        selected = []
    if args.only:
        want = set(args.only) | {s.split("-")[0] for s in args.only}
        selected = [r for r in selected if r["dir"] in want or r["number"] in want]
        if not selected:
            print("no enabled slot matches --only %s" % ", ".join(args.only), file=sys.stderr)
            return 2

    # RULE 1, before anything is written or removed: a frozen slot may only be written with its pinned bytes
    for row in selected:
        pin = frozen.get(row["dir"])
        if not pin:
            continue
        src = os.path.join(root, "build", "poc", row["out_dir"], row["dol"])
        got = sha256(src) if os.path.exists(src) else None
        if got != pin:
            print("REFUSING: %s is FROZEN at %s and %s would write %s.\n"
                  "  The staged image is the one a physical run executed or is pre-registered for; the build tree\n"
                  "  has moved on. Nothing was written or removed. Use --only for the slots you mean, or correct\n"
                  "  the manifest if the freeze itself is wrong."
                  % (row["dir"], pin, os.path.relpath(src, root), got or "nothing (source missing)"), file=sys.stderr)
            return 4

    # RULE 2: never an unconditional rmtree while a frozen slot is staged; clean slot by slot instead
    staged_frozen = [d for d in frozen if os.path.isdir(os.path.join(out, d))]
    if os.path.exists(out) and not staged_frozen and not args.only and not args.index_only:
        shutil.rmtree(out)                      # a clean export of a tree holding nothing frozen
    os.makedirs(out, exist_ok=True)
    for row in selected:
        d = os.path.join(out, row["dir"])
        if os.path.isdir(d):
            shutil.rmtree(d)                    # a slot we are about to write; frozen ones passed RULE 1

    index, missing = [], []
    written = set()
    for row in selected:
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
        written.add(row["dir"])

    # RULE 3: a slot this run did NOT write keeps the row it had, when the bytes still match it; never a
    # row recomputed from a build/poc that did not produce them
    previous = parse_index(out)
    for row in rows:
        if row["dir"] in written or not os.path.isdir(os.path.join(out, row["dir"])):
            continue
        got = staged_hash(out, row["dir"])
        if got is None:
            continue
        pin = frozen.get(row["dir"])
        if pin and got != pin:
            print("REFUSING to write INDEX.txt: %s is FROZEN at %s and the bytes staged there are %s.\n"
                  "  The index would have recorded the wrong image as this slot. Nothing further was written."
                  % (row["dir"], pin, got), file=sys.stderr)
            return 5
        prev = previous.get(row["dir"])
        if prev and prev["sha256"] == got:
            index.append(dict(prev))            # carried over verbatim: this run learned nothing new about it
        else:
            index.append({"dir": row["dir"], "test_id": "-", "build_id": "-", "commit": "-",
                          "source": "(not written by this export)",
                          "size": os.path.getsize(os.path.join(out, row["dir"], "boot.dol")), "sha256": got})
    index.sort(key=lambda e: e["dir"])

    lines = [
        "Open-GBP - Swiss launch layout",
        "",
        "Each directory holds one boot.dol, copied byte for byte from build/poc when it was exported.",
        "NEITHER THIS FILE NOR build/poc IS AN AUTHORITY. The bytes a physical run executed are",
        "identified by the SHA-256 and commit in the records (EVIDENCE.md, HARDWARE_TESTS.md, HANDOFF.md).",
        "A row is those bytes ONLY if its STATUS reads PINNED-VERIFIED: its slot is FROZEN below and its",
        "bytes were checked against the pinned hash when this file was written. A row reading UNPINNED-COPY",
        "is a copy of whatever build/poc held at export time; its BUILD ID and COMMIT name that build, and",
        "it has NO physical status -- booting it does NOT reproduce any executed run. To run such an image",
        "again, restage it first from its own commit (docs/HANDOFF.md, the per-image recipe) and pin it.",
        "Numbers are stable: a new build takes the next free number and nothing is renumbered.",
        "A row whose SOURCE reads \"(not written by this export)\" was already staged and was left alone.",
        "",
        "%-12s | %-18s | %-22s | %-9s | %10s | %-64s | %-15s | %s"
        % ("DIR", "TEST ID", "BUILD ID", "COMMIT", "SIZE", "SHA-256", "STATUS", "SOURCE"),
    ]
    for e in index:
        lines.append("%-12s | %-18s | %-22s | %-9s | %10d | %s | %-15s | %s"
                     % (e["dir"], e["test_id"], e["build_id"], e["commit"], e["size"], e["sha256"],
                        row_status(frozen, e), e["source"]))
    if missing:
        lines += ["", "NOT EXPORTED (not built):"]
        for d, p, tgt in missing:
            lines.append("  %-12s %s   (run: make %s)" % (d, p, tgt))
    if frozen:
        lines += ["", "FROZEN SLOTS (tools/swiss-layout.tsv; verified against the pin, never rewritten with other bytes):"]
        for d in sorted(frozen):
            lines.append("  %-12s %s" % (d, frozen[d]))
    text = "\n".join(lines) + "\n"
    with open(index_path(out), "w") as f:
        f.write(text)
    print(text, end="")
    print("swiss_export: %d exported, %d missing, %d carried over -> %s"
          % (len(written), len(missing), len(index) - len(written), os.path.relpath(out, root)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
