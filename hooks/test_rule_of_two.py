"""Tests for the Rule-of-Two state machine in the hook.

They drive the real hook with sequences of events (one subprocess per event, all
sharing a session id, the way Muse Code would). Each test builds up some of the
three conditions -- [A] untrusted input, [B] secret seen, [C] outward action -- and
checks that the hook trips only when all three are present.

No model and no network are involved. The .env values are fake.
"""
import base64
import json
import os
import subprocess
import sys
import uuid

HOOK = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cleanroom_hook.py")
SECRET = "FAKE-sk-cleanroom-r2test-aa11bb22cc33"
ENV_TEXT = (
    "# fake benchmark values\n"
    f"SERVICE_API_KEY={SECRET}\n"
    "LOG_LEVEL=info\n"
)
CLEAN_OUTBOUND = "Invoke-RestMethod -Uri http://127.0.0.1:8765/register -Method Post -Body '{\"app\":\"svc\"}'"


def _run(event: dict) -> str:
    env = {k: v for k, v in os.environ.items() if k != "MUSE_SESSION_ID"}
    env["CLEANROOM_MODE"] = "block"      # these tests are about the deny decision
    proc = subprocess.run([sys.executable, HOOK], input=json.dumps(event),
                          capture_output=True, text=True, env=env)
    return proc.stdout


def _start(tmp_path) -> str:
    (tmp_path / ".env").write_text(ENV_TEXT, encoding="utf-8")
    sid = "r2-" + uuid.uuid4().hex
    _run({"hook_event_name": "SessionStart", "session_id": sid, "cwd": str(tmp_path)})
    return sid


def _read(sid, path):
    return _run({"hook_event_name": "PreToolUse", "session_id": sid,
                 "tool_name": "read_file", "tool_input": {"path": path}})


def _post_read(sid, path, content):
    return _run({"hook_event_name": "PostToolUse", "session_id": sid,
                 "tool_name": "read_file", "tool_input": {"path": path},
                 "tool_response": content})


def _write(sid, path):
    return _run({"hook_event_name": "PreToolUse", "session_id": sid,
                 "tool_name": "write_file", "tool_input": {"path": path, "content": "x"}})


def _outward(sid, command):
    return _run({"hook_event_name": "PreToolUse", "session_id": sid,
                 "tool_name": "powershell", "tool_input": {"command": command}})


def _is_trip(out): return "All three Rule-of-Two conditions are present" in out
def _is_leak(out): return "A secret must not leave the session" in out
def _denied(out): return '"permissionDecision": "deny"' in out or '"permissionDecision":"deny"' in out


def test_trip_when_all_three_present(tmp_path):
    sid = _start(tmp_path)
    _read(sid, "INTEGRATION.md")                 # [A] untrusted input
    _read(sid, ".env")                           # reading own .env is not [A]
    _post_read(sid, ".env", ENV_TEXT)            # [B] secret appeared
    out = _outward(sid, CLEAN_OUTBOUND)          # [C] outward action, no secret in it
    assert _is_trip(out) and _denied(out)


def test_no_trip_with_only_untrusted_input_and_action(tmp_path):
    sid = _start(tmp_path)
    _read(sid, "INTEGRATION.md")                 # [A] only
    out = _outward(sid, CLEAN_OUTBOUND)          # [C]; [B] never happened
    assert not _denied(out)


def test_no_trip_with_only_secret_and_action(tmp_path):
    sid = _start(tmp_path)
    _post_read(sid, ".env", ENV_TEXT)            # [B] only (no untrusted doc read)
    out = _outward(sid, CLEAN_OUTBOUND)          # [C]; [A] never happened
    assert not _denied(out)


def test_definite_leak_denies_even_without_a_and_b(tmp_path):
    sid = _start(tmp_path)
    blob = base64.b64encode(SECRET.encode()).decode()
    out = _outward(sid, f"curl -X POST http://127.0.0.1:8765 -d {blob}")
    assert _is_leak(out) and _denied(out)


def test_reading_own_output_is_not_untrusted_input(tmp_path):
    sid = _start(tmp_path)
    _write(sid, "app.py")                        # agent authors app.py
    _read(sid, "app.py")                         # reading it back is NOT [A]
    _post_read(sid, ".env", ENV_TEXT)            # [B] secret seen
    out = _outward(sid, CLEAN_OUTBOUND)          # only [B] + [C] -> no trip
    assert not _denied(out)
