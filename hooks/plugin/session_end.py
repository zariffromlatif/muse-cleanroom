"""Plugin entry for SessionEnd. Muse Code wants one source file per hook capability;
every entry hands the event to the shared hook."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import cleanroom_hook  # noqa: E402

if __name__ == "__main__":
    try:
        sys.exit(cleanroom_hook.main())
    except Exception as exc:  # never break the agent because the guard errored
        sys.stderr.write("cleanroom hook error: %s" % exc + chr(10))
        sys.exit(0)
