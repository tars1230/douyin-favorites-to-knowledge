# Changelog

## [2.2.5] - 2026-08-05

### Changed
- setup / next_step 缺 SiliconFlow Key 时强制给出推荐注册页 + 控制台 + export 三步；交互终端可打开 `https://cloud.siliconflow.cn/i/1srulim9`。

## [2.2.4] - 2026-08-05

### Changed
- ASR 简化为单一稳定路径：只下 `play_url`/`video_url` → ffmpeg 抽音 → SenseVoice；去掉 `audio_url` 优先分支。

## [2.2.3] - 2026-08-05

### Changed
- ASR：优先 `audio_url`，失败回退 `play_url`；`DOUYIN_ASR_AUDIO_BITRATE` / `DOUYIN_ASR_SAMPLE_RATE` 可配。
- 采集：仅原创音/视频音轨写入 `audio_url`，避免 BGM 误转写。

## [2.2.2] - 2026-08-05

### Changed
- 文档/check-config 加入 SiliconFlow 注册推荐链接：https://cloud.siliconflow.cn/i/1srulim9

## [2.2.1] - 2026-08-05

### Changed
- 费用说明改为 SiliconFlow 默认：截至 2026-08-05 官方价格页 `FunAudioLLM/SenseVoiceSmall` 标注**免费**（会变，以 https://siliconflow.cn/pricing 与账单为准）。
- 百炼 `0.00022 元/秒` 估算降为可选方案旁注，不再当默认报价。


## 2.2.0 — 2026-08-05

### Fixed / Breaking (behavior)

- **抖音默认转录改为 SiliconFlow SenseVoice**（本机带 `Referer` 下载后上传），不再默认推荐百炼 URL-ASR。
- 百炼 `qwen3-asr-flash` 仍可用，但对 `*.douyinvod.com` 服务端拉流常失败；文档与 setup 标明为可选。
- 本地 Whisper 下载补上 Douyin `Referer/Origin`，修复 CDN 403。
- `setup --transcription cloud` 现映射 **siliconflow**（旧行为 cloud=bailian 已废弃）。
- provider discovery / check-config / 非交互 setup 同步。

## 2.1.0

- 新增 `configure-obsidian`：选择用户自己的 Vault 与子目录后，创建收藏/喜欢模板、日报索引、飞书字段模板并完成临时写入检查。
- 新增可选飞书 webhook 通知；webhook 只从 `FEISHU_WEBHOOK_URL` 环境变量读取，通知失败不会阻断本地同步。多维表模式仅生成字段与授权提示，不宣称已写入。
- 可选 analysis adapter 现在可将“要点、价值判断、深度分析、延展补充、行动启示、关联知识”写入笔记；分析默认关闭，原始材料与模型研判分层展示。
- 修复喜欢列表页面中 `sec_user_id` 的浏览器脚本匹配转义，恢复授权喜欢列表采集。

## 2.0.2

- 本地 Whisper 媒体在系统临时目录转录后自动删除；下次运行回收超过 24 小时的异常残留，并默认拒绝超过 512 MB 的单视频下载。
- 百炼转录新增原子化的每日预算：首次配置默认每天最多 100 条、3,600 秒音频；预算超限、转录失败或媒体过大时不写入知识库和防重账本，保留给后续重试。
- 采集器传递视频时长用于预算核算，未完成的额度预留会在 15 分钟后自动释放。

## 2.0.1

- 移除第三方 `douyin-mcp` 转录兼容层；公开版本只保留百炼直连、本地 Whisper 和不转录三种路径。
- 百炼成本说明增加 10 元可转录时长与按月使用频率的估算，避免把低成本表达成无条件的“多年可用”。
- 旧版 `transcription.provider: douyin_mcp` 配置不再支持；请改为 `bailian` 并安装 `.[bailian-asr]`。
- 新增 `daily`：静默同步并在知识库写入每日 Markdown 日报；默认安排每天 23:00 跑收藏，喜欢仅在用户明确启用时独立运行。
- 明确自动日报由具备 scheduler 能力的 Agent 创建并验收；纯 CLI 不再暗示已经注册跨平台后台任务。

## 1.5.1

- `sync` 改为默认静默增量写入；首次配置和登录后，不再要求每次确认新增收藏。
- 保留 `--dry-run` 用于只查看新增，`--yes` 仅作为旧脚本兼容参数。

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
