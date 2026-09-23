#!/usr/bin/env python3
"""
tools/geckorx.py — receive a USB Gecko stream on the host and write it to a file.

    tools/geckorx.py --out captures/local/GECKO-SMOKE-HW-001-run1.txt

WHAT THIS IS FOR. Today a run's log is written ONLY at the end of a session
(`HARDWARE_TESTS.md` §V7.6.10), so a run that hangs, or that the recovery
procedure ends at the power button, produces NOTHING. A Gecko turns "the trip is
lost" into "we have it up to the point it stopped". For Phase 7, where the
current image cannot open a GB/GBC session at all, that is the difference
between a wasted run and a diagnosis.

**IT IS OPTIONAL AND MUST NEVER BECOME NECESSARY** (`CLAUDE.md` §14). The SD save
stays the primary record; nothing in any procedure may come to depend on a Gecko
being present, and every POC already treats it as absent by default —
`usb_isgeckoalive()` decides, and the send path is skipped silently when it says
no.

THE PORT IS RESOLVED BY ID, NEVER BY `ttyACM0`. The kernel numbers ACM devices
in the order they appear, so `/dev/ttyACM0` is whichever CDC device enumerated
first this boot; `/dev/serial/by-id/` names the device instead. A receiver that
opened `ttyACM0` would silently read somebody else's modem.

ABOUT THE BAUD, SAID RATHER THAN ASSUMED. The port is a USB CDC-ACM interface.
A baud rate has to be set because termios requires one, and the value is carried
to the device as CDC line coding — but a CDC device is free to ignore it, and
for a bridge whose other side runs at a fixed hardware clock (the EXI bus here)
it normally does. **We do not know what this firmware does with it**: the Pico
Gecko is the Operator's own hardware, built by him and unpinned by this project.
So the default is stated, not justified, and `--baud` exists for the case where
it turns out to matter.

NOTHING IS TIMESTAMPED AND NOTHING IS PARSED. The output file is the byte stream
exactly as it arrived, so it can be compared with the SD log without a decoder
in between. Everything this tool has to say goes to stderr.

LINE ENDINGS ARE THE CONSUMER'S PROBLEM, NOT THE WIRE'S. The images send bare
`\n`, and so does Swiss, so a terminal in raw mode draws each line starting
where the last one ended -- the classic staircase. **That is a display setting,
not a defect, and `gecko_puts()` is not changed to send `\r\n`**: it would mean
editing fourteen images and their logs to work around a cursor, and Swiss would
still disagree. A capture-to-file tool has no cursor, so the FILE never has the
problem; only `--echo` does, and `--echo` maps LF to CRLF on its way to the
terminal and leaves the file alone. Interactively, `picocom --imap lfcrlf` does
the same thing.

Standard library only: no pyserial, so a clone can run this and its tests.
"""
import argparse
import errno
import os
import re
import signal
import sys
import time

DEFAULT_BY_ID = "/dev/serial/by-id"
# The Operator's Pico Gecko enumerates as Raspberry Pi's VID 2e8a, PID 000a and
# currently names itself `usb-Raspberry_Pi_Pico-if00`. The pattern deliberately
# stops before the `-if`, because a firmware that reports a SERIAL NUMBER names
# itself `usb-Raspberry_Pi_Pico_E6614103E7…-if00` and a pattern ending in `-if`
# would then match nothing at all. Writing the test is what found that.
DEFAULT_PATTERN = "usb-Raspberry_Pi_Pico"
DEFAULT_BAUD = 115200
FLUSH_EVERY = 1          # every read: a hang must not cost the bytes already in hand


class NoPort(Exception):
    pass


class ManyPorts(Exception):
    pass


def match_ports(entries, pattern=DEFAULT_PATTERN):
    """The by-id entries matching `pattern`, sorted. Pure: `entries` is a list of
    names, so this is testable with no device and no /dev at all."""
    return sorted(e for e in entries if pattern in e)


def resolve(by_id_dir=DEFAULT_BY_ID, pattern=DEFAULT_PATTERN, listdir=None, realpath=None):
    """The one by-id path to open, or an exception that says what to do.

    Refusing to guess between two matching devices is deliberate: a second Pico
    on the bench would otherwise be opened silently."""
    listdir = listdir or os.listdir
    realpath = realpath or os.path.realpath
    try:
        entries = listdir(by_id_dir)
    except OSError as e:
        raise NoPort("%s: %s -- is the device plugged in?" % (by_id_dir, e.strerror))
    hits = match_ports(entries, pattern)
    if not hits:
        raise NoPort("no entry under %s matches %r (found: %s)"
                     % (by_id_dir, pattern, ", ".join(sorted(entries)) or "nothing"))
    if len(hits) > 1:
        # One device can expose several interfaces (`-if00`, `-if02`, ...), and the
        # DATA interface of a CDC-ACM device is the first one. So a single device with
        # more than one interface resolves to `-if00`; TWO devices, which would give
        # two `-if00` entries, still refuse. Guessing between two Picos on the bench is
        # exactly the mistake resolving by id exists to prevent.
        first = [h for h in hits if h.endswith("-if00")]
        if len(first) == 1:
            hits = first
        else:
            raise ManyPorts("%d entries match %r: %s -- name one with --port"
                            % (len(hits), pattern, ", ".join(hits)))
    path = os.path.join(by_id_dir, hits[0])
    return path, realpath(path)


