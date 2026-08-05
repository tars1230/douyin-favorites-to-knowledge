# 抖音收藏转本地知识库

刷到有用的视频就收藏。需要整理时运行一次同步，新收藏会变成可搜索的本地 Markdown 笔记。默认采集**收藏**；用户明确说“喜欢/点赞”时才采集喜欢列表，二者绝不混用。

[![CI](https://github.com/tars1230/douyin-favorites-to-knowledge/actions/workflows/ci.yml/badge.svg)](https://github.com/tars1230/douyin-favorites-to-knowledge/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)

不用复制 Cookie，也不用理解内部处理步骤。首次 `setup` 会明确让你选择：**推荐 SiliconFlow 云端转录**（抖音 CDN 真实可用）、可选百炼 URL-ASR、本地 Whisper，或暂不转录。

## 最短使用路径

### 交给 Agent

支持 ClawHub 的 Agent 先运行：

```bash
clawhub install douyin-favorites-to-knowledge
```

然后告诉 Agent：

```text
把我的抖音收藏同步到本地 Markdown 或 Obsidian 知识库。使用推荐的 SiliconFlow 云端转录（SILICONFLOW_API_KEY），不要让我复制 Cookie。
```

Agent 会在缺少程序时优先从 Gitee 安装完整程序。你只需要确认知识库目录，再在抖音官方页面正常登录。

### 手动安装

```bash
git clone https://gitee.com/tars123/douyin-favorites-to-knowledge.git
cd douyin-favorites-to-knowledge
python3 -m venv .venv
. .venv/bin/activate
python -m pip install .
```

第一次使用：

```bash
douyin-favorites-knowledge setup
```

按照提示选择知识库目录和转录方案，随后在打开的抖音官方页面正常登录。

以后同步只需要：

```bash
douyin-favorites-knowledge sync
```

命令会静默把新增收藏写入知识库。首次设置后不再要求确认；终端只输出本次写入数量。具备定时任务能力的 Agent 会在首次配置后创建并验证每天 **23:00** 的收藏日报；纯命令行安装不假装已创建后台任务。使用 `--dry-run` 才只查看、不写入。

### Obsidian 与飞书

本地 Markdown 是默认且完整的知识库；Obsidian 和飞书均为可选增强，不会阻断同步。

```bash
# 选择 Vault 与子目录，自动创建收藏/喜欢/日报/模板/系统目录、默认模板和日报索引
douyin-favorites-knowledge configure-obsidian --vault "我的 Vault" --subdir "抖音知识库"

# 使用环境变量中的 webhook 发送同步摘要；URL 不会写入配置文件
export FEISHU_WEBHOOK_URL="用户自己的飞书机器人 webhook"
douyin-favorites-knowledge configure-feishu --mode webhook

# 已有或新建多维表：先在知识库生成字段模板与授权提示
douyin-favorites-knowledge configure-feishu --mode bitable-existing
douyin-favorites-knowledge configure-feishu --mode bitable-new
```

Obsidian 初始化会做一次临时写入检查，并提供“收藏/喜欢”两套默认模板、日报索引和飞书字段模板。同步产生的笔记继续使用可移植 Markdown，不依赖 Obsidian 插件。

飞书 webhook 配置后，通知失败只在同步结果中标为 `not_sent`，本地笔记和防重账本仍会正常写入。多维表模式当前会生成推荐字段（标题、来源类型、作者、原视频、标签、转录状态、沉淀时间、Obsidian 笔记）与授权提示；用户仍须在飞书中登录、创建或选择表格、授权应用并共享表格，Skill 不保存 App Secret 或 webhook。

[GitHub](https://github.com/tars1230/douyin-favorites-to-knowledge) 保存源码、版本和问题反馈；[Gitee](https://gitee.com/tars123/douyin-favorites-to-knowledge) 提供国内下载，并自动同步 `main` 与正式标签。

## 转录说明（2.2 重要变更）

| 方案 | 适用 | 密钥 |
|------|------|------|
| **SiliconFlow SenseVoice（默认推荐）** | 抖音 CDN 口播 | `SILICONFLOW_API_KEY` |
| 百炼 qwen3-asr-flash（可选） | 可公网直链的音频；**抖音 douyinvod 服务端常拉不到** | `DASHSCOPE_API_KEY` |
| 本地 Whisper | 无云费用、本机算力 | 无 API Key |

抖音播放地址带防盗链：本机下载必须带 `Referer: https://www.douyin.com/`。SiliconFlow / 本地 Whisper 路径已处理；百炼 URL 模式把 URL 交给阿里云服务器去拉，对抖音 CDN **结构性失败**，因此不再作为默认推荐。

`setup --transcription cloud` 在 2.2+ 映射到 **siliconflow**（不再等于 bailian）。

## 安装说明

### 系统要求

- Python 3.10 或更高版本；
- Chrome、Edge 或 Playwright Chromium；
- 有权访问自己账号中的抖音收藏。

先检查 Python：

```bash
python3 --version
```

Windows PowerShell 使用下面的环境命令：

```powershell
py -3 -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install .
```

没有 Git 时，可以在 Gitee 页面选择 **克隆/下载 -> 下载 ZIP**，解压后进入项目目录。

系统会优先使用 Chrome 或 Edge。两者都没有时运行：

```bash
python -m playwright install chromium
```

安装成功后，`douyin-favorites-knowledge --help` 会显示中文命令说明。

### `setup` 做了什么

`setup` 做四件事：

1. 询问 Markdown 或 Obsidian 知识库目录；
2. 让你明确选择百炼云端、本地 Whisper 或暂不转录；
3. 在系统应用配置目录生成安全的配置；
4. 打开抖音官方页面完成登录。

配置文件不保存 Cookie、API key、密码或 token。Cookie 只留在独立的本地浏览器 profile 中。

常用选项：

```bash
# 直接指定知识库目录
douyin-favorites-knowledge setup --knowledge-dir "我的知识库目录"

# 非交互安装必须明确选择转录方案
douyin-favorites-knowledge setup --knowledge-dir "我的知识库目录" --transcription bailian

# 只创建配置，稍后再登录
douyin-favorites-knowledge setup --knowledge-dir "我的知识库目录" --skip-login

# 重新选择知识库目录
douyin-favorites-knowledge setup --force --knowledge-dir "新的知识库目录"
```

### `sync` 做了什么

```text
扫描新增收藏 -> 写入 Markdown -> 记录防重账本
```

- 没有新增时返回 `no_changes`；
- 有新增时静默写入，返回 `committed`；
- 同一条收藏再次同步不会重复入库；
- 登录过期时会重新打开登录页，而不是误报“没有新增”。

只查看新增、不写入：

```bash
douyin-favorites-knowledge sync --dry-run
```

登录过期时不打开登录页、直接失败：

```bash
douyin-favorites-knowledge sync --no-login-prompt
```

`--no-login-prompt` 表示登录过期时直接失败。`--yes` 仅为旧脚本兼容保留，不再需要。

### 每晚 23:00 日报

首次配置完成后，具备定时任务能力的 Agent 必须创建并验证本机每天 **23:00** 运行：

```bash
douyin-favorites-knowledge daily --source collection --no-login-prompt
```

它会静默同步新增收藏，并在知识库的 `日报/` 目录生成当天的 Markdown 日报；没有新增也会写明“今日没有新增条目”。登录失效时任务失败但不会弹出浏览器，下一次用户运行 `douyin-favorites-knowledge login` 后自动恢复。任务创建失败或当前 Agent 没有 scheduler 能力时，必须明确报告“自动日报未启用”；手动安装则直接运行同一条 `daily` 命令。

### 收藏与喜欢

- **收藏（默认）**：`showTab=favorite_collection` / `listcollection`，是用户主动筛选的知识候选集；默认每天 23:00 同步并出日报。
- **喜欢（可选）**：`showTab=like` / `favorite`，是另一套独立列表，通常量更大、噪声更多；默认不扫，避免把“随手点赞”混进知识库。

对 Agent 说“同步我的抖音收藏”或不指定来源时，一律运行收藏；只有用户明确说“喜欢”“点赞”才运行：

```bash
douyin-favorites-knowledge sync --source like
```

两类来源有独立的防重键和 Markdown 文件名，防止历史上“收藏与喜欢混成同一增量状态”的漏采事故。

用户明确说“转录我的喜欢”或“给喜欢列表出日报”时，使用同一套已选择的百炼或本地 Whisper 转录能力：

```bash
douyin-favorites-knowledge daily --source like --no-login-prompt
```

喜欢笔记命名为 `like-*.md`，日报命名为 `日报/YYYY-MM-DD-喜欢日报.md`，与收藏完全隔离。

## 视频转录与费用

首次 `setup` 必须明确选择一种方案。它会先进行不读取密钥、不下载模型、不产生费用的本机能力检测，再展示建议；非交互环境使用 `--transcription siliconflow|bailian|local|none`（`cloud` = siliconflow）。检测到 Key 也不会自动开启付费转录。

| 方案 | 适合谁 | 首次要求 | 费用 |
|---|---|---|---|
| **`siliconflow`（推荐，`cloud` 别名）** | 抖音 CDN 口播全文 | `SILICONFLOW_API_KEY`；建议有 `ffmpeg` | 截至 2026-08-05 官方价 `SenseVoiceSmall`=**免费**；以 [价格页](https://siliconflow.cn/pricing)/账单为准 |
| `bailian`（可选） | 可公网直链的音频；**抖音 douyinvod 常失败** | `DASHSCOPE_API_KEY` + `.[bailian-asr]` | 按音频秒数计费 |
| `local` | 不希望使用云端 API | `ffmpeg`、`faster-whisper`、约 500 MB 模型 | 无 API 费用 |
| `none` | 只需要收藏描述与链接 | 无 | 无 |

### SiliconFlow 云端（推荐）

默认方案：本机用浏览器式 `Referer: https://www.douyin.com/` 临时下载已授权 `play_url`，可选抽音频后上传 SiliconFlow `FunAudioLLM/SenseVoiceSmall`，结束后删临时文件。Key 只读环境变量 `SILICONFLOW_API_KEY`，不写配置/笔记/日志。

```bash
export SILICONFLOW_API_KEY="你的硅基流动 Key"   # https://cloud.siliconflow.cn/account/ak

- **注册推荐链接**：[https://cloud.siliconflow.cn/i/1srulim9](https://cloud.siliconflow.cn/i/1srulim9)
douyin-favorites-knowledge setup --transcription siliconflow
douyin-favorites-knowledge check-config
```

### 百炼 URL-ASR（可选，非抖音默认）

把临时播放地址直接交给阿里云百炼 `qwen3-asr-flash`（服务端拉 URL，项目不下载）。**对抖音 `*.douyinvod.com` 服务端常拉不到**，因此不再作为公开默认推荐；仅当你确认媒体 URL 可被阿里云公网访问时使用。

```bash
export DASHSCOPE_API_KEY="你的百炼 Key"
python -m pip install '.[bailian-asr]'
douyin-favorites-knowledge setup --transcription bailian
douyin-favorites-knowledge check-config
```

### SiliconFlow 费用（默认推荐）

截至 **2026-08-05**，硅基流动[官方价格页](https://siliconflow.cn/pricing)语音模型 `FunAudioLLM/SenseVoiceSmall` 标注为 **免费**（同页 `TeleSpeechASR` 亦为免费；TTS 如 CosyVoice 另计）。需要有效 `SILICONFLOW_API_KEY`。价格会调整，**不承诺永久免费**；以价格页与控制台账单为准。

控制台 Key：https://cloud.siliconflow.cn/account/ak

### 百炼费用（仅可选公网直链）

若你显式选择 `bailian`：截至 2026-07-30 阿里云百炼[官方价格页](https://help.aliyun.com/zh/model-studio/model-pricing)华北 2 `qwen3-asr-flash` 约 **0.00022 元/秒**。抖音 CDN 服务端常拉不到，不作为默认。



### 本地 Whisper

选 `local` 后，程序才会在第一次同步时允许下载 `small` 模型（约 500 MB，实际大小随上游版本变化）。先安装运行时：

```bash
python -m pip install '.[local-asr]'
# 另行安装 ffmpeg，例如 macOS: brew install ffmpeg
douyin-favorites-knowledge setup --transcription local
douyin-favorites-knowledge check-config
```

程序只用已授权采集到的临时播放地址下载媒体，提取音频并在临时目录转录，结束后删除临时媒体和音频；若进程被强制终止，下次运行会清理超过 24 小时的遗留临时目录。默认单视频下载上限为 512 MB，可在 `transcription.options.max_media_bytes` 调整。Whisper 的约 500 MB 模型缓存会保留给后续转录，不会作为临时媒体删除。转录失败、文件过大或预算超限的条目不会入库或写入防重账本，下次同步会自动重试。

## 输出结果

每条新增收藏生成一份独立 Markdown 文件，包含：

- 标题、作者和抖音原始地址；
- 收藏描述；
- 已提供或通过扩展生成的转录文本；
- 标签和采集时间。

`setup` 选择 Obsidian Vault 中的子目录后，笔记可以直接在 Obsidian 中打开，不要求安装 Obsidian 插件。

## 自检与登录管理

检查当前配置，不显示本机路径、Cookie、adapter 或凭据：

```bash
douyin-favorites-knowledge check-config
```

管理抖音登录状态：

```bash
douyin-favorites-knowledge login
douyin-favorites-knowledge status
douyin-favorites-knowledge logout
```

## 常见问题

| 现象 | 处理方法 |
|---|---|
| 提示尚未完成配置 | 运行 `douyin-favorites-knowledge setup` |
| 找不到 Chrome、Edge 或 Chromium | 运行 `python -m playwright install chromium` |
| 返回 `login_required` | 运行 `douyin-favorites-knowledge login` |
| `candidate_count` 为 `0` | 当前没有未入库的新收藏，不是错误 |
| `secret-like key blocked` | 从配置删除密钥、Cookie 或 token，改用环境变量或密钥管理器 |
| 想更换知识库目录 | 运行 `douyin-favorites-knowledge setup --force` |
| 每晚任务因登录失效失败 | 运行 `douyin-favorites-knowledge login`，下次 23:00 自动恢复 |
| 百炼未就绪 | 设置 `DASHSCOPE_API_KEY`，安装 `python -m pip install '.[bailian-asr]'`，再运行 `check-config` |
| 本地转录未就绪 | 安装 `.[local-asr]`、`ffmpeg`，并留出至少 1.5 GB 临时空间 |

仍无法判断时，保留执行命令、`check-config` 输出和脱敏后的 `ERROR:` 文本。不要提交浏览器 profile、Cookie 或密钥文件。

## 进阶配置

普通使用到这里已经足够。只有需要本地转录、模型分析或飞书通知时，才继续本节。

`setup` 默认配置文件位置：

- macOS：`~/Library/Application Support/douyin-favorites-to-knowledge/config.json`；
- Windows：`%APPDATA%\douyin-favorites-to-knowledge\config.json`；
- Linux：`${XDG_CONFIG_HOME:-~/.config}/douyin-favorites-to-knowledge/config.json`。

也可以通过 `DOUYIN_FAVORITES_CONFIG` 指定自定义配置路径。环境变量只保存路径，不要放任何凭据。

### 可选能力

配置 v2 支持三个独立阶段：

| 阶段 | 可选来源 |
|---|---|
| 转录 | 内置百炼、内置本地 Whisper 或自定义 adapter |
| 分析 | 本地模型、MiniMax 或其他 adapter |
| 通知 | 飞书或其他 adapter |

MiniMax 不是必需项，本地模型也不写死。不同电脑可以选择不同模型。具体能力通过 `module:function` adapter 接入；当前仓库不自动安装模型运行时、MiniMax 客户端或飞书机器人。分析默认关闭；启用后 adapter 返回 `{"analysis": {"content_summary": "…", "value_judgment": "…", "deep_analysis": "…", "extensions": "…", "action_items": "…", "related_knowledge": "…"}}`，非空字段才写入笔记。`tags` 仍可由 adapter 单独返回；不要把模型推理过程写入任一字段。

完整配置结构见 [config/config.schema.json](config/config.schema.json)。修改前先完成一次默认 `setup -> sync`，并确认 adapter 能在当前虚拟环境中导入。所有凭据只能来自环境变量、系统钥匙串或 Secret Manager。

### MiniMax 与本机发现

`check-config` 会安全检查已知的本机命令，不扫描配置文件，也不显示凭据值。目前检测到 `mmx` 只有 `synthesize/generate/voices` 等语音生成命令时，会明确显示“不可用于转录”；仅有 `MINIMAX_API_KEY` 也不代表可用。只有将来发现公开、可验证的 ASR 命令或适配器时才会显示为候选，并且仍需用户确认后启用。

Adapter 契约：

```python
def transcribe(item: dict, context: dict) -> dict:
    return {"transcript": "..."}

def analyze(item: dict, context: dict) -> dict:
    return {"tags": ["主题"], "description": "..."}

def notify(event: dict, context: dict) -> None:
    ...
```

自定义 adapter 如需下载视频，必须使用已授权会话、限制临时文件范围并完成清理。

### 原子命令

`sync` 内部复用以下安全事务。需要局部批准、JSON 导入或调试 adapter 时，可以单独调用：

```text
scan -> review -> promote
```

```bash
douyin-favorites-knowledge --config config.json scan --review review.json
douyin-favorites-knowledge --config config.json review \
  --review review.json --approve-all --approval approval.json
douyin-favorites-knowledge --config config.json promote \
  --review review.json --approval approval.json
```

每一步都支持 `--dry-run`。批准文件绑定 review 的 SHA-256，入库使用 SQLite 账本和原子文件替换。

## 安全边界

- 只访问用户主动登录账号后有权查看的收藏；
- 不绕过登录或平台访问控制；
- Cookie 不作为参数或配置字段，也不进入笔记和日志；
- 推理标签、NUL、常见密钥格式、可疑配置字段、重复 ID、哈希篡改和冲突文件都会阻止入库；
- 文本检查无法识别截图或视频画面中的秘密，本核心只写文本笔记。

## 验证

```bash
python3 -m compileall -q src tests
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

CI 会在 Python 3.10 和 3.12 中运行测试，并把构建后的 wheel 安装到全新虚拟环境完成 onboarding 与 fixture E2E。

## 卸载

```bash
douyin-favorites-knowledge logout
python -m pip uninstall douyin-favorites-to-knowledge
```

卸载 Python 包不会自动删除知识库、SQLite 账本或浏览器 profile。

## 许可证

[MIT](LICENSE)

### ASR 媒体与码率（2.2.4+）
- **单一路径**：下载 `play_url`/`video_url` → `ffmpeg -vn` 抽音 → 上传 SenseVoice。
- **不再优先** `audio_url`（抖音 `music.play_url` 经常是 BGM 不是口播）。
- 环境变量：`DOUYIN_ASR_AUDIO_BITRATE`（默认 `64k`）、`DOUYIN_ASR_SAMPLE_RATE`（默认 `16000`）。
- 网络下载阶段可能是视频体积；上传给 SenseVoice 的是抽好的小音频。

