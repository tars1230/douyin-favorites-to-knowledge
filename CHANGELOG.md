# Changelog

## 1.0.0 - 2026-07-25

- First public release.
- Adds explicit `scan -> review -> promote` CLI transaction.
- Adds collector, enricher, and post-commit notifier adapter boundaries.
- Adds canonical source URLs, content hashes, review SHA-256 approval, atomic note replacement, and SQLite idempotency ledger.
- Blocks reasoning leakage, common secret shapes, modified approvals, duplicate IDs, and immutable-content conflicts.
- Adds synthetic clean-machine E2E, failure recovery, security guidance, and uninstall documentation.
