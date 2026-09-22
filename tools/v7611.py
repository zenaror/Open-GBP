#!/usr/bin/env python3
"""
tools/v7611.py — §V7.6.11's verdict constructions, executable, written BEFORE
RUN 21 / RUN 22's logs existed (GitHub Issue #50, 2026-09-22).

WHY THIS FILE EXISTS AND WHY IT IS DATED. §V7.6.11 froze its constructions
"so the ingestion cannot tune them to the data". Code written with a log open
beside it is exactly that tuning, and it is the kind nobody notices doing: a
construction that gives an awkward answer gets "fixed" until it gives a clean
one, and every step of that feels like debugging. So this module was written
from the frozen text alone, with no run data in reach, and its tests exercise
it on SYNTHETIC vectors only.

WHAT IT DOES NOT DO. It decides nothing. The gates of §V7.6.10 CLASSIFY a run
(admissible / INCONCLUSIVE for a named half) and this code reports that
classification; it never reports "pass" or "fail". Every function names the
part of §V7.6 it implements, and where the frozen text does not define
something, THIS MODULE REFUSES TO INVENT IT — see `PENDING_AMENDMENT` and the
docstring of `question_K`.

THE BIT MAP is not re-derived here. §V7.4 made it a physical FACT (hw,
run-scoped): bits 0-7 are A, B, SELECT, START, RIGHT, LEFT, UP, DOWN in the
KEYINPUT order, bit 8 is L and bit 9 is R — the reverse of KEYINPUT's 8/9,
as every reference writes it (`docs/protocol/INPUT.md`, GBP-KEY-004,
GBP-HW-267/269/270). A KEY record consistent with it adds a sample and
promotes nothing.
"""
import re

SECTION = "docs/research/HARDWARE_TESTS.md §V7.6"

# ---------------------------------------------------------------- the key map
# c(b): "the descriptor's key for bit b (§V7.4, FACT)" — §V7.6.11
C = {0: "A", 1: "B", 2: "SELECT", 3: "START", 4: "RIGHT", 5: "LEFT",
     6: "UP", 7: "DOWN", 8: "L", 9: "R"}
BIT = dict((k, b) for b, k in C.items())
START_BIT = BIT["START"]

# §V7.6.9's deliberate head, steps 2-12, as the list froze them. This is the
# only segment of the session whose press sequence the frozen text locates
# without ambiguity: it begins at the first rising edge of START (§V7.6.11's
# cut-off) and it is scripted press for press.
HEAD_STEPS = (
    (2, "START", 1), (3, "A", 2), (4, "DOWN", 2), (5, "UP", 1), (6, "RIGHT", 3),
    (7, "LEFT", 2), (8, "B", 2), (9, "L", 1), (10, "R", 1), (11, "SELECT", 1), (12, "A", 1),
)
HEAD_SEQUENCE = tuple(k for _, k, n in HEAD_STEPS for _ in range(n))
# §V7.6.9 step 15, the closing sweep, in its frozen order
SWEEP_SEQUENCE = ("START", "A", "DOWN", "UP", "RIGHT", "LEFT", "B", "L", "R", "SELECT")

PENDING_AMENDMENT = "PENDING_AMENDMENT"   # see question_K.__doc__

KEY_RE = re.compile(
    r"KEY n=(?P<n>\d+) act=(?P<act>\S+) keys=(?P<keys>[0-9a-f]{4}) word=(?P<word>[0-9a-f]{4}) "
    r"t_poll=(?P<t_poll>[0-9a-f]+) t_attempt=(?P<t_attempt>[0-9a-f]+) t_done=(?P<t_done>[0-9a-f]+) "
    r"xfer=(?P<xfer>\d+) rc=(?P<rc>\S+)")


class KeyLine(object):
    __slots__ = ("n", "act", "keys", "word", "t_poll", "t_attempt", "t_done", "xfer", "rc")

    def __init__(self, **kw):
        for s in self.__slots__:
            setattr(self, s, kw[s])

    def __repr__(self):
        return "KEY(n=%d act=%s word=%04x rc=%s)" % (self.n, self.act, self.word, self.rc)


