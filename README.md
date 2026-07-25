# Douyin Favorites to Knowledge

A small, transactional public core for turning authorized Douyin favorite metadata into reviewed local Markdown notes.

[![CI](https://github.com/tars1230/douyin-favorites-to-knowledge/actions/workflows/ci.yml/badge.svg)](https://github.com/tars1230/douyin-favorites-to-knowledge/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)

This repository is the reusable transaction layer, not a bundled login bypass or private browser automation. A real collector is an explicit adapter supplied by the user in an authorized environment.

## Design

```text
authorized export or collector adapter
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

Install the Agent Skill separately when needed:

```bash
cp -R skill ~/.codex/skills/douyin-favorites-to-knowledge
```

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

The public config accepts output paths only and rejects secret-like keys. Adapters must read credentials from their host environment or secret manager. The notifier runs after commit, so a notifier error means local promotion may already be complete.

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
python -m pip uninstall douyin-favorites-to-knowledge
```

Uninstalling the package intentionally does not delete your configured knowledge directory or SQLite ledger. Remove those data paths only after backing them up and verifying the exact config target.

## License

[MIT](LICENSE)
