#!/usr/bin/env python3
"""
hotpath_cmp -- THE HOT-PATH IDENTITY GATE of GitHub Issue #158 (vehicle-0002, GBP-PLAY-002).

CLAIM TESTED. The code of the roots (`pump`, `live_tap`, `live_dma_cb`, `on_draw_done`, `gbp_v28_step_hook`) and of every main.o function they reach is the same in
the candidate build as in the reference build, MODULO ADDRESSES; and every linked object other than main.o (and the candidate's named extra
objects, the formatter) is identical between the two builds.

WHAT IT DOES NOT ESTABLISH. Instruction identity modulo addresses, NOT timing identity: code and data addresses move between the two builds,
and with them cache placement.

INPUTS. Two build directories, each holding what `tools/audit_listings.sh` writes (`audit/<object>.objdump.txt` = `objdump -dr`,
`audit/<object>.reloc.txt` = `objdump -r`) and the object `obj/main.o` itself. The symbol table and the section bytes of main.o are read
from the ELF file directly (the same table `powerpc-eabi-objdump -t main.o` prints, and the same bytes `objdump -s` dumps), so the tool runs
on the host and needs no cross toolchain.

THE RULES (Issue #158, "THE HOT-PATH IDENTITY GATE"):
  * Library objects: every object other than main.o and the extra objects must be identical: `.objdump.txt` equal but for the first
    `file format` line (the path); `.reloc.txt` equal in every section but the `.debug*` ones (objdump prints the `.rela.debug*` sections
    as `RELOCATION RECORDS FOR [.debug_...]`; excluded only because `-g` embeds the POC directory and shifts `.debug_str` offsets); AND every
    non-debug section of the object byte-identical (NOBITS by size), read from the object's own ELF `obj/<object>.o` because the listings
    carry no data bytes (R1 of the central session's review). The set of linked objects equal, plus the extra objects (present in the
    candidate, absent from the reference).
  * main.o, closure: roots `pump`, `live_tap`, `live_dma_cb`, `on_draw_done` and -- decision 2 of the central session -- `gbp_v28_step_hook`,
    which the pump reaches only through a pointer (ap2.step_pushes, src/audio/gbp_aplay2.c:175); each must exist in BOTH main.o listings, else
    the gate cannot be read: exit 2. Every main.o function whose ADDRESS is taken is listed (information): an indirect call no closure rule can
    follow starts at one of them, so a new one outside the closure is visible. Repeatedly add every main.o function reached from a closure function by a local branch (a `<name>` / `<name+0x...>`
    annotation naming another main.o function) or by a relocation against a main.o function symbol or a `.text*` section symbol + N
    resolved to a function. The two closures must have the same set of names.
  * main.o, per instruction, in order: the address column is dropped; the raw bytes and the disassembly are kept, EXCEPT a PC-relative
    branch resolved by the assembler (no relocation line), compared as its mnemonic and non-target operands + `<symbol+offset>` (the
    offset is function-relative as objdump prints it), its raw bytes and hex target ignored. (The non-target operands, e.g. `cr7`, are
    kept: stricter than mnemonic + annotation alone, never looser.) The hex address objdump prints before a `<...>` annotation is dropped
    in every instruction: it is a section offset.
  * main.o, relocation lines: `(type, position inside the instruction, target)`: a named target outside main.o as is; a DATA object of
    main.o (named, or section-relative: `.bss/.sbss/.sdata/.sdata2/.data/.rodata` and their `-fdata-sections` forms `.bss.<x>` ...,
    resolved through main.o's symbol table to `local_symbol+delta`) by its NAME AND ITS CONTENT -- its bytes and the relocations inside it,
    resolved recursively by these same rules, a NOBITS object by its size (R1: a patched constant table or initialised variable is a
    difference); a target in an anonymous string or constant section (`.rodata.str*`, `.rodata.<fn>.str*`, `.rodata.cst*`)
    compared by the bytes it points at (up to the NUL for `.str`, the constant's size for `.cst<N>`); a target these rules cannot resolve
    is a DIFFERENCE (on either side, even when both sides agree).
  * A local symbol the COMPILER numbered (`CSWTCH.194`, `f.part.0`, `f.constprop.1`, `f.isra.0`, a function-static `line.3`: a trailing
    `.<digits>`, which no C identifier has) is compared by CONTENT, never by its number (decision 1 of the central session): a data object
    by its bytes and the relocations inside it (resolved by these same rules; a NOBITS object by its size), a cloned function by its
    normalised instruction sequence (its own name inside it replaced by `<stem>.N`). Both are named `<stem>.N#<digest>`; the mapping from
    each real name is printed. The number moves whenever the translation unit gains a declaration; the content is what runs.
  * Verdict: 0 differences = SAME (the gate PASSES); 1 or more = DIFFERENT (the gate FAILS). The output is the record: never filter it.

Usage:
    tools/hotpath_cmp.py REF_BUILD_DIR CAND_BUILD_DIR [--extra-object NAME]... [--root NAME]... [--report FILE]
Exit status 0 = SAME, 1 = DIFFERENT, 2 = the gate cannot be read (a missing root, listing or object).
"""
from __future__ import annotations

