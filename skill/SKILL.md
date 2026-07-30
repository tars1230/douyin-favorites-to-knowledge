---
name: douyin-favorites-to-knowledge
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

`sync` 将新增收藏静默写入知识库。首次配置完成后，日常同步不得要求用户逐条或逐次确认；终端只返回汇总结果。SQLite 防重账本、原子文件替换和内容冲突 fail-closed 仍必须保留。

登录失效时不打开登录页、直接失败时使用：

```bash
douyin-favorites-knowledge sync --no-login-prompt
```

`--yes` 只为旧脚本兼容保留，不再是同步前提。

## 每晚日报

首次 `setup` 和 `login` 成功后，若当前 Agent 支持定时任务，默认在用户本机建立每天 **23:00** 的任务，执行：

```bash
douyin-favorites-knowledge daily --source collection --no-login-prompt
```

使用当前环境可用的任务调度器；任务只运行已安装的命令，不传凭据，不弹出登录页。百炼转录时，只有调度环境能从用户已有的 Secret Manager 或安全环境变量读取 `DASHSCOPE_API_KEY` 才能创建任务；不能持久化读取时必须报告未创建，不能制造必然失败的计划任务。`daily` 静默同步并在知识库 `日报/` 写入当天 Markdown 日报，零新增也写日报。登录失效时任务失败，由用户下次运行 `login` 恢复。

收藏是默认且唯一自动来源。用户明确说“喜欢”“点赞”“转录喜欢列表”或“喜欢日报”时，才额外建立或执行 `daily --source like --no-login-prompt`；它复用同一转录方案，但喜欢笔记、账本键和日报文件必须与收藏隔离。不要把两类来源合并，也不要因用户选择喜欢而停止收藏日报。

## 转录

用户未指定时，建议百炼云端转录，但要先告知它会按音频时长计费，且让用户在 `setup` 中明确选择。默认直连 `qwen3-asr-flash`，只需要 `DASHSCOPE_API_KEY` 和 `python -m pip install '.[bailian-asr]'`。云端只提交已授权采集到的临时播放地址，项目不落地下载视频。密钥不能写入 config、笔记或日志。

截至 2026-07-30，官方价格页的华北 2 `qwen3-asr-flash` 为 0.00022 元/秒，约 0.0132 元/分钟；10 元约转录 12.6 小时音频。若用户每月转录 10 分钟，约可使用 6 年多；每月 1 小时则约够 1 年。页面列 36,000 秒免费额度（有效期与地域以官方页为准）。价格、额度会变，实际扣费只以用户百炼控制台账单为准。笔记必须保留 `transcript_source` 与 `transcript_status`；未转录时必须说明原始 Description 不是逐字稿。

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

原子命令 `scan -> review -> promote` 只保留给局部审核、调试和迁移。不要把它暴露为普通用户的日常步骤；不得为了自动化把哈希、重复 ID、敏感信息或冲突文件错误降级为警告。

## 验证

```bash
python3 -m compileall -q src tests
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

真实采集依赖有效的授权登录和抖音当前页面结构。fixture 通过只证明事务与编排契约。
