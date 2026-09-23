#!/usr/bin/env python3
"""
tools/v17decode.py — decode an OGBPAW1 audio sidecar to PCM under H-PWM's layout.

    tools/v17decode.py <audio.bin> <out-dir> [--label RUN34]

THE LAYOUT, in one paragraph (§V17.2). Each 4096-byte AUDIO block drained from
the window is ONE sample. Its value is the fraction of one-bits in the block
(`v14repeat.bitduty`) — the byte grid is the wrong ruler (GBP-HW-304, GBP-HW-312).
The order of bytes within a block does not matter under this layout, and the
block's sixteen repeated 256-byte cells all carry the same sample. Samples arrive
at 4096 per second (GBP-HW-301). DISCARDED: the sidecar's header, its 128-byte
anchors and its footer. The resting level — the mean of the run's own CONTROL
window, which the ROM keeps silent — is subtracted, so silence decodes to zero.
The verdict skips each press window's first 96 blocks (§V11.9); the audio files
keep every block.

THE VERDICT IS JUDGED AGAINST `tools/v17pred.py`, frozen in the commit before this
module existed. The period estimator is §V9.8's (`v11sweep.window_period`) and the
amplitude is `v14repeat.deviation`, both unedited: nothing that decides the
verdict is new here. What is new is the decode, the WAV writer and the resampler.

THE AUDIO FILES. 16-bit mono PCM. ONE FIXED GAIN for every file — a deviation of
0.125 (the ±32/256 §V11.4 predicted at volume 15) maps to 80 % of full scale — so
relative loudness is preserved across windows and runs, and the gain depends on
no measured value. The 4096 Hz files are THE EVIDENCE. The 48 kHz files are a
CONVENIENCE, made by the resampler below. Standard library only.
"""
import math
import os
import struct
import sys
import wave

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import v11sweep   # noqa: E402
import v14repeat  # noqa: E402
import v17pred    # noqa: E402

GAIN = 0.80 / 0.125          # a 0.125 deviation -> 80 % of full scale, for every file
OUT_RATE = 48000             # 48000 / 4096 = 375 / 32 exactly
SINC_HALF_TAPS = 16          # the interpolation kernel's half-width, in input samples


# ------------------------------------------------------------------ decoding

def resting_level(control_blocks):
    """The run's own silence, measured on its CONTROL window."""
    s = [v14repeat.bitduty(b) for b in control_blocks]
    return sum(s) / float(len(s))


def decode(blocks, rest):
    """H-PWM: one block -> one sample, the one-bit fraction minus the rest."""
    return [v14repeat.bitduty(b) - rest for b in blocks]


# ------------------------------------------------------------------- verdict

def measure_window(blocks):
    """Period by §V9.8's estimator and amplitude by v14repeat.deviation, both on
    the sliced region, both unedited."""
    sl = v11sweep.sliced(blocks)
    series = [v14repeat.bitduty(b) for b in sl]
    per = v11sweep.window_period(series)
    return {"period": per["period"], "uniformity": per["uniformity"], "edges": per["edges"],
            "deviation": v14repeat.deviation(blocks)}


def question_D(windows, anchor_keys):
    """§V17.4. `windows` are the four PRESS windows in press order."""
    axis = v11sweep.derive_schedule(anchor_keys)
    if axis not in ("F", "V"):
        return {"verdict": "INCONCLUSIVE", "why": "the axis cannot be derived: %s" % axis}
    pred = v17pred.predict(axis)
    rows, bad, absent = [], [], []
    for i, (w, p) in enumerate(zip(windows, pred)):
        m = measure_window(w)
        lo, hi = v17pred.period_band(p["period"])
        ok = (m["period"] is not None and lo <= m["period"] <= hi
              and m["uniformity"] >= v17pred.UNIFORMITY_MIN)
        rows.append(dict(p, **m, band=(lo, hi), period_ok=ok))
        if m["period"] is None:
            absent.append(i + 1)
        elif not ok:
            bad.append(i + 1)
    out = {"axis": axis, "rows": rows}
    if absent:
        out.update(verdict="INCONCLUSIVE", why="windows %s have no period" % absent)
        return out
    if bad:
        out.update(verdict="LAYOUT REFUTED", why="windows %s fall outside their period band" % bad)
        return out
    if axis == "V":
        devs = [r["deviation"] for r in rows]
        if any(d is None for d in devs) or not all(devs[i] > devs[i + 1] for i in range(len(devs) - 1)):
            out.update(verdict="LAYOUT REFUTED",
                       why="on the V axis the decoded amplitude does not strictly fall: %s"
                           % [None if d is None else round(d * 256, 3) for d in devs])
            return out
    out.update(verdict="LAYOUT HOLDS", why="every period in band%s"
               % ("" if axis == "F" else ", and the amplitude falls with the volume"))
    return out


