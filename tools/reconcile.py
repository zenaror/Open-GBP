#!/usr/bin/env python3
"""
tools/reconcile.py — the promotion sweep of GitHub Issue #29: which lines of the
consolidated pages rest on which evidence, side by side, for a person to read.

WHY. Consolidated pages in docs/hardware/ and docs/protocol/ drift from
docs/research/EVIDENCE.md, and the project has found it twice by accident:
Issue #17 found four Phase-2 pages UNDERSTATING what EVIDENCE already carried,
and Issue #26 found ARCHITECTURE.md's keypad plane CONTRADICTING GBP-KEY-001 /
GBP-KEY-005 on the polarity. Nothing in the process compared the two layers.

WHAT THIS IS, AND WHAT IT IS NOT. It is a REPORT. It prints, for the evidence
ids you name (or for the ids whose EVIDENCE entries changed since a commit),
every line of every consolidated page that cites them, with the page's own
status cell and EVIDENCE's status beside it. IT JUDGES NOTHING and it changes
nothing: a promotion checkpoint reads the output, records what it found —
including "nothing" — and escalates a genuine disagreement instead of editing a
page to match a guess (Issue #29's own rule).

WHY IT IS NOT A GATE, measured rather than assumed (2026-09-21): of 278 table
rows in the consolidated pages, only 44 carry BOTH a status letter and an id
EVIDENCE defines, and 8 of those 44 read "weaker" than their evidence under a
naive comparison. Every one of the 8 is CORRECT documentation: the rows carry
COMPOUND, ASPECT-SCOPED statuses -- "C (format and polarity: GBP-KEY-001,
GBP-KEY-005); F (hw, run-scoped)" -- while an EVIDENCE entry has one status for
one claim. Comparing a letter to a status is a category error, so a gate built
on it would be ~18 % false on the rows it can see and blind to the other 84 %.
It would be switched off within two checkpoints. A report a person reads at
promotion time is the honest mechanization; the CHEAP mechanical half that IS a
gate lives in tests/host/test_page_citations.py (every cited id must exist).

    tools/reconcile.py GBP-KEY-004 GBP-HW-270      one or more ids
    tools/reconcile.py --since 2e48ca7             the ids whose EVIDENCE entries changed since a commit
    tools/reconcile.py --all                       every id the pages cite
"""
import os
import re
import subprocess
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
EVIDENCE = os.path.join(ROOT, "docs", "research", "EVIDENCE.md")
UNKNOWNS = os.path.join(ROOT, "docs", "research", "UNKNOWNS.md")
PAGE_DIRS = (os.path.join(ROOT, "docs", "protocol"), os.path.join(ROOT, "docs", "hardware"))
ID = re.compile(r"\b((?:GBP|ENV)-[A-Z]+-\d{3}|U-(?:GBP|ENV)-\d{3})\b")
# families that name an EXPERIMENT (a test id), not a piece of evidence: they are defined in HARDWARE_TESTS.md
TEST_FAMILIES = ("VIDEO", "INIT", "AV", "PROBE", "BASELINE", "PLAY", "INPUT", "BBA")


def read(p):
    with open(p, encoding="utf-8") as f:
        return f.read()


STATUS_WORDS = r"\b(FACT|CORROBORATED|HYPOTHESIS|UNKNOWN|OPEN|CLOSED)\b"


