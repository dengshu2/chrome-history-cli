# chrome-history-cli

一个跨平台的命令行工具，用于从本地 Chrome 读取**浏览历史**与**书签**。只读，不修改任何 Chrome 数据。

主要面向 [Claude Code](https://github.com/anthropics/claude-code) 等 AI Agent 作为 **Skill** 使用，也可直接当普通 CLI 跑。

- ✅ 支持 **Windows / macOS / Linux**
- ✅ 零依赖（只用 Python 标准库：`sqlite3`、`json`、`argparse`）
- ✅ Chrome 运行时可直接读（自动复制 SQLite 数据库及其 WAL/journal 附属文件到临时目录）
- ✅ 输出默认 YAML（省 token），`--format json` 可切 JSON

## 安装

要求 Python 3.8+。下载 `chrome_history_cli.py` 到任意目录即可：

```bash
curl -O https://raw.githubusercontent.com/dengshu2/chrome-history-cli/main/chrome_history_cli.py
python3 chrome_history_cli.py profiles
```

作为 Claude Code Skill 使用：把整个仓库（包含 `SKILL.md` 和 `chrome_history_cli.py`）放到 `~/.claude/skills/chrome-history-cli/` 即可。

```bash
git clone https://github.com/dengshu2/chrome-history-cli.git ~/.claude/skills/chrome-history-cli
```

## 支持的 Chrome 数据位置

| 平台      | 默认路径                                                |
| --------- | ------------------------------------------------------- |
| Windows   | `%LOCALAPPDATA%\Google\Chrome\User Data\`               |
| macOS     | `~/Library/Application Support/Google/Chrome/`          |
| Linux     | `~/.config/google-chrome/`（也兼容 `~/.config/chromium/`） |

非默认安装（Canary / Beta / Chromium / 自定义 profile）可通过环境变量覆盖：

```bash
export CHROME_USER_DATA_DIR="$HOME/Library/Application Support/Google/Chrome Canary"
```

## 快速示例

```bash
# 列出所有 Chrome profile
python3 chrome_history_cli.py profiles

# 最近 50 条浏览记录
python3 chrome_history_cli.py history list

# 搜索标题 / URL 包含 "github" 的记录
python3 chrome_history_cli.py history search "github"

# 某段时间内访问最多的 URL
python3 chrome_history_cli.py history top --since 2026-04-01 -n 30

# 按域名聚合统计
python3 chrome_history_cli.py history domains -n 20

# Omnibox 搜索词
python3 chrome_history_cli.py history searches "claude" -n 20

# 全部书签（按添加时间倒序）
python3 chrome_history_cli.py bookmarks list

# 搜索书签
python3 chrome_history_cli.py bookmarks search "react"

# 树形展示整棵书签树
python3 chrome_history_cli.py bookmarks tree

# 切换 profile
python3 chrome_history_cli.py history list --profile "Profile 1"

# 切换为 JSON 输出
python3 chrome_history_cli.py history list --format json -n 100
```

完整命令列表和字段说明见 [`SKILL.md`](./SKILL.md)。

## 工作原理

- **历史记录**：读取 `<profile>/History`，一个 SQLite 数据库。查的主要是 `urls` 表（每个 URL 一行，含累计访问次数 `visit_count` 与 `last_visit_time`）。
- **书签**：读取 `<profile>/Bookmarks`，一个 JSON 文件。脚本递归遍历 `roots.*.children`。
- **Chrome 运行时锁**：Chrome 会锁住 History 数据库。脚本把它（以及 `-journal`、`-wal`、`-shm` 附属文件）先 `copy2` 到临时目录再读，避开锁。
- **时间戳**：Chrome 用 WebKit 微秒时间戳（从 1601-01-01 UTC 起）。脚本转换成本地时区的 ISO 字符串。

## 隐私

本工具**只读**本地 Chrome 数据，不发送任何数据到网络，不修改 Chrome 的任何文件。

## License

MIT
