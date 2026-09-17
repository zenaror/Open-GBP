#!/usr/bin/env python3
"""gbahdr.py — inspect and complete the 192-byte AGB ROM header.

    tools/gbahdr.py show  <rom.gba>
    tools/gbahdr.py fix   <rom.gba> [--title T] [--game-code C] [--maker M]
    tools/gbahdr.py check <rom.gba> [--require-logo]

devkitARM's GBA crt0 emits the entry branch and the title/code area and leaves
the complement check as a placeholder; this image ships no `gbafix`, so the
complement byte at 0x0BD is computed here, from the bytes on disk, every time.

THE 156-BYTE NINTENDO LOGO AREA IS LEFT AS THE TOOLCHAIN PRODUCED IT — zero in
devkitARM's crt0 — and this repository does NOT supply it. Those bytes are
Nintendo's, and CLAUDE.md §7 forbids vendoring proprietary content.

WHAT THIS TOOL MAY AND MAY NOT CONCLUDE. It reads 192 bytes of header and
nothing else. It therefore reports exactly two things and refuses to go further:

    header-valid       entry branch, fixed byte 0x96, complement check,
                       reserved areas and size are structurally correct.
    logo area          EMPTY or NON-EMPTY. "Non-empty" is a byte test, NOT a
                       comparison against the real Nintendo logo, and this tool
                       never claims the logo is valid.

It deliberately does NOT classify an image as cartridge-bootable or as BIOS
multiboot-compatible. Cartridge boot is decided by the AGB boot ROM against the
real logo, which is not present here. Multiboot is a property of the LINK
ADDRESS and the transfer protocol, not of this header: devkitARM's `gba.specs`
links through `gba_cart.ld` at 0x08000000, while a multiboot image is linked
through `gba_mb.ld` at 0x02000000 (EWRAM). A header inspector cannot see that
and must not pretend to.

The delivery route is the unresolved PHYSICAL EXECUTION DEPENDENCY of
HARDWARE_TESTS §V3.7. The tool states what the header supports; it never
patches a logo in and never asserts a delivery format.

    header layout (GBATEK), offsets inside the ROM:
      0x000..0x003  entry point, an ARM branch
      0x004..0x09F  Nintendo logo (156 bytes, checked by the boot ROM)
      0x0A0..0x0AB  game title, ASCII, space/NUL padded
      0x0AC..0x0AF  game code
      0x0B0..0x0B1  maker code
      0x0B2         fixed value 0x96
      0x0B3         main unit code (0x00)
      0x0B4         device type (0x00)
      0x0B5..0x0BB  reserved, zero
      0x0BC         software version
      0x0BD         complement check  = -(0x19 + sum(0x0A0..0x0BC)) & 0xFF
      0x0BE..0x0BF  reserved, zero
"""
import hashlib
import sys

HEADER_SIZE = 0xC0
LOGO_OFF, LOGO_LEN = 0x004, 156
TITLE_OFF, TITLE_LEN = 0x0A0, 12
GAME_CODE_OFF, GAME_CODE_LEN = 0x0AC, 4
MAKER_OFF, MAKER_LEN = 0x0B0, 2
FIXED_OFF, FIXED_VALUE = 0x0B2, 0x96
COMPLEMENT_OFF = 0x0BD


def complement_check(data):
    """-(0x19 + sum of 0x0A0..0x0BC) & 0xFF, exactly as the AGB boot ROM computes it."""
    return (-(0x19 + sum(data[TITLE_OFF:COMPLEMENT_OFF])) ) & 0xFF


def describe(data):
    if len(data) < HEADER_SIZE:
        raise ValueError("file is shorter than the 192-byte header")
    logo = bytes(data[LOGO_OFF:LOGO_OFF + LOGO_LEN])
    return {
        "size": len(data),
        "entry": int.from_bytes(bytes(data[0:4]), "little"),
        "entry_is_branch": (data[3] & 0xFE) == 0xEA,          # ARM B / BL opcode
        "logo_sha256": hashlib.sha256(logo).hexdigest(),
        "logo_nonzero": any(logo),
        "title": bytes(data[TITLE_OFF:TITLE_OFF + TITLE_LEN]).decode("ascii", "replace"),
        "game_code": bytes(data[GAME_CODE_OFF:GAME_CODE_OFF + GAME_CODE_LEN]).decode("ascii", "replace"),
        "maker": bytes(data[MAKER_OFF:MAKER_OFF + MAKER_LEN]).decode("ascii", "replace"),
        "fixed": data[FIXED_OFF],
        "unit_code": data[0xB3],
        "device_type": data[0xB4],
        "reserved_b5_bb_zero": not any(data[0xB5:0xBC]),
        "version": data[0xBC],
        "complement_stored": data[COMPLEMENT_OFF],
        "complement_expected": complement_check(data),
        "reserved_be_bf_zero": not any(data[0xBE:0xC0]),
    }


