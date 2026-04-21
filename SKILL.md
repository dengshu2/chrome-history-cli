---
name: chrome-history-cli
description: "chrome-history-cli — 从本地 Chrome 读取浏览历史与书签（支持 Windows / macOS / Linux）。当用户提到 Chrome/谷歌浏览器的历史记录、访问记录、浏览历史、书签、收藏夹、bookmarks 时使用此 skill。"
---

# chrome-history-cli

从本地 Chrome 读取**浏览历史**与**书签**。只读，不修改任何 Chrome 数据。支持 Windows / macOS / Linux。

## Triggers

- 查 Chrome 历史记录 / 浏览记录 / 访问历史
- Chrome 书签 / 收藏夹 / bookmarks
- 最近访问的网站 / 访问最多的网站
- 谷歌浏览器历史 / 谷歌浏览器书签
- chrome history / bookmarks
- "我前几天看过那个网站"

## Prerequisites

- Python 3.8+
- Chrome 已安装，默认数据目录：
  - **Windows**: `%LOCALAPPDATA%\Google\Chrome\User Data\`
  - **macOS**: `~/Library/Application Support/Google/Chrome/`
  - **Linux**: `~/.config/google-chrome/`（也兼容 `~/.config/chromium/`）
- 如 Chrome 安装在非默认位置，可设置环境变量 `CHROME_USER_DATA_DIR` 指定

**不需要安装任何 Python 包**，全部用标准库（`sqlite3`、`json`、`argparse`）。

## 调用方式

脚本路径依平台不同：

- Windows: `%USERPROFILE%\.claude\skills\chrome-history-cli\chrome_history_cli.py`
- macOS / Linux: `~/.claude/skills/chrome-history-cli/chrome_history_cli.py`

统一入口：

```bash
python3 ~/.claude/skills/chrome-history-cli/chrome_history_cli.py <subcommand> ...
```

为简洁起见，下文示例省略前缀，写作 `chrome-history-cli <subcommand>`。

## 命令速查

所有命令默认输出 YAML（省 token）；加 `--format json` 切换为 JSON。

### Profile 管理

```bash
chrome-history-cli profiles                    # 列出所有 Chrome profile
```

Chrome 的账号/配置以 profile 形式存在（`Default`、`Profile 1`、`Profile 2`...）。所有子命令默认使用 `Default`，用 `--profile "Profile 1"` 切换。

### 历史记录

```bash
# 最近访问（按时间倒序）
chrome-history-cli history list                # 默认 50 条
chrome-history-cli history list -n 200

# 按时间范围
chrome-history-cli history list --since 2026-04-01
chrome-history-cli history list --since 2026-04-01 --until 2026-04-15 -n 500

# 搜索 URL 或标题
chrome-history-cli history search "github"
chrome-history-cli history search "claude" --since 2026-04-01 -n 100

# 访问次数最多的 URL
chrome-history-cli history top -n 30

# 按域名聚合（访问总数、独立页面数）
chrome-history-cli history domains -n 20
```

**字段说明**：
- `url` / `title` — 页面 URL 与标题
- `visit_count` — 该 URL 的访问次数。**不带 `--since/--until` 时是终生累计**；带时间窗时，`top` 命令返回的是**窗口内访问次数**（JOIN `visits` 表实算）。
- `last_visit` — 最近访问时间（本地时区 ISO 格式）
- `domains` 命令额外字段：`visits`（域名下所有 URL 访问总和；时间窗下为窗口内真实计数）、`pages`（该域名下独立 URL 数）

### 书签

```bash
# 全部书签（扁平列表，按添加时间倒序）
chrome-history-cli bookmarks list
chrome-history-cli bookmarks list -n 500

# 搜索书签（匹配 name / url）
chrome-history-cli bookmarks search "react"

# 某文件夹下的书签（模糊匹配文件夹路径）
chrome-history-cli bookmarks folder "工作"
chrome-history-cli bookmarks folder "书签栏"

# 树形展示整个书签结构
chrome-history-cli bookmarks tree
```

**字段说明**：
- `name` / `url` — 书签名与链接
- `folder` — 书签所在文件夹路径（如 `书签栏/前端/React`）
- `added` — 添加时间

**根目录命名**：
- `书签栏` — Chrome 顶部工具栏上的书签（`bookmark_bar`）
- `其他书签` — "其他书签"文件夹（`other`）
- `移动书签` — 手机同步过来的（`synced`）

## Agent 使用建议

1. **不确定用哪个 profile 时**，先跑 `chrome-history-cli profiles` 查看账号绑定
2. **大批量分析时**加 `--format json` 方便程序处理：
   ```bash
   chrome-history-cli history list --format json -n 1000 > /tmp/hist.json
   ```
3. **模糊需求**（"前几天看过那个讲 X 的网站"）用 `history search`，再配合 `--since` 缩小时间窗
4. **找某个主题的资料积累**用 `bookmarks search`
5. Chrome 运行时数据库会被锁，脚本内部会**先复制到临时文件再读**（同时复制 `-journal`/`-wal`/`-shm` 附属文件），所以无需关闭 Chrome

## 数据位置（仅供参考）

Windows：
```
%LOCALAPPDATA%\Google\Chrome\User Data\
├── Local State              # profile 元数据（账号名映射）
├── Default\
│   ├── History              # SQLite，包含 urls / visits / downloads
│   └── Bookmarks            # JSON
└── Profile 1\
```

macOS：
```
~/Library/Application Support/Google/Chrome/
├── Local State
├── Default/
│   ├── History
│   └── Bookmarks
└── Profile 1/
```

Linux：
```
~/.config/google-chrome/
├── Local State
├── Default/
│   ├── History
│   └── Bookmarks
└── Profile 1/
```

## 常见问题

**Q: `database is locked`？**
A: 脚本内部已自动复制文件到临时目录读取。如仍报错，关闭 Chrome 再试。

**Q: 时间戳看起来不对？**
A: Chrome 用的是 WebKit 时间戳（1601-01-01 起的微秒数）。脚本已转换为本地时区 ISO 格式。

**Q: `--since 2026-04-01` 包含当天吗？**
A: 包含。`--until 2026-04-15` 包含到 04-15 的 23:59:59。

**Q: `history top --since` 返回的 `visit_count` 是什么？**
A: 是**窗口内**的访问次数（通过 JOIN `visits` 表按 `visit_time` 实算），不是终生累计。不带 `--since/--until` 时走快速路径，直接读 `urls.visit_count`（终生累计）。

**Q: 空结果怎么显示？**
A: YAML 输出 `[]`，JSON 输出 `[]`。便于区分"查了没结果" vs "命令挂了"。

**Q: 为什么 `history domains` 的 pages 数比 urls 表的总行数小？**
A: 因为 `--since/--until` 过滤了时间；不加时间参数时，pages 数应等于 urls 表的总行数（除非有隐藏记录）。

**Q: 搜索词本身（Omnibox 搜索）能查吗？**
A: 当前命令覆盖 `urls` 表。`keyword_search_terms` 表（搜索词）暂未暴露，如需可扩展。

**Q: 我用的是 Chrome Canary / Beta / Chromium，怎么办？**
A: 设置环境变量 `CHROME_USER_DATA_DIR` 指向对应的 User Data 目录即可。例如 macOS 上的 Chrome Canary：
```bash
export CHROME_USER_DATA_DIR="$HOME/Library/Application Support/Google/Chrome Canary"
```