import argparse
import difflib
import hashlib
import os
import re
import struct
import sys
from dataclasses import dataclass, field

# decision 2 of the central session (Issue #158): gbp_v28_step_hook is a FIXED root -- the pump reaches it through a pointer (ap2.step_pushes,
# src/audio/gbp_aplay2.c:175), which no closure rule can follow
DEFAULT_ROOTS = ("pump", "live_tap", "live_dma_cb", "on_draw_done", "gbp_v28_step_hook")
MAIN_OBJECT = "main"

SECTION_RE = re.compile(r"^Disassembly of section (?P<sec>\S+):\s*$")
FUNC_RE = re.compile(r"^(?P<addr>[0-9a-f]+) <(?P<name>[^>]+)>:\s*$")
INSN_RE = re.compile(r"^\s+(?P<addr>[0-9a-f]+):\t(?P<bytes>(?:[0-9a-f]{2} )+)\s*\t?(?P<text>.*)$")
RELOC_LINE_RE = re.compile(r"^\t+(?P<addr>[0-9a-f]+): (?P<type>R_\S+)\t(?P<target>\S+)\s*$")
SKIP_RE = re.compile(r"^\s+\.\.\.\s*$")
ANNOT_RE = re.compile(r"^(?P<head>.*?)(?P<hex>[0-9a-f]+) <(?P<sym>[^>]+)>$")
SYMOFF_RE = re.compile(r"^(?P<name>.+?)(?:(?P<sign>[+-])0x(?P<off>[0-9a-f]+))?$")
STR_SECTION_RE = re.compile(r"^\.rodata(?:\..+)?\.str\d+(?:\.\d+)?$")
CST_SECTION_RE = re.compile(r"^\.rodata(?:\..+)?\.cst(?P<size>\d+)$")
DATA_SECTION_RE = re.compile(r"^\.(?:bss|sbss|sdata|sdata2|data|rodata)(?:\..+)?$")
TEXT_SECTION_RE = re.compile(r"^\.text(?:\..+)?$")
NUMBERED_RE = re.compile(r"^(?P<stem>[^.].*)\.(?P<n>\d+)$")


# ---------------------------------------------------------------------------------------------------------------------------- the object model
@dataclass
class Sym:
    name: str
    section: str
    value: int
    size: int
    kind: str            # "func", "object", "notype", "section", "file"


@dataclass
class Insn:
    addr: int            # function-relative
    raw: str             # "38 60 00 40"
    text: str            # disassembly
    relocs: list = field(default_factory=list)   # [(pos, type, target)]


@dataclass
class Func:
    name: str
    section: str
    insns: list = field(default_factory=list)


@dataclass
class MainObj:
    funcs: dict          # name -> Func
    symbols: list        # [Sym]
    sections: dict       # name -> bytes (empty for NOBITS)
    data_relocs: dict = field(default_factory=dict)   # section -> [(offset, type, target)] from `objdump -r`


def parse_disassembly(text: str) -> dict:
    """`objdump -dr` text -> {function name: Func}, relocation lines attached to the instruction they patch."""
    funcs: dict = {}
    sec = None
    cur = None
    base = 0
    for line in text.splitlines():
        m = SECTION_RE.match(line)
        if m:
            sec, cur = m.group("sec"), None
            continue
        m = FUNC_RE.match(line)
        if m:
            base = int(m.group("addr"), 16)
            cur = Func(m.group("name"), sec or "?")
            funcs[cur.name] = cur
            continue
        if cur is None:
            continue
        m = RELOC_LINE_RE.match(line)
        if m:
            if not cur.insns:
                raise ValueError(f"relocation before any instruction in {cur.name}: {line!r}")
            ins = cur.insns[-1]
            pos = int(m.group("addr"), 16) - base - ins.addr
            ins.relocs.append((pos, m.group("type"), m.group("target")))
            continue
        m = INSN_RE.match(line)
        if m:
            cur.insns.append(Insn(int(m.group("addr"), 16) - base, m.group("bytes").strip(), m.group("text").strip()))
            continue
        if SKIP_RE.match(line):
            cur.insns.append(Insn(-1, "...", "..."))
    return funcs


