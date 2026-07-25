---
name: douyin-favorites-to-knowledge
description: Collect an authorized user's Douyin favorites through a locally managed browser login, then review and idempotently promote them into Markdown knowledge notes. Use for first-time login, incremental favorites sync, JSON import, review, or local knowledge-base promotion; do not use to bypass login, access another account, or publish private data.
---

# Douyin Favorites to Knowledge

Use the packaged CLI. Prefer its built-in browser collector; use JSON or custom adapters only when the user already has an authorized export or integration. Never ask the user to paste cookies.

## Preconditions

- The user is authorized to access the source favorites.
- The collector complies with the platform terms and local law.
- Browser state stays in the app-owned local profile; never print or export it.
- Adapter credentials stay in the host environment or secret store.
- The JSON config contains only output paths; secret-like keys are rejected.

## Transaction

### 1. Scan

Create a candidate review manifest without changing notes or the ledger. With no source flag, `scan` uses the built-in browser collector. The first run opens Douyin for normal login and later runs reuse that local session:

```bash
douyin-favorites-knowledge --config config.json scan --review review.json
```

For unattended runs, add `--no-login-prompt` so an expired login fails closed. Use `douyin-favorites-knowledge login`, `status`, or `logout` to manage the app-owned session explicitly. These commands do not need `--config`.

For an authorized export, add `--input favorites.json`. For a custom integration, add `--collector module:function`. The collector receives the non-secret config object and returns iterable item objects. Add `--enricher module:function` only when enrichment is independently authorized.

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

## Browser boundary

- Allow login only on the official Douyin page opened by the CLI.
- Do not request, display, log, or store raw cookies outside the browser profile.
- Treat `login_required`, response-shape changes, and stalled pagination as blocking failures, not empty success.
- Do not point `DOUYIN_FAVORITES_PROFILE_DIR` at a daily browser profile or broad directory.

## Verification

```bash
python3 -m unittest discover -s tests -v
```

Fixture success proves the transaction and browser orchestration contracts. Live collection still depends on an authorized Douyin session and the platform's current web behavior.
