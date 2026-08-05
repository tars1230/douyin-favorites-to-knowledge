---
name: douyin-favorites-to-knowledge
description: 将用户已授权账号中的抖音视频收藏或用户明确指定的喜欢列表配置并同步到本地 Markdown 或 Obsidian 知识库；默认收藏，只有用户明确说喜欢/点赞才切换来源。首次明确选择推荐的 SiliconFlow转录、本地 Whisper 或不转录。不得绕过登录、访问他人账号或泄露 Cookie 与私密数据。
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

让用户选择 Markdown 或 Obsidian 知识库目录，再让用户选择转录方案。推荐 SiliconFlow云端；本地 Whisper 只有用户愿意下载模型、承担本机资源时才选；`none` 只保存描述与链接。不要要求用户复制 Cookie。默认来源是收藏；仅当用户明确说“喜欢”或“点赞”时，向 `login`/`sync` 传 `--source like`。

用户明确选择 Obsidian 时，在已有 setup 后执行：

```bash
douyin-favorites-knowledge configure-obsidian --vault "用户选择的 Vault" --subdir "抖音知识库"
```

它会切换知识库目录并创建默认模板、日报索引和写入检查。不要猜测 Vault 位置。

飞书默认关闭且不影响本地同步。用户主动选择 webhook 通知时，让其自行把 webhook 放入安全环境变量 `FEISHU_WEBHOOK_URL`，随后运行 `configure-feishu --mode webhook`；不要把 URL 写入配置。用户选择已有或新建多维表时运行对应的 `configure-feishu --mode bitable-existing|bitable-new` 生成字段模板和授权提示。用户必须自行完成飞书登录、应用授权、建表或选表和共享权限；无授权时返回提示，不得假装多维表已经写入。

如果 Agent 在非交互环境执行，明确指定目录：

```bash
douyin-favorites-knowledge setup --knowledge-dir "用户确认的目录" --transcription siliconflow --skip-login
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

首次 `setup` 和 `login` 成功后，若当前 Agent 支持定时任务，必须在用户本机创建并验证每天 **23:00** 的任务，执行：

```bash
douyin-favorites-knowledge daily --source collection --no-login-prompt
```

使用当前环境可用的任务调度器；创建后必须读取任务状态或执行一次 dry-run 验证，并向用户返回任务标识与用户时区。任务只运行已安装的命令，不传凭据，不弹出登录页。云端转录时，只有调度环境能从用户已有的 Secret Manager 或安全环境变量读取 `SILICONFLOW_API_KEY`（或可选 `DASHSCOPE_API_KEY`）才能创建任务；不能持久化读取或当前 Agent 没有 scheduler 能力时，必须明确报告“自动日报未启用”，不能制造必然失败的计划任务或暗示已启用。`daily` 静默同步并在知识库 `日报/` 写入当天 Markdown 日报，零新增也写日报。登录失效时任务失败，由用户下次运行 `login` 恢复。

收藏是默认且唯一自动来源。用户明确说“喜欢”“点赞”“转录喜欢列表”或“喜欢日报”时，才额外建立或执行 `daily --source like --no-login-prompt`；它复用同一转录方案，但喜欢笔记、账本键和日报文件必须与收藏隔离。不要把两类来源合并，也不要因用户选择喜欢而停止收藏日报。

## 转录

用户未指定时，建议 **SiliconFlow** 云端转录（`FunAudioLLM/SenseVoiceSmall`），并让用户在 `setup` 中明确选择。
需要 `SILICONFLOW_API_KEY` 与可选 `ffmpeg`。

**新用户按序拿 Key（setup 缺 Key 时会打印同样步骤，交互可打开浏览器）：**

1. 推荐注册/登录：https://cloud.siliconflow.cn/i/1srulim9  
2. 控制台创建 Key：https://cloud.siliconflow.cn/account/ak  
3. `export SILICONFLOW_API_KEY='…'` 或写入 `~/.hermes/.env`，**重启 Agent**  
4. `douyin-favorites-knowledge check-config`

抖音 CDN：本机用浏览器式 `Referer: https://www.douyin.com/` 临时下载已授权 `play_url` → 上传 SenseVoice → **立即删除临时文件**；不要把 douyinvod URL 丢给百炼服务端。
密钥不能写入 config、笔记或日志。

### 费用（SiliconFlow 默认）

截至 **2026-08-05**，硅基流动[官方价格页](https://siliconflow.cn/pricing)将 `FunAudioLLM/SenseVoiceSmall` 标注为 **免费**（同页 `TeleSpeechASR` 亦免费；TTS 如 CosyVoice 另计 ¥0.05/千字符）。
价格会调整，**不承诺永久免费**；以价格页与控制台账单为准。

可选百炼 `qwen3-asr-flash`：截至 2026-07-30 华北 2 约 0.00022 元/秒，仅公网直链媒体；抖音 CDN 不默认。

笔记必须写清 `transcript_source` 与 `transcript_status`；未转录时必须说明原始 Description 不是逐字稿。

用户明确要求“本地免费转写”时，使用内置 `local_whisper`：先安装 `python -m pip install '.[local-asr]'` 与 `ffmpeg`，再 `setup --transcription local`。首次同步才下载 `small` 模型（约 500 MB），并要求至少 1.5 GB 临时空间。视频和音频只在系统临时目录存在，完成后删除；下次运行会回收超过 24 小时的异常残留。默认单视频下载上限 512 MB，模型缓存保留供复用。失败、过大或预算超限的条目不入库且下次自动重试。它没有 API 费用，但会使用本机 CPU、磁盘和电力；未满足前置条件时，`check-config` 必须报缺项，不能静默降级或下载。

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
- 分析默认关闭。用户明确启用时，analysis adapter 只返回结构化的 `analysis` 对象：`content_summary`、`value_judgment`、`deep_analysis`、`extensions`、`action_items`、`related_knowledge`；只有非空字段会写入笔记。不得写入模型的推理过程。

原子命令 `scan -> review -> promote` 只保留给局部审核、调试和迁移。不要把它暴露为普通用户的日常步骤；不得为了自动化把哈希、重复 ID、敏感信息或冲突文件错误降级为警告。

## 验证

```bash
python3 -m compileall -q src tests
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

真实采集依赖有效的授权登录和抖音当前页面结构。fixture 通过只证明事务与编排契约。


## ASR（2.2）

抖音默认 **SiliconFlow SenseVoice**（本机 Referer 下载上传）。百炼 URL-ASR 对 douyinvod 常失败，仅可选。密钥：`SILICONFLOW_API_KEY`。

### ASR 媒体与码率（2.2.4+）
- **单一路径**：下载 `play_url`/`video_url` → `ffmpeg -vn` 抽音 → 上传 SenseVoice。
- **不再优先** `audio_url`（抖音 `music.play_url` 经常是 BGM 不是口播）。
- 环境变量：`DOUYIN_ASR_AUDIO_BITRATE`（默认 `64k`）、`DOUYIN_ASR_SAMPLE_RATE`（默认 `16000`）。
- 网络下载阶段可能是视频体积；上传给 SenseVoice 的是抽好的小音频。

