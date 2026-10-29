"""Synthesize the soundtrack for video.html: a short score plus sound effects on the visual beats.

Everything is generated here from numpy (no samples, no licences to worry about). The cue
times match the timeline in video.html; change one, change the other.

    python soundtrack.py out/soundtrack.wav
"""
from __future__ import annotations

import sys
import wave

import numpy as np

SR = 44100
DUR = 64.0
N = int(SR * DUR)
rng = np.random.default_rng(7)
L = np.zeros(N)
R = np.zeros(N)


def add(x: np.ndarray, t: float, gain: float = 1.0, pan: float = 0.0) -> None:
    """Mix mono buffer x in at time t. pan -1 (left) .. 1 (right), equal-power."""
    i = int(t * SR)
    if i >= N or len(x) == 0:
        return
    x = x[: N - i] * gain
    a = (pan + 1) * np.pi / 4
    L[i:i + len(x)] += x * np.cos(a)
    R[i:i + len(x)] += x * np.sin(a)


def tt(d: float) -> np.ndarray:
    return np.arange(int(d * SR)) / SR


def band(x: np.ndarray, lo: float = 0.0, hi: float = SR / 2, soft: float = 0.15) -> np.ndarray:
    """Zero-phase band filter by FFT with soft edges."""
    X = np.fft.rfft(x)
    f = np.fft.rfftfreq(len(x), 1 / SR)
    g = np.ones_like(f)
    if lo > 0:
        g *= 1 / (1 + (lo / np.maximum(f, 1e-3)) ** (2 / soft))
    if hi < SR / 2:
        g *= 1 / (1 + (f / hi) ** (2 / soft))
    return np.fft.irfft(X * g, len(x))


def noise(d: float) -> np.ndarray:
    return rng.standard_normal(int(d * SR))


def env(d: float, a: float, rel: float) -> np.ndarray:
    t = tt(d)
    e = np.minimum(1, t / max(a, 1e-4))
    return e * np.minimum(1, np.maximum(0, (d - t) / max(rel, 1e-4)))


def hz(note: str) -> float:
    names = {"C": 0, "C#": 1, "D": 2, "D#": 3, "E": 4, "F": 5, "F#": 6, "G": 7, "G#": 8, "A": 9, "A#": 10, "B": 11}
    n, o = note[:-1], int(note[-1])
    return 440.0 * 2 ** ((names[n] + 12 * (o + 1) - 69) / 12)


# ---------------------------------------------------------------- instruments

def kick(gain=1.0):
    t = tt(0.42)
    f = 46 + 120 * np.exp(-t * 32)
    x = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 8.5)
    x[:200] += np.linspace(0.6, 0, 200) * rng.standard_normal(200) * 0.3
    return np.tanh(x * 1.6) * gain


def clap():
    d = 0.32
    x = band(noise(d), 900, 5000)
    t = tt(d)
    e = np.exp(-t * 16)
    for k in (0.0, 0.012, 0.024):
        e += 0.6 * np.exp(-np.maximum(0, t - k) * 120) * (t >= k)
    return x * e * 0.22


def hat(open_=False):
    d = 0.18 if open_ else 0.05
    x = band(noise(d), 7000)
    return x * np.exp(-tt(d) * (18 if open_ else 70)) * 0.35


def pluck(f, d=0.45):
    t = tt(d)
    x = sum((1 / k) * np.sin(2 * np.pi * f * k * t) * np.exp(-t * (7 + 5 * k)) for k in range(1, 7))
    return x * np.minimum(1, t / 0.003) * 0.35


def bass(f, d):
    t = tt(d)
    x = np.sin(2 * np.pi * f * t) + 0.25 * np.sin(2 * np.pi * 2 * f * t)
    return x * env(d, 0.01, 0.08) * 0.42


def saw(f, t):
    return 2 * ((f * t) % 1.0) - 1


def pad(freqs, d, cutoff=1800, a=0.35, rel=0.6):
    t = tt(d)
    x = np.zeros(len(t))
    for f in freqs:
        for c in (-7, 0, 7):
            x += saw(f * 2 ** (c / 1200), t + rng.random())
    x = band(x / (3 * len(freqs)), 60, cutoff, soft=0.5)
    return x * env(d, a, rel)


