# Changelog

## 1.2.1 - 2026-07-28

- 增加 ClawHub 的 Agent 安装入口和 Gitee 国内下载入口。
- Skill 在缺少命令时优先引导 Agent 从 Gitee 安装完整程序。
- 增加 GitHub `main` 与正式标签到 Gitee 的自动同步。

## 1.1.0 - 2026-07-25

- Adds a built-in Playwright collector for the signed-in user's Douyin favorites.
- Adds `login`, `status`, and `logout` commands backed by an app-owned local browser profile.
- Makes authorized browser collection the default `scan` source while preserving JSON and custom adapters.
- Opens normal Douyin login when needed without accepting or printing raw cookies.
- Adds browser orchestration tests and fail-closed handling for login, response, and pagination failures.

## 1.0.0 - 2026-07-25

- First public release.
- Adds explicit `scan -> review -> promote` CLI transaction.
- Adds collector, enricher, and post-commit notifier adapter boundaries.
- Adds canonical source URLs, content hashes, review SHA-256 approval, atomic note replacement, and SQLite idempotency ledger.
- Blocks reasoning leakage, common secret shapes, modified approvals, duplicate IDs, and immutable-content conflicts.
- Adds synthetic clean-machine E2E, failure recovery, security guidance, and uninstall documentation.
