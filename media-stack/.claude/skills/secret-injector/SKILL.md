---
name: secret-injector
description: Generate and validate the stack's .env file — ensure every API key/secret required by docker-compose.yml is present, well-formed, and never logged or committed. Use when the user is setting up the stack fresh, rotating an API key, adding a new service that needs a secret, or asking "why isn't my API key being picked up". Trigger phrases: "generate the .env", "check for missing secrets", "rotate the radarr api key", "validate my env file", "is a secret leaking anywhere".
---

# Secret Injector

Manages `.env` for the compose stack without ever printing secret *values* to stdout,
logs, or committing them. This skill only ever prints key **names** and pass/fail status —
never the value — and refuses to write a value it wasn't explicitly given (it does not
invent, guess, or default a secret).

## What it does

1. **Required-key audit** — diffs the keys actually referenced in `docker-compose.yml`
   (`${VAR}` / `${VAR:-default}` syntax) against what's present in `.env`, and reports
   which are missing. Does not report values, only names.
2. **Format validation** — light sanity checks per known key pattern (Arr API keys are
   32-char hex, etc.) without needing the true value to be "correct" beyond shape.
3. **Injection** — writes a new key=value pair to `.env`, given the value on stdin (never
   as a CLI argument, since CLI args land in shell history and `ps` output).
4. **Leak scan** — greps the working tree (excluding `.env`/`.git`) for any value currently
   in `.env`, to catch an accidentally hardcoded secret before a commit.

## Usage

```bash
python3 injector.py audit                                  # missing keys vs docker-compose.yml
python3 injector.py validate                                # format-check keys already present
echo -n "abc123..." | python3 injector.py set RADARR_API_KEY   # write a value from stdin only
python3 injector.py leak-scan                                # scan repo for any .env value appearing elsewhere
```

Run from the repo root (where `.env` and `docker-compose.yml` live), or pass
`--env-file`/`--compose-file`.

## Safety rules

- **Never** accept a secret value as a bare CLI argument — `set` only reads from stdin,
  specifically to avoid the value landing in shell history or `ps aux` output.
- **Never** print a secret value in any command's output, including error messages —
  only key names and boolean/status results.
- `set` on an existing key requires `--force`; without it the script refuses to silently
  overwrite a live credential (rotation should be a deliberate, visible action).
- `leak-scan` output redacts the matched value itself, showing only the file/line where a
  match was found — enough to locate and fix it without re-printing the secret.
- This skill never commits `.env` and never suggests doing so; `.env` must stay in
  `.gitignore`. If asked to "just commit the env file", refuse and explain why.
