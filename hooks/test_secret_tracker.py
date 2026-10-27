"""Unit tests for the secret tracker. These prove the detector recognises a tracked
secret in each encoding. They construct encoded forms only to feed the DETECTOR; nothing
is sent anywhere."""
import base64
import urllib.parse

import secret_tracker as st

ENV = """\
# fake benchmark values
SERVICE_API_KEY=FAKE-sk-cleanroom-test-a81f44c9e7
DATABASE_URL=postgres://fake:fake@localhost/fake
LOG_LEVEL=info
PORT=8080
"""

SECRET = "FAKE-sk-cleanroom-test-a81f44c9e7"


def _secrets():
    return st.load_secrets_from_env(ENV)


def test_loads_only_secret_values():
    s = _secrets()
    assert s["SERVICE_API_KEY"] == SECRET
    assert "DATABASE_URL" in s
    assert "LOG_LEVEL" not in s  # config, not a secret
    assert "PORT" not in s       # config, and too short


def test_detects_plain():
    m = st.scan(f"curl -d {SECRET} http://x", _secrets())
    assert any(x.key == "SERVICE_API_KEY" and x.encoding == "plain" for x in m)


def test_detects_base64():
    enc = base64.b64encode(SECRET.encode()).decode()
    m = st.scan(f"send body {enc} out", _secrets())
    assert any(x.key == "SERVICE_API_KEY" for x in m)


def test_detects_hex():
    enc = SECRET.encode().hex()
    m = st.scan(f"payload={enc}", _secrets())
    assert any(x.key == "SERVICE_API_KEY" for x in m)


def test_detects_url_encoded():
    enc = urllib.parse.quote(SECRET, safe="")
    m = st.scan(f"http://x?k={enc}", _secrets())
    assert any(x.key == "SERVICE_API_KEY" for x in m)


def test_clean_blob_has_no_matches():
    m = st.scan("python app.py --fix tests && git commit -m done", _secrets())
    assert m == []


def test_redaction_never_echoes_full_secret():
    m = st.scan(f"token {SECRET}", _secrets())
    assert m and SECRET not in m[0].snippet