def drone(f, d, cutoff=420):
    t = tt(d)
    x = saw(f, t) + saw(f * 1.5 * 2 ** (4 / 1200), t) * 0.6 + saw(f * 0.5, t) * 0.5
    return band(x, 30, cutoff, soft=0.5)


# ---------------------------------------------------------------- effects

def whoosh(d=0.55, up=True):
    x = noise(d)
    lo, hi = band(x, 200, 1200), band(x, 1500, 9000)
    t = tt(d)
    m = t / d if up else 1 - t / d
    e = np.sin(np.pi * np.minimum(1, t / d)) ** 2
    return (lo * (1 - m) + hi * m) * e * 0.55


def impact(gain=1.0, dur=1.6):
    t = tt(dur)
    f = 38 + 70 * np.exp(-t * 14)
    boom = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 3.2)
    crash = band(noise(dur), 300, 6000) * np.exp(-t * 4.5) * 0.35
    return np.tanh((boom + crash) * 1.4) * 0.8 * gain


def alarm():
    out = np.zeros(int(0.62 * SR))
    for k, f in enumerate((932, 698, 932, 698)):
        t = tt(0.13)
        x = np.sign(np.sin(2 * np.pi * f * t)) * 0.5 + np.sin(2 * np.pi * f * 2 * t) * 0.2
        x = band(x, 200, 4000) * env(0.13, 0.004, 0.03)
        i = int(k * 0.15 * SR)
        out[i:i + len(x)] += x
    return out * 0.28


def blip(f=1200, d=0.07):
    t = tt(d)
    return np.sin(2 * np.pi * f * t) * np.exp(-t * 60) * 0.3


def pop(f=520):
    t = tt(0.09)
    ff = f * (1 + 1.5 * np.exp(-t * 80))
    return np.sin(2 * np.pi * np.cumsum(ff) / SR) * np.exp(-t * 45) * 0.32


def ding(f, d=1.4, gain=0.3):
    t = tt(d)
    x = (np.sin(2 * np.pi * f * t) + 0.35 * np.sin(2 * np.pi * f * 2.76 * t) * np.exp(-t * 4)
         + 0.15 * np.sin(2 * np.pi * f * 5.4 * t) * np.exp(-t * 8))
    return x * np.exp(-t * 3.2) * np.minimum(1, t / 0.002) * gain


def chime(notes=("C6", "E6", "G6", "C7"), step=0.07, gain=0.22):
    out = np.zeros(int((step * len(notes) + 1.6) * SR))
    for k, n in enumerate(notes):
        x = ding(hz(n), 1.5, gain)
        i = int(k * step * SR)
        out[i:i + len(x)] += x
    return out


def clicks(d, rate, gain=0.12):
    out = np.zeros(int(d * SR))
    t = 0.0
    while t < d:
        x = band(noise(0.012), 2500, 9000) * np.exp(-tt(0.012) * 400)
        i = int(t * SR)
        out[i:i + len(x)] += x[: len(out) - i] * (0.6 + 0.4 * rng.random())
        t += rng.exponential(1 / rate)
    return out * gain


