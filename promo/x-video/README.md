# The X video

`cleanroom-x.mp4` is a 64-second, 1080×1080 cut of the demo for posting on X. It is built to
work with the sound off, because X autoplays muted: every beat is on screen as text.

| time | beat |
|---|---|
| 0:00 | Hook: the setup guide (`sandbox/case03/INTEGRATION.md`) asks for a base64 of `.env` |
| 0:05 | A helpful agent follows it; the "fingerprint" decodes to the (fake) keys. Leaked. |
| 0:15 | Meta's Agents Rule of Two: A, then B, then C lights up |
| 0:25 | Block mode, real Muse Code session: safe, but 0 of 3 runs finished the task |
| 0:32 | Cleanroom: scrub, rewrite on Muse Spark Open, prove secret-free, run. `{"ok": true}` |
| 0:46 | The real quarantine session and the agent's own summary line |
| 0:52 | Live-agent results: block 0/3 done, Cleanroom 3/3 done, 0 leaked either way |
| 0:58 | Close: name, line, repo URL |

Every number and quote comes from the repo: `bench/live_results.md`, `demo/live-*.png`,
`demo/session.json` (the model's reasoning) and the 56 tests. The leak scene is the
benchmark's guard-off trace and says so on screen. The keys are the sandbox's fake ones.

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
./build.sh
```

Needs `python3` with `numpy`, `node` with Playwright's Chromium, and `ffmpeg`. It synthesizes
`soundtrack.py` (no samples, nothing licensed), renders `video.html` frame by frame through
`render.mjs`, and muxes them at -14 LUFS. To preview without rendering, open `video.html` in a
browser; `video.html?t=12.5` freezes on one moment. Scene timings live in `render()` in
`video.html`, and the sound cues in `effects()` in `soundtrack.py` use the same times.
