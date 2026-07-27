# 抖音收藏转本地知识库

刷到有用的视频就收藏。需要整理时运行一次同步，新收藏会变成可搜索的本地 Markdown 笔记。

[![CI](https://github.com/tars1230/douyin-favorites-to-knowledge/actions/workflows/ci.yml/badge.svg)](https://github.com/tars1230/douyin-favorites-to-knowledge/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)

不用复制 Cookie，不用先选模型，也不用理解内部处理步骤。

## 最短使用路径

安装：

```bash
git clone https://github.com/tars1230/douyin-favorites-to-knowledge.git
cd douyin-favorites-to-knowledge
python3 -m venv .venv
. .venv/bin/activate
python -m pip install .
```

第一次使用：

```bash
douyin-favorites-knowledge setup
```

按照提示选择知识库目录，随后在打开的抖音官方页面正常登录。

以后同步只需要：

```bash
douyin-favorites-knowledge sync
```

命令会列出本次新增收藏。输入 `y` 后才会写入知识库；输入其他内容会取消，不改任何文件。

## 让 AI 帮你安装

把下面这句话发给 Codex、Claude Code 或其他能够操作本机项目的编程 Agent：

```text
请安装并配置这个项目：https://github.com/tars1230/douyin-favorites-to-knowledge
把我的抖音收藏同步到本地 Markdown 知识库。先使用默认轻量配置，不要让我复制 Cookie。
```

Agent 应当完成安装并运行 `setup`。你只需要确认知识库目录，并在抖音官方页面登录。

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

没有 Git 时，可以在 GitHub 页面点击 **Code -> Download ZIP**，解压后进入项目目录。

系统会优先使用 Chrome 或 Edge。两者都没有时运行：

```bash
python -m playwright install chromium
```

安装成功后，`douyin-favorites-knowledge --help` 会显示中文命令说明。

### `setup` 做了什么

`setup` 只做三件事：

1. 询问 Markdown 或 Obsidian 知识库目录；
2. 在系统应用配置目录生成安全的默认配置；
3. 打开抖音官方页面完成登录。

配置文件不保存 Cookie、API key、密码或 token。Cookie 只留在独立的本地浏览器 profile 中。

常用选项：

```bash
# 直接指定知识库目录
douyin-favorites-knowledge setup --knowledge-dir "我的知识库目录"

# 只创建配置，稍后再登录
douyin-favorites-knowledge setup --knowledge-dir "我的知识库目录" --skip-login

# 重新选择知识库目录
douyin-favorites-knowledge setup --force --knowledge-dir "新的知识库目录"
```

### `sync` 做了什么

```text
扫描新增收藏 -> 展示标题 -> 等待确认 -> 写入 Markdown -> 记录防重账本
```

- 没有新增时返回 `no_changes`；
- 有新增时先展示标题，不会直接写入；
- 确认后返回 `committed`；
- 同一条收藏再次同步不会重复入库；
- 登录过期时会重新打开登录页，而不是误报“没有新增”。

只查看新增、不写入：

```bash
douyin-favorites-knowledge sync --dry-run
```

用于明确授权的无人值守任务：

```bash
douyin-favorites-knowledge sync --yes --no-login-prompt
```

`--yes` 表示批准本次全部新增；`--no-login-prompt` 表示登录过期时直接失败。项目提供同步命令，但不会擅自创建系统定时任务。

## 输出结果

每条批准收藏生成一份独立 Markdown 文件，包含：

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
| 自动任务等待确认 | 使用显式参数 `sync --yes --no-login-prompt` |

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
| 转录 | 本地语音模型或自定义 adapter |
| 分析 | 本地模型、MiniMax 或其他 adapter |
| 通知 | 飞书或其他 adapter |

MiniMax 不是必需项，本地模型也不写死。不同电脑可以选择不同模型。具体能力通过 `module:function` adapter 接入；当前仓库没有内置视频下载器、模型自动安装器、MiniMax 客户端或飞书机器人。

完整配置结构见 [config/config.schema.json](config/config.schema.json)。修改前先完成一次默认 `setup -> sync`，并确认 adapter 能在当前虚拟环境中导入。所有凭据只能来自环境变量、系统钥匙串或 Secret Manager。

Adapter 契约：

```python
def transcribe(item: dict, context: dict) -> dict:
    return {"transcript": "..."}

def analyze(item: dict, context: dict) -> dict:
    return {"tags": ["主题"], "description": "..."}

def notify(event: dict, context: dict) -> None:
    ...
```

如果转录需要下载视频，adapter 必须使用已授权会话、限制临时文件范围并完成清理。核心仓库不负责下载视频。

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
