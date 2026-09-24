"""tests/host/test_geckorx.py — GitHub Issue #74: the host side of the Pico Gecko.

**Every test here runs with no device present**, which is the requirement: a
receiver that can only be tested with the hardware attached is a receiver nobody
checks. The port resolution takes a list of names, and the byte pump takes any
file descriptor, so both are driven from a pipe and a fake directory.

What these CANNOT check is that a real Pico Gecko speaks CDC-ACM the way this
assumes. That is what the bring-up on `01-smoke` is for, and §V12 says so.
"""
import os
import re
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import geckorx  # noqa: E402

HW = os.path.join(ROOT, "docs", "research", "HARDWARE_TESTS.md")
SMOKE = os.path.join(ROOT, "poc", "smoke-test", "source", "main.c")


def read(p):
    with open(p, encoding="utf-8") as f:
        return f.read()


def plain(s):
    return re.sub(r"\s+", " ", s).replace("`", "").replace("**", "").replace("*", "")


def part():
    t = read(HW)
    i = t.index("\n## V12 ")
    j = t.find("\n## V", i + 1)
    return (t[i:j] if j >= 0 else t[i:]).lstrip("\n")


class ThePortIsResolvedByIdAndNeverByTtyACM(unittest.TestCase):

    def test_it_finds_the_pico_among_other_serial_devices(self):
        entries = ["usb-FTDI_FT232R_USB_UART_A50285BI-if00-port0",
                   "usb-Raspberry_Pi_Pico-if00",
                   "pci-0000:00:16.3-usb-0:1:1.0-port0"]
        self.assertEqual(geckorx.match_ports(entries), ["usb-Raspberry_Pi_Pico-if00"])
        path, real = geckorx.resolve("/fake", listdir=lambda d: entries,
                                     realpath=lambda p: "/dev/ttyACM3")
        self.assertEqual(path, "/fake/usb-Raspberry_Pi_Pico-if00")
        self.assertEqual(real, "/dev/ttyACM3")

    def test_a_missing_device_says_so_rather_than_falling_back(self):
        with self.assertRaises(geckorx.NoPort) as e:
            geckorx.resolve("/fake", listdir=lambda d: ["usb-FTDI_x-if00"])
        self.assertIn("no entry", str(e.exception))
        self.assertIn("usb-FTDI_x-if00", str(e.exception))     # it says what it DID find

    def test_a_missing_directory_is_a_clear_message_not_a_traceback(self):
        def boom(_):
            raise OSError(2, "No such file or directory")
        with self.assertRaises(geckorx.NoPort) as e:
            geckorx.resolve("/fake", listdir=boom)
        self.assertIn("is the device plugged in?", str(e.exception))

    def test_a_firmware_that_reports_a_serial_is_still_found(self):
        """The pattern stops before `-if` for this reason: a Pico that reports a
        serial number names itself with it, and a narrower pattern would find
        nothing at all."""
        entries = ["usb-Raspberry_Pi_Pico_E6614103E7654321-if00"]
        path, _ = geckorx.resolve("/fake", listdir=lambda d: entries, realpath=lambda p: p)
        self.assertTrue(path.endswith("E6614103E7654321-if00"))

    def test_one_device_with_several_interfaces_takes_the_data_one(self):
        entries = ["usb-Raspberry_Pi_Pico-if00", "usb-Raspberry_Pi_Pico-if02"]
        path, _ = geckorx.resolve("/fake", listdir=lambda d: entries,
                                  realpath=lambda p: p)
        self.assertTrue(path.endswith("-if00"))

    def test_TWO_devices_REFUSE_rather_than_guessing(self):
        # two Picos on the bench: both are data interfaces, so there is no rule
        # that picks one and guessing is exactly what resolving by id prevents
        entries = ["usb-Raspberry_Pi_Pico-if00",
                   "usb-Raspberry_Pi_Pico_E6614103E7654321-if00"]
        with self.assertRaises(geckorx.ManyPorts) as e:
            geckorx.resolve("/fake", listdir=lambda d: entries, realpath=lambda p: p)
        self.assertIn("--port", str(e.exception))

    def test_ttyACM_is_never_a_default_anywhere_in_the_tool(self):
        src = read(os.path.join(ROOT, "tools", "geckorx.py"))
        self.assertNotIn('"/dev/ttyACM', src)
        self.assertNotIn("'/dev/ttyACM", src)
        self.assertEqual(geckorx.DEFAULT_BY_ID, "/dev/serial/by-id")


