# 抖音收藏转本地知识库

把自己账号里新增的抖音收藏，整理成经过审核、可重复运行的本地 Markdown 知识笔记。首次使用会打开抖音官方页面登录，之后复用独立的本地浏览器会话；不用复制 Cookie，Cookie 也不会写进配置、笔记或日志。

[![CI](https://github.com/tars1230/douyin-favorites-to-knowledge/actions/workflows/ci.yml/badge.svg)](https://github.com/tars1230/douyin-favorites-to-knowledge/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)

本项目只访问你主动登录账号后有权查看的收藏内容，不绕过登录和平台访问控制。

## 两种模式

| 模式 | 适合谁 | 默认行为 |
|---|---|---|
| 轻量模式 `light` | 先把收藏稳定沉淀到本地的人 | 登录、扫描、人工批准、写入 Markdown 和 SQLite 账本 |
| 完整模式 `full` | 已有转录、分析或通知能力的人 | 在轻量流程上，按顺序调用可选的转录、分析和通知 adapter |

轻量模式是默认项，不下载大模型，也不要求 MiniMax。完整模式允许按电脑实际情况选择：

- 转录：本地语音模型或自定义 adapter；
- 分析：本地模型、MiniMax 或其他 adapter；
- 通知：飞书或其他 adapter。

`provider` 只是明确记录你选择的能力来源，真正调用由 `module:function` adapter 完成。当前仓库没有内置抖音视频下载器、模型自动安装器、MiniMax 客户端或飞书机器人，因此不会把这些外部能力伪装成开箱即用。这样可以避免绑定某一台电脑、某一个模型和某一种通知服务。

## 工作流程

```text
官方页面登录 -> 扫描收藏
                    |
                    +-> 可选转录 -> 可选分析
                    |
                    v
              review.json
                    |
              明确批准内容
                    |
                    v
        Markdown 笔记 + SQLite 幂等账本
                    |
                    +-> 可选通知
```

- `scan` 只生成待审核清单，不改知识库；
- `review` 重新校验内容哈希，并要求明确批准全部或部分条目；
- `promote` 校验审核文件未被修改，再原子写入笔记和账本；
- 同一批内容重复运行不会重复入库，已入库内容发生变化时会停止并要求人工迁移。

## 安装

第一次使用请直接选择轻量模式。确认收藏能正常写入 Markdown 后，再考虑本地转录、MiniMax 或飞书通知。

### 1. 下载项目

安装了 Git 时运行：

```bash
git clone https://github.com/tars1230/douyin-favorites-to-knowledge.git
cd douyin-favorites-to-knowledge
```

没有 Git 也可以在 GitHub 页面点击 **Code -> Download ZIP**，解压后在终端进入该目录。

### 2. 创建 Python 环境

需要 Python 3.10 或更高版本，先确认版本：

```bash
python3 --version
```

macOS / Linux：

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install .
```

Windows PowerShell：

```powershell
py -3 -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install .
```

安装完成后，这条命令应能显示帮助：

```bash
douyin-favorites-knowledge --help
```

### 3. 准备浏览器

系统会优先使用 Chrome 或 Edge。两者都没有时，安装一次 Playwright Chromium：

```bash
python -m playwright install chromium
```

### 4. 可选安装 Codex Skill

只使用命令行时可以跳过。需要在 Codex 中调用本项目时再安装：

```bash
cp -R skill ~/.codex/skills/douyin-favorites-to-knowledge
```

## 第一次入库

### 1. 创建自己的配置

不要直接修改示例文件。macOS / Linux：

```bash
cp config/config.example.json config/config.local.json
```

Windows PowerShell：

```powershell
Copy-Item config/config.example.json config/config.local.json
```

`config/config.local.json` 已加入 `.gitignore`，不会被意外提交。默认配置已经是轻量模式：

```json
{
  "schema_version": 2,
  "mode": "light",
  "knowledge_dir": "../.runtime/knowledge",
  "ledger_path": "../.runtime/state/ledger.sqlite3",
  "transcription": {"enabled": false, "provider": "none"},
  "analysis": {"enabled": false, "provider": "none"},
  "notification": {"enabled": false, "provider": "none"}
}
```

只需要先修改 `knowledge_dir`：

- 普通 Markdown 知识库：填写你准备存放笔记的目录；
- Obsidian：填写 Vault 里的一个独立子目录；
- 相对路径以配置文件所在目录为基准，也可以使用绝对路径；
- `ledger_path` 是防重复入库的本地账本，通常保持默认即可。

### 2. 检查配置

```bash
douyin-favorites-knowledge --config config/config.local.json check-config
```

首次使用应看到类似结果：

```json
{
  "mode": "light",
  "schema_version": 2,
  "stages": {
    "analysis": {"enabled": false, "provider": "none"},
    "notification": {"enabled": false, "provider": "none"},
    "transcription": {"enabled": false, "provider": "none"}
  },
  "status": "valid"
}
```

这条命令不会输出 Cookie、配置路径、知识库路径或 adapter 名称。注意：`--config` 必须写在 `check-config`、`scan`、`review`、`promote` 等子命令之前。

### 3. 登录抖音

```bash
douyin-favorites-knowledge login
```

浏览器会打开抖音官方页面。正常登录后，终端返回 `authenticated`。后续运行会复用这个独立本地会话。

### 4. 扫描新增收藏

```bash
douyin-favorites-knowledge --config config/config.local.json scan \
  --review .runtime/review.json
```

返回 `status: written` 表示待审核清单已经生成。`candidate_count` 是本次等待审核的新增数量；为 `0` 时不会生成可批准内容。

### 5. 批准并写入知识库

确认 review 内容后批准全部条目：

```bash
douyin-favorites-knowledge --config config/config.local.json review \
  --review .runtime/review.json \
  --approve-all \
  --approval .runtime/approval.json

douyin-favorites-knowledge --config config/config.local.json promote \
  --review .runtime/review.json \
  --approval .runtime/approval.json
```

返回 `status: committed` 后，打开 `knowledge_dir`：每条批准收藏应有一份 `.md` 文件。再次运行同一批内容时，`promoted_count` 为 `0`，不会重复入库。

需要只批准部分内容时，不使用 `--approve-all`，改为重复指定 ID：

```bash
douyin-favorites-knowledge --config config/config.local.json review \
  --review .runtime/review.json \
  --approve 7000000000000000001 \
  --approve 7000000000000000002 \
  --approval .runtime/approval.json
```

登录状态管理：

```bash
douyin-favorites-knowledge status
douyin-favorites-knowledge logout
```

无人值守任务可在 `scan` 后加 `--no-login-prompt`。登录过期时任务会明确失败，不会把“没抓到内容”误判成“没有新增收藏”。

## 完整模式配置

完整模式是进阶功能。启用前先确认：

1. 轻量模式已经成功完成一次入库；
2. 对应 adapter 已安装在当前虚拟环境，能通过 `module:function` 导入；
3. 本地模型或云端模型名称真实可用；
4. API key、飞书密钥等已经放进环境变量、系统钥匙串或 Secret Manager。

下面只展示结构。adapter 名称和模型名必须替换成当前电脑上真实可用的实现：

```json
{
  "schema_version": 2,
  "mode": "full",
  "knowledge_dir": "../.runtime/knowledge",
  "ledger_path": "../.runtime/state/ledger.sqlite3",
  "transcription": {
    "enabled": true,
    "provider": "local",
    "adapter": "my_pipeline:transcribe",
    "model": "my-local-asr-model"
  },
  "analysis": {
    "enabled": true,
    "provider": "minimax",
    "adapter": "my_pipeline:analyze",
    "model": "my-minimax-model"
  },
  "notification": {
    "enabled": true,
    "provider": "feishu",
    "adapter": "my_pipeline:notify"
  }
}
```

每个阶段都可以独立关闭或换成 `adapter`。使用本地模型时，`model` 写本机实际模型；使用 MiniMax 时，`model` 写账号可用模型。API key、飞书密钥和其他凭据只允许从环境变量、系统钥匙串或宿主 Secret Manager 读取，配置文件中的 secret、token、password、cookie、credential 和 API key 类字段会被拒绝。

修改后再次运行 `check-config`。它只验证配置契约；adapter 能否连接模型或飞书，仍要由对应 adapter 自己提供连接测试。

## Adapter 契约

配置中的转录和分析 adapter 会依次收到单条收藏与当前阶段上下文：

```python
def transcribe(item: dict, context: dict) -> dict:
    # context: mode、stage、provider、model、options
    return {"transcript": "..."}

def analyze(item: dict, context: dict) -> dict:
    return {"tags": ["主题"], "description": "..."}

def notify(event: dict, context: dict) -> None:
    # 仅在本地事务提交成功后调用
    ...
```

Adapter 不得修改 `aweme_id`，传入的 `source_url` 也不会覆盖系统生成的规范地址。如果转录需要下载视频，adapter 必须使用已授权会话、限制临时文件范围并在完成后清理；核心仓库目前不负责下载视频。

原有命令行扩展仍然可用：

```bash
douyin-favorites-knowledge --config config.json scan \
  --enricher my_module:enrich \
  --review review.json

douyin-favorites-knowledge --config config.json promote \
  --review review.json \
  --approval approval.json \
  --notifier my_module:notify
```

命令行 `--notifier` 会覆盖配置中的通知 adapter。

## 输入与 Obsidian

浏览器收藏、授权导出的 JSON 和自定义 collector 最终都会归一成同一结构。至少需要：

| 字段 | 必需 | 说明 |
|---|---|---|
| `aweme_id` | 是 | 6 到 30 位数字，作为不可变 ID |
| `title` 或 `description` | 是 | 至少一个非空 |
| `author` | 否 | 作者公开信息 |
| `transcript` | 否 | 转录文本，通过安全检查后写入笔记 |
| `tags` | 否 | 去重并排序的标签 |
| `observed_at` | 否 | 采集时间 |

输出是普通 Markdown 文件，因此 `knowledge_dir` 可以直接指向 Obsidian Vault 中的一个独立目录。项目不修改 Obsidian 设置，也不要求安装 Obsidian 插件。

## 常见问题

| 现象 | 怎么处理 |
|---|---|
| `--config is required` | 把 `--config config/config.local.json` 放在子命令前面 |
| `config ... must` 或 `unknown config fields` | 先对照示例恢复字段，再运行 `check-config` |
| `secret-like key blocked` | 从 JSON 删除密钥、Cookie 或 token，改从环境变量或密钥管理器读取 |
| 找不到 Chrome、Edge 或 Chromium | 运行 `python -m playwright install chromium` |
| 返回 `login_required` | 运行 `douyin-favorites-knowledge login` 重新登录 |
| `candidate_count` 为 `0` | 当前没有未入库的新收藏；这不是错误 |
| 完整模式提示缺少 `adapter` 或 `model` | 暂时切回 `light`，或先安装并验证对应 adapter 和模型 |
| adapter 连接 MiniMax、飞书或本地模型失败 | 检查该 adapter 的环境变量、模型名称和连接测试；核心不会读取其凭据 |

仍无法判断时，依次保留 `check-config` 输出、执行命令和脱敏后的 `ERROR:` 文本。不要提交浏览器 profile、Cookie 或配置外的密钥文件。

## 隐私与安全边界

- 登录发生在 CLI 打开的抖音官方页面中；
- 浏览器状态保存在系统应用数据目录下的独立 profile；
- Cookie 不会作为命令行参数或配置字段，也不会进入 review、笔记和日志；
- `logout` 会清除保存的浏览器会话；卸载 Python 包不会擅自删除知识库和账本；
- 推理标签、NUL、常见密钥格式、可疑配置字段、重复 ID、哈希篡改和冲突文件都会阻止入库；
- 文本扫描无法识别截图或视频画面中的秘密，本核心只写文本笔记。

## 验证

```bash
python3 -m compileall -q src tests
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

CI 还会把构建后的包安装到全新虚拟环境，并执行一次完整的 fixture 事务。

## 卸载

```bash
douyin-favorites-knowledge logout
python -m pip uninstall douyin-favorites-to-knowledge
```

知识库、SQLite 账本和浏览器 profile 都属于用户数据，不会随包卸载自动删除。

## 许可证

[MIT](LICENSE)