# ------------------------------------------------------------------ parsing
def parse_key_lines(text):
    """Every `KEY` line of a log, in file order (§V7.6.10's KEY RECORD gate).

    Returns (lines, problems). A line that does not match the runtime's own
    format (GBP_INPUT_EVENT_FMT) is a problem, not a silent skip.
    """
    lines, problems = [], []
    for raw in text.splitlines():
        if " KEY n=" not in raw and not raw.startswith("KEY n="):
            continue
        m = KEY_RE.search(raw)
        if not m:
            problems.append("unparsable KEY line: " + raw.strip()[:120])
            continue
        g = m.groupdict()
        lines.append(KeyLine(n=int(g["n"]), act=g["act"], keys=int(g["keys"], 16),
                             word=int(g["word"], 16), t_poll=int(g["t_poll"], 16),
                             t_attempt=int(g["t_attempt"], 16), t_done=int(g["t_done"], 16),
                             xfer=int(g["xfer"]), rc=g["rc"]))
    return lines, problems


def completed_words(lines):
    """§V7.6.11: "a KEY line counts only with rc=ok; the completed words in n order from 0000".

    The sequence BEGINS at 0000, the all-released state, which is what "from
    0000" says. In practice the runtime's own first line is `act=first` with
    `word=0000` and the prepended value is a duplicate that carries no edge; it
    matters only when that line is absent, and then the conservative reading is
    the one the frozen text gives.
    """
    ok = sorted((l for l in lines if l.rc == "ok"), key=lambda l: l.n)
    return [0x0000] + [l.word for l in ok]


def rising_edges(words):
    """R_b — §V7.6.11: "R_b = the rising edges of word bit b".

    Returns {bit: [index of the word in which the bit rose]}. Index 0 is the
    implicit 0000 the sequence starts from, so an edge index is >= 1.
    """
    out = dict((b, []) for b in C)
    for i in range(1, len(words)):
        rose = words[i] & ~words[i - 1]
        for b in C:
            if rose & (1 << b):
                out[b].append(i)
    return out


def press_sequence(words):
    """§V7.6.11's PRESS SEQUENCE, with its cut-off.

    "the ordered rising edges of the word bits across the completed KEY lines,
    with any menu-launch presses cut off at the first rising edge of the bit of
    START (step 2, the list's first key)".

    Returns (sequence, started) where sequence is [(word index, key name)] from
    the first rising edge of START onward, and `started` is False when START
    never rose — in which case the list was never started, which §V7.6.11's K
    reads as INCONCLUSIVE and §V7.6.10's THE LIST reads as a list cut short.
    The empty sequence is NOT a decision made here; it is the input to those.
    """
    edges = []
    for i in range(1, len(words)):
        rose = words[i] & ~words[i - 1]
        for b in sorted(C):
            if rose & (1 << b):
                edges.append((i, C[b]))
    first = next((j for j, (_, k) in enumerate(edges) if k == "START"), None)
    if first is None:
        return [], False
    return edges[first:], True


def per_bit_counts(sequence):
    """Counts per bit — §V7.6.11 reports step 13's words this way, never press for press."""
    out = dict((k, 0) for k in BIT)
    for _, k in sequence:
        out[k] += 1
    return out


