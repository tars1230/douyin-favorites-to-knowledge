---
name: douyin-favorites-to-knowledge
description: 将用户已授权账号中的抖音收藏配置并同步到本地 Markdown 或 Obsidian 知识库；提供首次 setup、增量 sync、登录恢复、JSON 导入、局部审核，以及按需接入本地转录、MiniMax 或其他分析模型和飞书通知。不得绕过登录、访问他人账号或泄露 Cookie 与私密数据。
---

# 抖音收藏转本地知识库

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

让用户选择 Markdown 或 Obsidian 知识库目录。`setup` 生成默认轻量配置并打开抖音官方页面登录。不要要求用户复制 Cookie。

如果 Agent 在非交互环境执行，明确指定目录：

```bash
douyin-favorites-knowledge setup --knowledge-dir "用户确认的目录" --skip-login
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
- 当前仓库不内置视频下载器、模型安装器、MiniMax 客户端或飞书机器人；
- 转录、分析和通知通过 `module:function` adapter 接入。

原子命令 `scan -> review -> promote` 保留给局部审核和调试。批准必须明确；不得为了自动化把哈希、重复 ID、敏感信息或冲突文件错误降级为警告。

## 验证

```bash
python3 -m compileall -q src tests
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

真实采集依赖有效的授权登录和抖音当前页面结构。fixture 通过只证明事务与编排契约。
