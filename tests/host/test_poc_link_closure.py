"""
tests/host/test_poc_link_closure.py — every project function a POC's sources
call is defined in that POC's sources (GitHub Issue #84, the Orchestrator's
finding 1).

WHY IT EXISTS. Issue #59 made the shared service module call into the AUDIO
window (`gbp_awin_block`, `gbp_awin_note_ticks`, under `if (cfg->awin)`), and
four POCs whose SRCS do not name `gbp_awin.c` -- play-0001's, stream-0015's,
vstate's and color's -- stopped linking at HEAD. Nothing noticed for a whole
day of checkpoints: the physically executed images reproduce at their own
commits, nobody rebuilt them, and a full Docker build of every POC is far too
slow for the suite. It was found only because the drain image, play's SRCS
plus two, failed on exactly those two symbols.

WHAT IT CHECKS, STATICALLY. For every POC under poc/: resolve its SRCS through
its own `vpath`, strip comments and string literals, and collect (a) every
function DEFINED in those sources and in the headers under src/, and (b) every
call to a PROJECT function -- the prefixes the project owns: gbp_, hsp_backend_,
sdlog_, ringlog_, opengbp_. A call to a project function that no source of the
image defines is an unresolved symbol the linker will refuse, and it is a
finding here in a fraction of a second.

WHAT IT DOES NOT CHECK: libogc2's and newlib's symbols (the toolchain resolves
them, and a missing one would be a toolchain fault, not this class), and calls
through function pointers (`t->read_block(...)`), which name no symbol.
"""
import os
import re
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
POC = os.path.join(ROOT, "poc")
PROJECT_PREFIXES = ("gbp_", "hsp_backend_", "sdlog_", "ringlog_", "opengbp_")


def read(p):
    with open(p, encoding="utf-8", errors="replace") as f:
        return f.read()


def strip_c(text):
    """Comments and string / character literals out, line structure kept."""
    out, i, n = [], 0, len(text)
    while i < n:
        c = text[i]
        if text.startswith("/*", i):
            j = text.find("*/", i + 2)
            j = n if j < 0 else j + 2
            out.append("\n" * text.count("\n", i, j))
            i = j
        elif text.startswith("//", i):
            j = text.find("\n", i)
            i = n if j < 0 else j
        elif c in "\"'":
            j = i + 1
            while j < n and text[j] != c:
                j += 2 if text[j] == "\\" else 1
            out.append(c + c)
            i = j + 1
        else:
            out.append(c)
            i += 1
    return "".join(out)


DEF_RE = re.compile(r"^[A-Za-z_][\w \t\*]*?\b([a-z_][a-z0-9_]*)\s*\(([^;{}()]|\([^;{}()]*\))*\)\s*\{", re.M)
MACRO_RE = re.compile(r"^\s*#\s*define\s+([a-z_][a-z0-9_]*)\(", re.M)
CALL_RE = re.compile(r"(?<![\w>.])([a-z_][a-z0-9_]*)\s*\(")


def definitions(text):
    t = strip_c(text)
    return {m.group(1) for m in DEF_RE.finditer(t)} | {m.group(1) for m in MACRO_RE.finditer(text)}


def project_calls(text):
    t = strip_c(text)
    t = re.sub(r"^\s*#.*$", "", t, flags=re.M)          # preprocessor lines name no call
    return {m.group(1) for m in CALL_RE.finditer(t) if m.group(1).startswith(PROJECT_PREFIXES)}


def header_definitions():
    out = set()
    for d, _dirs, files in os.walk(os.path.join(ROOT, "src")):
        for fn in files:
            if fn.endswith(".h"):
                out |= definitions(read(os.path.join(d, fn)))
    return out


def poc_sources(poc_dir):
    mk = read(os.path.join(poc_dir, "Makefile"))
    m = re.search(r"^SRCS\s*:=\s*(.*)$", mk, re.M)
    if not m:
        return None
    vp = re.search(r"^vpath %\.c (.*)$", mk, re.M)
    dirs = [d.replace("$(CURDIR)", poc_dir).replace("$(ROOT)", ROOT) for d in vp.group(1).split()] if vp else [
        os.path.join(poc_dir, "source")]
    files = []
    for name in m.group(1).split():
        hit = [os.path.join(d, name) for d in dirs if os.path.isfile(os.path.join(d, name))]
        if not hit:
            raise AssertionError("%s: SRCS names %s and no vpath directory holds it" % (poc_dir, name))
        files.append(hit[0])
    return files


def unresolved(poc_dir, headers):
    files = poc_sources(poc_dir)
    if files is None:
        return None
    defined, called = set(headers), {}
    for f in files:
        text = read(f)
        defined |= definitions(text)
        for s in project_calls(text):
            called.setdefault(s, os.path.relpath(f, ROOT))
    return {s: where for s, where in called.items() if s not in defined}


class EveryPocLinksItsOwnProjectCalls(unittest.TestCase):

    def test_no_poc_calls_a_project_function_its_sources_do_not_define(self):
        headers = header_definitions()
        pocs = sorted(d for d in os.listdir(POC) if os.path.isfile(os.path.join(POC, d, "Makefile")))
        self.assertGreaterEqual(len(pocs), 15, pocs)
        bad = {}
        for p in pocs:
            u = unresolved(os.path.join(POC, p), headers)
            if u:
                bad[p] = u
        self.assertEqual(bad, {}, "POCs whose sources call project functions they never link: %r" % bad)


class TheCheckCatchesTheClassItWasWrittenFor(unittest.TestCase):
    """A guard that has never failed has never been shown to work (Issue #83)."""

    def test_the_59_shape_is_caught(self):
        headers = header_definitions()
        play = os.path.join(POC, "gbp-play-session")
        files = poc_sources(play)
        defined = set(headers)
        called = set()
        for f in files:
            if os.path.basename(f) == "gbp_awin.c":
                continue                                     # the image as it stood before the fix
            text = read(f)
            defined |= definitions(text)
            called |= project_calls(text)
        self.assertIn("gbp_awin_block", called - defined)
        self.assertIn("gbp_awin_note_ticks", called - defined)

    def test_calls_through_pointers_comments_and_strings_are_not_calls(self):
        text = ('/* gbp_nowhere(1); */ x = t->gbp_ptr(2); s = "gbp_str(3)"; y = a.gbp_member(4);\n'
                'int gbp_real(void) { return gbp_other(5); }\n')
        self.assertEqual(project_calls(text), {"gbp_real", "gbp_other"})
        self.assertEqual(definitions(text), {"gbp_real"})


if __name__ == "__main__":
    unittest.main()
