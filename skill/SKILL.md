---
name: douyin-favorites-to-knowledge
description: 将用户已授权账号中的抖音收藏，通过本地浏览器登录、增量扫描、人工审核和幂等事务写入 Markdown 知识库；按需接入本地转录、MiniMax 或其他分析模型及飞书通知。用于首次登录、收藏同步、JSON 导入、审核批准、Obsidian 入库或配置可选 adapter；不得绕过登录、访问他人账号或泄露私密数据。
---

# 抖音收藏转本地知识库

使用仓库提供的 CLI。默认选择轻量模式；只有用户已经具备可靠的转录、模型或通知 adapter 时，才启用完整模式。不要要求用户复制 Cookie。

## 先确定模式

- `light`：官方页面登录、扫描、审核、批准、写入 Markdown 与 SQLite 账本。
- `full`：在轻量流程中依次增加可选转录、分析和通知 adapter。

MiniMax 不是必需项。本地模型名称因电脑而异，必须以用户实际可用模型为准。`provider` 记录选择，`adapter` 执行调用；不要声称仓库会自动下载视频、安装模型或配置飞书。

## 前置边界

- 用户有权访问来源收藏，采集方式符合平台条款和当地法律。
- 浏览器状态只留在应用独立 profile，不打印、不导出。
- Cookie、API key、飞书密钥等凭据只从环境变量、系统钥匙串或 Secret Manager 读取。
- JSON 配置只保存路径、provider、模型名和非敏感选项；可疑密钥字段会被拒绝。

## 事务流程

### 1. 扫描

无来源参数时使用内置浏览器 collector。首次运行打开抖音官方页面登录，之后复用本地会话：

```bash
douyin-favorites-knowledge --config config.json scan --review review.json
```

无人值守任务加 `--no-login-prompt`，让登录过期明确失败。可用 `login`、`status`、`logout` 单独管理会话，这三个命令不需要配置文件。

授权导出使用 `--input favorites.json`；外部 collector 使用 `--collector module:function`。配置为完整模式时，CLI 会按 `transcription -> analysis` 顺序调用已启用的 adapter。临时的一次性增强仍可用 `--enricher module:function`。

### 2. 审核与批准

先校验内容哈希、规范来源地址、笔记内容、重复 ID 和敏感信息，再明确批准：

```bash
douyin-favorites-knowledge --config config.json review \
  --review review.json \
  --approve-all \
  --approval approval.json
```

部分批准时重复使用 `--approve <aweme_id>`。批准后不要修改 review，promote 会校验其 SHA-256。

### 3. 写入知识库

```bash
douyin-favorites-knowledge --config config.json promote \
  --review review.json \
  --approval approval.json
```

CLI 先原子写入 Markdown，再提交不可变内容哈希到 SQLite。同一内容重复执行是空操作。已入库 ID 的内容发生变化时停止，交由人工迁移。配置通知 adapter 后，仅在本地提交成功且确有新增时调用。

## Adapter 规则

```python
def transcribe(item: dict, context: dict) -> dict: ...
def analyze(item: dict, context: dict) -> dict: ...
def notify(event: dict, context: dict) -> None: ...
```

配置阶段的 `context` 只包含 `mode`、`stage`、`provider`、`model` 和 `options`。转录或分析返回字段更新；禁止改变 `aweme_id`。通知发生在本地事务提交之后，通知失败不代表本地笔记已回滚。

如果转录需要下载视频，adapter 必须只使用已授权会话、限制临时目录并主动清理。不要把核心仓库描述成内置下载器。

## 必须阻止

- `<think>` 或 `<analysis>` 推理标签；
- Unicode 替换字符、NUL 或常见真实密钥格式；
- secret、token、password、cookie、credential、API key 类配置字段；
- 非法或冲突的重复 ID；
- 笔记、内容哈希或批准文件被修改；
- 已入库 ID 的内容变化；
- 未登记但同名且内容冲突的笔记。

不要为了自动化继续运行而把这些错误降级为警告。

## 验证

```bash
python3 -m compileall -q src tests
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

fixture 成功只证明事务和浏览器编排契约；真实采集仍依赖有效的授权登录和抖音当前页面结构。