def dft_peak_hz(samples, rate=v17pred.SAMPLE_RATE, lo=20.0, hi=2040.0, step=1.0):
    """A MEASUREMENT beside the verdict, never a gate: the frequency at which
    the discrete-time Fourier transform of the (mean-removed) series peaks,
    searched at 1 Hz steps. Finer than the period estimate, and independent of
    it."""
    m = sum(samples) / float(len(samples))
    x = [s - m for s in samples]
    best, best_f = -1.0, None
    f = lo
    while f <= hi:
        w = 2.0 * math.pi * f / rate
        re_ = sum(v * math.cos(w * n) for n, v in enumerate(x))
        im_ = sum(v * math.sin(w * n) for n, v in enumerate(x))
        p = re_ * re_ + im_ * im_
        if p > best:
            best, best_f = p, f
        f += step
    return best_f


# ----------------------------------------------------------------- the audio

def resample(samples, in_rate=v17pred.SAMPLE_RATE, out_rate=OUT_RATE, half=SINC_HALF_TAPS):
    """Band-limited interpolation from in_rate to out_rate (an UPSAMPLE here).

    Each output sample at input position x = k * in_rate / out_rate is
    sum_n in[n] * sinc(x - n) * hann(x - n) over the `half` input samples on
    either side. The sinc's cutoff is the INPUT Nyquist (2048 Hz), so nothing
    above what the 4096 Hz evidence can represent is invented; the Hann taper
    keeps the truncated kernel from ringing. Samples outside the input are zero.
    It adds no information: the 4096 Hz file is the evidence."""
    n_in = len(samples)
    n_out = int(n_in * out_rate / in_rate)
    out = []
    for k in range(n_out):
        x = k * in_rate / float(out_rate)
        c = int(math.floor(x))
        acc = 0.0
        for n in range(c - half + 1, c + half + 1):
            if 0 <= n < n_in:
                t = x - n
                s = 1.0 if t == 0 else math.sin(math.pi * t) / (math.pi * t)
                w = 0.5 * (1.0 + math.cos(math.pi * t / half)) if abs(t) < half else 0.0
                acc += samples[n] * s * w
        out.append(acc)
    return out


def write_wav(path, samples, rate):
    """16-bit mono, clipped at full scale, with the fixed GAIN."""
    frames = b"".join(struct.pack("<h", max(-32767, min(32767, int(round(s * GAIN * 32767)))))
                      for s in samples)
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(frames)


def write_run(path_bin, out_dir, label):
    """Decode one sidecar and write its files. Returns (verdict, files)."""
    import awinparse
    _, _, anc, wins = awinparse.load(path_bin)
    press = [a for a in anc if a["kind"] == 1]
    keys = [a["keys"] for a in press]
    rest = resting_level(wins[0])
    verdict = question_D(wins[1:], keys)
    os.makedirs(out_dir, exist_ok=True)
    files = []
    whole = []
    for i, w in enumerate(wins[1:]):
        pcm = decode(w, rest)
        whole += pcm
        for rate, data in ((v17pred.SAMPLE_RATE, pcm), (OUT_RATE, resample(pcm))):
            p = os.path.join(out_dir, "%s_w%d_%dHz.wav" % (label, i + 1, rate))
            write_wav(p, data, rate)
            files.append(p)
    for rate, data in ((v17pred.SAMPLE_RATE, whole), (OUT_RATE, resample(whole))):
        p = os.path.join(out_dir, "%s_all_%dHz.wav" % (label, rate))
        write_wav(p, data, rate)
        files.append(p)
    # A LISTENING copy, and only that: each window's SLICED region looped to about one second.
    # 160 samples is a whole number of periods at every frequency in the schedule (5, 20, 10,
    # 40), so the loop joins without a click. It is not evidence and it says so in its name.
    listen = []
    for w in wins[1:]:
        pcm = decode(v11sweep.sliced(w), rest)
        listen += pcm * max(1, int(round(v17pred.SAMPLE_RATE / float(len(pcm)))))
    p = os.path.join(out_dir, "%s_LISTEN-looped_%dHz.wav" % (label, OUT_RATE))
    write_wav(p, resample(listen), OUT_RATE)
    files.append(p)
    return verdict, files


def main(argv):
    if len(argv) < 3:
        print(__doc__)
        return 2
    label = argv[argv.index("--label") + 1] if "--label" in argv else "decoded"
    verdict, files = write_run(argv[1], argv[2], label)
    print("axis %s  verdict %s -- %s" % (verdict.get("axis"), verdict["verdict"], verdict.get("why")))
    for f in files:
        print("  wrote", f)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
