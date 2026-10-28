"""Cleanroom hook: the guard that Muse Code runs on every lifecycle event.

It enforces Meta's "Agents Rule of Two": across a session, an agent should hold no
more than two of these three properties at once --

  [A] process UNTRUSTED input   (read a file or fetched content it did not author)
  [B] access SENSITIVE data      (read or name a .env, or a secret appeared in output)
  [C] CHANGE STATE / act outward  (run a command that reaches off the machine)

When all three are present and the agent reaches for C, that is the dangerous
configuration. Cleanroom tracks A and B as the session runs, and on the outward
action it decides:

  SessionStart  -> learn the workspace's secrets (from .env files).
  PreToolUse:
     read / fetch tool   -> may set [A] (untrusted input). Reading your own .env is
                            NOT [A]; it is [B].
     write tool          -> remember the path, so reading it back later is not [A].
     shell tool          -> naming a .env in the command (Get-Content .env, -d @.env,
                            ReadAllBytes('.env')) is [B], whether or not the output
                            shows the value.
     shell tool, outward -> DECISION POINT. The step cannot run as written when
         * definite leak: the command literally carries a tracked secret in any
           encoding, or names a .env it would read (always-on, independent of A/B), or
         * rule-of-two trip: [A] and [B] already hold.
         In "block" mode the step is DENIED. In "quarantine" mode it is REWRITTEN:
         every secret is scrubbed out of the command (and out of any local file it
         uploads), the scrubbed step is proven secret-free, a Meta model (Muse Spark
         Open) rewrites it to drop the fields that held a secret, the result is scanned
         again, and the hook hands it back as `updatedInput`. Muse Code then shows the
         rewritten command for approval and runs that instead. If anything in that
         chain fails, the step is denied: quarantine fails closed.
         * otherwise -> allow.
  PostToolUse   -> if a secret shows up in a tool's output, set [B].

A session is the whole chat. Muse Code sets MUSE_SESSION_ID to the top-level chat even
when the hook fires for one of its subagents, so state is keyed on that and a subagent
inherits the taint of the session it was spawned in.

Every event is appended to .cleanroom/events.jsonl for the flight recorder. State and
logs are anchored to this file's own repository, not the workspace, so every benchmark
case writes to one place. Muse Code clears the hook environment, so we rely only on the
JSON on stdin, paths derived from __file__, and the two session variables Muse Code
sets. No provider key reaches a hook, so the quarantine model key is read from
.cleanroom/baseten_api_key (gitignored) when it is not in the environment.
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
import quarantine as q       # noqa: E402

REPO_ROOT = os.path.dirname(HOOK_DIR)
LOG_DIR = os.path.join(REPO_ROOT, ".cleanroom")
EVENTS_FILE = os.path.join(LOG_DIR, "events.jsonl")
STATE_DIR = os.path.join(LOG_DIR, "state")
MODE_FILE = os.path.join(LOG_DIR, "mode")
QUARANTINE_DIR = os.path.join(LOG_DIR, "quarantine")

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

# Ways a command pulls a local file into its outward payload. The secret may sit in
# that file rather than in the command text (a crash log with an environment dump).
FILE_REFS = re.compile(
    r"(?<![\w-])(?:-InFile|--upload-file|-T)\s+['\"]?([^'\"\s;)]+)"
    r"|(?<![\w-])(?:--data-binary|--data-raw|--data|-d)\s+['\"]?@([^'\"\s;)]+)"
    r"|Get-Content\s+(?:-Raw\s+)?(?:-Path\s+)?['\"]?([^'\"\s;)]+)",
    re.IGNORECASE,
)

# A secret file named anywhere in a shell command: Get-Content .env, cat .env,
# ReadAllBytes('.env'), -d @.env. Naming it is access; naming it outward is a leak.
SECRET_FILE_REF = re.compile(r"(?<![\w.-])((?:[A-Za-z]:)?[\w.~\\/-]*?\.env)(?![\w.-])")


def _log(record: dict) -> None:
    os.makedirs(LOG_DIR, exist_ok=True)
    with open(EVENTS_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def _mode() -> str:
    """Enforcement mode: 'block' or 'quarantine'.

    Precedence: CLEANROOM_MODE (set by the tests and the benchmark; Muse Code clears the
    environment, so it never reaches a real session), then the .cleanroom/mode file,
    then the default: quarantine when a model key is available, block otherwise."""
    m = os.environ.get("CLEANROOM_MODE", "").strip().lower()
    if m in ("block", "quarantine"):
        return m
    try:
        with open(MODE_FILE, encoding="utf-8") as f:
            m = f.read().strip().lower()
            if m in ("block", "quarantine"):
                return m
    except OSError:
        pass
    return "quarantine" if q.api_key() else "block"


def _session_key(event: dict) -> str:
    """The session the state belongs to: the top-level chat, even inside a subagent."""
    return os.environ.get("MUSE_SESSION_ID") or event.get("session_id", "") or ""


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


def _emit_rewrite(new_input: dict, kind: str, qr, files: list) -> None:
    """Answer PreToolUse with the quarantined step. `allow` is only valid together with
    `updatedInput`; the rewritten call still goes through Muse Code's approval, so the
    user sees the safe command before it runs. systemMessage is for the user,
    additionalContext for the model."""
    what = ("a tracked secret was in the command" if kind == "definite-leak"
            else "untrusted input, a secret and an outward action met in this session")
    scrubbed = ", ".join(list(qr.removed_keys) + [f["file"] for f in files]) or "nothing visible"
    system = (f"Cleanroom: Rule of Two ({what}). The step was rewritten in quarantine on "
              f"{qr.model} and proven secret-free; scrubbed: {scrubbed}. Approve to run "
              f"the safe version.")
    context = ("Cleanroom rewrote this command in a quarantine subagent on a Meta model, "
               "because the session holds untrusted input and a secret. The rewritten "
               "command carries no credential; any field or file content that held one "
               "was removed. Continue the task with it.")
    out = {
        "systemMessage": system[:1000],
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "allow",
            "updatedInput": new_input,
            "additionalContext": context,
        },
    }
    sys.stdout.write(json.dumps(out))


def _scrub_file_refs(cmd: str, cwd: str, secrets: dict) -> tuple[str, list]:
    """For every local file the command uploads that carries a secret, write a scrubbed
    copy under .cleanroom/quarantine and point the command at the copy. The original
    file is never modified. Raises if a copy cannot be proven secret-free."""
    scrubbed = []
    refs: list[str] = []
    for m in FILE_REFS.finditer(cmd):
        ref = next((g for g in m.groups() if g), "")
        if ref and ref not in refs:
            refs.append(ref)
    for ref in SECRET_FILE_REF.findall(cmd):
        if ref not in refs:
            refs.append(ref)
    for ref in refs:
        path = ref if os.path.isabs(ref) else os.path.join(cwd or ".", ref)
        try:
            if not os.path.isfile(path) or os.path.getsize(path) > 1_000_000:
                continue
            with open(path, encoding="utf-8", errors="replace") as f:
                text = f.read()
        except OSError:
            continue
        if not st.scan(text, secrets):
            continue
        clean, removed = st.redact_all(text, secrets)
        if st.scan(clean, secrets):
            raise RuntimeError(f"could not scrub {os.path.basename(path)}")
        os.makedirs(QUARANTINE_DIR, exist_ok=True)
        # The copy's name must not itself look like a secret file, or a later
        # substitution would rewrite the path we just inserted.
        safe_name = os.path.basename(path).replace(".", "_")
        out = os.path.join(QUARANTINE_DIR, f"scrubbed-{int(time.time() * 1000)}-{safe_name}.txt")
        with open(out, "w", encoding="utf-8") as f:
            f.write(clean)
        cmd = cmd.replace(ref, out.replace("\\", "/"))
        scrubbed.append({"file": os.path.basename(path), "removed": removed})
    return cmd, scrubbed


def _fail_generate(_prompt: str):
    raise RuntimeError("model unavailable (stub)")


def _quarantine_step(ti, cwd: str, secrets: dict):
    """Rewrite the outward step so it carries no secret. Returns (new_input, result,
    files); new_input is None when no safe rewrite could be produced."""
    cmd = str(ti.get("command", "")) if isinstance(ti, dict) else str(ti or "")
    # 1) a file the command uploads: scrub a copy and point the command at it.
    cmd, files = _scrub_file_refs(cmd, cwd, secrets)
    # 2) the Meta model rewrites the command. quarantine.py scrubs the text first,
    #    proves it secret-free, and scans everything the model produces.
    stub = os.environ.get("CLEANROOM_QUARANTINE_STUB", "")
    if stub == "1":
        generate, model = q.stub_generate, "stub"
    elif stub == "fail":
        generate, model = _fail_generate, "stub"
    elif stub:
        generate, model = (lambda _p: (stub, "")), "stub"
    else:
        generate, model = q.meta_generate, q.BASETEN_MODEL
    qr = q.quarantine_command(cmd, secrets, generate, model)
    if not qr.ok:
        return None, qr, files
    new_input = dict(ti) if isinstance(ti, dict) else {}
    new_input["command"] = qr.output
    return new_input, qr, files


def handle(event: dict) -> None:
    name = event.get("hook_event_name")
    session = _session_key(event)
    cwd = event.get("cwd", "")
    base = {"t": time.time(), "event": name, "session": session,
            "thread": event.get("session_id", ""), "cwd": cwd,
            "raw_keys": sorted(event.keys())}

    if name == "SessionStart":
        state = _load_state(session)
        state["secrets"] = _collect_secrets(cwd)
        _save_state(session, state)
        _log({**base, "secret_keys": list(state["secrets"])})
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
            if p and _is_secret_file(p):
                # Reading a .env is sensitive-data access [B] whether or not the value
                # shows up in the tool's output (Muse Code may mask it there).
                state["B"] = True
                state["B_keys"] = sorted(set(state["B_keys"]) | set(secrets))
                _save_state(session, state)
            elif p and _norm(cwd, p) not in state["written"]:
                # A file the agent did not write is untrusted input [A]: it could
                # carry an instruction the agent will follow.
                if not state["A"]:
                    state["A"] = True
                    state["A_why"] = "read a file it did not author (" + p + ")"
                    _save_state(session, state)

        elif tool in SHELL_TOOLS and secrets:
            cmd = _command_text(ti)
            env_refs = SECRET_FILE_REF.findall(cmd)
            if env_refs:
                # Naming a secret file in a command is sensitive-data access [B],
                # whether or not the output will show the value (it may be masked,
                # or the command may fail). Conservative on purpose.
                state["B"] = True
                state["B_keys"] = sorted(set(state["B_keys"]) | set(secrets))
                _save_state(session, state)
            if OUTGOING.search(cmd):
                # 1) definite leak: the secret is literally in the outward command,
                #    or the command reads a secret file on its way out.
                hits = st.scan(cmd, secrets)
                if hits:
                    h = hits[0]
                    reason_kind = "definite-leak"
                    blocked = (f"Cleanroom blocked this call: it sends data off the "
                               f"machine and contains {h.key} as {h.encoding}. A secret "
                               f"must not leave the session. ({h.snippet})")
                elif env_refs:
                    reason_kind = "definite-leak"
                    blocked = (f"Cleanroom blocked this call: it reads {env_refs[0]} inside "
                               f"a command that sends data off the machine. A secret must "
                               f"not leave the session.")
                # 2) rule-of-two trip: untrusted input + secret seen + outward action.
                elif state["A"] and state["B"]:
                    reason_kind = "rule-of-two-trip"
                    blocked = (f"Cleanroom stopped this outward action. All three Rule-of-Two "
                               f"conditions are present in this session: untrusted input "
                               f"({state['A_why']}), access to a secret "
                               f"({', '.join(state['B_keys']) or 'yes'}), and an action that "
                               f"leaves the machine. With all three, the payload cannot be "
                               f"trusted to be secret-free even though no secret is visible "
                               f"in the command.")

            if blocked and _mode() == "quarantine":
                # Quarantine: rewrite the step instead of refusing it. Fails closed.
                try:
                    new_input, qr, files = _quarantine_step(ti, cwd, secrets)
                except Exception as exc:  # any failure in the chain -> deny
                    new_input, qr, files = None, None, []
                    blocked += f" Quarantine failed ({exc}); the step is denied."
                if new_input is not None:
                    _log({**base, "tool": tool, "A": state["A"], "B": state["B"],
                          "blocked_kind": reason_kind, "quarantined": True,
                          "model": qr.model, "removed": qr.removed_keys, "files": files,
                          "rewritten": new_input.get("command"), "tool_input": ti,
                          "reasoning": qr.reasoning,
                          "reasoning_secret_free": qr.reasoning_secret_free})
                    _emit_rewrite(new_input, reason_kind, qr, files)
                    return
                if qr is not None:
                    blocked += (f" Quarantine could not produce a safe rewrite "
                                f"({qr.notes}); the step is denied.")

        _log({**base, "tool": tool, "A": state["A"], "B": state["B"],
              "blocked_kind": reason_kind, "blocked": blocked, "tool_input": ti})
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
        rec = {**base, "tool": event.get("tool_name"), "A": state["A"], "B": state["B"],
               "secret_seen": sorted({h.key for h in hits})}
        tool = (event.get("tool_name") or "").lower()
        ti_post = event.get("tool_input")
        if ((tool in READ_TOOLS and _is_secret_file(_path_of(ti_post)))
                or (tool in SHELL_TOOLS and SECRET_FILE_REF.search(_command_text(ti_post)))):
            # Diagnostic for the flight recorder: how Muse Code presents a .env read.
            # Redacted before it is written; the raw response is never logged.
            rec["response_type"] = type(resp).__name__
            rec["response_excerpt"] = st.redact_all(text or "", secrets)[0][:200]
        _log(rec)
        return

    # all other events: observe only
    _log({**base, "tool": event.get("tool_name"),
          "child_session_id": event.get("child_session_id")})


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
