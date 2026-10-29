"""Build the launch film: launch.html's graphics over the Seedance shots, with the score.

    python build.py            -> cleanroom-launch.mp4 (1920x1080, 30 fps)

Needs python3 + numpy, node + Playwright's Chromium, ffmpeg. The shots in shots/ are final, so
rebuilding spends no generation credits.
"""
from __future__ import annotations

import os
import re
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "out")
RENDER = os.path.join(HERE, "..", "x-video", "render.mjs")
FPS = 30


def shots():
    """The shot list, read from launch.html so the page and the edit cannot disagree."""
    src = open(os.path.join(HERE, "launch.html"), encoding="utf-8").read()
    rows = re.findall(r'\{\s*clip:\s*"([^"]+)",\s*start:\s*([\d.]+),\s*dur:\s*([\d.]+)\s*\}', src)
    dur = float(re.search(r"const DURATION = ([\d.]+);", src).group(1))
    return [(c, float(s), float(d)) for c, s, d in rows], dur


def run(*cmd, env=None):
    subprocess.run(cmd, check=True, env=env)


def main():
    os.makedirs(OUT, exist_ok=True)
    shot_list, total = shots()
    score = os.path.join(OUT, "score.wav")
    run("python3", os.path.join(HERE, "score.py"), score)
    overlay = os.path.join(OUT, "overlay.mov")
    run("node", RENDER, overlay,
        env=dict(os.environ, PAGE=os.path.join(HERE, "launch.html"), SIZE="1920x1080", ALPHA="1"))

    # the picture underneath: each shot where it plays, black everywhere else
    inputs, chains, labels, cursor = [], [], [], 0
    for k, (clip, start, dur) in enumerate(shot_list):
        f0, f1 = round(start * FPS), round((start + dur) * FPS)
        if f0 > cursor:
            chains.append(f"color=c=black:s=1920x1080:r={FPS}:d={(f0 - cursor) / FPS},format=yuv420p[g{k}]")
            labels.append(f"[g{k}]")
        inputs += ["-i", os.path.join(HERE, "shots", clip)]
        i = len(inputs) // 2 - 1
        chains.append(f"[{i}:v]fps={FPS},scale=1920:1080:flags=lanczos,setsar=1,trim=end_frame={f1 - f0},"
                      f"setpts=PTS-STARTPTS,format=yuv420p[s{k}]")
        labels.append(f"[s{k}]")
        cursor = f1
    end = round(total * FPS)
    if end > cursor:
        chains.append(f"color=c=black:s=1920x1080:r={FPS}:d={(end - cursor) / FPS},format=yuv420p[tail]")
        labels.append("[tail]")
    ov = len(inputs) // 2
    inputs += ["-i", overlay, "-i", score]
    graph = ";".join(chains) + f";{''.join(labels)}concat=n={len(labels)}:v=1:a=0[base];" \
                               f"[base][{ov}:v]overlay=format=auto,format=yuv420p[v]"
    final = os.path.join(HERE, "cleanroom-launch.mp4")
    run("ffmpeg", "-y", "-loglevel", "error", *inputs, "-filter_complex", graph,
        "-map", "[v]", "-map", f"{ov + 1}:a",
        "-c:v", "libx264", "-preset", "slow", "-crf", "17", "-profile:v", "high", "-pix_fmt", "yuv420p",
        "-r", str(FPS), "-af", "loudnorm=I=-14:TP=-1.5:LRA=9", "-c:a", "aac", "-b:a", "256k", "-ar", "48000",
        "-movflags", "+faststart", "-shortest", final)
    print(f"wrote {final} ({total:.1f}s)")


if __name__ == "__main__":
    main()
