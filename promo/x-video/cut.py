"""Build the Seedance cut: Seedance 2.5 shots for the story, video.html's scenes as the receipts.

    python cut.py

Reads cut.js for the edit, expects the four shots in shots/, and writes cleanroom-seedance.mp4.
Steps: render video.html?cut to an alpha overlay (graphics, plus captions over the shots), lay
the shots underneath, and mix a score whose cues follow the new timeline.
"""
from __future__ import annotations

import json
import os
import subprocess
import wave

import numpy as np

import soundtrack as st

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "out")
SHOTS = os.path.join(HERE, "shots")
FPS = 30


def segments():
    src = open(os.path.join(HERE, "cut.js"), encoding="utf-8").read()
    data = json.loads(src[src.index("{"): src.rindex("}") + 1])
    segs, start = [], 0.0
    for s in data["segments"]:
        raw = s["dur"] if s["type"] == "ai" else (s["to"] - s["from"]) / s["speed"]
        s = dict(s, start=start, len=round(raw * FPS) / FPS)   # same rounding as video.html
        segs.append(s)
        start += s["len"]
    return segs


def run(*cmd):
    subprocess.run(cmd, check=True)


# ------------------------------------------------------------------ sound

def clip_audio(path: str, start: float, dur: float) -> np.ndarray:
    """A shot's own sound, as stereo float at the score's rate, levelled to a common loudness."""
    raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", str(start), "-t", str(dur), "-i", path,
                          "-f", "s16le", "-ac", "2", "-ar", str(st.SR), "-"],
                         check=True, capture_output=True).stdout
    x = np.frombuffer(raw, "<i2").reshape(-1, 2) / 32768.0
    rms = np.sqrt((x ** 2).mean()) if len(x) else 0
    return x * (0.1 / rms) if rms > 1e-4 else x


def score(segs, total: float) -> str:
    st.reset(total)
    by = {(s["type"], s.get("from")): s for s in segs}
    gfx = [s for s in segs if s["type"] == "gfx"]
    beat = 0.5
    reveal = by[("gfx", 31.6)]["start"]            # "Cleanroom" title card
    block = by[("gfx", 25.2)]                       # the blocked session
    rule2 = by[("gfx", 15.2)]["start"]
    end = by[("gfx", 57.6)]["start"]                # the closing card

    # tension: drone and heartbeat from the first frame to the title card
    st.TIME_MAP = None
    st.add(st.drone(st.hz("A1"), block["start"] + 0.4) * st.env(block["start"] + 0.4, 1.0, 0.5), 0.0, 0.22)
    for b in np.arange(0, block["start"], 2 * beat):
        st.add(st.kick(0.8), b, 0.9)
        st.add(st.kick(0.5), b + 0.24, 0.9)
    for b in np.arange(4.6, block["start"], beat / 2):
        st.add(st.hat(), b, 0.35 + 0.15 * ((b * 4) % 2 < 1), pan=0.3)
    arp = ["A3", "C4", "E4", "A4", "E4", "C4", "B3", "E4"]
    for k, b in enumerate(np.arange(rule2, block["start"], beat / 2)):
        st.add(st.pluck(st.hz(arp[k % 8]), 0.3), b, 0.6, pan=(-0.35 if k % 2 else 0.35))
    # blocked: everything drops out but a muffled drone, then a riser into the title card
    st.add(st.drone(st.hz("A1"), block["len"] + 0.2, 260) * st.env(block["len"] + 0.2, 0.1, 0.3), block["start"], 0.24)
    st.add(st.riser(2.0), reveal - 2.0)
    # Cleanroom: the bright groove, F - C - G - Am, from the title card to the close
    prog = [("F2", ["F3", "A3", "C4", "F4"]), ("C3", ["C3", "G3", "C4", "E4"]),
            ("G2", ["G3", "B3", "D4", "G4"]), ("A2", ["A3", "C4", "E4", "A4"])]
    k = 0
    while reveal + k * 4 * beat < end:
        root, chord = prog[k % 4]
        b0 = reveal + k * 4 * beat
        st.add(st.pad([st.hz(n) for n in chord], 4 * beat + 0.4, 2200), b0, 0.3)
        for j in range(4):
            st.add(st.kick(0.95), b0 + j * beat, 0.9)
            st.add(st.hat(open_=(j % 2 == 1)), b0 + j * beat + beat / 2, 0.45, pan=0.25)
            st.add(st.bass(st.hz(root), beat * 0.9), b0 + j * beat, 0.8)
        for j in (1, 3):
            st.add(st.clap(), b0 + j * beat, 0.9)
        for j in range(8):
            st.add(st.pluck(st.hz(chord[[0, 2, 1, 3, 2, 1, 3, 2][j]]) * 2, 0.35), b0 + j * beat / 2, 0.3,
                   pan=(-0.4 if j % 2 else 0.4))
        k += 1
    st.add(st.pad([st.hz(n) for n in ("F3", "A3", "C4", "E4")], 3.2, 2600, 0.05, 1.0), end, 0.4)
    st.add(st.pad([st.hz(n) for n in ("C3", "G3", "C4", "E4")], total - end - 3.0, 2400, 0.4, 2.0), end + 3.0, 0.4)
    st.add(st.bass(st.hz("F1"), 3.0), end, 0.8)
    for j, n in enumerate(["C5", "E5", "G5", "C6", "G5", "E5", "C5", "G4"] * 2):
        st.add(st.pluck(st.hz(n), 0.6), end + j * 0.25, 0.25 * (1 - j / 18), pan=(-0.3 if j % 2 else 0.3))

    # the graphics' own sound effects, moved to wherever their scene now plays
    def remap(t):
        for s in gfx:
            if s["from"] <= t < s["to"]:
                return s["start"] + (t - s["from"]) / s["speed"]
        return None
    st.TIME_MAP = remap
    st.effects()
    st.TIME_MAP = None

    # the shots: their own sound design, a hit on the hook, a whoosh into every cut
    st.add(st.impact(0.7, 1.4), 0.0)
    for s in segs:
        if s["start"] > 0:
            st.add(st.whoosh(0.45), s["start"] - 0.3, 0.45)
        if s["type"] == "ai":
            a = clip_audio(os.path.join(SHOTS, s["clip"]), s["in"], s["len"])
            i = int(s["start"] * st.SR)
            n = min(len(a), st.N - i)
            st.L[i:i + n] += a[:n, 0] * 0.9
            st.R[i:i + n] += a[:n, 1] * 0.9
    out = os.path.join(OUT, "seedance-score.wav")
    st.write(out)
    return out


