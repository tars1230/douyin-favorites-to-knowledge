# Douyin Favorites to Knowledge

Turn your authorized Douyin favorites into reviewed local Markdown notes. The built-in browser collector handles first-run login without asking you to copy or configure cookies.

[![CI](https://github.com/tars1230/douyin-favorites-to-knowledge/actions/workflows/ci.yml/badge.svg)](https://github.com/tars1230/douyin-favorites-to-knowledge/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)

This project accesses only the favorites of the account that you explicitly sign into. It does not bypass login or platform access controls.

## Design

```text
authorized browser session, export, or adapter
              |
              v
        scan -> review.json
                    |
                    v
        review -> approval.json
                    |
                    v
        promote -> Markdown notes + SQLite ledger
```

- `scan` normalizes source items, derives canonical Douyin URLs, blocks leakage, compares the immutable ledger, and writes no knowledge notes.
- `review` revalidates every content hash and generated note, then requires explicit full or partial approval.
- `promote` verifies the exact review SHA-256, stages approved notes, atomically replaces each file, and commits idempotency records.

## Install

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install .
```

Chrome or Edge is used when available. If neither is installed, install Playwright Chromium once:

```bash
python -m playwright install chromium
```

Install the Agent Skill separately when needed:

```bash
cp -R skill ~/.codex/skills/douyin-favorites-to-knowledge
```

## First sync

Create a config from [config/config.example.json](config/config.example.json), then run `scan`. On the first run, a local browser opens for normal Douyin login. Later runs reuse that app-owned browser session.

```bash
douyin-favorites-knowledge --config config/config.example.json scan \
  --review .runtime/review.json

douyin-favorites-knowledge --config config/config.example.json review \
  --review .runtime/review.json \
  --approve-all \
  --approval .runtime/approval.json

douyin-favorites-knowledge --config config/config.example.json promote \
  --review .runtime/review.json \
  --approval .runtime/approval.json
```

The login can also be managed explicitly:

```bash
douyin-favorites-knowledge login
douyin-favorites-knowledge status
douyin-favorites-knowledge logout
```

`login`, `status`, and `logout` never print cookie values or require a config file. For unattended jobs, add `--no-login-prompt` to `scan` so an expired session fails instead of opening a browser.

## Quick fixture E2E

Keep runtime state outside the repository when using real data. The included example deliberately writes to ignored `.runtime/` paths.

```bash
douyin-favorites-knowledge --config config/config.example.json scan \
  --input tests/fixtures/favorites.json \
  --source-label synthetic_fixture \
  --review .runtime/review.json

douyin-favorites-knowledge --config config/config.example.json review \
  --review .runtime/review.json \
  --approve-all \
  --approval .runtime/approval.json

douyin-favorites-knowledge --config config/config.example.json promote \
  --review .runtime/review.json \
  --approval .runtime/approval.json \
  --dry-run

douyin-favorites-knowledge --config config/config.example.json promote \
  --review .runtime/review.json \
  --approval .runtime/approval.json
```

Run the last command again: it succeeds with `promoted_count: 0` and `skipped_count: 2`.

## Input schema

The input is a JSON list, or an object with an `items` list. Each item accepts:

| Field | Required | Behavior |
|---|---|---|
| `aweme_id` | yes | 6-30 digits; becomes the immutable identity |
| `title` or `description` | yes | At least one must be non-empty |
| `author` | no | Stored as public source metadata |
| `description` | no | Included in the note |
| `transcript` | no | Included only after leakage checks |
| `tags` | no | Non-empty strings, deduplicated and sorted |
| `observed_at` | no | Caller-supplied provenance timestamp |
| `source_url` | ignored | Replaced with `https://www.douyin.com/video/<aweme_id>` |

Unknown source fields are not copied into notes. Query parameters, cookies, and collector-specific metadata therefore do not leak through by default.

## Browser privacy

- Login happens on Douyin's website in a dedicated local browser profile.
- Raw cookies are not accepted as CLI arguments or config fields and are never written to review files or notes.
- The default profile is stored under the operating system's application-state directory, outside the repository.
- `logout` clears the saved browser session. Uninstalling the Python package does not silently delete user data.
- Douyin can expire a session or change its private web response shape. The collector fails closed and asks for login or an update instead of treating that failure as an empty collection.

Use `DOUYIN_FAVORITES_PROFILE_DIR` only when you need to relocate the app-owned profile. Do not point it at a daily browser profile or a broad directory.

## Adapters

Use `module:function` specs:

```python
def collector(config: dict) -> list[dict]:
    ...

def enricher(item: dict, config: dict) -> dict:
    ...

def notifier(event: dict, config: dict) -> None:
    ...
```

The config accepts output paths only and rejects secret-like keys. Adapters must read credentials from their host environment or secret manager. The notifier runs after commit, so a notifier error means local promotion may already be complete.

## Safety gates

The pipeline blocks before promotion on:

- `<think>` / `<analysis>` reasoning tags;
- Unicode replacement characters and NUL bytes;
- common live-secret token shapes;
- secret-like config keys;
- invalid or conflicting duplicate IDs;
- modified notes or content hashes;
- a review changed after approval;
- changed content for an already promoted ID;
- conflicting untracked note files.

Text scanning cannot detect secrets rendered inside screenshots or video. This core intentionally writes text notes only.

## Dry-run and recovery

Every command supports `--dry-run` and avoids writes for that stage.

- If scan fails, fix the source or adapter and rerun; notes and ledger were untouched.
- If review fails, discard the approval candidate and fix the manifest source.
- If promote is interrupted after a note replacement but before ledger commit, rerun the same review and approval. Identical orphan notes are accepted; conflicting notes are blocked.
- Do not edit a promoted item in place. Use a separately reviewed migration process for changed content.

## Test

```bash
python3 -m compileall -q src tests
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

CI also installs the built wheel into a fresh virtual environment and runs the fixture transaction through the console command.

## Uninstall

```bash
douyin-favorites-knowledge logout
python -m pip uninstall douyin-favorites-to-knowledge
```

Uninstalling the package intentionally does not delete your configured knowledge directory, SQLite ledger, or browser profile. Remove those data paths only after backing them up and verifying the exact target.

## License

[MIT](LICENSE)