def problems(info, require_logo=False):
    """Structural faults. The logo is only a fault when the caller asks for a
    cartridge-bootable image: nothing else in the header depends on it."""
    out = []
    if not info["entry_is_branch"]:
        out.append("entry point 0x%08X is not an ARM branch" % info["entry"])
    if require_logo and not info["logo_nonzero"]:
        out.append("the logo area is empty (byte test): an AGB cartridge boot would refuse this image")
    if info["fixed"] != FIXED_VALUE:
        out.append("fixed byte 0x0B2 is 0x%02X, must be 0x96" % info["fixed"])
    if info["complement_stored"] != info["complement_expected"]:
        out.append("complement check is 0x%02X, must be 0x%02X"
                   % (info["complement_stored"], info["complement_expected"]))
    if not info["reserved_b5_bb_zero"]:
        out.append("reserved bytes 0x0B5..0x0BB are not zero")
    if not info["reserved_be_bf_zero"]:
        out.append("reserved bytes 0x0BE..0x0BF are not zero")
    if info["size"] % 4:
        out.append("ROM size %u is not a multiple of 4" % info["size"])
    return out


def verdict(info):
    """The only two things 192 bytes of header can support, never a boot format.

    Returns ('INVALID: ...' | 'header-valid; logo area ...', exit code). The
    delivery format is NOT decided here: see the module docstring."""
    structural = problems(info, require_logo=False)
    if structural:
        return "INVALID: " + "; ".join(structural), 1
    if info["logo_nonzero"]:
        return ("header-valid; logo area NON-EMPTY (a byte test only, NOT verified "
                "against the real Nintendo logo); delivery format UNRESOLVED"), 0
    return ("header-valid; logo area EMPTY, so an AGB cartridge boot would refuse this "
            "image and this repository does not supply those bytes; delivery format "
            "UNRESOLVED"), 0


def show(path, require_logo=False):
    with open(path, "rb") as f:
        data = bytearray(f.read())
    info = describe(data)
    print("rom              %s" % path)
    print("size             %u bytes" % info["size"])
    print("entry            0x%08X  %s" % (info["entry"], "ARM branch" if info["entry_is_branch"] else "NOT A BRANCH"))
    print("logo area        156 bytes, sha256 %s   %s" %
          (info["logo_sha256"], "NON-EMPTY (not verified)" if info["logo_nonzero"] else "EMPTY"))
    print("title            %r" % info["title"])
    print("game code        %r   maker %r" % (info["game_code"], info["maker"]))
    print("fixed 0x0B2      0x%02X   unit 0x%02X   device 0x%02X   version 0x%02X"
          % (info["fixed"], info["unit_code"], info["device_type"], info["version"]))
    print("complement 0x0BD 0x%02X   expected 0x%02X   %s"
          % (info["complement_stored"], info["complement_expected"],
             "OK" if info["complement_stored"] == info["complement_expected"] else "MISMATCH"))
    print("reserved zero    0x0B5..0x0BB %s   0x0BE..0x0BF %s"
          % (info["reserved_b5_bb_zero"], info["reserved_be_bf_zero"]))
    text, code = verdict(info)
    if require_logo and not info["logo_nonzero"]:
        text, code = "INVALID for cartridge boot: the logo area is empty (byte test)", 1
    print("verdict          %s" % text)
    return code


def fix(path, title=None, game_code=None, maker=None):
    with open(path, "rb") as f:
        data = bytearray(f.read())
    if len(data) < HEADER_SIZE:
        raise ValueError("file is shorter than the 192-byte header")
    if title is not None:
        field = title.encode("ascii")[:TITLE_LEN].ljust(TITLE_LEN, b"\x00")
        data[TITLE_OFF:TITLE_OFF + TITLE_LEN] = field
    if game_code is not None:
        data[GAME_CODE_OFF:GAME_CODE_OFF + GAME_CODE_LEN] = \
            game_code.encode("ascii")[:GAME_CODE_LEN].ljust(GAME_CODE_LEN, b"\x00")
    if maker is not None:
        data[MAKER_OFF:MAKER_OFF + MAKER_LEN] = \
            maker.encode("ascii")[:MAKER_LEN].ljust(MAKER_LEN, b"\x00")
    data[FIXED_OFF] = FIXED_VALUE
    data[COMPLEMENT_OFF] = complement_check(data)
    if len(data) % 4:
        data += b"\x00" * (4 - len(data) % 4)
    with open(path, "wb") as f:
        f.write(data)
    info = describe(data)
    text, code = verdict(info)
    print("gbahdr: %s  title=%r code=%r maker=%r complement=0x%02X  %s"
          % (path, info["title"].rstrip("\x00"), info["game_code"], info["maker"],
             info["complement_stored"], text))
    return code


def main(argv):
    if len(argv) < 3 or argv[1] not in ("show", "fix", "check"):
        print(__doc__)
        return 2
    cmd, path = argv[1], argv[2]
    if cmd in ("show", "check"):
        return show(path, require_logo="--require-logo" in argv)
    kw = {}
    for name, flag in (("title", "--title"), ("game_code", "--game-code"), ("maker", "--maker")):
        if flag in argv:
            kw[name] = argv[argv.index(flag) + 1]
    return fix(path, **kw)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