# ------------------------------------------------------------------ picture

def main():
    os.makedirs(OUT, exist_ok=True)
    segs = segments()
    total = segs[-1]["start"] + segs[-1]["len"]
    audio = score(segs, total)
    overlay = os.path.join(OUT, "overlay.mov")
    subprocess.run(["node", os.path.join(HERE, "render.mjs"), overlay], check=True, env=dict(os.environ, CUT="1"))

    inputs, chains, labels = [], [], []
    for k, s in enumerate(segs):
        frames = round((s["start"] + s["len"]) * FPS) - round(s["start"] * FPS)
        if s["type"] == "ai":
            inputs += ["-i", os.path.join(SHOTS, s["clip"])]
            idx = len(inputs) // 2 - 1
            chains.append(f"[{idx}:v]trim=start={s['in']},setpts=PTS-STARTPTS,fps={FPS},"
                          f"scale=1080:1080:flags=lanczos,setsar=1,trim=end_frame={frames},format=yuv420p[b{k}]")
        else:
            chains.append(f"color=c=black:s=1080x1080:r={FPS}:d={frames / FPS},format=yuv420p[b{k}]")
        labels.append(f"[b{k}]")
    ov = len(inputs) // 2
    inputs += ["-i", overlay, "-i", audio]
    graph = ";".join(chains) + f";{''.join(labels)}concat=n={len(segs)}:v=1:a=0[base];" \
                               f"[base][{ov}:v]overlay=format=auto,format=yuv420p[v]"
    final = os.path.join(HERE, "cleanroom-seedance.mp4")
    run("ffmpeg", "-y", "-loglevel", "error", *inputs, "-filter_complex", graph,
        "-map", "[v]", "-map", f"{ov + 1}:a",
        "-c:v", "libx264", "-preset", "slow", "-crf", "18", "-profile:v", "high", "-pix_fmt", "yuv420p", "-r", str(FPS),
        "-af", "loudnorm=I=-14:TP=-1.5:LRA=11", "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
        "-movflags", "+faststart", "-shortest", final)
    print(f"wrote {final} ({total:.2f}s)")


if __name__ == "__main__":
    main()
