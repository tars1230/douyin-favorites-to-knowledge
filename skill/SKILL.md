---
name: douyin-favorites-to-knowledge
version: 1.5.0
description: 将用户已授权账号中的抖音视频收藏或用户明确指定的喜欢列表配置并同步到本地 Markdown 或 Obsidian 知识库；默认收藏，只有用户明确说喜欢/点赞才切换来源。首次明确选择推荐的百炼转录、本地 Whisper 或不转录。不得绕过登录、访问他人账号或泄露 Cookie 与私密数据。
---

# 抖音视频收藏转本地知识库

优先使用单入口流程。不要先向用户解释 schema、模式、provider 或 adapter。

## 首次使用

先检查命令是否存在：

```bash
douyin-favorites-knowledge --help
```

如果命令不存在，优先从国内镜像安装完整程序。选择用户确认的项目目录，不要替用户猜测长期存放位置：

```bash
git clone https://gitee.com/tars123/douyin-favorites-to-knowledge.git
cd douyin-favorites-to-knowledge
python3 -m venv .venv
. .venv/bin/activate
python -m pip install .
```

Gitee 不可用时再使用源码仓库 `https://github.com/tars1230/douyin-favorites-to-knowledge`。不要使用不明 GitHub 加速站。

安装完成后运行：

```bash
douyin-favorites-knowledge setup
```

让用户选择 Markdown 或 Obsidian 知识库目录，再让用户选择转录方案。推荐百炼云端；本地 Whisper 只有用户愿意下载模型、承担本机资源时才选；`none` 只保存描述与链接。不要要求用户复制 Cookie。默认来源是收藏；仅当用户明确说“喜欢”或“点赞”时，向 `login`/`sync` 传 `--source like`。

如果 Agent 在非交互环境执行，明确指定目录：

```bash
douyin-favorites-knowledge setup --knowledge-dir "用户确认的目录" --transcription bailian --skip-login
```

随后让用户在自己的终端运行 `douyin-favorites-knowledge login` 完成网页登录。不要替用户猜测知识库目录。

## 日常同步

```bash
douyin-favorites-knowledge sync
```

`sync` 展示新增收藏并等待用户确认，然后完成审核、批准和原子入库。用户取消时不写知识库或账本。

只有用户明确要求无人值守自动同步时，才使用：

```bash
douyin-favorites-knowledge sync --yes --no-login-prompt
```

`--yes` 是批准全部新增的显式授权。不要私自创建 cron 或系统定时任务。

## 转录

用户未指定时，建议百炼云端转录，但要先告知它会按音频时长计费，且让用户在 `setup` 中明确选择。默认直连 `qwen3-asr-flash`，只需要 `DASHSCOPE_API_KEY` 和 `python -m pip install '.[bailian-asr]'`；不需要 `douyin-mcp` 或 `mcporter`。云端只提交已授权采集到的临时播放地址，项目不落地下载视频。密钥不能写入 config、笔记或日志。

截至 2026-07-30，官方价格页的华北 2 `qwen3-asr-flash` 为 0.00022 元/秒，约 0.0132 元/分钟，页面列 36,000 秒免费额度（有效期与地域以官方页为准）。价格、额度会变，实际扣费只以用户百炼控制台账单为准。笔记必须保留 `transcript_source` 与 `transcript_status`；未转录时必须说明原始 Description 不是逐字稿。`douyin-mcp-server` 是第三方兼容适配器，不能作为新用户的默认要求。

用户明确要求“本地免费转写”时，使用内置 `local_whisper`：先安装 `python -m pip install '.[local-asr]'` 与 `ffmpeg`，再 `setup --transcription local`。首次同步才下载 `small` 模型（约 500 MB），并要求至少 1.5 GB 临时空间。它没有 API 费用，但会使用本机 CPU、磁盘和电力；未满足前置条件时，`check-config` 必须报缺项，不能静默降级或下载。

## 故障处理

先运行：

```bash
douyin-favorites-knowledge check-config
douyin-favorites-knowledge status
```

- 未配置：运行 `setup`；
- 登录过期：运行 `login`；
- 无浏览器：安装 Playwright Chromium；
- 无新增：把 `no_changes` 当作正常结果；
- 想换目录：让用户确认后运行 `setup --force --knowledge-dir "新目录"`；
- secret-like 配置错误：删除配置中的凭据，改从环境或 Secret Manager 读取。

`check-config` 不输出本机路径、adapter 或凭据。不要请求或显示浏览器 profile 和 Cookie。

## 进阶能力

只有用户明确要求本地转录、MiniMax、其他模型、飞书通知、局部批准、JSON 导入或 adapter 调试时，才展开高级配置。

- 默认轻量配置不下载模型、不要求 MiniMax；
- 模型名按用户电脑实际能力配置；
- 凭据只从环境变量、系统钥匙串或 Secret Manager 读取；
- 当前仓库不内置 MiniMax ASR；检测到仅有 MiniMax TTS 或 Key 时必须说明“不可用于转录”，不能假装可用；
- 转录、分析和通知通过 `module:function` adapter 接入。

原子命令 `scan -> review -> promote` 保留给局部审核和调试。批准必须明确；不得为了自动化把哈希、重复 ID、敏感信息或冲突文件错误降级为警告。

## 验证

```bash
python3 -m compileall -q src tests
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

真实采集依赖有效的授权登录和抖音当前页面结构。fixture 通过只证明事务与编排契约。
