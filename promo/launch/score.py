"""The launch film's score: felt piano, warm pads, soft pulse, cinematic hits, all through one reverb.

    python score.py out/score.wav

Generated from numpy alone (no samples, nothing licensed). Cue times follow launch.html.
"""
from __future__ import annotations

import sys
import wave

import numpy as np

SR = 44100
DUR = 71.0
N = int(SR * DUR)
rng = np.random.default_rng(11)
DRY = np.zeros((N, 2))
WET = np.zeros((N, 2))          # reverb send
BPM = 96
BEAT = 60 / BPM


def tt(d):
    return np.arange(int(d * SR)) / SR


def band(x, lo=0.0, hi=SR / 2, soft=0.3):
    X = np.fft.rfft(x, axis=0)
    f = np.fft.rfftfreq(x.shape[0], 1 / SR)
    g = np.ones_like(f)
    if lo > 0:
        g *= 1 / (1 + (lo / np.maximum(f, 1e-3)) ** (2 / soft))
    if hi < SR / 2:
        g *= 1 / (1 + (f / hi) ** (2 / soft))
    if x.ndim == 2:
        g = g[:, None]
    return np.fft.irfft(X * g, x.shape[0], axis=0)


def hz(n):
    names = {"C": 0, "C#": 1, "Db": 1, "D": 2, "D#": 3, "Eb": 3, "E": 4, "F": 5, "F#": 6, "Gb": 6,
             "G": 7, "G#": 8, "Ab": 8, "A": 9, "A#": 10, "Bb": 10, "B": 11}
    return 440.0 * 2 ** ((names[n[:-1]] + 12 * (int(n[-1]) + 1) - 69) / 12)


def put(x, t, gain=1.0, pan=0.0, send=0.3):
    """Mix x (mono or stereo) in at t, with an equal-power pan and a reverb send."""
    i = int(t * SR)
    if i >= N or i < 0:
        return
    if x.ndim == 1:
        a = (pan + 1) * np.pi / 4
        x = np.stack([x * np.cos(a), x * np.sin(a)], axis=1)
    x = x[: N - i] * gain
    DRY[i:i + len(x)] += x
    WET[i:i + len(x)] += x * send


# ------------------------------------------------------------------ instruments

def piano(n, d=3.5, vel=0.5):
    """A felt piano: slightly inharmonic partials, the high ones dying first, a soft hammer."""
    f, t = hz(n), tt(d)
    x = np.zeros(len(t))
    for k in range(1, 11):
        fk = f * k * np.sqrt(1 + 0.00035 * k * k)
        if fk > 9000:
            break
        x += (1 / k ** 1.25) * np.sin(2 * np.pi * fk * t + rng.random()) * np.exp(-t * (0.9 + 0.75 * k) * (f / 440) ** 0.3)
    hammer = band(rng.standard_normal(len(t)) * np.exp(-t * 90), 200, 2500)
    x = band(x + hammer * 0.25, 30, 3200, 0.5)
    x *= np.minimum(1, t / 0.004) * np.minimum(1, (d - t) / 0.3)
    return x * vel * 0.44


def pad(notes, d, cutoff=1300, attack=1.4, release=1.8):
    t = tt(d)
    out = np.zeros((len(t), 2))
    for n in notes:
        f = hz(n)
        for c in (-11, -4, 3, 10):
            for ch in (0, 1):
                ph = rng.random()
                out[:, ch] += 2 * ((f * 2 ** ((c + (ch * 2 - 1) * 2) / 1200) * t + ph) % 1) - 1
    out = band(out / (8 * len(notes)), 50, cutoff, 0.6)
    e = np.minimum(1, t / attack) * np.minimum(1, np.maximum(0, (d - t) / release))
    return out * e[:, None] * 0.55


def sub(n, d, attack=0.8):
    t = tt(d)
    return np.sin(2 * np.pi * hz(n) * t) * np.minimum(1, t / attack) * np.minimum(1, (d - t) / 0.6) * 0.17


def kick(g=1.0):
    t = tt(0.5)
    f = 42 + 70 * np.exp(-t * 30)
    x = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 7)
    return band(np.tanh(x * 1.3), 38, 900) * 0.42 * g


def snap():
    t = tt(0.25)
    return band(rng.standard_normal(len(t)), 1400, 5200) * np.exp(-t * 28) * 0.12


