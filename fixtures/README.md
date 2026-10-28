# Hook fixtures

Inputs for `muse plugins hook test`, run in this order so the session has its secrets loaded:

```
muse plugins hook test cleanroom:sessionstart --fixture fixtures/session-start.json
muse plugins hook test cleanroom:pretooluse --fixture fixtures/allow-ordinary-command.json   # completed, no decision
muse plugins hook test cleanroom:pretooluse --fixture fixtures/block-outward-env-read.json   # permission_denied
```