def evidence_status():
    """id -> (status, the heading line) for everything EVIDENCE and UNKNOWNS define.

    The status of a recent entry is in its HEADING ("… — FACT"); an older one carries it in a
    `**Status:**` line in the body instead (e.g. GBP-CTL-001: "CORROBORATED for usage of 0x01-0x10;
    HYPOTHESIS for …"). The first sweep run in anger (GitHub Issue #46) printed "-" for every older
    entry it touched, which is honest but useless, so both places are read -- heading first, then the
    body line, and either one with more than one status word is reported as the whole phrase because
    a compound status is exactly what must not be collapsed to a letter.

    TWO WAYS THIS TOOL HANDED OUT A STALE OR HALF STATUS, both found by using it on Issue #48, where
    the job was to COPY statuses onto a consolidated page:

      * a HEADING can be compound too. GBP-HW-272 reads "FACT for the split; … is HYPOTHESIS", and
        taking the last word reported HYPOTHESIS, which is half of what the entry says.
      * an entry can carry a LATER AMENDMENT in its body. GBP-HW-272's amendment moved its second
        claim from HYPOTHESIS to CORROBORATED, and nothing in the heading says so, because this
        project amends on top instead of rewriting. A reader copying the heading would have carried
        a status the entry no longer holds.

    So a compound heading is reported whole, and an amended entry is flagged. The tool still judges
    nothing: it points at the entry and says "read the amendment before you copy".
    """
    out = {}
    for p in (EVIDENCE, UNKNOWNS):
        text = read(p)
        heads = list(re.finditer(r"^#{2,4} +((?:GBP|ENV)-[A-Z]+-\d{3}|U-(?:GBP|ENV)-\d{3})\b(.*)$", text, re.M))
        for i, m in enumerate(heads):
            body = text[m.end():heads[i + 1].start() if i + 1 < len(heads) else len(text)]
            first = re.search(STATUS_WORDS, m.group(2))
            if first:
                # from the FIRST status word to the end of the heading: "FACT" alone prints as
                # "FACT", while "FACT for the split … is HYPOTHESIS" prints as what it says
                status = _phrase(m.group(2)[first.start():])
            else:
                status = "-"
                b = re.search(r"^\*\*Status:\*\*(.+?)(?:\n\n|\Z)", body, re.M | re.S)
                if b and re.search(STATUS_WORDS, b.group(1)):
                    status = _phrase(b.group(1))
            if re.search(r"\*\*AMEND(MENT|ED)\b", body):
                status += "   [+ LATER AMENDMENT IN THE BODY -- read it before copying this status]"
            out[m.group(1)] = (status, m.group(0).strip())
    return out


def _phrase(s):
    """A compound status, verbatim and bounded -- never collapsed to one word."""
    phrase = re.sub(r"\s+", " ", s).strip().strip("-— ").rstrip(".")
    phrase = phrase.replace("**", "")
    return phrase if len(phrase) < 120 else phrase[:117] + "..."


def pages():
    for d in PAGE_DIRS:
        if not os.path.isdir(d):
            continue
        for fn in sorted(os.listdir(d)):
            if fn.endswith(".md"):
                yield os.path.join(d, fn)


def citations(ids):
    """(page, line number, line) for every consolidated-page line citing any of `ids`."""
    want = set(ids)
    for p in pages():
        for n, line in enumerate(read(p).splitlines(), 1):
            hit = {i for i in ID.findall(line) if i in want}
            if hit:
                yield os.path.relpath(p, ROOT), n, line.rstrip(), sorted(hit)


def ids_changed_since(commit):
    r = subprocess.run(["git", "-C", ROOT, "diff", "-U0", commit, "--", "docs/research/EVIDENCE.md"],
                       capture_output=True, text=True)
    if r.returncode != 0:
        sys.exit("git diff failed: " + r.stderr.strip())
    out = set()
    for line in r.stdout.splitlines():
        if line.startswith(("+", "-")) and not line.startswith(("+++", "---")):
            out.update(ID.findall(line))
    return sorted(out)


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    status = evidence_status()
    if not argv:
        print(__doc__.strip().split("\n\n")[-1])
        return 2
    if argv[0] == "--all":
        ids = sorted({i for _p, _n, _l, hits in citations(status) for i in hits})
    elif argv[0] == "--since":
        ids = ids_changed_since(argv[1])
    else:
        ids = argv
    ids = [i for i in ids if i.split("-")[1] not in TEST_FAMILIES or i in status]
    if not ids:
        print("no evidence id to sweep (nothing changed, or only test ids were named)")
        return 0
    print("RECONCILIATION SWEEP — %d id(s). This report JUDGES NOTHING: read each line, and record what you found,\n"
          "including \"nothing\". A genuine disagreement between a page and EVIDENCE is ESCALATED, never fixed by\n"
          "editing the page to match a guess (Issue #29).\n" % len(ids))
    for i in ids:
        st, heading = status.get(i, ("NOT DEFINED", "(no heading in EVIDENCE.md or UNKNOWNS.md)"))
        print("=" * 100)
        print("%s   EVIDENCE says: %s" % (i, st))
        print("   %s" % heading[:150])
        rows = [(p, n, l) for p, n, l, _h in citations([i])]
        if not rows:
            print("   cited by no consolidated page")
            continue
        for p, n, l in rows:
            print("   %-28s :%-5d %s" % (p, n, l.strip()[:160]))
    print("=" * 100)
    print("%d id(s) swept. Record the outcome in the checkpoint, including \"nothing found\"." % len(ids))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
