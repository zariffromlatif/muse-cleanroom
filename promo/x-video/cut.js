// The Seedance cut: Seedance 2.5 shots for the story, video.html's scenes as the receipts.
// Read by video.html (?cut) and by cut.py, so it must stay plain JSON after "window.CUT = ".
//   ai   a Seedance clip from shots/, shown from `in` for `dur` seconds, with a caption on top
//   gfx  video.html's own timeline from `from` to `to`, played `speed` times faster
window.CUT = {
  "segments": [
    {"type": "ai", "clip": "s1-hook.mp4", "in": 0.0, "dur": 4.8,
     "cap": "Your AI agent is one setup guide away from <r>leaking your API keys.</r>"},
    {"type": "ai", "clip": "s2-stranger.mp4", "in": 0.0, "dur": 4.0,
     "cap": "No hacker needed. Just a helpful agent <r>following the docs.</r>"},
    {"type": "gfx", "from": 0.3, "to": 2.9, "speed": 1.0},
    {"type": "gfx", "from": 6.9, "to": 15.2, "speed": 1.35},
    {"type": "gfx", "from": 15.2, "to": 25.2, "speed": 1.7},
    {"type": "gfx", "from": 25.2, "to": 31.6, "speed": 1.45},
    {"type": "gfx", "from": 31.6, "to": 33.8, "speed": 1.0},
    {"type": "ai", "clip": "s3-airlock.mp4", "in": 0.0, "dur": 5.4,
     "cap": "Cleanroom pulls the secret <g>out of the step</g>…"},
    {"type": "ai", "clip": "s4-home.mp4", "in": 0.0, "dur": 4.0,
     "cap": "…and the task <g>still ships.</g>"},
    {"type": "gfx", "from": 34.45, "to": 46.4, "speed": 1.7},
    {"type": "gfx", "from": 46.4, "to": 52.0, "speed": 1.45},
    {"type": "gfx", "from": 52.0, "to": 57.6, "speed": 1.4},
    {"type": "gfx", "from": 57.6, "to": 63.6, "speed": 1.0}
  ]
};
