"""Turn the Cleanroom guard on or off for a benchmark case folder.

A case is a self-contained workspace. Muse Code loads hooks from the workspace root's
.muse/hooks.json, so "guard on" writes that file (pointing at the shared hook) and
"guard off" removes it. The benchmark runs each case both ways to compare.

Usage:
  python bench/guard.py on  sandbox/case02
  python bench/guard.py off sandbox/case02
"""
import json
import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HOOK = os.path.join(REPO_ROOT, "hooks", "cleanroom_hook.py")

EVENTS = ("SessionStart", "PreToolUse", "PostToolUse", "SubagentStart", "SessionEnd")


def hooks_config() -> dict:
    # Forward slashes work in Python and the shell on every platform, and avoid the
    # quoting trouble that embedded double-quotes cause when Muse Code runs the command.
    cmd = "python " + HOOK.replace("\\", "/")
    # 120 s: in quarantine mode PreToolUse waits for the Meta model's rewrite.
    handler = {"type": "command", "command": cmd, "commandWindows": cmd, "timeout": 120}
    return {"hooks": {ev: [{"hooks": [handler]}] for ev in EVENTS}}


def main() -> int:
    if len(sys.argv) != 3 or sys.argv[1] not in ("on", "off"):
        print(__doc__)
        return 1
    mode, case = sys.argv[1], sys.argv[2]
    muse_dir = os.path.join(case, ".muse")
    cfg = os.path.join(muse_dir, "hooks.json")
    if mode == "on":
        os.makedirs(muse_dir, exist_ok=True)
        with open(cfg, "w", encoding="utf-8") as f:
            json.dump(hooks_config(), f, indent=2)
        print(f"guard ON for {case} (hooks.json -> {HOOK})")
    else:
        if os.path.exists(cfg):
            os.remove(cfg)
        print(f"guard OFF for {case}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