def configure(fd, baud=DEFAULT_BAUD):
    """Raw mode, no echo, no flow control, blocking reads that return as soon as
    a byte is there. Returns the baud actually requested, or None when the fd is
    not a terminal (a pipe, in the tests)."""
    import termios
    try:
        attrs = termios.tcgetattr(fd)
    except termios.error:
        return None                       # a pipe or a regular file: nothing to configure
    iflag, oflag, cflag, lflag, ispeed, ospeed, cc = attrs
    iflag &= ~(termios.IXON | termios.IXOFF | termios.IXANY | termios.ICRNL |
               termios.INLCR | termios.IGNCR | termios.ISTRIP | termios.BRKINT)
    oflag &= ~termios.OPOST
    lflag &= ~(termios.ECHO | termios.ECHOE | termios.ECHONL | termios.ICANON |
               termios.ISIG | termios.IEXTEN)
    cflag &= ~(termios.CSIZE | termios.PARENB | termios.CSTOPB | termios.CRTSCTS)
    cflag |= termios.CS8 | termios.CREAD | termios.CLOCAL
    speed = getattr(termios, "B%d" % baud, None)
    if speed is None:
        raise ValueError("termios has no constant for %d baud" % baud)
    cc[termios.VMIN] = 1                  # return as soon as one byte is available
    cc[termios.VTIME] = 0
    termios.tcsetattr(fd, termios.TCSANOW,
                      [iflag, oflag, cflag, lflag, speed, speed, cc])
    return baud


def pump(fd, out, stop=None, idle_exit=None, until=None, on_chunk=None, clock=time.monotonic):
    """Copy bytes from `fd` to the binary stream `out` until `stop()` says so.

    Flushes after every read, because the whole point is that a run which never
    reaches its own save still leaves what it managed to say. Returns the number
    of bytes copied.
    """
    total = 0
    tail = b""
    last = clock()
    rx = re.compile(until.encode() if isinstance(until, str) else until) if until else None
    while not (stop and stop()):
        try:
            chunk = os.read(fd, 4096)
        except OSError as e:
            if e.errno in (errno.EAGAIN, errno.EWOULDBLOCK):
                chunk = b""
            elif e.errno == errno.EIO:
                break                     # the device went away: stop, keep what we have
            else:
                raise
        if chunk:
            out.write(chunk)
            out.flush()
            total += len(chunk)
            last = clock()
            if on_chunk:
                on_chunk(chunk)
            if rx:
                tail = (tail + chunk)[-4096:]
                if rx.search(tail):
                    break
        elif idle_exit is not None and clock() - last >= idle_exit:
            break
        elif not chunk:
            time.sleep(0.005)
    return total


def _echo(chunk):
    """The terminal's copy, and ONLY the terminal's: LF becomes CRLF so the
    output does not staircase. The file written by pump() is untouched."""
    sys.stderr.buffer.write(chunk.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n"))
    sys.stderr.buffer.flush()


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.strip().split("\n")[0])
    ap.add_argument("--out", required=True, help="file to write the raw byte stream to")
    ap.add_argument("--port", help="open this path instead of resolving by id")
    ap.add_argument("--by-id", default=DEFAULT_BY_ID)
    ap.add_argument("--pattern", default=DEFAULT_PATTERN)
    ap.add_argument("--baud", type=int, default=DEFAULT_BAUD)
    ap.add_argument("--idle-exit", type=float, default=None,
                    help="exit after this many seconds with no bytes (default: never)")
    ap.add_argument("--until", default=None,
                    help="exit once this regex appears in the stream (e.g. 'EXIT reason=')")
    ap.add_argument("--echo", action="store_true",
                    help="also copy the stream to stderr, with LF mapped to CRLF for the "
                         "terminal only; the output FILE is never modified")
    a = ap.parse_args(argv)

    if a.port:
        by_id, real = a.port, os.path.realpath(a.port)
    else:
        try:
            by_id, real = resolve(a.by_id, a.pattern)
        except (NoPort, ManyPorts) as e:
            print("geckorx: %s" % e, file=sys.stderr)
            return 2

    fd = os.open(by_id, os.O_RDONLY | os.O_NOCTTY)
    try:
        baud = configure(fd, a.baud)
        print("geckorx: %s -> %s  baud=%s (CDC line coding; the device may ignore it)"
              % (by_id, real, baud if baud else "n/a, not a terminal"), file=sys.stderr)
        print("geckorx: writing raw bytes to %s -- nothing is timestamped or parsed" % a.out,
              file=sys.stderr)
        stopped = []
        signal.signal(signal.SIGINT, lambda *_: stopped.append(True))
        signal.signal(signal.SIGTERM, lambda *_: stopped.append(True))
        with open(a.out, "wb") as out:
            n = pump(fd, out, stop=lambda: bool(stopped), idle_exit=a.idle_exit,
                     until=a.until,
                     on_chunk=_echo if a.echo else None)
        print("geckorx: %d bytes" % n, file=sys.stderr)
        return 0
    finally:
        os.close(fd)


if __name__ == "__main__":
    sys.exit(main())