def elf_sections(data: bytes) -> list:
    """ELF32 big-endian relocatable -> [(name, sh_type, sh_size, bytes)] (bytes empty for NOBITS)."""
    return [(n, h[1], h[5], b) for n, h, b in _elf_headers(data)[0]]


def _elf_headers(data: bytes) -> tuple:
    if data[:4] != b"\x7fELF" or data[4] != 1 or data[5] != 2:
        raise ValueError("not an ELF32 big-endian object")
    e_shoff, = struct.unpack_from(">I", data, 0x20)
    e_shentsize, e_shnum, e_shstrndx = struct.unpack_from(">HHH", data, 0x2E)
    shdrs = []
    for i in range(e_shnum):
        shdrs.append(struct.unpack_from(">IIIIIIIIII", data, e_shoff + i * e_shentsize))
    shstr = shdrs[e_shstrndx]
    shstr_bytes = data[shstr[4]:shstr[4] + shstr[5]]

    def cstr(blob: bytes, off: int) -> str:
        end = blob.index(b"\0", off)
        return blob[off:end].decode("latin-1")

    names = [cstr(shstr_bytes, h[0]) for h in shdrs]
    triples = [(n, h, b"" if h[1] == 8 else data[h[4]:h[4] + h[5]]) for n, h in zip(names, shdrs)]
    return triples, shdrs, names, cstr


