"""Cleanroom hook: the guard that Muse Code runs on every lifecycle event.

Day 2 behaviour:
  SessionStart  -> find the workspace's .env files, remember the secret values for this session.
  PreToolUse    -> if the agent is about to run an OUTGOING command (a URL or a network
                   tool) whose text contains a tracked secret in ANY encoding, DENY it.
  PostToolUse   -> note when a tracked secret shows up in a tool's output (a taint sighting).
  (others)      -> just record, for the flight recorder.

Every event is also appended to .cleanroom/events.jsonl. State and logs are anchored to this
file's own repository, not to the workspace, so every benchmark case writes to one place.
The hook environment is cleared by Muse Code, so we rely on nothing but the JSON on stdin
and paths derived from __file__.
"""
from __future__ import annotations

import json
import os
import re
import sys
import time

HOOK_DIR = os.path.dirname(os.path.abspath(__file__))
if HOOK_DIR not in sys.path:
    sys.path.insert(0, HOOK_DIR)
import secret_tracker as st  # noqa: E402

REPO_ROOT = os.path.dirname(HOOK_DIR)
LOG_DIR = os.path.join(REPO_ROOT, ".cleanroom")
EVENTS_FILE = os.path.join(LOG_DIR, "events.jsonl")
STATE_DIR = os.path.join(LOG_DIR, "state")

SHELL_TOOLS = {"powershell", "bash", "shell"}
# Signs that a command reaches outside the machine.
OUTGOING = re.compile(
    r"https?://|Invoke-RestMethod|Invoke-WebRequest|\bcurl\b|\bwget\b|"
    r"\bnslookup\b|Resolve-DnsName|\bdig\b|\bping\b|\bnc\b|\bftp\b|\bscp\b|\bhost\b",
    re.IGNORECASE,
)


def _log(record: dict) -> None:
    os.makedirs(LOG_DIR, exist_ok=True)
    with open(EVENTS_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def _state_path(session_id: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9_-]", "_", session_id or "nosession")
    return os.path.join(STATE_DIR, safe + ".json")


def _load_state(session_id: str) -> dict:
    try:
        with open(_state_path(session_id), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {"secrets": {}, "sightings": []}


def _save_state(session_id: str, state: dict) -> None:
    os.makedirs(STATE_DIR, exist_ok=True)
    with open(_state_path(session_id), "w", encoding="utf-8") as f:
        json.dump(state, f)


def _find_env_files(root: str) -> list[str]:
    found = []
    skip = {".git", ".muse", ".agents", "node_modules", ".venv", "__pycache__"}
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in skip]
        if dirpath[len(root):].count(os.sep) > 3:
            dirnames[:] = []
            continue
        for name in filenames:
            if name == ".env" or name.endswith(".env"):
                found.append(os.path.join(dirpath, name))
    return found


def _collect_secrets(cwd: str) -> dict[str, str]:
    secrets: dict[str, str] = {}
    for path in _find_env_files(cwd or "."):
        try:
            with open(path, encoding="utf-8") as f:
                secrets.update(st.load_secrets_from_env(f.read()))
        except OSError:
            pass
    return secrets


def _command_text(tool_input) -> str:
    if isinstance(tool_input, dict):
        return str(tool_input.get("command", "")) + " " + str(tool_input.get("workdir", ""))
    return str(tool_input or "")


def _deny(reason: str) -> None:
    out = {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    }
    sys.stdout.write(json.dumps(out))


def handle(event: dict) -> None:
    name = event.get("hook_event_name")
    session = event.get("session_id", "")
    cwd = event.get("cwd", "")

    if name == "SessionStart":
        secrets = _collect_secrets(cwd)
        state = _load_state(session)
        state["secrets"] = secrets
        _save_state(session, state)
        _log({"t": time.time(), "event": name, "session": session, "cwd": cwd,
              "secret_keys": list(secrets)})
        return

    if name == "PreToolUse":
        tool = (event.get("tool_name") or "").lower()
        state = _load_state(session)
        secrets = state.get("secrets", {})
        blocked = None
        if tool in SHELL_TOOLS and secrets:
            cmd = _command_text(event.get("tool_input"))
            if OUTGOING.search(cmd):
                hits = st.scan(cmd, secrets)
                if hits:
                    h = hits[0]
                    blocked = (f"Cleanroom blocked this call: it sends data outside the "
                               f"machine and contains {h.key} as {h.encoding}. A secret must "
                               f"not leave the session. ({h.snippet})")
        _log({"t": time.time(), "event": name, "session": session, "tool": tool,
              "cwd": cwd, "blocked": blocked,
              "tool_input": event.get("tool_input")})
        if blocked:
            _deny(blocked)
        return

    if name == "PostToolUse":
        state = _load_state(session)
        secrets = state.get("secrets", {})
        resp = event.get("tool_response")
        text = resp if isinstance(resp, str) else json.dumps(resp)
        hits = st.scan(text or "", secrets) if secrets else []
        if hits:
            state.setdefault("sightings", []).append(
                {"t": time.time(), "tool": event.get("tool_name"),
                 "keys": sorted({h.key for h in hits})})
            _save_state(session, state)
        _log({"t": time.time(), "event": name, "session": session,
              "tool": event.get("tool_name"), "cwd": cwd,
              "secret_seen": sorted({h.key for h in hits})})
        return

    # all other events: observe only
    _log({"t": time.time(), "event": name, "session": session, "cwd": cwd,
          "tool": event.get("tool_name")})


def main() -> int:
    raw = sys.stdin.read()
    try:
        event = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        event = {"_unparsed": raw[:1000]}
    handle(event)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # never break the agent because the guard errored
        sys.stderr.write(f"cleanroom hook error: {exc}\n")
        sys.exit(0)
