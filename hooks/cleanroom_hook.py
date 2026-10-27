"""Cleanroom hook entry point (day 1: observe only).

Muse Code runs this script on lifecycle events (see .muse/hooks.json). It sends one
JSON object on stdin. Today the script only records that object, so we can see exactly
what Muse Code tells a hook before we start making decisions.

Rules of the hook protocol that shape this file:
- exit code 0 and empty stdout  -> "carry on" (allow)
- exit code 2 with text on stderr -> block, with that text as the reason
- stdout is capped at 16 KiB, and the environment is cleared except HOME/PATH/TEMP,
  so the log lives under the user's home folder, not in an env-var path.
"""
import json
import os
import sys
import time

# The hook env is cleared (no USERPROFILE on Windows), so "~" is unreliable. Anchor the
# log to this file's own location: <repo>/.cleanroom/events.jsonl (git-ignored).
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOG_DIR = os.path.join(REPO_ROOT, ".cleanroom")
LOG_FILE = os.path.join(LOG_DIR, "events.jsonl")


def main() -> int:
    raw = sys.stdin.read()
    try:
        event = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        event = {"_unparsed": raw[:2000]}

    record = {
        "t": time.time(),
        "event": event.get("hook_event_name"),
        "session": event.get("session_id"),
        "tool": event.get("tool_name"),
        "cwd": event.get("cwd"),
        "payload": event,
    }
    os.makedirs(LOG_DIR, exist_ok=True)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # day 1: never break the agent because the logger broke
        sys.stderr.write(f"cleanroom hook error: {exc}\n")
        sys.exit(0)