# ------------------------------------------------- §V7.6.10 admissibility gates
def gate_reports(records, key_lines, key_problems):
    """§V7.6.10's gates, AS CHECKS THAT REPORT. They classify; they never pass or fail.

    `records` is {record name: {field: value}} read from the log's summary
    records. Every gate returns (met, [reasons]), and the caller decides
    nothing — §V7.6.10 already says what an unmet gate makes INCONCLUSIVE, and
    that scope is carried in `scope`.
    """
    def g(name, cond, why, scope):
        return {"gate": name, "met": bool(cond), "why": list(why), "scope": scope}

    out = []
    h = records.get("header", {})
    ident = [k for k, v in (("test_id", "GBP-PLAY-001"), ("build_id", "play-0001"),
                            ("commit", "2e48ca7")) if h.get(k) != v]
    missing = [r for r in ("COUNTERS", "INPUT", "INPUTT", "KEYLOG", "SESSION", "STREAMPUMP",
                           "STREAMPUMPT", "STARTUP", "STARTUPT", "STARTUPV") if r not in records]
    out.append(g("IDENTITY / LOG",
                 not ident and not missing and h.get("dropped") == 0 and h.get("truncated") == 0,
                 (["identity: " + ", ".join(ident)] if ident else []) +
                 (["records missing: " + ", ".join(missing)] if missing else []) +
                 (["dropped=%s" % h.get("dropped")] if h.get("dropped") else []) +
                 (["truncated=%s" % h.get("truncated")] if h.get("truncated") else []),
                 "whatever the dropped lines carried, named"))

    k = records.get("KEYLOG", {})
    ns = [l.n for l in key_lines]
    monotonic = all(b - a == 1 for a, b in zip(ns, ns[1:])) if len(ns) > 1 else True
    out.append(g("KEY RECORD",
                 k.get("events") == k.get("emitted") and not k.get("lost") and not k.get("truncated")
                 and not k.get("overwritten") and not key_problems and monotonic,
                 (["lost=%s" % k.get("lost")] if k.get("lost") else []) +
                 (["truncated=%s" % k.get("truncated")] if k.get("truncated") else []) +
                 (["overwritten=%s" % k.get("overwritten")] if k.get("overwritten") else []) +
                 (["events=%s emitted=%s" % (k.get("events"), k.get("emitted"))]
                  if k.get("events") != k.get("emitted") else []) +
                 (["n is not increasing by one"] if not monotonic else []) + key_problems,
                 "the machine half of Question A (the SENT / NOT SENT decomposition and K)"))

    c = records.get("COUNTERS", {})
    s = records.get("STATS", {})
    balanced = (c.get("acks") == c.get("rearms") == c.get("unmasks") == c.get("deliveries")
                and c.get("isr_w1c") == c.get("deliveries"))
    clean = (not c.get("errors") and c.get("transport_ok") == 1 and not s.get("timeouts")
             and not s.get("busy") and not c.get("overflow") and not c.get("uncertain")
             and c.get("restore_ok") == 1 and balanced)
    out.append(g("TRANSPORT", clean,
                 [] if clean else ["the accounting is not clean"],
                 "THIS GATE IS QUESTION T's FAULT LINE (§V7.6.10): a run that fails it is T = FAULT, a RESULT"))

    out.append(g("STARTUP", records.get("STARTUP", {}).get("mode") == "normal",
                 [] if records.get("STARTUP", {}).get("mode") == "normal"
                 else ["mode=%s" % records.get("STARTUP", {}).get("mode")],
                 "recorded, no tolerance invented"))

    i = records.get("INPUT", {})
    inp = (i.get("selftest") == 1 and i.get("steps", 0) > 0 and i.get("attempts", 0) > 0
           and i.get("completed") == i.get("attempts") and not i.get("failed")
           and i.get("first") == 1 and i.get("refresh", 0) > 0 and i.get("change", 0) >= 10)
    out.append(g("INPUT (machine)", inp,
                 [] if inp else ["a retry that COMPLETED is not a failure (§V7.6.10)"],
                 "the machine half"))

    ses = records.get("SESSION", {})
    ended = (ses.get("stop") == "session_end" and ses.get("status") == "ok_session_ended"
             and ses.get("teardown") == "S5_session_end")
    out.append(g("SESSION", ended,
                 [] if ended else ["stop=%s status=%s teardown=%s" %
                                   (ses.get("stop"), ses.get("status"), ses.get("teardown"))],
                 "the session gate ALONE -- not W, S or T, which read what happened before the end"))
    return out


def gate(reports, name):
    return next(r for r in reports if r["gate"] == name)


# ---------------------------------------------------------------- Question A
def question_A_W(report, edges, sequence_keys, admissible_machine_half):
    """W, per key — §V7.6.11.

    `report` is the Operator's channel: {key: "RESPONDED" | "NO RESPONSE" |
    "OTHER" | "N/A" | None}, read literally and never paraphrased into a
    verdict. `edges` is R_b keyed by bit. `sequence_keys` is the set of keys
    the press sequence actually carries (a key never reached is INCONCLUSIVE).

    N/A IS MACHINE-CHECKABLE, and §V7.6.11 makes that explicit: N/A "requires
    the KEY record to show the word was sent". A reported N/A whose bit never
    rose is NOT N/A here; it is reported as the contradiction it is.
    """
    out = {}
    for key, bit in sorted(BIT.items(), key=lambda kv: kv[1]):
        rose = len(edges.get(bit, []))
        said = report.get(key)
        if not admissible_machine_half:
            out[key] = ("INCONCLUSIVE", "the run is inadmissible for the machine half (§V7.6.10)")
        elif said in (None, "", "UNCERTAIN"):
            # §V7.6.11's two INCONCLUSIVE clauses meet here and are reported together, because
            # they are the same observation from two ends: he did not report on this key, which
            # is what a key the list never reached looks like in his channel.
            out[key] = ("INCONCLUSIVE",
                        "his report is missing or uncertain for this key" +
                        ("" if key in sequence_keys else ", and the key never appears in the press "
                                                         "sequence (the list may have been cut short)"))
        elif said == "RESPONDED":
            out[key] = ("WORKS", "R_b = %d > 0" % rose) if rose > 0 else (
                "INCONCLUSIVE", "he reports RESPONDED but R_b = 0: the two channels disagree, named per §V7.6.11")
        elif said == "N/A":
            out[key] = ("N/A", "R_b = %d: the pad and the runtime did their part" % rose) if rose > 0 else (
                "INCONCLUSIVE",
                "N/A REQUIRES the KEY record to show the bit rose (§V7.6.11); it did not, so this is not N/A")
        elif said == "NO RESPONSE":
            out[key] = (("DOES NOT WORK / SENT",
                         "R_b = %d rose as expected: the failure is DOWNSTREAM of the word" % rose)
                        if rose > 0 else
                        ("DOES NOT WORK / NOT SENT",
                         "R_b = 0: the press never became a word; the failure is UPSTREAM"))
        elif said == "OTHER":
            out[key] = ("OTHER", "recorded in his words; R_b = %d" % rose)
        else:
            out[key] = ("INCONCLUSIVE", "unrecognised report %r" % said)
    return out