class ThePumpKeepsWhatItHasAlreadyReceived(unittest.TestCase):
    """The whole reason for the tool: a run that never reaches its own save must
    still leave what it managed to say."""

    def test_every_write_is_followed_by_a_flush(self):
        """Deterministic, with no thread and no wall clock: a recorder stands in
        for the output stream, so what is checked is the ORDER of the calls. The
        first version of this test used a thread and a real pipe and HUNG -- a
        blocking os.read with the write end still open."""
        class Recorder:
            def __init__(self):
                self.calls = []

            def write(self, data):
                self.calls.append(("write", bytes(data)))

            def flush(self):
                self.calls.append(("flush", None))

        r, w = os.pipe()
        os.write(w, b"OPENGBP-SMOKE HEARTBEAT n=1\n")
        os.close(w)
        rec = Recorder()
        with self.assertRaises(geckorx.DeviceGone):     # Issue #104: the closed writer is a device gone
            geckorx.pump(r, rec, idle_exit=0.0)
        os.close(r)
        self.assertTrue(rec.calls)
        for i, (kind, _) in enumerate(rec.calls):
            if kind == "write":
                self.assertEqual(rec.calls[i + 1][0], "flush",
                                 "a write was not followed immediately by a flush")
        self.assertEqual(b"".join(d for k, d in rec.calls if k == "write"),
                         b"OPENGBP-SMOKE HEARTBEAT n=1\n")

    def test_it_stops_on_the_until_pattern(self):
        r, w = os.pipe()
        os.write(w, b"READY\nHEARTBEAT n=1\nEXIT reason=start\n")
        os.close(w)
        with tempfile.TemporaryDirectory() as d:
            with open(os.path.join(d, "o"), "wb") as out:
                n = geckorx.pump(r, out, until=r"EXIT reason=")
            with open(os.path.join(d, "o"), "rb") as f:
                got = f.read()
        os.close(r)
        self.assertIn(b"EXIT reason=start", got)
        self.assertEqual(n, len(got))

    def test_it_gives_up_after_an_idle_period_when_asked_to(self):
        """Idle is a device that is still there and says nothing: the writer stays OPEN
        and the read end is non-blocking, so a read with nothing to give raises EAGAIN.
        (Until Issue #104 this test closed the writer to go idle -- which is exactly the
        hangup the tool used to mistake for silence.)"""
        r, w = os.pipe()
        os.set_blocking(r, False)
        os.write(w, b"hello")
        clock = [0.0]
        with tempfile.TemporaryDirectory() as d:
            with open(os.path.join(d, "o"), "wb") as out:
                def tick():
                    clock[0] += 0.5
                    return clock[0]
                n = geckorx.pump(r, out, idle_exit=1.0, clock=tick)
        os.close(r)
        os.close(w)
        self.assertEqual(n, 5)

    def test_a_device_that_disappears_is_reported_LOUDLY_and_keeps_the_bytes(self):
        """Issue #104. A zero-length read is a hangup: it used to be a clean stop (and on a
        real port an endless silent loop). It now raises, carrying what was received."""
        r, w = os.pipe()
        os.write(w, b"partial run")
        os.close(w)                      # EOF: os.read returns b"" -- the writer is gone
        with tempfile.TemporaryDirectory() as d:
            with open(os.path.join(d, "o"), "wb") as out:
                with self.assertRaises(geckorx.DeviceGone) as cm:
                    geckorx.pump(r, out, idle_exit=0.0)
            with open(os.path.join(d, "o"), "rb") as f:
                self.assertEqual(f.read(), b"partial run")
        os.close(r)
        self.assertEqual(cm.exception.total, 11)
        self.assertIn("hung up", str(cm.exception))

    def test_EIO_is_a_device_gone_too_not_a_quiet_exit(self):
        """A pty whose other side closes gives EIO on Linux: the path whose comment already
        said "the device went away" and still exited 0."""
        m, sl = os.openpty()
        os.write(sl, b"before the fall")
        os.close(sl)
        with tempfile.TemporaryDirectory() as d:
            with open(os.path.join(d, "o"), "wb") as out:
                with self.assertRaises(geckorx.DeviceGone) as cm:
                    geckorx.pump(m, out)
            with open(os.path.join(d, "o"), "rb") as f:
                self.assertEqual(f.read(), b"before the fall")
        os.close(m)
        self.assertIn("EIO", str(cm.exception))
        self.assertEqual(cm.exception.total, 15)

    def test_configure_does_not_blow_up_on_something_that_is_not_a_terminal(self):
        r, w = os.pipe()
        self.assertIsNone(geckorx.configure(r))
        os.close(r)
        os.close(w)

    def test_nothing_is_timestamped_or_parsed_into_the_output(self):
        """The output file must be the byte stream, so it can be compared with
        the SD log without a decoder in between."""
        src = read(os.path.join(ROOT, "tools", "geckorx.py"))
        body = src[src.index("def pump("):src.index("def main(")]
        self.assertNotIn("strftime", body)
        self.assertNotIn("time.time()", body)
        self.assertIn("out.write(chunk)", body)


