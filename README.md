# Cleanroom

**Let your coding agent read the internet. Cleanroom makes sure your keys don't leave.**

Cleanroom is a plugin for Meta's [Muse Code](https://dev.meta.ai/docs/muse-code) coding agent. It enforces Meta's
["Agents Rule of Two"](https://ai.meta.com/blog/practical-ai-agent-security/) at runtime: when one session would combine
**untrusted input** (a PR comment, an issue, a README), **a secret** (something read from `.env` or a key file) and
**an external action** (a network call, a git push, a GitHub comment), Cleanroom steps in. It tracks the secret
through encodings (base64, hex, URL-encoding, split pieces), and instead of just saying "no", it hands the risky step
to a fresh *cleanroom* subagent that holds no secrets, so the task still gets done.

> Status: day 1 of 9. Built solo during the Meta Global AI Developer Hackathon, 27 Oct – 4 Nov 2026.

## Built during the hackathon

Everything in this repository was written during the hackathon building period (27 Oct – 4 Nov 2026), starting from an
empty folder. The commit history is the record.

Third-party software used, not written here: Muse Code (the agent being protected), Python standard library,
the `openai` Python package (API client), Muse Spark Open served by Baseten (the judge model).

## Layout

```
.muse/hooks.json     project hooks: wires Muse Code's lifecycle events to Cleanroom
hooks/               the hook entry point
sandbox/             throwaway repos used only to exercise the agent; fake secrets only
```

## License

MIT, see [LICENSE](LICENSE).
