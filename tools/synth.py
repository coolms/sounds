#!/usr/bin/env python3
"""Makes the master of every CoolMS sound: sources/<kind>.wav, mono, 48 kHz, 16-bit PCM.

The sounds are original. Each is synthesized here from a recipe of notes and partials, with the Python standard
library only, and the same recipe always writes the same bytes. A recipe changed is a new sound: its source's sha256
changes, and sounds.json must name a new `sound` version for that kind (tools/check.py refuses otherwise).

    python3 tools/synth.py            write every source
    python3 tools/synth.py --check    write nothing; exit 1 when a source on disk differs from its recipe
"""
import math
import os
import struct
import sys
import wave

RATE = 48000
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Partials as (ratio to the note's frequency, amplitude, decay per second).
MARIMBA = [(1.0, 1.0, 9.0), (3.93, 0.16, 28.0), (9.2, 0.04, 60.0)]
SOFT = [(1.0, 1.0, 11.0), (2.0, 0.22, 22.0), (3.0, 0.06, 40.0)]
WARM = [(1.0, 1.0, 6.5), (2.0, 0.32, 10.0), (3.0, 0.1, 16.0), (4.0, 0.04, 24.0)]
POP = [(1.0, 1.0, 26.0), (2.0, 0.28, 40.0), (3.0, 0.07, 60.0)]
# A struck bell: the hum, the prime, the minor third, the fifth, the nominal and two upper partials.
BELL = [(0.5, 0.35, 1.6), (1.0, 1.0, 2.6), (1.183, 0.55, 3.4), (1.506, 0.35, 4.2), (2.0, 0.42, 5.0),
        (2.514, 0.16, 7.5), (2.662, 0.12, 8.5), (3.011, 0.08, 10.0)]


def hz(note):
    """'A4' -> 440 Hz, equal temperament; sharps as '#'."""
    names = {'C': -9, 'C#': -8, 'D': -7, 'D#': -6, 'E': -5, 'F': -4, 'F#': -3, 'G': -2, 'G#': -1, 'A': 0,
             'A#': 1, 'B': 2}
    return 440.0 * 2 ** ((names[note[:-1]] + 12 * (int(note[-1]) - 4)) / 12)


def strike(buf, at, freq, length, partials, gain=1.0, attack=0.004):
    """Adds one struck note to `buf` at `at` seconds: partials with exponential decays and a short linear attack,
    so the onset never clicks."""
    start = int(at * RATE)
    n = int(length * RATE)
    if start + n > len(buf):
        buf.extend([0.0] * (start + n - len(buf)))
    a = max(1, int(attack * RATE))
    for i in range(n):
        t = i / RATE
        env = min(1.0, i / a)
        v = 0.0
        for ratio, amp, decay in partials:
            v += amp * math.exp(-decay * t) * math.sin(2 * math.pi * freq * ratio * t)
        buf[start + i] += gain * env * v


def fade_tail(buf, seconds):
    """A linear fade over the last `seconds`, so the end meets silence exactly (a loop wraps without a click)."""
    n = min(len(buf), int(seconds * RATE))
    for i in range(n):
        buf[len(buf) - n + i] *= (n - 1 - i) / max(1, n - 1)


def pad(buf, seconds):
    want = int(seconds * RATE)
    return buf + [0.0] * (want - len(buf)) if len(buf) < want else buf[:want]


def level(buf, rms_db, peak_db=-1.0):
    """Scales to an RMS of `rms_db` dBFS over the sounding part (samples within 40 dB of the peak), then lowers it
    when the peak would pass `peak_db`."""
    peak = max(abs(v) for v in buf) or 1.0
    loud = [v for v in buf if abs(v) > peak * 0.01]
    rms = math.sqrt(sum(v * v for v in loud) / len(loud))
    g = 10 ** (rms_db / 20) / rms
    if peak * g > 10 ** (peak_db / 20):
        g = 10 ** (peak_db / 20) / peak
    return [v * g for v in buf]


def ring():
    """The ring's loop unit, 2.0 s: two soft chords, twice, then a rest. Sound for about 1.4 s, silence to 2.0 s."""
    buf = []
    one = ['E5', 'G#5', 'B5']
    two = ['F#5', 'A5', 'C#6']
    for at, chord in ((0.0, one), (0.3, two), (0.6, one), (0.9, two)):
        for note in chord:
            strike(buf, at, hz(note), 0.55, MARIMBA, gain=0.6)
    buf = pad(buf, 1.5)
    fade_tail(buf, 0.08)
    return pad(level(buf, -17.0), 2.0)


def message():
    buf = []
    strike(buf, 0.0, hz('E6'), 0.14, POP)
    strike(buf, 0.07, hz('A6'), 0.16, POP)
    fade_tail(buf, 0.02)
    return level(buf, -18.0)


def visitor():
    buf = []
    for at, note in ((0.0, 'C6'), (0.11, 'E6'), (0.22, 'G6')):
        strike(buf, at, hz(note), 0.32, MARIMBA)
    fade_tail(buf, 0.04)
    return level(buf, -17.0)


def task():
    buf = []
    strike(buf, 0.0, hz('A5'), 0.5, WARM)
    fade_tail(buf, 0.05)
    return level(buf, -18.0)


def mail():
    buf = []
    strike(buf, 0.0, hz('G5'), 0.2, SOFT)
    strike(buf, 0.12, hz('D5'), 0.24, SOFT)
    fade_tail(buf, 0.04)
    return level(buf, -21.0)


def bell():
    buf = []
    strike(buf, 0.0, hz('E5'), 1.0, BELL, attack=0.002)
    fade_tail(buf, 0.15)
    return level(buf, -18.0)


RECIPES = {'ring': ring, 'message': message, 'visitor': visitor, 'task': task, 'mail': mail, 'bell': bell}


def pcm(samples):
    return b''.join(struct.pack('<h', max(-32768, min(32767, int(round(v * 32767))))) for v in samples)


def wav_bytes(samples):
    """The WAV file's bytes, header and all, so the check can compare them with the file on disk."""
    import io
    out = io.BytesIO()
    with wave.open(out, 'wb') as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(pcm(samples))
    return out.getvalue()


def main():
    check = '--check' in sys.argv[1:]
    differ = []
    for kind, recipe in RECIPES.items():
        data = wav_bytes(recipe())
        path = os.path.join(ROOT, 'sources', kind + '.wav')
        if check:
            on_disk = open(path, 'rb').read() if os.path.exists(path) else None
            if on_disk != data:
                differ.append(kind)
            continue
        with open(path, 'wb') as f:
            f.write(data)
        print('%s: %.3f s, %d bytes' % (kind, (len(data) - 44) / 2 / RATE, len(data)))
    if check:
        if differ:
            print('FOUND -- %d of %d sources differ from their recipe: %s' % (len(differ), len(RECIPES), ', '.join(differ)))
            return 1
        print('CLEAR -- %d of %d sources are what their recipe writes' % (len(RECIPES), len(RECIPES)))
    return 0


if __name__ == '__main__':
    sys.exit(main())
