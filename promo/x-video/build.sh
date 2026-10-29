#!/usr/bin/env bash
# Build the X video: synthesize the soundtrack, render the frames, mux, normalize loudness.
# Needs python3 + numpy, node + playwright (Chromium), ffmpeg.
set -euo pipefail
cd "$(dirname "$0")"
mkdir -p out
python3 soundtrack.py out/soundtrack.wav
node render.mjs out/frames.mp4
ffmpeg -y -loglevel error -i out/frames.mp4 -i out/soundtrack.wav \
  -c:v libx264 -preset slow -crf 18 -profile:v high -pix_fmt yuv420p -r 30 \
  -af loudnorm=I=-14:TP=-1.5:LRA=11 -c:a aac -b:a 192k -ar 48000 \
  -movflags +faststart -shortest cleanroom-x.mp4
echo "wrote $(pwd)/cleanroom-x.mp4"
