"""
tools/vqual.py — the OGBPQUAL1 structural fixture: the ONLY thing a
qualification replay is allowed to see.

WHY THIS FORMAT EXISTS AT ALL

The prospective window (§V5.44) decides when to start measuring, and it must
decide that WITHOUT consulting the measurement. A replay that fed the witness
its own sidecar would hand the state machine FRAME_ID, STATUS, SYNC, CRC-8 and
54 words of stimulus per block — every quantity the design forbids it to read.
So the fixture is a projection: from each recorded frame it keeps the
assembler's structural verdict and throws the rest away. What is not in the file
cannot be consulted by accident.

KEPT              frame_index, blocks, flags, completeness
DELIBERATELY NOT  the 40x54 witness words, the presence bitmap, the timestamps,
                  and therefore FRAME_ID, STATUS, SYNC, CRC-8 and every pixel

WHAT A REPLAY OVER THIS FILE CAN AND CANNOT PROVE

Two terms of the runtime predicate are LIVE LATCHES -- `st->resync_pending` and
`step->resync` -- and a sidecar never recorded them. A replay therefore
evaluates the recorded terms only, which can only qualify a frame the runtime
would have rejected, never the reverse. The replayed window is consequently an
EARLIEST BOUND: the real runtime opens its window here or later. That is the
safe direction for the claim this round makes, and it is the reason the bound is
stated as a bound and not as an equality.

Provenance is in the header: the size and SHA-256 of the sidecar the fixture was
projected from, so a fixture can always be re-derived and checked against the
raw evidence it claims to summarise.
"""
import binascii
import hashlib
import struct

MAGIC = b"OGBPQUAL"
FOOTER = b"OGBPQEND"
VERSION = 1
HEADER_SIZE = 0x40
RECORD_SIZE = 12


class QualError(ValueError):
    pass


def build(records, src_size: int, src_sha256: str) -> bytes:
    """`records` is any iterable of dicts carrying the four structural keys."""
    h = bytearray(HEADER_SIZE)
    h[0:8] = MAGIC
    struct.pack_into(">HHI", h, 0x08, VERSION, 0, len(records))
    struct.pack_into(">Q", h, 0x10, src_size)
    h[0x18:0x38] = bytes.fromhex(src_sha256)
    struct.pack_into(">I", h, 0x38, binascii.crc32(bytes(h[:0x38])) & 0xFFFFFFFF)
    body = bytearray()
    for r in records:
        body += struct.pack(">IHHHH", r["frame_index"], r["blocks"],
                            r["flags"], r["completeness"], 0)
    out = bytes(h) + bytes(body) + FOOTER
    return out + struct.pack(">I", binascii.crc32(out) & 0xFFFFFFFF)


def parse(data: bytes) -> dict:
    if len(data) < HEADER_SIZE + len(FOOTER) + 4:
        raise QualError("shorter than a header and a footer")
    if data[0:8] != MAGIC:
        raise QualError("bad magic")
    version, _, n = struct.unpack_from(">HHI", data, 0x08)
    if version != VERSION:
        raise QualError("unsupported version %d" % version)
    if struct.unpack_from(">I", data, 0x38)[0] != (binascii.crc32(data[:0x38]) & 0xFFFFFFFF):
        raise QualError("header CRC-32 mismatch")
    end = HEADER_SIZE + n * RECORD_SIZE
    if len(data) != end + len(FOOTER) + 4:
        raise QualError("size does not match the record count")
    if data[end:end + len(FOOTER)] != FOOTER:
        raise QualError("bad footer")
    if struct.unpack_from(">I", data, end + len(FOOTER))[0] != \
            (binascii.crc32(data[:end + len(FOOTER)]) & 0xFFFFFFFF):
        raise QualError("total CRC-32 mismatch")
    recs = []
    for i in range(n):
        fi, blocks, flags, compl, rsv = struct.unpack_from(">IHHHH", data, HEADER_SIZE + i * RECORD_SIZE)
        if rsv:
            raise QualError("record %d: reserved word is not zero" % i)
        recs.append({"frame_index": fi, "blocks": blocks,
                     "flags": flags, "completeness": compl})
    return {"version": version, "records_n": n,
            "src_size": struct.unpack_from(">Q", data, 0x10)[0],
            "src_sha256": data[0x18:0x38].hex(),
            "records": recs}


def project(sidecar_path: str) -> bytes:
    """Derives the fixture from an OGBPIDXCAP1 sidecar."""
    import vidxcap
    raw = open(sidecar_path, "rb").read()
    info = vidxcap.parse(raw)
    return build(info["records"], len(raw), hashlib.sha256(raw).hexdigest())


def load(path: str) -> dict:
    with open(path, "rb") as f:
        return parse(f.read())


if __name__ == "__main__":
    import sys
    if len(sys.argv) != 3:
        sys.exit("usage: vqual.py <sidecar.bin> <out.ogbpqual>")
    out = project(sys.argv[1])
    open(sys.argv[2], "wb").write(out)
    i = parse(out)
    print("%s: %d records, src %d B sha256 %s" %
          (sys.argv[2], i["records_n"], i["src_size"], i["src_sha256"][:16]))
