# The X videos

> The 16:9 launch film in [`../launch/`](../launch/) (`cleanroom-launch.mp4`) supersedes these
> two square cuts as the video to post. They stay here as alternates.

Two cuts of the demo for posting on X, both 1080×1080 and readable with the sound off (X
autoplays muted):

- **`cleanroom-seedance.mp4`** (about 60 s), the one to post. Four Seedance 2.5 shots tell the
  story as an animated short. Between them, the motion-graphics scenes are the receipts: the
  real guide, the Rule of Two, the real Muse Code sessions and the live-agent numbers.
- **`cleanroom-x.mp4`** (64 s), motion graphics only.

## The Seedance cut

| time | beat |
|---|---|
| 0:00 | Seedance: an eager little robot seals a glowing key in an envelope and posts it. "Your AI agent is one setup guide away from leaking your API keys." |
| 0:05 | Seedance: a gloved hand snatches the envelope out of a data storm. "No hacker needed." |
| 0:09 | Receipts: the guide's `fingerprint` line, the base64 decoding to the (fake) keys, LEAKED |
| 0:17 | Meta's Agents Rule of Two lights up A, B, C |
| 0:23 | Block mode, real Muse Code session: safe, but 0 of 3 runs finished the task |
| 0:27 | Cleanroom title card |
| 0:30 | Seedance: in a green airlock, an arm locks the key in a safe and the envelope flies on |
| 0:35 | Seedance: the robot hugs the key under a green check. "…and the task still ships." |
| 0:39 | Receipts: scrub, Muse Spark Open rewrite, proven secret-free, `{"ok": true}`; the real session; 3/3 vs 0/3 |
| 0:54 | Close: name, line, repo URL |

The animated shots are a metaphor and look like one. Every number, quote and screenshot in
the receipts comes from the repo (`bench/live_results.md`, `demo/live-*.png`,
`demo/session.json`, the 56 tests). The leak scene is the benchmark's guard-off trace and
says so on screen. The keys are the sandbox's fake ones.

How the shots were made: Nano Banana Pro drew the robot and one keyframe per shot. Seedance 2.5
animated each keyframe (omni-reference, start image, 1:1), first as 480p drafts and then
finalized at 1080p. The finished shots are in `shots/`, so rebuilding needs no credits.

## Post copy

Main post (267 characters):

```
What if a setup guide asks your AI coding agent for a base64 of your .env?

Blocking keeps the key safe, but the task dies.

Cleanroom enforces Meta's Agents Rule of Two in Muse Code and rewrites the risky step on Muse Spark Open instead.

Task ships. Key stays home.
```

First reply (put the link here, not in the main post):

```
Open source, 56 tests, Python stdlib only. Try it in 3 minutes:
github.com/zariffromlatif/muse-cleanroom

Built for the Meta Global AI Developer Hackathon @MetaforDevs @AIatMeta
```

Check the event guide for an official hashtag before posting, and submit the post's link on
the hackathon platform.

## Rebuild

```
python3 cut.py      # the Seedance cut -> cleanroom-seedance.mp4
./build.sh          # the graphics-only cut -> cleanroom-x.mp4
```

Needs `python3` with `numpy`, `node` with Playwright's Chromium, and `ffmpeg`.
- `video.html` draws every graphics frame as a function of time. `render.mjs` steps it into
  ffmpeg.
- `soundtrack.py` synthesizes the score and effects, with no samples and nothing licensed.
- `cut.js` is the Seedance edit: which shot plays when, and which stretch of `video.html`
  plays between shots, at what speed. `cut.py` renders the graphics with alpha (`video.html?cut`),
  lays the shots underneath, re-times the score to the new cut, and mixes in the shots' own
  sound.

To preview without rendering, open `video.html` in a browser; `video.html?t=12.5` freezes on one
moment.
