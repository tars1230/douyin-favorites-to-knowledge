# Changelog

## 1.5.0

- 新安装默认直连阿里云百炼 `qwen3-asr-flash`，只需 `DASHSCOPE_API_KEY` 与可选依赖 `.[bailian-asr]`，不再要求安装第三方 `douyin-mcp`。
- `setup` 和 `check-config` 增加不读取凭据、不下载模型、不调用付费接口的能力发现；MiniMax 仅在发现明确 ASR 接口时作为候选，不会由 Key 或 TTS 命令误判为可转录。
- 保留已有 `douyin_mcp` 配置的兼容支持，并明确它是第三方可选适配器。

## 1.4.0 - 2026-07-30

- 新增内置 `douyin_mcp` 转录 provider，Key 仅从环境变量读取，转录状态与来源写入笔记。
- 新增 `sync --source collection|like`；默认收藏，喜欢必须显式选择，来源纳入防重键与文件名。
- `setup` 现在明确选择百炼云端、本地 Whisper 或不转录；非交互使用必须传 `--transcription`。
- 新增可选内置本地 Whisper provider：只有选中后才会下载模型，运行前检查 `ffmpeg`、运行时和临时磁盘空间，并清理临时媒体。
- 百炼 `qwen3-asr-flash` 的官方价格估算出现在 `check-config`，实际扣费仍以用户控制台账单为准。
- 兼容 v1 收藏账本，升级后不会将已入库的收藏重新导入。

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
