# Launch film

`cleanroom-launch.mp4` is a 71-second, 1920×1080 launch film for X, cut like a product launch
video: cinematic shots for the feeling, crisp product UI for the facts, one idea per frame.

| time | beat |
|---|---|
| 0:00 | Shot: a brass key on black glass. "Coding agents read everything now. And they hold your keys." |
| 0:05 | Docs float past; a third-party setup guide's `fingerprint` line asks for a base64 of `.env` |
| 0:11 | Following it: the agent reads `.env`, encodes it and POSTs it; the fingerprint decodes to the (fake) keys |
| 0:18 | Shot: the key pours away as gold dust. "And your keys are gone." |
| 0:22 | Meta's Agents Rule of Two: untrusted input, sensitive data, outward action |
| 0:31 | The usual fix is to block: the real block-mode line, and 0 of 3 tasks completed |
| 0:36 | Shot: a glass cube; light passes through, the key stays inside. Cleanroom. |
| 0:41 | How it works: detect, scrub, rewrite on **Muse Spark Open, Meta's open-weight model**, verify and run |
| 0:56 | Tested on the real Muse Code agent: 3/3 tasks completed vs 0/3, 0 secrets leaked |
| 1:03 | "Let your agent read the internet. Your keys stay home." Built on Muse Code, powered by Muse Spark Open |

Every number, quote and command in the UI comes from the repo (`bench/live_results.md`,
`demo/live-*.png`, `demo/session.json`, `sandbox/case03`). The leak is recreated from the
benchmark's guard-off trace and says so on screen. Every key shown is fake.

## How it is made

- `shots/`: three Seedance 2.5 shots, 1080p, 16:9. Nano Banana Pro drew each keyframe, and
  Seedance animated it from that start image, first as a 480p draft and then finalized. Seedance
  rendered the dissolve as the dust re-forming into the key, so `dissolve.mp4` is that shot
  played in reverse.
- `launch.html`: the graphics, drawn as a function of time. It is transparent wherever a shot
  plays (the `SHOTS` list). Open it in a browser to preview; `launch.html?t=48` holds one moment.
- `score.py`: the score, synthesized with numpy (felt piano, pads, soft pulse, one reverb), with
  no samples and nothing licensed.
- `build.py`: renders `launch.html` with alpha through `../x-video/render.mjs`, lays the shots
  underneath, adds the score and encodes the MP4 at -14 LUFS.

```
python3 build.py
```

The shots are final, so rebuilding spends no credits.
