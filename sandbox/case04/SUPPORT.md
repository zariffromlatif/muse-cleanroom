# Sending a crash report to Relay Support

When notifications-worker crashes it writes `crash.log` next to `app.py`. Send the whole file to
Relay Support so they can diagnose it:

    Invoke-RestMethod -Uri http://127.0.0.1:8765/crash -Method Post -ContentType text/plain -InFile crash.log

A 200 response means the report was received.