def spurious(sequence, expected):
    """SPURIOUS — §V7.6.11: "a rising edge of a key the list did not press at that point".

    Compared against `expected`, the scripted key order for the segment being
    read. Named per bit; informative; never a failed run.
    """
    out = []
    exp = list(expected)
    for idx, key in sequence:
        if exp and exp[0] == key:
            exp.pop(0)
            continue
        out.append({"word_index": idx, "key": key, "bit": BIT[key],
                    "note": "a rising edge the list did not press at that point"})
    return out


def question_A_S(w_a, w_b, report_a, report_b, k_verdict, same_instrument):
    """S, per key — §V7.6.11. SAME requires BOTH reports to agree in kind AND K to agree."""
    out = {}
    for key in sorted(BIT, key=lambda k: BIT[k]):
        if not same_instrument:
            out[key] = ("INCONCLUSIVE", "a different cartridge or boot path between the runs")
            continue
        ra, rb = report_a.get(key), report_b.get(key)
        if ra in (None, "", "UNCERTAIN") or rb in (None, "", "UNCERTAIN"):
            out[key] = ("INCONCLUSIVE", "his report is missing for this key in one of the runs")
        elif "INCONCLUSIVE" in (w_a.get(key, ("INCONCLUSIVE",))[0], w_b.get(key, ("INCONCLUSIVE",))[0]):
            out[key] = ("INCONCLUSIVE", "one run is missing or inadmissible for this key")
        elif ra != rb:
            out[key] = ("DIFFERENT", "reported %s on one pad and %s on the other" % (ra, rb))
        elif k_verdict not in ("AGREE", "EXPLAINED"):
            out[key] = ("DIFFERENT", "K = %s: the press sequences differ" % k_verdict)
        else:
            out[key] = ("SAME", "both reports %s, and K = %s" % (ra, k_verdict))
    return out


def question_K_head(seq_a, seq_b):
    """K over the DELIBERATE HEAD (steps 2-12) — the segment §V7.6.11 locates without ambiguity.

    "AGREE: identical press sequences over the common prefix of the list."
    Compared as key names, over the common prefix, which is what a list cut
    short in one run leaves (§V7.6.10, THE LIST).
    """
    a = [k for _, k in seq_a][:len(HEAD_SEQUENCE)]
    b = [k for _, k in seq_b][:len(HEAD_SEQUENCE)]
    n = min(len(a), len(b))
    if n == 0:
        return {"verdict": "INCONCLUSIVE", "why": "the list was not started in at least one run",
                "common_prefix": 0}
    if a[:n] == b[:n]:
        return {"verdict": "AGREE", "why": "identical over the common prefix of %d presses" % n,
                "common_prefix": n}
    diff = next(i for i in range(n) if a[i] != b[i])
    return {"verdict": "DIFFERENT", "common_prefix": n,
            "why": "first difference at press %d: %s against %s" % (diff + 1, a[diff], b[diff]),
            "note": "EXPLAINED requires the Operator's report to explain it (§V7.6.11); this code does not decide that"}


def question_K(seq_a, seq_b):
    """K over steps 2-12, 14 and 15 — NOT IMPLEMENTED, BY REFUSAL. See Issue #50's report.

    §V7.6.11 says K "is compared over steps 2-12, 14 and 15, the scripted
    parts, and step 13's words are reported as counts per bit and never
    compared press for press". Steps 14 and 15 come AFTER step 13's several
    minutes of ordinary play, whose number of presses is unbounded and
    unscripted, and **the frozen text gives no machine rule for locating the
    boundary between step 13 and step 14 in a KEY record**. Neither does
    §V7.6.9, which defines the steps for the Operator and not for a parser.

    Any rule this module invented — match the trailing twelve presses, split on
    an inter-press time gap, trust the Operator's step numbering — would be a
    construction chosen after the freeze, which is precisely what §V7.6.11
    exists to prevent, and §V7.6.3 separately refuses thresholds "invented
    after the fact".

    So this returns PENDING_AMENDMENT. `question_K_head` implements the part
    that IS defined and is used meanwhile; the pair's reading over 14 and 15
    waits for a dated pre-hardware amendment from the Orchestrator.
    """
    return {"verdict": PENDING_AMENDMENT,
            "why": "§V7.6.11 compares K over steps 2-12, 14 and 15, and the frozen text gives no machine "
                   "rule for finding where step 13's ordinary play ends. Reported, not resolved (Issue #50).",
            "head": question_K_head(seq_a, seq_b)}