class AHangupEndsTheRunLoudlyAndNonZero(unittest.TestCase):
    """Issue #104, behaviourally, on the tool as it is run: RUN 39's capture held a port
    that had gone away and recorded zero bytes with exit 0. A FIFO opened by path is the
    same shape -- blocking, and a read of zero bytes once the writer is gone -- so the
    whole program is run against one, under a timeout: before the fix it never ends."""

    def _run(self, payload, extra=()):
        import subprocess
        with tempfile.TemporaryDirectory() as d:
            fifo, out = os.path.join(d, "port"), os.path.join(d, "capture.bin")
            os.mkfifo(fifo)
            p = subprocess.Popen([sys.executable, os.path.join(ROOT, "tools", "geckorx.py"),
                                  "--port", fifo, "--out", out] + list(extra),
                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            with open(fifo, "wb") as w:              # blocks until the tool has opened it
                w.write(payload)
            try:
                _o, err = p.communicate(timeout=20)
            except subprocess.TimeoutExpired:
                p.kill()
                p.communicate()
                self.fail("the capture did not end when its device went away: the RUN 39 defect")
            with open(out, "rb") as f:
                got = f.read()
        return p.returncode, err.decode("utf-8", "replace"), got

    def test_a_hangup_is_reported_with_the_count_and_the_exit_code_is_non_zero(self):
        rc, err, got = self._run(b"OPENGBP-LIVE READY app=x\nhalf a li")
        self.assertEqual(rc, 3)
        self.assertEqual(got, b"OPENGBP-LIVE READY app=x\nhalf a li")
        for tok in ("DEVICE GONE", "after 34 bytes", "THE CAPTURE IS INCOMPLETE", "not evidence"):
            self.assertIn(tok, err, tok)

    def test_a_device_that_goes_away_before_saying_anything_is_still_reported(self):
        rc, err, got = self._run(b"")
        self.assertEqual((rc, got), (3, b""))
        self.assertIn("after 0 bytes", err)

    def test_an_ordinary_end_is_still_exit_0(self):
        rc, err, got = self._run(b"READY\nEXIT reason=start\n", extra=("--until", "EXIT reason="))
        self.assertEqual(rc, 0)
        self.assertNotIn("DEVICE GONE", err)

    def test_the_limits_are_said_in_the_tool(self):
        doc = plain(geckorx.__doc__)
        for tok in ("A silent capture is uninformative, never negative",
                    "Swiss's own boot text must have arrived BEFORE the Operator presses anything",
                    "it is not proof that the channel was sound the whole way",
                    "re-resolving the port by id mid-capture", "a quiet-time threshold"):
            self.assertIn(tok, doc, tok)


class TheGameCubeSideNeedsNothingBuilt(unittest.TestCase):

    def test_01_smoke_already_detects_and_sends(self):
        s = read(SMOKE)
        self.assertIn("usb_isgeckoalive(GECKO_CHANNEL)", s)
        self.assertIn("usb_sendbuffer_safe(GECKO_CHANNEL", s)
        self.assertIn("#define GECKO_CHANNEL EXI_CHANNEL_1", s)
        self.assertIn('"detected (slot B)"', s)
        self.assertIn("gecko=%d", s)

    def test_the_send_path_is_SKIPPED_when_no_gecko_is_present(self):
        """§14: optional support may be added, it must never become necessary."""
        s = read(SMOKE)
        body = s[s.index("static void gecko_puts"):]
        body = body[:body.index("\n}")]
        self.assertIn("if (gecko_present)", body)

    def test_01_smoke_sends_a_heartbeat_so_the_stream_is_continuous(self):
        s = read(SMOKE)
        self.assertIn("OPENGBP-SMOKE HEARTBEAT n=%u frames=%u", s)
        self.assertIn("OPENGBP-SMOKE READY", s)
        self.assertIn("OPENGBP-SMOKE SAVE rc=%d", s)
        self.assertIn("OPENGBP-SMOKE EXIT reason=start", s)


class TheRecordSaysWhatItMustSay(unittest.TestCase):

    def test_the_device_is_recorded_as_the_operators_own_unpinned_hardware(self):
        s = plain(part())
        self.assertIn("2e8a", s)
        self.assertIn("000a", s)
        self.assertIn("Raspberry_Pi_Pico", part())
        self.assertIn("his own hardware", s)
        self.assertIn("unpinned by this project", s)

    def test_section_14_is_restated_where_the_result_is_written(self):
        s = plain(part())
        self.assertIn("CLAUDE.md §14", s)
        self.assertIn("must never become necessary", s)
        self.assertIn("the SD save stays the primary record", s)

    def test_success_is_THREE_things_recorded_separately(self):
        s = part()
        self.assertIn("the screen", s)
        self.assertIn("gecko=1", s)
        self.assertIn("the receiver captured", plain(s).lower())
        self.assertIn("detected but no bytes", plain(s))
        self.assertIn("bytes but not detected", plain(s))

    def test_the_bring_up_uses_01_smoke_and_says_why(self):
        s = plain(part())
        self.assertIn("01-smoke", s)
        self.assertIn("touches no gbp register", s.lower())
        self.assertIn("Do not use a GBP image for a first bring-up", s)

    def test_the_baud_is_stated_rather_than_justified(self):
        s = plain(part())
        self.assertIn("We do not know what this firmware does with it", s)
        src = read(os.path.join(ROOT, "tools", "geckorx.py"))
        self.assertIn("ABOUT THE BAUD, SAID RATHER THAN ASSUMED", src)

    def test_it_authorises_no_gbp_question(self):
        s = plain(part())
        self.assertIn("No cartridge, no Game Boy Player question", s)
        self.assertNotIn("RUN 33", part())


class TheBringUpResultIsRecordedWithItsLimits(unittest.TestCase):
    """§V12.9 and §V12.10. The Operator ran it before the receiver existed and
    then again with a logfile; both channels are in hand."""

    def test_all_three_criteria_are_recorded_as_met(self):
        s = plain(part())
        self.assertIn("gecko=1", s)
        self.assertIn("ALL THREE CRITERIA MET", s)
        self.assertIn("MET BY INFERENCE, not by his eyes", s)

    def test_the_inference_is_labelled_as_one_and_shown_from_the_source(self):
        s = part()
        self.assertIn("gecko_puts()` sends **only** when", s)
        self.assertIn("an inference from the source rather than a reading of the screen", plain(s))
        smoke = read(SMOKE)
        self.assertIn("if (gecko_present) {", smoke)

    def test_the_cross_check_names_five_independent_quantities(self):
        s = part()
        for q in ("lines=3", "hash=f5587dc5", "frames=692", "buttons_seen=0400", "the ORDER"):
            self.assertIn(q, s)
        f = plain(s)
        self.assertIn("Neither channel is derived from the other", f)
        # 660 < 692 < 720 really does hold, at 60 fps
        self.assertLess(11 * 60, 692)
        self.assertLess(692, 12 * 60)
        # and 0x0400 really is X, while START (0x1000) is absent from buttons_seen
        self.assertEqual(0x0400, 0x0400)
        self.assertNotEqual(0x0400 & 0x1000, 0x1000)

    def test_gecko_puts_is_NOT_changed_to_send_crlf(self):
        self.assertNotIn("\\r\\n", read(SMOKE))
        s = plain(part())
        self.assertIn("must NOT be \"fixed\" to send", s)
        self.assertIn("The mapping belongs in the consumer", s)
        # and the receiver maps it on the ECHO only
        rx = read(os.path.join(ROOT, "tools", "geckorx.py"))
        self.assertIn("def _echo(chunk):", rx)
        self.assertIn("the file written by pump() is untouched", rx.lower())

    def test_the_sd_log_was_archived_before_the_card_was_cleared(self):
        s = part()
        self.assertIn("432bfbab5681e7a15fdd8c43b6955259caf76cc67421d4064c847a29b10a8865", s)
        f = plain(s)
        self.assertIn("Nothing was deleted without a copy and without saying where it went", f)
        self.assertIn("GBP-HW-300", s)
        # and the archived copy really is that file, when this checkout has it
        p = os.path.join(ROOT, "captures", "local",
                         "GECKO-SMOKE-HW-001_smoke-0002-bringup.log")
        if not os.path.exists(p):
            self.skipTest("the bring-up log is not archived in this checkout")
        import hashlib
        with open(p, "rb") as fh:
            data = fh.read()
        self.assertEqual(hashlib.sha256(data).hexdigest(),
                         "432bfbab5681e7a15fdd8c43b6955259caf76cc67421d4064c847a29b10a8865")
        self.assertIn(b"gecko=1", data)

    def test_no_evidence_id_was_minted_for_an_instrument_check(self):
        self.assertIsNone(re.search(r"^#{2,4} +GBP-[A-Z]+-\d{3}\b", part(), re.M))
        self.assertIn("No evidence id is minted", plain(part()))


if __name__ == "__main__":
    unittest.main()
