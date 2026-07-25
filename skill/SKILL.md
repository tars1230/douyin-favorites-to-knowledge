---
name: douyin-favorites-to-knowledge
description: Convert authorized Douyin favorite metadata into reviewed, idempotent local Markdown knowledge notes through an explicit scan, review, and promote transaction. Use when a user wants a reproducible favorites-to-knowledge workflow; do not use to bypass login, scrape accounts without authorization, or publish private data.
---

# Douyin Favorites to Knowledge

Use the packaged CLI as the public transaction core. Collection, enrichment, and notification are explicit adapters; this Skill never assumes a browser profile, token, Feishu target, personal directory, or live production database.

## Preconditions

- The user is authorized to access the source favorites.
- The collector complies with the platform terms and local law.
- Credentials stay in the adapter host's environment or secret store.
- The JSON config contains only output paths; secret-like keys are rejected.

## Transaction

### 1. Scan

Create a candidate review manifest without changing notes or the ledger:

```bash
douyin-favorites-knowledge --config config.json scan \
  --input favorites.json \
  --source-label authorized_export \
  --review review.json
```

For a real collector, replace `--input` with `--collector module:function`. The collector receives the non-secret config object and returns iterable item objects. Add `--enricher module:function` only when enrichment is independently authorized.

### 2. Review

Validate hashes, schema, canonical source URLs, generated notes, duplicate IDs, and reasoning/secret leakage. Approval must be explicit:

```bash
douyin-favorites-knowledge --config config.json review \
  --review review.json \
  --approve-all \
  --approval approval.json
```

Use repeated `--approve <aweme_id>` for partial approval. Do not edit the review after approval; promotion verifies its SHA-256.

### 3. Promote

```bash
douyin-favorites-knowledge --config config.json promote \
  --review review.json \
  --approval approval.json
```

Promotion stages Markdown notes, atomically replaces final files, then commits immutable content hashes to SQLite. Repeating the same promotion is a no-op. Changed content for an already promoted ID is blocked for manual migration.

## Dry-run

All three commands accept `--dry-run`. Dry-run performs validation and reports counts but does not write its stage artifact or mutate notes/ledger.

## Blocking behavior

Stop on:

- `<think>` or `<analysis>` reasoning tags;
- Unicode replacement characters, NUL bytes, or common live-secret patterns;
- secret-like config keys;
- malformed or duplicate IDs;
- note/content hash mismatch;
- approval hash mismatch;
- changed content for an immutable promoted ID;
- an untracked note file with conflicting content.

Never convert these failures into warnings to keep automation moving.

## Adapter contracts

```python
def collector(config: dict) -> list[dict]: ...
def enricher(item: dict, config: dict) -> dict: ...
def notifier(event: dict, config: dict) -> None: ...
```

The notifier runs after the local transaction commits. A notification failure does not mean the notes were rolled back; inspect the command error, then notify again without re-promoting changed data.

## Verification

```bash
python3 -m unittest discover -s tests -v
```

Fixture success proves the public transaction core, not the availability or authorization of a third-party collector.
