#!/usr/bin/env python3
"""
tools/gbaderive.py — derive a DELIVERY image from a CANONICAL stimulus ROM.

    tools/gbaderive.py <canonical.gba> <donor.gba> <out.gba>

The canonical ROM is the source authority and is reproducible from this
repository; its 156-byte Nintendo logo area (0x004..0x09F) is EMPTY, so a real
AGB refuses to boot it. The DERIVED image copies that area from a DONOR that
has already booted the physical flashcart route (HARDWARE_TESTS §V3.7,
§V5.39.15: `build/physical/agb-color-bars-cart.gba`, whose logo bytes booted
twice), recomputes the header complement with tools/gbahdr.py, and verifies
that EVERYTHING past 0x0C0 is byte-identical to the canonical ROM. Nothing
proprietary enters the repository: the donor and the output live under
build/physical/, which Git ignores, and this script refuses to write anywhere
else. The output gains no physical status by existing.
"""
import hashlib
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gbahdr  # noqa: E402

LOGO_OFF, LOGO_LEN = 0x004, 156
HEADER_END = 0x0C0


def sha(b):
    return hashlib.sha256(b).hexdigest()


def main(argv):
    if len(argv) != 4:
        print(__doc__)
        return 2
    canon, donor, out = argv[1:4]
    if "build/physical" not in os.path.abspath(out).replace(os.sep, "/"):
        print("refusing: the derived image may only be written under build/physical/", file=sys.stderr)
        return 3
    with open(canon, "rb") as f:
        c = bytearray(f.read())
    with open(donor, "rb") as f:
        d = f.read()
    logo = d[LOGO_OFF:LOGO_OFF + LOGO_LEN]
    if len(logo) != LOGO_LEN or not any(logo):
        print("refusing: the donor's logo area is empty", file=sys.stderr)
        return 4
    if any(c[LOGO_OFF:LOGO_OFF + LOGO_LEN]):
        print("refusing: the canonical ROM already carries a logo area", file=sys.stderr)
        return 5
    c[LOGO_OFF:LOGO_OFF + LOGO_LEN] = logo
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    with open(out, "wb") as f:
        f.write(bytes(c))
    rc = gbahdr.fix(out)          # recomputes the complement; keeps title/code/maker as they are
    if rc:
        return rc
    with open(canon, "rb") as f:
        c0 = f.read()
    with open(out, "rb") as f:
        o = f.read()
    if o[HEADER_END:] != c0[HEADER_END:] or len(o) != len(c0):
        print("refusing: the payload past 0x0C0 differs from the canonical ROM", file=sys.stderr)
        return 6
    print("canonical %s  %d B  sha256 %s" % (canon, len(c0), sha(c0)))
    print("donor     %s  logo sha256 %s" % (donor, sha(logo)))
    print("derived   %s  %d B  sha256 %s  (payload past 0x0C0 byte-identical to the canonical ROM)" % (out, len(o), sha(o)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
