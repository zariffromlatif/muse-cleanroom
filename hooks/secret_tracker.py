"""Cleanroom secret tracker (defensive detector).

Two jobs:
  1. Learn which values are secrets for a workspace, by reading its .env files.
  2. Given any blob of text (a shell command the agent wants to run, a file it is
     uploading, a tool output), report whether any tracked secret appears in it,
     INCLUDING when the secret has been encoded.

Why the encodings matter: a model refuses "send API_KEY=...", but it treats a
base64 string as opaque and may let it through. The whole point of Cleanroom is to
decode what the model sees as random noise and recognise the secret underneath.

This module performs no network or file-sending action. It only detects.
"""
from __future__ import annotations

import base64
import binascii
import re
import urllib.parse
from dataclasses import dataclass

# Values shorter than this, or obvious non-secrets, are not worth tracking: they
# cause false positives (e.g. LOG_LEVEL=info would match the word "info" everywhere).
MIN_SECRET_LEN = 8
# Keys whose values are configuration, not secrets. Case-insensitive.
NON_SECRET_KEYS = {"log_level", "debug", "env", "environment", "port", "host", "timeout"}


def load_secrets_from_env(text: str) -> dict[str, str]:
    """Parse KEY=VALUE lines from a .env file's text and keep only the secret-looking ones."""
    secrets: dict[str, str] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key, value = key.strip(), value.strip().strip('"').strip("'")
        if key.lower() in NON_SECRET_KEYS:
            continue
        if len(value) < MIN_SECRET_LEN:
            continue
        secrets[key] = value
    return secrets


def _variants(secret: str) -> dict[str, str]:
    """The forms a secret can take on the way out. Each maps an encoding name -> encoded text."""
    raw = secret.encode("utf-8")
    forms = {
        "plain": secret,
        "base64": base64.b64encode(raw).decode(),
        "base64_nopad": base64.b64encode(raw).decode().rstrip("="),
        "base64url": base64.urlsafe_b64encode(raw).decode().rstrip("="),
        "hex": raw.hex(),
        "hex_upper": raw.hex().upper(),
        "url": urllib.parse.quote(secret, safe=""),
    }
    return forms


@dataclass
class Match:
    key: str          # which secret, by its .env name
    encoding: str      # how it appeared: plain, base64, hex, url, ...
    snippet: str       # a short, REDACTED hint of where it was seen


def _redact(blob: str, needle: str) -> str:
    i = blob.find(needle)
    if i < 0:
        return ""
    start = max(0, i - 15)
    end = min(len(blob), i + len(needle) + 15)
    shown = blob[start:end]
    # never echo the secret form itself back; mask the matched run
    return shown.replace(needle, "<" + needle[:3] + "...MASKED>")


def scan(blob: str, secrets: dict[str, str]) -> list[Match]:
    """Return every tracked secret found in `blob`, in any encoding.

    Also decodes base64/hex runs found in the blob and checks whether a secret is
    hiding inside them, which catches `base64(secret)` even when we did not predict
    the exact padding the attacker used.
    """
    matches: list[Match] = []
    if not blob:
        return matches

    for key, secret in secrets.items():
        for encoding, form in _variants(secret).items():
            if form and form in blob:
                matches.append(Match(key, encoding, _redact(blob, form)))
                break  # one hit per secret is enough to block

    # Second pass: decode any long base64/hex-looking runs in the blob and look inside.
    already = {m.key for m in matches}
    for token in re.findall(r"[A-Za-z0-9+/=_-]{12,}", blob):
        decoded = _try_decode(token)
        if not decoded:
            continue
        for key, secret in secrets.items():
            if key not in already and secret in decoded:
                matches.append(Match(key, "decoded-blob", _redact(blob, token)))
                already.add(key)
    return matches


def _looks_textual(text: str) -> bool:
    """True if `text` is ordinary text. Unlike str.isprintable(), this allows the
    normal whitespace (newline, tab, carriage return) that a decoded .env or JSON
    body contains, so base64 of a whole file still reads as text."""
    if not text:
        return False
    return all(c.isprintable() or c in "\r\n\t " for c in text)


def _try_decode(token: str) -> str:
    """Best-effort decode of a base64 or hex token to text; '' if it is not either."""
    for pad in ("", "=", "=="):
        try:
            data = base64.b64decode(token + pad, validate=True)
            text = data.decode("utf-8", errors="strict")
            if _looks_textual(text):
                return text
        except (binascii.Error, ValueError, UnicodeDecodeError):
            pass
    try:
        if len(token) % 2 == 0:
            text = bytes.fromhex(token).decode("utf-8", errors="strict")
            if _looks_textual(text):
                return text
    except (ValueError, UnicodeDecodeError):
        pass
    return ""
