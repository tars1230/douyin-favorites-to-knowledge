# Security Policy

Use GitHub private vulnerability reporting. Do not open a public issue with cookies, browser profiles, tokens, private favorite exports, generated personal notes, or production configuration.

The package accepts no credential fields. The built-in collector stores Douyin session state only in an app-owned local browser profile and never emits cookie values. Do not point `DOUYIN_FAVORITES_PROFILE_DIR` at a daily browser profile, shared directory, or repository. Use `douyin-favorites-knowledge logout` to clear the saved session.

Collector, enricher, and notifier adapters must obtain secrets from their host's environment or secret manager and must avoid returning them in item data or errors.

Reasoning-tag and token-pattern checks are defense in depth, not a complete data-loss-prevention system. Review the generated manifest before approval and keep real review/approval artifacts outside the repository.