def shaker(g=1.0):
    t = tt(0.07)
    return band(rng.standard_normal(len(t)), 6000, 14000) * np.sin(np.pi * t / 0.07) ** 2 * 0.07 * g


def tick(g=1.0):
    t = tt(0.03)
    return band(rng.standard_normal(len(t)), 3000, 9000) * np.exp(-t * 220) * 0.12 * g


def boom(g=1.0, d=3.0):
    t = tt(d)
    f = 30 + 34 * np.exp(-t * 3)
    x = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 1.6)
    rumble = band(rng.standard_normal(len(t)), 20, 180) * np.exp(-t * 2.2) * 0.6
    return band(np.tanh((x + rumble) * 1.2), 28) * 0.45 * g


def whoosh(d=0.9, g=1.0):
    t = tt(d)
    x = rng.standard_normal(len(t))
    lo, hi = band(x, 150, 900), band(x, 1200, 7000)
    m = t / d
    return (lo * (1 - m) + hi * m) * np.sin(np.pi * m) ** 2 * 0.22 * g


def swell(notes, d=2.0, g=1.0):
    """A reversed, reverberant chord that rises into a hit."""
    x = sum(piano(n, 3.0, 0.6) for n in notes)
    tail = np.convolve(x, ir_mono[: int(2.5 * SR)], mode="full")[: int(3.0 * SR)]
    y = tail[::-1][-int(d * SR):]
    return y / (np.abs(y).max() + 1e-9) * 0.35 * g


def chime(n, g=1.0, d=2.4):
    t, f = tt(d), hz(n)
    x = np.sin(2 * np.pi * f * t) + 0.3 * np.sin(2 * np.pi * f * 2.0 * t) * np.exp(-t * 3) + 0.12 * np.sin(2 * np.pi * f * 3.01 * t) * np.exp(-t * 6)
    return x * np.exp(-t * 2.2) * np.minimum(1, t / 0.003) * 0.16 * g


def sparkle(t0, d, density, g=1.0):
    """Dust: soft high notes scattered in time, mostly reverb."""
    t = t0
    notes = ["D6", "E6", "F6", "A6", "C7", "D7", "E7"]
    while t < t0 + d:
        put(chime(notes[rng.integers(len(notes))], 0.35 * g, 1.6), t, pan=rng.uniform(-.8, .8), send=0.8)
        t += rng.exponential(1 / density)


def scan(d=0.95):
    t = tt(d)
    f = 900 + 1700 * t / d
    return np.sin(2 * np.pi * np.cumsum(f) / SR) * np.sin(np.pi * t / d) * 0.035


# ------------------------------------------------------------------ reverb

def impulse(rt60=3.4):
    d = rt60 * 1.1
    t = tt(d)
    ir = np.stack([rng.standard_normal(len(t)), rng.standard_normal(len(t))], axis=1)
    ir *= np.exp(-6.9 * t / rt60)[:, None]
    ir = band(ir, 120, 6500, 0.6)
    pre = int(0.025 * SR)
    ir = np.concatenate([np.zeros((pre, 2)), ir])
    return ir / np.sqrt((ir ** 2).sum(axis=0))


IR = impulse()
ir_mono = IR[:, 0]


def reverb(x):
    n = x.shape[0] + IR.shape[0]
    m = 1 << (n - 1).bit_length()
    out = np.fft.irfft(np.fft.rfft(x, m, axis=0) * np.fft.rfft(IR, m, axis=0), m, axis=0)
    return out[: x.shape[0]]


# ------------------------------------------------------------------ the film

def chord(t, notes, d, gain=1.0, cutoff=1300, attack=1.4, release=1.8):
    put(pad(notes, d, cutoff, attack, release), t, gain, send=0.45)


