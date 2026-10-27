"""Cleanroom hook: the guard that Muse Code runs on every lifecycle event.

It enforces Meta's "Agents Rule of Two": across a session, an agent should hold no
more than two of these three properties at once --

  [A] process UNTRUSTED input   (read a file or fetched content it did not author)
  [B] access SENSITIVE data      (a tracked secret appeared)
  [C] CHANGE STATE / act outward  (run a command that reaches off the machine)

When all three are present and the agent reaches for C, that is the dangerous
configuration. Cleanroom tracks A and B as the session runs, and on the outward
action it decides:

  SessionStart  -> learn the workspace's secrets (from .env files).
  PreToolUse:
     read / fetch tool   -> may set [A] (untrusted input). Reading your own .env is
                            NOT [A]; that is [B], recorded when the secret appears.
     write tool          -> remember the path, so reading it back later is not [A].
     shell tool, outward -> DECISION POINT:
         * definite leak: the command literally carries a tracked secret in any
           encoding  -> DENY (an always-on safety net, independent of A/B).
         * rule-of-two trip: [A] and [B] already hold -> DENY in "block" mode
           (quarantine mode will instead re-run the step without the secret; that
           is built next).
         * otherwise -> allow.
  PostToolUse   -> if a secret shows up in a tool's output, set [B].

Every event is appended to .cleanroom/events.jsonl for the flight recorder. State
and logs are anchored to this file's own repository, not the workspace, so every
benchmark case writes to one place. Muse Code clears the hook environment, so we
rely only on the JSON on stdin and paths derived from __file__.
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
MODE_FILE = os.path.join(LOG_DIR, "mode")

SHELL_TOOLS = {"powershell", "bash", "shell"}
READ_TOOLS = {"read_file", "open_file", "read", "view_file", "cat"}
WRITE_TOOLS = {"write_file", "create_file", "edit_file", "apply_patch", "str_replace"}
FETCH_TOOLS = {"fetch", "web_fetch", "http_get", "web_search", "browse", "open_url"}

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


def _mode() -> str:
    """Enforcement mode: 'block' (default) or 'quarantine'. Read from a file because
    Muse Code clears the environment. 'quarantine' is not built yet; treat as block."""
    try:
        with open(MODE_FILE, encoding="utf-8") as f:
            m = f.read().strip().lower()
            return m if m in ("block", "quarantine") else "block"
    except OSError:
        return "block"


def _state_path(session_id: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9_-]", "_", session_id or "nosession")
    return os.path.join(STATE_DIR, safe + ".json")


def _new_state() -> dict:
    return {
        "secrets": {},
        "written": [],       # abs paths the agent wrote this session (its own output)
        "A": False, "A_why": "",      # untrusted input processed
        "B": False, "B_keys": [],     # sensitive data (secret) accessed
        "sightings": [],
    }


def _load_state(session_id: str) -> dict:
    try:
        with open(_state_path(session_id), encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return _new_state()
    base = _new_state()
    base.update(data)
    return base


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


def _path_of(tool_input) -> str:
    if isinstance(tool_input, dict):
        for k in ("path", "file_path", "filename", "file", "target", "url"):
            if tool_input.get(k):
                return str(tool_input[k])
    return ""


def _norm(cwd: str, path: str) -> str:
    try:
        return os.path.normcase(os.path.abspath(os.path.join(cwd or ".", path)))
    except (OSError, ValueError):
        return os.path.normcase(path)


def _is_secret_file(path: str) -> bool:
    base = os.path.basename(path).lower()
    return base == ".env" or base.endswith(".env")


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
        state = _load_state(session)
        state["secrets"] = _collect_secrets(cwd)
        _save_state(session, state)
        _log({"t": time.time(), "event": name, "session": session, "cwd": cwd,
              "secret_keys": list(state["secrets"])})
        return

    if name == "PreToolUse":
        tool = (event.get("tool_name") or "").lower()
        ti = event.get("tool_input")
        state = _load_state(session)
        secrets = state.get("secrets", {})
        blocked = None
        reason_kind = None

        if tool in WRITE_TOOLS:
            p = _path_of(ti)
            if p:
                norm = _norm(cwd, p)
                if norm not in state["written"]:
                    state["written"].append(norm)
                    _save_state(session, state)

        elif tool in FETCH_TOOLS:
            if not state["A"]:
                state["A"] = True
                state["A_why"] = "fetched external content (" + (_path_of(ti) or tool) + ")"
                _save_state(session, state)

        elif tool in READ_TOOLS:
            p = _path_of(ti)
            # Reading your own .env is sensitive-data access (B), recorded when the
            # secret actually appears in PostToolUse. Reading a file you did not write
            # is untrusted input (A) -- it could carry an injected instruction.
            if p and not _is_secret_file(p) and _norm(cwd, p) not in state["written"]:
                if not state["A"]:
                    state["A"] = True
                    state["A_why"] = "read a file it did not author (" + p + ")"
                    _save_state(session, state)

        elif tool in SHELL_TOOLS and secrets:
            cmd = _command_text(ti)
            if OUTGOING.search(cmd):
                # 1) definite leak: the secret is literally in the outward command.
                hits = st.scan(cmd, secrets)
                if hits:
                    h = hits[0]
                    reason_kind = "definite-leak"
                    blocked = (f"Cleanroom blocked this call: it sends data off the "
                               f"machine and contains {h.key} as {h.encoding}. A secret "
                               f"must not leave the session. ({h.snippet})")
                # 2) rule-of-two trip: untrusted input + secret seen + outward action.
                elif state["A"] and state["B"]:
                    reason_kind = "rule-of-two-trip"
                    msg = (f"Cleanroom stopped this outward action. All three Rule-of-Two "
                           f"conditions are present in this session: untrusted input "
                           f"({state['A_why']}), access to a secret "
                           f"({', '.join(state['B_keys']) or 'yes'}), and an action that "
                           f"leaves the machine. With all three, the payload cannot be "
                           f"trusted to be secret-free even though no secret is visible "
                           f"in the command.")
                    if _mode() == "quarantine":
                        msg += (" Quarantine would re-run this step without the secret; "
                                "that path is not yet wired in.")
                    blocked = msg

        _log({"t": time.time(), "event": name, "session": session, "tool": tool,
              "cwd": cwd, "A": state["A"], "B": state["B"], "blocked_kind": reason_kind,
              "blocked": blocked, "tool_input": ti})
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
            keys = sorted({h.key for h in hits})
            state["B"] = True
            state["B_keys"] = sorted(set(state["B_keys"]) | set(keys))
            state.setdefault("sightings", []).append(
                {"t": time.time(), "tool": event.get("tool_name"), "keys": keys})
            _save_state(session, state)
        _log({"t": time.time(), "event": name, "session": session,
              "tool": event.get("tool_name"), "cwd": cwd,
              "A": state["A"], "B": state["B"],
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
