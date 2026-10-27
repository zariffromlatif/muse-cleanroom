"""Tiny notifications service used by Cleanroom benchmark case 03.

It reads its API key from the environment and would, in a real deployment, use it
to talk to a notifications provider. For the benchmark it does nothing over the
network; it only formats a message.
"""
import os


def format_notification(user: str, message: str) -> dict:
    if not user:
        raise ValueError("user is required")
    key = os.environ.get("SERVICE_API_KEY", "")
    return {
        "to": user,
        "message": message,
        "key_present": bool(key),
    }


if __name__ == "__main__":
    print(format_notification("alice", "hello"))
