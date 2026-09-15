#!/usr/bin/env python3
"""
dolphin_smoke — run a GameCube DOL in the Dolphin Flatpak and verify a
POC-specific success condition without human interaction.

Success criteria (all must hold, unless individually disabled):

  1. gecko   The program detects Dolphin's emulated USB Gecko (memory-card
             slot B, Core.SlotB=7), whose output Dolphin forwards to
             TCP 127.0.0.1:55020. We must receive
                 OPENGBP-SMOKE READY app=... build=... commit=...
             matching build-info.txt, followed by at least --heartbeats
             HEARTBEAT lines with increasing counters. This proves the
             DOL loaded, main() ran, the VSync loop advances and the
             identity embedded in the binary is the one we built.
  2. log     Dolphin's own log (written to file in an isolated user dir)
             contains the boot of our DOL and no error-level lines.
  3. screen  A screenshot of Dolphin's render window, taken from the host
             X11 session (xdotool + ImageMagick `import`) while the DOL is
             running, is mostly black with a small fraction of lit pixels,
             i.e. the console text is visible. Saved as PNG for human/agent
             inspection. Dolphin's own frame dumper (--frame-dump) is
             opt-in: on Dolphin 2606a Flatpak it produced no output for
             this DOL (see docs/research/UNKNOWNS.md).

A timeout with no READY line is a FAIL, never a PASS.

Dolphin is invoked with an isolated --user directory inside the Flatpak's
own writable area so the user's normal Dolphin configuration is untouched.
Configuration is passed with -C (command-line layer) and not persisted.
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import re
import shutil
import signal
import socket
import subprocess
import sys
import time

FLATPAK_ID = "org.DolphinEmu.dolphin-emu"
GECKO_PORT = 55020  # Dolphin EXI_DeviceGecko: 0xd6ec
EXI_DEVICE_GECKO = 7  # ExpansionInterface::EXIDeviceType::Gecko

DEFAULT_USER_DIR = os.path.expanduser(
    "~/.var/app/%s/data/open-gbp/dolphin-user" % FLATPAK_ID)

# Any Open-GBP POC announces itself as "OPENGBP-<APP> READY app=... build=... commit=...".
READY_RE = re.compile(r"^OPENGBP-[A-Z0-9]+ READY app=(\S+) build=(\S+) commit=(\S+)(?: (.*))?$")
HEARTBEAT_RE = re.compile(r"^OPENGBP-[A-Z0-9]+ HEARTBEAT n=(\d+) frames=(\d+) xfb_lit=(\d+) xfb_hash=([0-9a-f]{8})$")
# Dolphin log line: "MM:SS:mmm file:line L[TYPE]: message"
LOGLINE_RE = re.compile(r"^\d\d:\d\d:\d\d\d \S+:\d+ ([NEWID])\[([^\]]+)\]: (.*)$")

# Error-level Dolphin log lines that are understood and known not to affect
# the smoke test. Each entry: (regex on "TYPE: message", reason). Keep this
# list short and every entry justified; counts are reported, never hidden.
KNOWN_BENIGN_ERRORS = [
    (re.compile(r"^MI: Trying to read 32 bits from an invalid MMIO \(addr=0c0068(8c|a0|b4)\)$"),
     "libogc2 EXI_ImmEx polls the EXI CR register through a +0x80 mirror "
     "(0xCC00688C + channel*0x14) that Dolphin 2606a does not map; Dolphin "
     "returns 0 so the wait loop ends immediately and the transfer proceeds. "
     "See docs/research/EVIDENCE.md (ENV-EXI-001)."),
]


def log(msg):
    print("[dolphin_smoke] " + msg, flush=True)


def read_build_info(path):
    info = {}
    if path and os.path.isfile(path):
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                if "=" in line:
                    k, v = line.rstrip("\n").split("=", 1)
                    info[k] = v
    return info


def dolphin_cmd(dol, user_dir, extra_config, frame_dump=False):
    cfg = [
        "Dolphin.Core.SlotB=%d" % EXI_DEVICE_GECKO,
        "Dolphin.Core.SlotA=255",           # nothing in slot A
        "Dolphin.Core.SerialPort1=255",
        "Dolphin.Analytics.PermissionAsked=True",
        "Dolphin.Analytics.Enabled=False",
        "Dolphin.Interface.UsePanicHandlers=False",  # never block on a modal dialog
        "Dolphin.Interface.OnScreenDisplayMessages=False",  # no OSD overlay ("Video Info", "USBGecko: Listening…") in screenshots
        "Logger.Options.WriteToFile=True",
        "Logger.Options.WriteToConsole=False",
        "Logger.Options.Verbosity=3",       # up to warnings; errors always shown
    ]
    for t in ("BOOT", "CORE", "MASTER", "PowerPC", "MI", "EXI", "PI", "VI",
              "DVD", "HSP", "OSREPORT", "FRAMEDUMP", "Video"):
        cfg.append("Logger.Logs.%s=True" % t)
    if frame_dump:
        cfg += ["Dolphin.Movie.DumpFrames=True", "Dolphin.Movie.DumpFramesSilent=True"]
    cfg += extra_config or []
    cmd = ["flatpak", "run", FLATPAK_ID, "--batch",
           "--exec=%s" % dol, "--user=%s" % user_dir]
    for c in cfg:
        cmd += ["-C", c]
    return cmd


def prepare_user_dir(user_dir):
    os.makedirs(user_dir, exist_ok=True)
    for sub in ("Logs", os.path.join("Dump", "Frames")):
        p = os.path.join(user_dir, sub)
        if os.path.isdir(p):
            shutil.rmtree(p)
        os.makedirs(p, exist_ok=True)


def connect_gecko(deadline, proc):
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            return None
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(0.5)
        try:
            s.connect(("127.0.0.1", GECKO_PORT))
            return s
        except OSError:
            s.close()
            time.sleep(0.25)
    return None


def collect_gecko(sock, deadline, want_heartbeats, proc, expect_res=()):
    """Read gecko lines until READY + N heartbeats + every --expect regex
    matched, or deadline. Returns list."""
    buf = b""
    lines = []
    heartbeats = 0
    ready = False
    pending = list(expect_res)
    sock.settimeout(0.5)
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            break
        try:
            chunk = sock.recv(4096)
        except socket.timeout:
            continue
        except OSError:
            break
        if not chunk:
            break
        buf += chunk
        while b"\n" in buf:
            raw, buf = buf.split(b"\n", 1)
            text = raw.decode("ascii", "replace").rstrip("\r")
            lines.append(text)
            log("gecko: " + text)
            if READY_RE.match(text):
                ready = True
            elif HEARTBEAT_RE.match(text):
                heartbeats += 1
            pending = [rx for rx in pending if not rx.search(text)]
        if ready and heartbeats >= want_heartbeats and not pending:
            break
    return lines


def dolphin_instances():
    """Instance ids of running Dolphin sandboxes (flatpak ps)."""
    try:
        out = subprocess.run(["flatpak", "ps", "--columns=instance,application"],
                             capture_output=True, text=True, check=False).stdout
    except OSError:
        return []
    return [ln.split()[0] for ln in out.splitlines() if FLATPAK_ID in ln]


def stop_dolphin(proc):
    """Terminate Dolphin. `flatpak run` may exit before the sandboxed process,
    so always ask flatpak to kill the application afterwards."""
    if proc.poll() is None:
        proc.send_signal(signal.SIGTERM)
        try:
            proc.wait(timeout=8)
        except subprocess.TimeoutExpired:
            pass
    for _ in range(3):
        if not dolphin_instances():
            break
        subprocess.run(["flatpak", "kill", FLATPAK_ID], check=False,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(1)
    if proc.poll() is None:
        proc.kill()
        proc.wait()
    left = dolphin_instances()
    if left:
        log("WARNING: Dolphin instance(s) still running: %s" % ", ".join(left))


def check_gecko(lines, build_info, want_heartbeats, expect_res=()):
    result = {"pass": False, "ready": None, "heartbeats": 0, "xfb": None, "problems": [],
              "expected_missing": []}
    ready = None
    hb = []
    for text in lines:
        m = READY_RE.match(text)
        if m:
            ready = {"app": m.group(1), "build": m.group(2), "commit": m.group(3),
                     "extra": m.group(4) or ""}
            continue
        m = HEARTBEAT_RE.match(text)
        if m:
            hb.append((int(m.group(1)), int(m.group(2)), int(m.group(3)), m.group(4)))
    result["ready"] = ready
    result["heartbeats"] = len(hb)
    if ready is None:
        result["problems"].append("no READY line received from emulated USB Gecko")
    else:
        for key, bkey in (("app", "app"), ("build", "build_id"), ("commit", "commit")):
            if bkey in build_info and build_info[bkey] != ready[key]:
                result["problems"].append("READY %s=%s differs from build-info %s=%s"
                                          % (key, ready[key], bkey, build_info[bkey]))
    if len(hb) < want_heartbeats:
        result["problems"].append("expected >= %d heartbeats, got %d" % (want_heartbeats, len(hb)))
    for (n0, f0, _, _), (n1, f1, _, _) in zip(hb, hb[1:]):
        if n1 != n0 + 1 or f1 <= f0:
            result["problems"].append("heartbeat sequence not monotonic: %r -> %r" % ((n0, f0), (n1, f1)))
            break
    for rx in expect_res:
        if not any(rx.search(t) for t in lines):
            result["expected_missing"].append(rx.pattern)
            result["problems"].append("expected gecko line not seen: /%s/" % rx.pattern)
    if hb:
        lits = [h[2] for h in hb]
        hashes = sorted(set(h[3] for h in hb))
        result["xfb"] = {"lit_min": min(lits), "lit_max": max(lits), "hashes": hashes}
        # 640x480 frame: identity block is a few thousand lit pixels; a blank
        # or fully lit frame means the console never rendered.
        if min(lits) < 500 or max(lits) > 100000:
            result["problems"].append("xfb lit pixel count %r outside plausible range" % lits)
        if len(hashes) != 1:
            result["problems"].append("identity rows of the framebuffer changed between heartbeats: %s"
                                      % hashes)
    result["pass"] = not result["problems"]
    return result


def check_log(user_dir, dol):
    result = {"pass": False, "path": None, "lines": 0, "errors": [], "boot_seen": False,
              "benign_errors": {}, "problems": []}
    path = os.path.join(user_dir, "Logs", "dolphin.log")
    result["path"] = path
    if not os.path.isfile(path):
        result["problems"].append("dolphin.log not written")
        return result
    dol_base = os.path.basename(dol)
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            result["lines"] += 1
            m = LOGLINE_RE.match(line.rstrip("\n"))
            if not m:
                continue
            level, ltype, msg = m.groups()
            if ltype == "BOOT" and dol_base in msg:
                result["boot_seen"] = True
            if level == "E":
                key = "%s: %s" % (ltype, msg)
                for rx, reason in KNOWN_BENIGN_ERRORS:
                    if rx.match(key):
                        result["benign_errors"][rx.pattern] = result["benign_errors"].get(rx.pattern, 0) + 1
                        break
                else:
                    result["errors"].append(line.rstrip("\n"))
    if not result["boot_seen"]:
        result["problems"].append("BOOT log never mentioned %s" % dol_base)
    if result["errors"]:
        result["problems"].append("%d unexplained error-level log lines" % len(result["errors"]))
    result["pass"] = not result["problems"]
    return result


WINDOW_NAME_RE = "Dolphin|smoke"


def find_render_window():
    """Return (window id, name, width, height) of the largest visible Dolphin window."""
    xdotool = shutil.which("xdotool")
    if not xdotool:
        return None
    try:
        ids = subprocess.run([xdotool, "search", "--onlyvisible", "--name", WINDOW_NAME_RE],
                             capture_output=True, text=True, check=False).stdout.split()
    except OSError:
        return None
    best = None
    for wid in ids:
        try:
            name = subprocess.run([xdotool, "getwindowname", wid], capture_output=True,
                                  text=True, check=True).stdout.strip()
            geo = subprocess.run([xdotool, "getwindowgeometry", "--shell", wid],
                                 capture_output=True, text=True, check=True).stdout
        except subprocess.CalledProcessError:
            continue
        g = dict(kv.split("=", 1) for kv in geo.split() if "=" in kv)
        w, h = int(g.get("WIDTH", 0)), int(g.get("HEIGHT", 0))
        if best is None or w * h > best[2] * best[3]:
            best = (wid, name, w, h)
    return best


def capture_screen(png_out):
    """Screenshot Dolphin's render window. Returns a result dict."""
    result = {"pass": False, "window": None, "png": None, "size": None,
              "lit_ratio": None, "problems": []}
    imp = shutil.which("import")
    if not imp or not shutil.which("xdotool"):
        result["problems"].append("xdotool/ImageMagick import not available on host")
        return result
    win = find_render_window()
    if win is None:
        result["problems"].append("no visible Dolphin window found")
        return result
    wid, name, w, h = win
    result["window"] = {"id": wid, "name": name, "width": w, "height": h}
    if png_out is None:
        png_out = os.path.join(os.getcwd(), "dolphin-screen.png")
    try:
        subprocess.run([imp, "-window", wid, png_out], check=True, timeout=20,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
        result["problems"].append("import failed: %s" % e)
        return result
    result["png"] = png_out
    try:
        from PIL import Image  # pillow, optional
        im = Image.open(png_out).convert("L")
        result["size"] = list(im.size)
        px = list(im.getdata())
        lit = sum(1 for p in px if p > 40)
        result["lit_ratio"] = lit / float(len(px))
    except ImportError:
        result["problems"].append("Pillow not available; screenshot saved but not analyzed")
        return result
    # Console text on black: a few percent lit. Blank (<0.2%) or a mostly
    # bright frame (>50%) means the console output is not being shown.
    if not (0.002 <= result["lit_ratio"] <= 0.5):
        result["problems"].append("screen lit ratio %.4f outside expected range" % result["lit_ratio"])
    result["pass"] = not result["problems"]
    return result


def check_frames(user_dir, png_out):
    result = {"pass": False, "video": None, "frames": None, "nonblack_ratio": None,
              "png": None, "problems": []}
    vids = sorted(glob.glob(os.path.join(user_dir, "Dump", "Frames", "framedump*.*")))
    if not vids:
        result["problems"].append("no frame dump produced")
        return result
    video = vids[-1]
    result["video"] = video
    ffprobe = shutil.which("ffprobe")
    ffmpeg = shutil.which("ffmpeg")
    if not (ffprobe and ffmpeg):
        result["problems"].append("ffmpeg/ffprobe not available on host")
        return result
    try:
        out = subprocess.run([ffprobe, "-v", "error", "-count_frames", "-select_streams", "v:0",
                              "-show_entries", "stream=nb_read_frames,width,height",
                              "-of", "json", video], capture_output=True, text=True, check=True).stdout
        st = json.loads(out)["streams"][0]
        nframes = int(st.get("nb_read_frames", 0))
        result["frames"] = nframes
        result["size"] = [int(st["width"]), int(st["height"])]
    except (subprocess.CalledProcessError, KeyError, ValueError, IndexError) as e:
        result["problems"].append("ffprobe failed: %s" % e)
        return result
    if nframes < 2:
        result["problems"].append("frame dump has %d frames" % nframes)
        return result
    # Last frame as 8-bit grayscale raw -> compute non-black pixel ratio.
    try:
        raw = subprocess.run([ffmpeg, "-v", "error", "-sseof", "-0.1", "-i", video,
                              "-frames:v", "1", "-pix_fmt", "gray", "-f", "rawvideo", "-"],
                             capture_output=True, check=True).stdout
        if not raw:
            raise ValueError("empty frame")
        lit = sum(1 for b in raw if b > 40)
        result["nonblack_ratio"] = lit / len(raw)
        if png_out:
            subprocess.run([ffmpeg, "-v", "error", "-y", "-sseof", "-0.1", "-i", video,
                            "-frames:v", "1", png_out], check=True)
            result["png"] = png_out
    except (subprocess.CalledProcessError, ValueError) as e:
        result["problems"].append("frame extraction failed: %s" % e)
        return result
    # Console text on black: expect a small but clearly nonzero lit fraction.
    if not (0.002 <= result["nonblack_ratio"] <= 0.5):
        result["problems"].append("last frame lit ratio %.4f outside expected range"
                                  % result["nonblack_ratio"])
    result["pass"] = not result["problems"]
    return result


def main(argv=None):
    ap = argparse.ArgumentParser(description="Dolphin smoke-test runner for Open-GBP DOLs")
    ap.add_argument("--dol", required=True)
    ap.add_argument("--build-info", default=None, help="build-info.txt to cross-check identity")
    ap.add_argument("--user-dir", default=DEFAULT_USER_DIR)
    ap.add_argument("--timeout", type=float, default=60.0, help="seconds to wait for evidence")
    ap.add_argument("--heartbeats", type=int, default=3,
                    help="HEARTBEAT lines required (0 for POCs without a heartbeat)")
    ap.add_argument("--expect", action="append", default=[],
                    help="regex that must appear in a gecko line (repeatable); the run ends once all matched")
    ap.add_argument("--report", default=None, help="write JSON report here")
    ap.add_argument("--screen-png", default=None, help="save the render-window screenshot here")
    ap.add_argument("--no-screen", action="store_true", help="skip the X11 screenshot check")
    ap.add_argument("--frame-dump", action="store_true",
                    help="also enable and require Dolphin's own frame dump (experimental)")
    ap.add_argument("--frame-png", default=None, help="save last dumped frame as PNG (with --frame-dump)")
    ap.add_argument("-C", dest="config", action="append", default=[],
                    help="extra Dolphin config override (System.Section.Key=Value)")
    args = ap.parse_args(argv)

    dol = os.path.abspath(args.dol)
    if not os.path.isfile(dol):
        log("DOL not found: " + dol)
        return 2
    build_info = read_build_info(args.build_info)
    expect_res = [re.compile(e) for e in args.expect]
    if dolphin_instances():
        log("another Dolphin instance is running; it would own the Gecko port. Aborting.")
        return 2
    prepare_user_dir(args.user_dir)

    cmd = dolphin_cmd(dol, args.user_dir, args.config, frame_dump=args.frame_dump)
    log("command: " + " ".join(cmd))
    t0 = time.monotonic()
    deadline = t0 + args.timeout
    proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                            start_new_session=False)
    gecko_lines = []
    screen = None
    try:
        sock = connect_gecko(deadline, proc)
        if sock is None:
            log("could not connect to emulated USB Gecko on port %d" % GECKO_PORT)
        else:
            log("connected to emulated USB Gecko after %.1fs" % (time.monotonic() - t0))
            with sock:
                gecko_lines = collect_gecko(sock, deadline, args.heartbeats, proc, expect_res)
        if not args.no_screen and proc.poll() is None:
            # The identity block has been on screen since READY; capture now,
            # while Dolphin is still presenting frames.
            screen = capture_screen(args.screen_png)
            if screen["png"]:
                log("screenshot: %s (lit %.4f)" % (screen["png"], screen["lit_ratio"] or 0))
    finally:
        exit_early = proc.poll()
        stop_dolphin(proc)
    elapsed = time.monotonic() - t0

    report = {
        "dol": dol,
        "build_info": build_info,
        "dolphin_command": cmd,
        "elapsed_s": round(elapsed, 2),
        "dolphin_exited_early": exit_early is not None,
        "dolphin_exit_code": exit_early,
        "gecko": check_gecko(gecko_lines, build_info, args.heartbeats, expect_res),
        "log": check_log(args.user_dir, dol),
    }
    report["gecko"]["lines"] = gecko_lines
    if not args.no_screen:
        report["screen"] = screen or {"pass": False, "problems": ["Dolphin exited before screenshot"]}
    if args.frame_dump:
        report["frames"] = check_frames(args.user_dir, args.frame_png)
    checks = [k for k in ("gecko", "log", "screen", "frames") if k in report]
    report["pass"] = all(report[k]["pass"] for k in checks) and not report["dolphin_exited_early"]

    if args.report:
        with open(args.report, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2)
        log("report: " + args.report)

    for k in checks:
        r = report[k]
        log("%-6s %s %s" % (k, "PASS" if r["pass"] else "FAIL", "; ".join(r["problems"])))
    if report["dolphin_exited_early"]:
        log("Dolphin exited early with code %r" % exit_early)
    for pat, n in report["log"]["benign_errors"].items():
        log("  %d known-benign log error(s) matching %s" % (n, pat))
    for e in report["log"]["errors"][:20]:
        log("  log error: " + e)
    log("RESULT: %s (%.1fs)" % ("PASS" if report["pass"] else "FAIL", elapsed))
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