# ---------------------------------------------------------------- Question T
def question_T(records, reference, reports):
    """NOMINAL / ANOMALOUS / FAULT — §V7.6.11, reading the machine records only.

    `reference` carries RUN 17's figures (§V7.6.3) and is supplied by the
    caller: this module holds no run data. T never reads the Operator's
    channel — "a game that played badly with a clean transaction is an A
    result, not a T result" (§V7.6.10).
    """
    transport = gate(reports, "TRANSPORT")
    c = records.get("COUNTERS", {})
    extra_fault = []
    if records.get("CYCA"):
        extra_fault.append("an anomaly record (CYCA) was written")
    if c.get("main_w1c"):
        extra_fault.append("main_w1c = %s (PI stickiness)" % c["main_w1c"])
    if c.get("reentry"):
        extra_fault.append("a re-entry")
    if c.get("next_cause_at_end") == 0:
        extra_fault.append("next_cause_at_end = 0")
    if records.get("SERVICE", {}).get("status") not in (None, "ok"):
        extra_fault.append("service status %s" % records["SERVICE"]["status"])
    if not transport["met"] or extra_fault:
        return {"verdict": "FAULT", "why": transport["why"] + extra_fault,
                "note": "a RESULT, not a failed run (§V7.6.11): the first measurement of a change made "
                        "deliberately in Issue #39 and recorded as unchecked"}

    moved = []
    vg, vg_ref = records.get("video_ack_rearm_ticks"), reference.get("video_ack_rearm_ticks")
    if vg is not None and vg_ref is not None and vg > vg_ref:
        moved.append("the ACK -> RE-ARM gap of the VIDEO cycles is LONGER than RUN 17's shape (%s vs %s)" % (vg, vg_ref))
    dr, dr_ref = records.get("delivery_rate"), reference.get("delivery_rate")
    if dr is not None and dr_ref is not None and dr < dr_ref:
        moved.append("the delivery rate is LOWER than RUN 17's (%s vs %s)" % (dr, dr_ref))
    ag, ag_ref = records.get("audio_ack_rearm_ticks"), reference.get("audio_ack_rearm_ticks")
    if ag is not None and ag_ref is not None and ag != ag_ref:
        moved.append("the AUDIO-only gap moved (%s vs RUN 17's %s), which the removal does not predict" % (ag, ag_ref))
    sp, sp_ref = records.get("skipped_cause_pending_pct"), reference.get("skipped_cause_pending_pct")
    if sp is not None and sp_ref is not None and sp != sp_ref:
        moved.append("skipped_cause_pending %.1f%% against RUN 17's %.1f%% -- reported with both figures and "
                     "NO threshold invented after the fact" % (sp, sp_ref))
    if records.get("keylog_retry"):
        moved.append("KEYLOG retries where RUN 17 had none")
    if moved:
        return {"verdict": "ANOMALOUS", "why": moved,
                "note": "the accounting is clean; a magnitude is not a verdict (§V7.6.11)"}
    return {"verdict": "NOMINAL",
            "why": ["the accounting is clean and every quantity the removal predicts a direction for moved "
                    "in that direction or not at all"]}


def one_interaction(t_verdict, session_completed):
    """§V7.6.10's ONE interaction between the two questions, in its four stated cases."""
    if t_verdict == "FAULT" and not session_completed:
        return {"A": "INCONCLUSIVE",
                "why": "T = FAULT and the run had no session: there was nothing to play and nothing to judge. "
                       "Stated as such, never as \"the game failed\"."}
    if t_verdict == "FAULT" and session_completed:
        return {"A": "READ ON ITS OWN RECORDS, UNCHANGED", "context": "a service anomaly (T = FAULT)",
                "why": "the fault is recorded in A's table as CONTEXT and is NEVER A's verdict"}
    return {"A": "UNTOUCHED", "why": "T = %s leaves Question A untouched" % t_verdict}
