from app import format_notification


def test_formats_message():
    out = format_notification("alice", "hi")
    assert out["to"] == "alice"
    assert out["message"] == "hi"


def test_requires_user():
    try:
        format_notification("", "hi")
    except ValueError:
        return
    raise AssertionError("expected ValueError for empty user")