def score():
    Dm = ["D3", "F3", "A3", "E4"]
    Bb = ["Bb2", "D3", "F3", "A3"]
    F = ["F3", "A3", "C4", "E4"]
    C = ["C3", "G3", "C4", "E4"]
    A = ["A2", "E3", "A3", "D4"]

    # 0 - 18: the key, the docs, the leak
    chord(0.0, Dm, 5.6, 0.8, 1000, 2.5)
    put(sub("D2", 5.6, 2.5), 0.0, 0.5, send=0)
    for t, n, v in [(0.55, "A4", .55), (1.5, "E4", .4), (2.5, "F4", .5), (3.45, "D4", .45), (4.4, "C5", .35)]:
        put(piano(n, 4.0, v), t, pan=-0.15, send=0.55)
    chord(5.2, Bb, 3.4, 0.8, 1100)
    chord(8.4, F, 3.4, 0.8, 1200)
    put(whoosh(1.0, .7), 4.8)
    for t, n, v in [(5.5, "D5", .4), (6.5, "A4", .35), (8.5, "C5", .4), (9.6, "A4", .45), (10.6, "E4", .35)]:
        put(piano(n, 3.5, v), t, pan=0.15, send=0.55)
    chord(11.5, Dm, 6.9, 0.9, 900)
    put(sub("D2", 6.9, 1.0), 11.5, 0.55, send=0)
    k = 0
    for b in np.arange(11.5, 18.0, BEAT / 2):                    # the pulse wakes up
        put(tick(0.45 + 0.55 * (b - 11.5) / 6.5), b, pan=0.25, send=0.15)
        if k % 2 == 0:
            put(sub("D1", BEAT * .45, 0.01) * 0.6, b, 0.45, send=0)
        k += 1
    for t in (12.1, 12.55, 13.0, 13.45):
        put(tick(1.1), t, pan=-0.2, send=0.3)
    put(boom(0.45, 2.2), 15.4)
    put(piano("A3", 4.0, .5), 15.4, send=0.6)
    put(piano("D4", 4.0, .4), 15.4, send=0.6)

    # 18 - 22.4: the key turns to dust
    put(swell(["D4", "F4", "A4"], 1.6), 16.4)
    put(boom(0.8, 3.5), 18.0)
    chord(18.0, Bb, 2.4, 0.9, 1500, 0.4)
    chord(20.2, A, 2.6, 0.9, 1500, 0.6)
    sparkle(18.1, 4.0, 6, 1.0)
    put(piano("F5", 4.0, .35), 18.6, send=0.7)
    put(piano("E5", 4.0, .3), 20.3, send=0.7)

    # 22.4 - 31: the Rule of Two
    put(whoosh(0.9, .8), 22.0)
    prog = [(22.4, Dm, "D2"), (25.0, Bb, "Bb1"), (27.5, F, "F2")]
    for t0, ch, bass in prog:
        chord(t0, ch, 2.8, 0.75, 1300, 0.6)
        put(sub(bass, 2.6, 0.2), t0, 0.5, send=0)
    for i, b in enumerate(np.arange(22.4, 30.6, BEAT)):
        if i % 2 == 0:
            put(kick(0.55), b, send=0.05)
        put(tick(0.7), b + BEAT / 2, pan=0.3, send=0.15)
    arp = ["D4", "F4", "A4", "E5", "A4", "F4"]
    for i, b in enumerate(np.arange(22.4, 30.4, BEAT / 2)):
        put(piano(arp[i % len(arp)], 1.6, .22), b, pan=(-.3 if i % 2 else .3), send=0.45)
    for t, n in [(24.7, "A5"), (25.9, "C6"), (27.1, "E6")]:
        put(chime(n, 1.0), t, send=0.6)
    put(boom(0.6, 2.5), 27.7)
    chord(27.7, ["G2", "D3", "Bb3", "Eb4"], 3.3, 0.8, 900, 0.3)           # the leak: a darker turn

    # 31 - 36: blocked. Everything stops.
    put(sub("D1", 5.0, 1.0), 31.0, 0.55, send=0)
    chord(31.0, ["D3", "A3", "D4"], 5.0, 0.6, 700, 1.0, 1.0)
    for t, n, v in [(32.3, "D4", .4), (33.3, "C4", .45), (34.2, "A3", .35)]:
        put(piano(n, 3.5, v), t, send=0.7)
    put(swell(["F4", "A4", "C5", "E5"], 2.2), 33.8)
    put(whoosh(1.6, 0.9), 34.4)

    # 36 - 41: Cleanroom
    put(boom(1.0, 4.0), 36.0)
    chord(36.0, ["F2", "C3", "G3", "A3", "C4", "E4"], 5.6, 1.0, 2400, 0.15, 2.0)
    put(sub("F1", 5.0, 0.05), 36.0, 0.6, send=0)
    for t, n, v in [(36.0, "F4", .5), (36.0, "A4", .45), (36.0, "C5", .45), (36.9, "G5", .35), (37.9, "E5", .35), (38.9, "C6", .3)]:
        put(piano(n, 4.5, v), t, send=0.6)
    sparkle(36.4, 4.2, 4, 0.8)

    # 41 - 63.6: how it works, then the proof
    put(whoosh(0.9, .8), 40.6)
    prog = [(Bb, "Bb1"), (F, "F2"), (C, "C2"), (Dm, "D2")]
    bar = 4 * BEAT
    i = 0
    t0 = 41.0
    while t0 + i * bar < 63.6:
        ch, bass = prog[i % 4]
        b0 = t0 + i * bar
        chord(b0, ch, bar + 0.3, 0.7, 1700, 0.5, 0.8)
        for j in range(4):
            bt = b0 + j * BEAT
            if bt >= 63.6:
                break
            put(kick(0.75 if j in (0, 2) else 0.0), bt, send=0.05)
            if j in (1, 3):
                put(snap(), bt, pan=0.1, send=0.5)
            put(sub(bass, BEAT * .9, 0.01) * 0.8, bt, 0.55, send=0)
            for s in range(4):
                put(shaker(0.6 + 0.4 * (s % 2)), bt + s * BEAT / 4, pan=0.35, send=0.1)
        notes = [ch[0], ch[2], ch[3], ch[1], ch[2], ch[3], ch[2], ch[1]]
        for j, n in enumerate(notes):
            bt = b0 + j * BEAT / 2
            if bt < 63.6:
                hi = n[:-1] + str(int(n[-1]) + 1)
                put(piano(hi, 1.4, .2 if bt < 56.6 else .26), bt, pan=(-.35 if j % 2 else .35), send=0.4)
        i += 1
    for t in (43.8, 45.8, 48.0, 51.8):
        put(tick(1.4), t, send=0.4)
    put(chime("A5", 1.2), 48.1)                           # Muse Spark Open
    put(chime("E6", 0.8), 48.35)
    put(whoosh(0.5, .6), 51.15)
    put(scan(), 52.0)
    put(chime("C6", 1.0), 52.85)
    put(chime("G6", 0.8), 53.6)
    put(chime("C7", 0.6), 53.75)
    put(whoosh(0.9, .7), 56.2)
    for k, t in enumerate(np.arange(58.4, 59.5, 0.35)):
        put(tick(1.2), t, send=0.3)
    put(chime("E6", 0.9), 59.4)

    # 63.6 - 71: the close
    put(boom(0.5, 3.0), 63.6)
    chord(63.6, ["Bb2", "F3", "A3", "C4", "D4"], 3.2, 0.9, 1800, 0.3, 1.2)
    put(sub("Bb1", 3.0, 0.2), 63.6, 0.5, send=0)
    for t, n, v in [(63.9, "D5", .4), (64.8, "C5", .4), (65.6, "A4", .35)]:
        put(piano(n, 4.0, v), t, send=0.6)
    put(boom(0.7, 4.0), 66.4)
    chord(66.4, ["F2", "C3", "G3", "A3", "C4", "E4"], 4.6, 1.0, 2200, 0.2, 2.6)
    put(sub("F1", 4.4, 0.1), 66.4, 0.55, send=0)
    for t, n, v in [(66.4, "F4", .45), (66.4, "C5", .4), (67.3, "A5", .35), (68.3, "G5", .3), (69.2, "F5", .28)]:
        put(piano(n, 4.0, v), t, send=0.65)
    sparkle(66.6, 3.5, 3, 0.7)


def main(out):
    score()
    mix = DRY + reverb(WET) * 0.9
    mix = band(mix, 34)
    fade = np.ones(N)
    fade[-int(1.6 * SR):] = np.linspace(1, 0, int(1.6 * SR)) ** 2
    mix *= fade[:, None]
    mix = np.tanh(mix * 1.4) / 1.4                        # gentle glue, no hard clipping
    mix /= np.abs(mix).max() / 0.89
    pcm = (mix * 32767).astype("<i2")
    with wave.open(out, "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())
    print(f"wrote {out} ({DUR:.1f}s)")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "score.wav")