def glitch(d):
    x = noise(d)
    x = np.round(x * 3) / 3                       # crush
    gate = np.repeat(rng.random(int(d * 60) + 1) > 0.35, SR // 60 + 1)[: len(x)]
    tone = np.sign(np.sin(2 * np.pi * 180 * tt(d) * (1 + 3 * rng.random())))
    return band(x * gate + tone * gate * 0.3, 300, 7000) * 0.18


def riser(d):
    t = tt(d)
    f = 200 * 2 ** (3 * t / d)
    tone = np.sin(2 * np.pi * np.cumsum(f) / SR) * 0.25
    hiss = band(noise(d), 2000, 9000) * 0.28
    return (tone + hiss) * (t / d) ** 2 * 0.6


def thud():
    t = tt(0.9)
    x = np.sin(2 * np.pi * np.cumsum(55 * np.exp(-t * 2.5) + 30) / SR) * np.exp(-t * 5)
    return np.tanh(x * 2) * 0.7


def sweep(d):
    t = tt(d)
    f = 600 + 1800 * t / d
    return np.sin(2 * np.pi * np.cumsum(f) / SR) * np.sin(np.pi * t / d) * 0.09


# ---------------------------------------------------------------- score

def music():
    beat = 0.5
    # A: tension, 0 - 15.2. Drone and a heartbeat.
    add(drone(hz("A1"), 15.6) * env(15.6, 2.5, 0.6), 0.0, 0.22)
    for b in np.arange(0, 15.2, 2 * beat):
        g = 0.55 if b < 4.6 else 0.8
        add(kick(g), b, 0.9)
        add(kick(g * 0.6), b + 0.24, 0.9)
    for b in np.arange(4.6, 15.2, beat / 2):
        add(hat(), b, 0.35 + 0.15 * ((b * 4) % 2 < 1), pan=0.3)
    # B: the rule of two, 15.2 - 25.2. Arp and a steady kick.
    add(drone(hz("A1"), 10.4, 650) * env(10.4, 0.2, 0.4), 15.2, 0.2)
    arp = ["A3", "C4", "E4", "A4", "E4", "C4", "B3", "E4"]
    for k, b in enumerate(np.arange(15.2, 25.2, beat / 2)):
        add(pluck(hz(arp[k % len(arp)]), 0.3), b, 0.55 + 0.25 * (b - 15.2) / 10, pan=(-0.35 if k % 2 else 0.35))
    for b in np.arange(15.2, 25.2, beat):
        add(kick(0.85), b, 0.9)
        add(hat(), b + beat / 2, 0.5, pan=-0.2)
    for b in np.arange(15.2, 25.2, 4 * beat):
        add(bass(hz("A1"), 1.9), b, 0.7)
    # C: blocked, 25.2 - 31.6. Muffled, sparse.
    add(drone(hz("A1"), 6.6, 260) * env(6.6, 0.1, 0.4), 25.2, 0.24)
    for b in (25.2, 26.2, 27.2, 28.2):
        add(kick(0.5), b, 0.7)
    # D: Cleanroom, 31.6 - 57.6. Bright groove, F - C - G - Am.
    prog = [("F2", ["F3", "A3", "C4", "F4"]), ("C3", ["C3", "G3", "C4", "E4"]),
            ("G2", ["G3", "B3", "D4", "G4"]), ("A2", ["A3", "C4", "E4", "A4"])]
    t0, bar = 31.6, 4 * beat
    k = 0
    while t0 + k * bar < 57.6:
        root, chord = prog[k % 4]
        b0 = t0 + k * bar
        add(pad([hz(n) for n in chord], bar + 0.4, 2200), b0, 0.34)
        for j in range(4):
            add(kick(0.95), b0 + j * beat, 0.95)
            add(hat(open_=(j % 2 == 1)), b0 + j * beat + beat / 2, 0.45, pan=0.25)
            add(bass(hz(root), beat * 0.9), b0 + j * beat, 0.8)
            add(bass(hz(root) * 2, beat * 0.4), b0 + j * beat + beat / 2, 0.35)
        for j in (1, 3):
            add(clap(), b0 + j * beat, 0.9)
        for j in range(8):
            n = chord[[0, 2, 1, 3, 2, 1, 3, 2][j]]
            add(pluck(hz(n) * 2, 0.35), b0 + j * beat / 2, 0.32, pan=(-0.4 if j % 2 else 0.4))
        k += 1
    # E: outro, 57.6 - 64.
    add(pad([hz(n) for n in ("F3", "A3", "C4", "E4")], 3.4, 2600, 0.05, 1.0), 57.6, 0.4)
    add(pad([hz(n) for n in ("C3", "G3", "C4", "E4")], 3.2, 2400, 0.4, 2.6), 60.8, 0.4)
    add(bass(hz("F1"), 3.2), 57.6, 0.8)
    add(bass(hz("C2"), 3.2), 60.8, 0.6)
    for j, n in enumerate(["C5", "E5", "G5", "C6", "G5", "E5", "C5", "G4"] * 2):
        add(pluck(hz(n), 0.6), 57.6 + j * 0.25, 0.25 * (1 - j / 18), pan=(-0.3 if j % 2 else 0.3))


def effects():
    # 1. the guide
    add(impact(0.55, 1.2), 0.0)
    add(whoosh(0.6), 0.4, 0.5)
    add(pop(700), 1.9)
    # 2. the agent follows it
    add(whoosh(0.5), 4.4)
    for k, t in enumerate((4.95, 5.6, 6.25, 6.9)):
        add(blip(900 + 120 * k), t)
    add(pop(600), 7.15)
    add(clicks(1.9, 38), 7.35)
    add(blip(1500), 9.75)
    add(pop(500), 10.25)
    add(glitch(1.4), 10.4)
    add(impact(1.0), 12.45)
    add(alarm(), 12.5)
    # 3. rule of two
    add(whoosh(0.5), 15.0)
    for k in range(3):
        add(pop(420 + 60 * k), 15.6 + 0.18 * k, 0.8)
    add(ding(hz("E5")), 17.1)
    add(ding(hz("G5")), 18.5)
    add(whoosh(0.4), 18.6, 0.35)
    add(chime(("C6", "E6"), 0.09, 0.18), 19.3)
    add(ding(hz("B5")), 20.7)
    add(whoosh(0.5), 20.8, 0.4)
    add(impact(0.9), 21.5)
    add(alarm(), 21.55)
    # 4. blocking
    add(whoosh(0.5), 25.0)
    add(pop(480), 25.6)
    add(blip(700, 0.1), 26.7)
    add(thud(), 27.6)
    add(pop(380), 28.6)
    add(riser(2.0), 29.6)
    # 5. reveal
    add(impact(1.1, 2.2), 31.6)
    add(chime(("A5", "C6", "E6", "A6"), 0.06, 0.2), 31.65)
    add(pop(650), 32.2)
    add(pop(760), 32.75)
    # 6. the rewrite
    add(whoosh(0.5), 34.05)
    add(glitch(0.6), 35.1, 0.8)
    add(pop(820), 35.75)
    add(pop(560), 37.0)
    add(ding(hz("D6"), 1.0, 0.22), 37.15)
    add(clicks(1.4, 30, 0.07), 37.35)
    add(whoosh(0.35, up=False), 38.75, 0.4)
    add(whoosh(0.45, up=False), 39.15, 0.4)
    add(pop(560), 40.0)
    add(sweep(0.95), 40.2)
    add(chime(("G5", "D6"), 0.08, 0.2), 41.25)
    add(pop(560), 42.4)
    add(chime(), 42.8)
    add(impact(0.5, 1.2), 44.5)
    # 7. real session
    add(whoosh(0.5), 46.2)
    add(pop(500), 46.7)
    add(pop(620), 48.3)
    # 8. proof
    add(whoosh(0.5), 51.8)
    add(pop(500), 52.4)
    add(pop(560), 52.55)
    for k, t in enumerate((53.0, 53.15, 53.75, 53.9, 54.5, 54.65)):
        add(blip(1000 + 200 * (k % 2), 0.08), t)
    for k in range(4):
        add(pop(700 + 50 * k), 55.5 + 0.15 * k, 0.6)
    # 9. close
    add(impact(0.6, 2.0), 57.6)
    add(pop(600), 58.2)
    add(pop(700), 58.75)
    add(ding(hz("C6"), 2.0, 0.22), 60.2)


def main(out: str) -> None:
    music()
    effects()
    mix = np.stack([L, R], axis=1)
    fade = np.ones(N)
    fade[-int(2.2 * SR):] = np.linspace(1, 0, int(2.2 * SR)) ** 1.5
    mix *= fade[:, None]
    mix = np.stack([band(mix[:, 0], 32), band(mix[:, 1], 32)], axis=1)   # nothing a speaker cannot play
    mix = np.tanh(mix * 0.9)
    mix /= np.max(np.abs(mix)) / 0.89
    pcm = (mix * 32767).astype("<i2")
    with wave.open(out, "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())
    print(f"wrote {out} ({DUR:.1f}s)")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "soundtrack.wav")
