# Security Policy

Use GitHub private vulnerability reporting. Do not open a public issue with cookies, browser profiles, tokens, private favorite exports, generated personal notes, or production configuration.

The public package accepts no credential fields. Collector, enricher, and notifier adapters must obtain secrets from their host's environment or secret manager and must avoid returning them in item data or errors.

Reasoning-tag and token-pattern checks are defense in depth, not a complete data-loss-prevention system. Review the generated manifest before approval and keep real review/approval artifacts outside the repository.