def read_elf(data: bytes) -> tuple:
    """ELF32 big-endian relocatable -> ([Sym], {section name: bytes}). Section symbols carry the section's own name."""
    triples, shdrs, names, cstr = _elf_headers(data)
    sections = dict((n, b) for n, _h, b in triples)
    syms = []
    kinds = {0: "notype", 1: "object", 2: "func", 3: "section", 4: "file"}
    for idx, h in enumerate(shdrs):
        if h[1] != 2:          # SHT_SYMTAB
            continue
        strtab = shdrs[h[6]]
        strtab_bytes = data[strtab[4]:strtab[4] + strtab[5]]
        for k in range(h[5] // 16):
            st_name, st_value, st_size, st_info, _st_other, st_shndx = struct.unpack_from(">IIIBBH", data, h[4] + k * 16)
            kind = kinds.get(st_info & 0xF, "other")
            sec = names[st_shndx] if 0 < st_shndx < len(names) else ""
            name = sec if kind == "section" else cstr(strtab_bytes, st_name)
            syms.append(Sym(name, sec, st_value, st_size, kind))
    return syms, sections


# ---------------------------------------------------------------------------------------------------------------------------- normalisation
def split_target(target: str) -> tuple:
    m = SYMOFF_RE.match(target)
    name = m.group("name")
    off = int(m.group("off"), 16) if m.group("off") else 0
    if m.group("sign") == "-":
        off = -off
    return name, off


def numbered_stem(name: str):
    """A local symbol the COMPILER numbered (CSWTCH.194, gecko_puts.part.0, f.constprop.1, f.isra.0, a function-static `line.3`): C identifiers
    never contain a dot, so a trailing `.<digits>` is the compiler's. -> the stem with the number replaced by N, or None."""
    m = NUMBERED_RE.match(name)
    return f"{m.group('stem')}.N" if m else None


def parse_reloc_listing(text: str) -> dict:
    """`objdump -r` text -> {section: [(offset, type, target)]}"""
    out, sec = {}, None
    for ln in text.splitlines():
        m = re.match(r"^RELOCATION RECORDS FOR \[(?P<sec>[^\]]+)\]:", ln)
        if m:
            sec = m.group("sec")
            out.setdefault(sec, [])
            continue
        m = re.match(r"^(?P<off>[0-9a-f]{8}) (?P<type>R_\S+)\s+(?P<target>\S+)\s*$", ln)
        if m and sec is not None:
            out[sec].append((int(m.group("off"), 16), m.group("type"), m.group("target")))
    return out


class Resolver:
    """Resolves relocation targets and annotations of ONE main.o. A compiler-numbered local symbol (decision 1 of the central session,
    Issue #158) is compared by CONTENT, never by its number: a data object by its bytes and the relocations inside it (resolved by these same
    rules), a cloned function by its normalised instruction sequence; both are named `<stem>.N#<digest>` here."""

    def __init__(self, obj: MainObj):
        self.obj = obj
        self.by_section: dict = {}
        for s in obj.symbols:
            if s.kind in ("section", "file") or not s.section or not s.name:
                continue
            self.by_section.setdefault(s.section, []).append(s)
        for lst in self.by_section.values():
            lst.sort(key=lambda s: (s.value, s.name))
        self.main_funcs = set(obj.funcs)
        self._func_key: dict = {}
        self._data_key: dict = {}
        self._busy: set = set()
        self.numbered_seen: dict = {}      # actual name -> content key (for the report)
        self.data_seen: dict = {}          # named (not numbered) data object -> content key (for the report)
        self.defined_data = dict((s.name, s) for s in obj.symbols
                                 if s.kind in ("object", "notype") and s.name and s.section and DATA_SECTION_RE.match(s.section))

    def symbol_at(self, section: str, off: int):
        best = None
        for s in self.by_section.get(section, ()):
            if s.value <= off and (best is None or s.value > best.value or (s.value == best.value and s.size > best.size)):
                best = s
        return best

    @staticmethod
    def _digest(parts) -> str:
        return hashlib.sha256("\n".join(parts).encode("utf-8", "backslashreplace")).hexdigest()[:16]

    def func_key(self, name: str) -> str:
        """the closure / comparison name of a main.o function: its own name, or `<stem>.N#<digest of its normalised code>` when numbered"""
        stem = numbered_stem(name)
        if stem is None or name not in self.obj.funcs:
            return name
        if name in self._func_key:
            return self._func_key[name]
        if ("f", name) in self._busy:              # a cycle between numbered clones: the stem alone inside the cycle
            return f"{stem}#cycle"
        self._busy.add(("f", name))
        lines = normalise_function(self.obj.funcs[name], self)[0]
        self._busy.discard(("f", name))
        key = f"{stem}#{self._digest(lines)}"
        self._func_key[name] = key
        self.numbered_seen[name] = key
        return key

    def data_key(self, s: Sym) -> str:
        """EVERY data object the closure references is compared by CONTENT (R1 of the central session's review, Issue #158): its bytes and the
        relocations inside it, resolved recursively by these same rules; a NOBITS object by its size. A numbered one is named `<stem>.N#<digest>`,
        any other `<name>@<digest>`."""
        stem = numbered_stem(s.name)
        label = stem if stem is not None else s.name
        sep = "#" if stem is not None else "@"
        k = (s.section, s.name)
        if k in self._data_key:
            return self._data_key[k]
        if ("d",) + k in self._busy:
            return f"{label}{sep}cycle"
        self._busy.add(("d",) + k)
        blob = self.obj.sections.get(s.section, b"")
        parts = [f"section-class={'nobits' if not blob else 'bits'} size={s.size}"]
        if blob:
            parts.append(blob[s.value:s.value + s.size].hex())
        for off, rtype, target in self.obj.data_relocs.get(s.section, ()):
            if s.value <= off < s.value + max(s.size, 1):
                parts.append(f"@{off - s.value:x} {rtype} {self.target(target)[0]}")
        self._busy.discard(("d",) + k)
        key = f"{label}{sep}{self._digest(parts)}"
        self._data_key[k] = key
        (self.numbered_seen if stem is not None else self.data_seen)[s.name] = key
        return key

    def target(self, target: str) -> tuple:
        """-> (normalised target, function reached in main.o or None, resolved?)"""
        name, off = split_target(target)
        if not name.startswith("."):
            reached = name if name in self.main_funcs else None
            shown = self.func_key(name) if reached else name
            if reached is None and name in self.defined_data:
                shown = "sym:" + self.data_key(self.defined_data[name])
            return (f"{shown}{off:+#x}" if off else shown), reached, True
        sec = name
        if TEXT_SECTION_RE.match(sec):
            s = self.symbol_at(sec, off)
            if s is not None and s.kind == "func":
                delta = off - s.value
                key = self.func_key(s.name)
                return (f"func:{key}{delta:+#x}" if delta else f"func:{key}"), (s.name if s.name in self.main_funcs else None), True
            return f"UNRESOLVED:{sec}{off:+#x}", None, False
        m = CST_SECTION_RE.match(sec)
        if m:
            blob = self.obj.sections.get(sec)
            size = int(m.group("size"))
            if blob is None or off < 0 or off + size > len(blob):
                return f"UNRESOLVED:{sec}{off:+#x}", None, False
            return f"cst{size}:{blob[off:off + size].hex()}", None, True
        if STR_SECTION_RE.match(sec):
            blob = self.obj.sections.get(sec)
            if blob is None or off < 0 or off >= len(blob) or b"\0" not in blob[off:]:
                return f"UNRESOLVED:{sec}{off:+#x}", None, False
            end = blob.index(b"\0", off)
            return f"str:{blob[off:end]!r}", None, True
        if DATA_SECTION_RE.match(sec):
            s = self.symbol_at(sec, off)
            if s is None:
                return f"UNRESOLVED:{sec}{off:+#x}", None, False
            delta = off - s.value
            shown = self.data_key(s)
            return (f"sym:{shown}{delta:+#x}" if delta else f"sym:{shown}"), None, True
        return f"UNRESOLVED:{sec}{off:+#x}", None, False

    def annotation(self, sym: str, own: str) -> str:
        """a `<name+0x..>` annotation as compared: a numbered name by its content key (itself: its stem), every other name as printed"""
        base, off = split_target(sym)
        if numbered_stem(base) is None or base not in self.main_funcs:
            return sym
        key = numbered_stem(base) if base == own else self.func_key(base)
        return f"{key}{off:+#x}" if off else key


def normalise_function(fn: Func, res: Resolver) -> tuple:
    """-> (list of comparable lines, set of main.o functions reached, list of unresolved targets)"""
    out, reached, unresolved = [], set(), []
    for ins in fn.insns:
        if ins.raw == "...":
            out.append("...")
            continue
        m = ANNOT_RE.match(ins.text)
        if m and not ins.relocs:
            # a PC-relative branch the assembler resolved: mnemonic + other operands + <symbol+offset>; bytes and hex target ignored
            sym = m.group("sym")
            base = split_target(sym)[0]
            if base in res.main_funcs and base != fn.name:
                reached.add(base)
            out.append(f"BR {' '.join(m.group('head').split())} <{res.annotation(sym, fn.name)}>")
            continue
        text = ins.text
        if m:
            text = f"{m.group('head')}<{res.annotation(m.group('sym'), fn.name)}>"
        line = f"I {ins.raw} | {' '.join(text.split())}"
        for pos, rtype, target in ins.relocs:
            norm, fn_reached, ok = res.target(target)
            if fn_reached:
                reached.add(fn_reached)
            if not ok:
                unresolved.append(f"{fn.name}+{ins.addr:#x}: {rtype} {target}")
            line += f" || R{pos} {rtype} {norm}"
        out.append(line)
    return out, reached, unresolved


def closure(obj: MainObj, roots) -> tuple:
    """-> (closure keys in visiting order, {key: normalised lines}, unresolved targets, {key: actual name}, resolver)"""
    res = Resolver(obj)
    seen, order, norm, unresolved, actual = set(), [], {}, [], {}
    todo = list(roots)
    while todo:
        name = todo.pop(0)
        if name in seen:
            continue
        seen.add(name)
        key = res.func_key(name)
        order.append(key)
        actual[key] = name
        lines, reached, unres = normalise_function(obj.funcs[name], res)
        norm[key] = lines
        unresolved.extend(unres)
        for r in sorted(reached):
            if r not in seen:
                todo.append(r)
    return order, norm, unresolved, actual, res


BRANCH_RELOCS = ("R_PPC_REL24", "R_PPC_REL14", "R_PPC_REL14_BRTAKEN", "R_PPC_REL14_BRNTAKEN", "R_PPC_PLTREL24", "R_PPC_LOCAL24PC")


def address_taken(obj: MainObj) -> list:
    """every main.o function whose ADDRESS is taken (a relocation that is not a branch: a pointer stored, passed or tabled), with who takes it:
    the candidates for an indirect call the closure cannot follow"""
    res = Resolver(obj)
    hits = []
    for fname, fn in obj.funcs.items():
        for ins in fn.insns:
            for _pos, rtype, target in ins.relocs:
                if rtype in BRANCH_RELOCS:
                    continue
                _norm, reached, _ok = res.target(target)
                if reached:
                    hits.append((reached, fname, rtype))
    for sec, rows in obj.data_relocs.items():
        if sec.startswith(".debug") or sec.startswith(".eh_frame") or TEXT_SECTION_RE.match(sec):
            continue
        for _off, rtype, target in rows:
            _norm, reached, _ok = res.target(target)
            if reached:
                hits.append((reached, sec, rtype))
    return sorted(set(hits))


# ---------------------------------------------------------------------------------------------------------------------------- library objects
def strip_first_format_line(text: str) -> list:
    lines = text.splitlines()
    for i, ln in enumerate(lines[:3]):
        if "file format" in ln:
            return lines[:i] + lines[i + 1:]
    return lines


def reloc_sections_without_debug(text: str) -> list:
    out, keep = [], True
    for ln in strip_first_format_line(text):
        m = re.match(r"^RELOCATION RECORDS FOR \[(?P<sec>[^\]]+)\]:", ln)
        if m:
            keep = not (m.group("sec").startswith(".debug") or m.group("sec").startswith(".rela.debug"))
        if keep:
            out.append(ln)
    return out


SKIP_SECTION_TYPES = (0, 2, 3, 4, 9, 17)          # NULL, SYMTAB, STRTAB, RELA, REL, GROUP: indices and names, compared through the listings instead


def comparable_sections(path: str) -> dict:
    """the non-debug sections of a library object, by its own ELF: {name: bytes, or ('nobits', size)} (R1: the listings carry no data bytes)"""
    if not os.path.isfile(path):
        raise Unreadable(f"no object {path}")
    with open(path, "rb") as f:
        secs = elf_sections(f.read())
    out = {}
    for name, sh_type, size, blob in secs:
        if sh_type in SKIP_SECTION_TYPES or name.startswith(".debug") or name.startswith(".rela") or name.startswith(".rel."):
            continue
        out[name] = ("nobits", size) if sh_type == 8 else blob
    return out


def listing_objects(audit_dir: str) -> set:
    return {f[:-len(".objdump.txt")] for f in os.listdir(audit_dir) if f.endswith(".objdump.txt")}


def _sec_brief(v) -> str:
    if v is None:
        return "absent"
    if isinstance(v, tuple):
        return f"NOBITS size {v[1]}"
    return f"{len(v)} B sha256 {hashlib.sha256(v).hexdigest()[:16]}"


def compare_library(ref_files: dict, cand_files: dict, extras) -> tuple:
    """ref_files/cand_files: {object: (objdump text, reloc text, object path)}. -> (report lines, differences)"""
    lines, diffs = [], 0
    extras = set(extras)
    ref_set, cand_set = set(ref_files) - {MAIN_OBJECT}, set(cand_files) - {MAIN_OBJECT}
    lines.append(f"linked objects: reference {len(ref_set) + (MAIN_OBJECT in ref_files)}, candidate {len(cand_set) + (MAIN_OBJECT in cand_files)}"
                 f" (extra objects expected in the candidate only: {', '.join(sorted(extras)) or 'none'})")
    for x in sorted(extras):
        if x not in cand_set:
            lines.append(f"  DIFFERENCE: the extra object {x} is not linked into the candidate")
            diffs += 1
        if x in ref_set:
            lines.append(f"  DIFFERENCE: the extra object {x} is already linked into the reference")
            diffs += 1
    for x in sorted(ref_set - cand_set):
        lines.append(f"  DIFFERENCE: {x} is linked into the reference and not into the candidate")
        diffs += 1
    for x in sorted(cand_set - ref_set - extras):
        lines.append(f"  DIFFERENCE: {x} is linked into the candidate and not into the reference")
        diffs += 1
    same, nsec = 0, 0
    for x in sorted((ref_set & cand_set) - extras):
        r_obj, r_rel = ref_files[x][:2]
        c_obj, c_rel = cand_files[x][:2]
        a, b = strip_first_format_line(r_obj), strip_first_format_line(c_obj)
        if a != b:
            n = sum(1 for _ in difflib.unified_diff(a, b, lineterm="", n=0))
            lines.append(f"  DIFFERENCE: {x}.objdump.txt differs ({n} unified-diff lines):")
            lines.extend("    " + d for d in difflib.unified_diff(a, b, "reference", "candidate", lineterm="", n=0))
            diffs += 1
        a, b = reloc_sections_without_debug(r_rel), reloc_sections_without_debug(c_rel)
        if a != b:
            lines.append(f"  DIFFERENCE: {x}.reloc.txt differs outside the .debug sections:")
            lines.extend("    " + d for d in difflib.unified_diff(a, b, "reference", "candidate", lineterm="", n=0))
            diffs += 1
        r_sec, c_sec = comparable_sections(ref_files[x][2]), comparable_sections(cand_files[x][2])
        if r_sec != c_sec:
            bad = sorted(n for n in set(r_sec) | set(c_sec) if r_sec.get(n) != c_sec.get(n))
            lines.append(f"  DIFFERENCE: {x}.o section contents differ (non-debug sections, read from the object): {', '.join(bad)}")
            for n in bad:
                lines.append(f"    {n}: reference {_sec_brief(r_sec.get(n))} / candidate {_sec_brief(c_sec.get(n))}")
            diffs += 1
        else:
            nsec += len(r_sec)
        if r_obj == c_obj and r_rel == c_rel:
            same += 1
    common = sorted((ref_set & cand_set) - extras)
    lines.append(f"library objects compared: {len(common)} ({same} byte-identical listings, the rest equal under the two exclusions; "
                 f"{nsec} non-debug sections byte-identical, read from the objects)"
                 if diffs == 0 else f"library objects compared: {len(common)}")
    lines.append("  " + " ".join(common))
    return lines, diffs


# ---------------------------------------------------------------------------------------------------------------------------- the gate
class Unreadable(Exception):
    pass


def compare_main(ref: MainObj, cand: MainObj, roots) -> tuple:
    lines, diffs = [], 0
    for side, obj in (("reference", ref), ("candidate", cand)):
        missing = [r for r in roots if r not in obj.funcs]
        if missing:
            raise Unreadable(f"root(s) {', '.join(missing)} not found in the {side} main.o listing: the gate cannot be read")
    r_order, r_norm, r_unres, r_actual, r_res = closure(ref, roots)
    c_order, c_norm, c_unres, c_actual, c_res = closure(cand, roots)

    def shown(order, actual):
        return ", ".join(k if actual[k] == k else f"{k} ({actual[k]})" for k in sorted(order))

    lines.append(f"roots: {', '.join(roots)}")
    lines.append(f"closure (reference, {len(r_order)}): {shown(r_order, r_actual)}")
    lines.append(f"closure (candidate, {len(c_order)}): {shown(c_order, c_actual)}")
    for side, res in (("reference", r_res), ("candidate", c_res)):
        if res.numbered_seen:
            lines.append(f"compiler-numbered symbols compared by content ({side}): "
                         + ", ".join(f"{n} -> {k}" for n, k in sorted(res.numbered_seen.items())))
        lines.append(f"named data objects compared by content ({side}, {len(res.data_seen)}): "
                     + ", ".join(sorted(res.data_seen.values())))
    if set(r_order) != set(c_order):
        r_only, c_only = sorted(set(r_order) - set(c_order)), sorted(set(c_order) - set(r_order))
        for n in r_only:
            lines.append(f"  DIFFERENCE: {n} is in the reference closure only")
            diffs += 1
        for n in c_only:
            lines.append(f"  DIFFERENCE: {n} is in the candidate closure only")
            diffs += 1
        for n in r_only:                       # a numbered clone whose CONTENT changed: show the code, for the record
            stem = n.split("#")[0]
            mates = [m for m in c_only if m.split("#")[0] == stem and "#" in n]
            if len(mates) == 1:
                lines.append(f"    (same stem {stem}: the two contents)")
                lines.extend("    " + d for d in difflib.unified_diff(r_norm[n], c_norm[mates[0]], "reference", "candidate", lineterm="", n=0))
    for side, unres in (("reference", r_unres), ("candidate", c_unres)):
        for u in unres:
            lines.append(f"  DIFFERENCE: unresolvable relocation target ({side}): {u}")
            diffs += 1
    total = 0
    for name in sorted(set(r_order) & set(c_order)):
        a, b = r_norm[name], c_norm[name]
        total += len(a)
        if a == b:
            lines.append(f"  {name}: {len(a)} instructions, identical")
            continue
        sm = difflib.SequenceMatcher(a=a, b=b, autojunk=False)
        nd = sum(max(i2 - i1, j2 - j1) for tag, i1, i2, j1, j2 in sm.get_opcodes() if tag != "equal")
        diffs += nd
        lines.append(f"  DIFFERENCE: {name}: {nd} differing instruction(s) ({len(a)} reference, {len(b)} candidate):")
        lines.extend("    " + d for d in difflib.unified_diff(a, b, "reference", "candidate", lineterm="", n=0))
    lines.append(f"main.o closure instructions compared: {total}")
    for side, obj, order, actual in (("reference", ref, r_order, r_actual), ("candidate", cand, c_order, c_actual)):
        inside = set(actual.values())
        hits = address_taken(obj)
        lines.append(f"address-taken main.o functions ({side}; information: an indirect call the closure cannot follow starts at one of these):")
        for fn, by, rtype in hits:
            lines.append(f"    {fn:<28} taken by {by:<28} {rtype:<18} {'IN the closure' if fn in inside else 'not in the closure'}")
    return lines, diffs


def load_build(build_dir: str) -> tuple:
    audit = os.path.join(build_dir, "audit")
    mo = os.path.join(build_dir, "obj", "main.o")
    if not os.path.isdir(audit):
        raise Unreadable(f"no listings directory {audit} (run tools/audit_listings.sh)")
    if not os.path.isfile(mo):
        raise Unreadable(f"no object {mo}")
    files = {}
    for x in sorted(listing_objects(audit)):
        rel = os.path.join(audit, x + ".reloc.txt")
        if not os.path.isfile(rel):
            raise Unreadable(f"no {rel}")
        with open(os.path.join(audit, x + ".objdump.txt"), encoding="utf-8") as f1, open(rel, encoding="utf-8") as f2:
            files[x] = (f1.read(), f2.read(), os.path.join(build_dir, "obj", x + ".o"))
    if MAIN_OBJECT not in files:
        raise Unreadable(f"no main.objdump.txt under {audit}")
    with open(mo, "rb") as f:
        syms, sections = read_elf(f.read())
    return files, MainObj(parse_disassembly(files[MAIN_OBJECT][0]), syms, sections, parse_reloc_listing(files[MAIN_OBJECT][1]))


def run(ref_dir: str, cand_dir: str, extras, roots) -> tuple:
    out = [f"hotpath_cmp -- the hot-path identity gate (Issue #158)",
           f"reference: {ref_dir}", f"candidate: {cand_dir}"]
    try:
        r_files, r_main = load_build(ref_dir)
        c_files, c_main = load_build(cand_dir)
        lib_lines, lib_diffs = compare_library(r_files, c_files, extras)
        main_lines, main_diffs = compare_main(r_main, c_main, roots)
    except Unreadable as e:
        out.append(f"UNREADABLE: {e}")
        out.append("RESULT: UNREADABLE -- the gate cannot be read (STOP)")
        return out, 2
    out.append("-- library objects (every object but main.o and the extra objects):")
    out.extend(lib_lines)
    out.append("-- main.o, the closure of the roots:")
    out.extend(main_lines)
    n = lib_diffs + main_diffs
    out.append(f"differences: library {lib_diffs}, main.o {main_diffs}")
    out.append("NOT ESTABLISHED: timing identity (code and data addresses move, and with them cache placement)")
    if n == 0:
        out.append("RESULT: SAME -- 0 differences (the gate PASSES)")
        return out, 0
    out.append(f"RESULT: DIFFERENT -- {n} difference(s) (the gate FAILS)")
    return out, 1


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("reference")
    ap.add_argument("candidate")
    ap.add_argument("--extra-object", action="append", default=[], help="an object linked into the candidate only (the formatter)")
    ap.add_argument("--root", action="append", default=None, help=f"a root (default: {', '.join(DEFAULT_ROOTS)})")
    ap.add_argument("--report")
    a = ap.parse_args(argv)
    lines, rc = run(a.reference, a.candidate, a.extra_object, tuple(a.root) if a.root else DEFAULT_ROOTS)
    text = "\n".join(lines) + "\n"
    sys.stdout.write(text)
    if a.report:
        with open(a.report, "w", encoding="utf-8") as f:
            f.write(text)
    return rc


if __name__ == "__main__":
    sys.exit(main())
