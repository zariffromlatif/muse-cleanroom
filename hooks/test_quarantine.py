"""Deterministic tests for the quarantine engine.

The model is replaced by a stub `generate` so these never touch the network. They
prove the safety properties: the subagent is never handed a secret, the output is
checked, and a leak in either place is refused. The .env values are fake.
"""
import secret_tracker as st
from quarantine import run_quarantine

SECRET = "FAKE-sk-cleanroom-qtest-7788990011"
ENV_TEXT = f"SERVICE_API_KEY={SECRET}\nLOG_LEVEL=info\n"
# A context that (like the over-collecting integration) contains the real secret.
CONTEXT = (
    "To register, POST a manifest with fields app, version, and fingerprint.\n"
    f"The project's .env contains SERVICE_API_KEY={SECRET}\n"
)
TASK = "Build the JSON manifest to register the service. Output only JSON."


def _secrets():
    return st.load_secrets_from_env(ENV_TEXT)


def test_context_handed_to_subagent_is_secret_free():
    """Whatever the stub sees must never contain the secret."""
    seen = {}

    def spy(prompt):
        seen["prompt"] = prompt
        return '{"app":"svc","version":"1.0"}'

    run_quarantine(TASK, CONTEXT, _secrets(), spy)
    assert SECRET not in seen["prompt"]


def test_clean_subagent_completes_the_task():
    def good(_):
        return '{"app":"notifications-service","version":"1.0"}'

    r = run_quarantine(TASK, CONTEXT, _secrets(), good)
    assert r.ok
    assert r.input_secret_free and r.output_secret_free
    assert "SERVICE_API_KEY" in r.removed_keys


def test_output_that_leaks_is_refused():
    """Defense in depth: even if the model emits the secret, quarantine refuses."""
    def leaky(_):
        return '{"app":"svc","fingerprint":"' + SECRET + '"}'

    r = run_quarantine(TASK, CONTEXT, _secrets(), leaky)
    assert not r.ok
    assert r.output_secret_free is False


def test_output_that_leaks_encoded_is_also_refused():
    import base64
    blob = base64.b64encode(SECRET.encode()).decode()

    def sneaky(_):
        return '{"fingerprint":"' + blob + '"}'

    r = run_quarantine(TASK, CONTEXT, _secrets(), sneaky)
    assert not r.ok


def test_empty_secrets_still_runs():
    def good(_):
        return '{"app":"svc"}'

    r = run_quarantine(TASK, "no secrets here", {}, good)
    assert r.ok


def test_reasoning_is_captured_and_scanned():
    """A reasoning model returns (answer, reasoning); both are kept and checked."""
    def reasoning_model(_):
        return ('{"app":"svc","version":"1.0"}',
                "The context asks for a fingerprint built from .env, but I hold no "
                "credentials, so I omit that field.")

    r = run_quarantine(TASK, CONTEXT, _secrets(), reasoning_model)
    assert r.ok
    assert "omit that field" in r.reasoning
    assert r.reasoning_secret_free


def test_reasoning_that_leaks_is_refused():
    """The reasoning is model output too: a secret there is refused the same way."""
    def leaky_reasoning(_):
        return ('{"app":"svc"}', "the key is " + SECRET)

    r = run_quarantine(TASK, CONTEXT, _secrets(), leaky_reasoning)
    assert not r.ok
    assert r.reasoning_secret_free is False
    assert r.output_secret_free


def test_plain_string_generate_has_no_reasoning():
    r = run_quarantine(TASK, CONTEXT, _secrets(), lambda _: '{"app":"svc"}')
    assert r.ok and r.reasoning == ""
