#!/usr/bin/env python3
"""chrome-cli: 从本地 Chrome 读取历史记录与书签（跨平台：Windows / macOS / Linux）。"""

from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import sqlite3
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse

# Chrome 数据是 UTF-8，Windows 控制台默认 cp936 会乱码/崩溃，强制切 UTF-8。
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

CHROME_EPOCH_DIFF = 11_644_473_600  # seconds between 1601-01-01 and 1970-01-01


def chrome_user_data_dir() -> Path:
    """返回 Chrome 的 User Data 目录。可用 CHROME_USER_DATA_DIR 环境变量覆盖。"""
    override = os.environ.get("CHROME_USER_DATA_DIR")
    if override:
        path = Path(override).expanduser()
        if not path.exists():
            sys.exit(f"错误：CHROME_USER_DATA_DIR 指向的目录不存在：{path}")
        return path

    system = platform.system()
    candidates: list[Path] = []
    if system == "Windows":
        local = os.environ.get("LOCALAPPDATA")
        if local:
            candidates.append(Path(local) / "Google" / "Chrome" / "User Data")
    elif system == "Darwin":
        home = Path.home()
        candidates.append(home / "Library" / "Application Support" / "Google" / "Chrome")
        # Chrome Canary / Beta 可自行通过 CHROME_USER_DATA_DIR 指定
    else:  # Linux 及其他类 Unix
        home = Path.home()
        candidates.extend([
            home / ".config" / "google-chrome",
            home / ".config" / "chromium",
        ])

    for path in candidates:
        if path.exists():
            return path
    searched = "\n  ".join(str(p) for p in candidates) or "(无候选路径)"
    sys.exit(
        "错误：未找到 Chrome 数据目录。已尝试：\n  "
        f"{searched}\n可通过设置 CHROME_USER_DATA_DIR 环境变量指定。"
    )


def list_profiles() -> list[dict]:
    root = chrome_user_data_dir()
    local_state = root / "Local State"
    name_map: dict[str, str] = {}
    if local_state.exists():
        try:
            data = json.loads(local_state.read_text(encoding="utf-8"))
            for key, info in (data.get("profile", {}).get("info_cache") or {}).items():
                name_map[key] = info.get("name") or key
        except Exception:
            pass
    profiles = []
    for entry in sorted(root.iterdir()):
        if not entry.is_dir():
            continue
        if entry.name == "Default" or entry.name.startswith("Profile "):
            profiles.append({
                "dir": entry.name,
                "name": name_map.get(entry.name, entry.name),
                "has_history": (entry / "History").exists(),
                "has_bookmarks": (entry / "Bookmarks").exists(),
            })
    return profiles


def profile_dir(profile: str) -> Path:
    root = chrome_user_data_dir()
    path = root / profile
    if not path.exists():
        available = [p["dir"] for p in list_profiles()]
        sys.exit(f"错误：profile 不存在：{profile}。可用：{', '.join(available)}")
    return path


def copy_to_temp(src: Path) -> Path:
    if not src.exists():
        sys.exit(f"错误：文件不存在：{src}")
    fd, tmp = tempfile.mkstemp(prefix="chrome_cli_", suffix=".db")
    os.close(fd)
    shutil.copy2(src, tmp)
    # 同时复制 SQLite 附属文件（rollback journal / WAL / shared-memory），
    # 否则 Chrome 运行时的未提交事务可能丢失或报错。
    for suffix in ("-journal", "-wal", "-shm"):
        sidecar = src.with_name(src.name + suffix)
        if sidecar.exists():
            try:
                shutil.copy2(sidecar, tmp + suffix)
            except Exception:
                pass
    return Path(tmp)


def chrome_time_to_iso(us: int) -> str | None:
    if not us:
        return None
    try:
        ts = us / 1_000_000 - CHROME_EPOCH_DIFF
        return datetime.fromtimestamp(ts).strftime("%Y-%m-%dT%H:%M:%S")
    except (OSError, ValueError, OverflowError):
        return None


def iso_to_chrome_time(s: str, end_of_day: bool = False) -> int:
    """将 YYYY-MM-DD 或 ISO 字符串转成 Chrome 的 microsecond 时间戳。"""
    s = s.strip()
    # 支持 YYYY-MM-DD 和 YYYY-MM-DDTHH:MM:SS
    try:
        if "T" in s or " " in s:
            dt = datetime.fromisoformat(s.replace(" ", "T"))
        else:
            dt = datetime.strptime(s, "%Y-%m-%d")
            if end_of_day:
                dt = dt + timedelta(days=1) - timedelta(microseconds=1)
    except ValueError:
        sys.exit(f"错误：无法解析时间：{s}（使用 YYYY-MM-DD 或 YYYY-MM-DDTHH:MM:SS）")
    # 本地时间 → epoch seconds
    epoch = dt.timestamp()
    return int((epoch + CHROME_EPOCH_DIFF) * 1_000_000)


# -------------------- 输出格式 --------------------

def yaml_dump(items) -> str:
    """简单 YAML 输出，只处理 list[dict] 和 dict。"""
    if items is None:
        return ""
    if isinstance(items, dict):
        return _yaml_dict(items, 0)
    if isinstance(items, list):
        out = []
        for item in items:
            if isinstance(item, dict):
                first = True
                for k, v in item.items():
                    prefix = "- " if first else "  "
                    first = False
                    out.append(f"{prefix}{k}: {_yaml_scalar(v, indent=2)}")
            else:
                out.append(f"- {_yaml_scalar(item, indent=0)}")
        return "\n".join(out)
    return str(items)


def _yaml_dict(d: dict, indent: int) -> str:
    lines = []
    pad = " " * indent
    for k, v in d.items():
        lines.append(f"{pad}{k}: {_yaml_scalar(v, indent + 2)}")
    return "\n".join(lines)


def _yaml_scalar(v, indent: int) -> str:
    if v is None:
        return "null"
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return str(v)
    if isinstance(v, list):
        if not v:
            return "[]"
        pad = " " * indent
        lines = [""]
        for item in v:
            if isinstance(item, dict):
                first = True
                for k, val in item.items():
                    prefix = f"{pad}- " if first else f"{pad}  "
                    first = False
                    lines.append(f"{prefix}{k}: {_yaml_scalar(val, indent + 2)}")
            else:
                lines.append(f"{pad}- {_yaml_scalar(item, indent + 2)}")
        return "\n".join(lines)
    if isinstance(v, dict):
        if not v:
            return "{}"
        return "\n" + _yaml_dict(v, indent)
    s = str(v)
    if s == "":
        return '""'
    # 简单转义：含特殊字符时引号包裹
    if any(ch in s for ch in [":", "#", "\n", "\"", "'"]) or s[0] in " -?*&!|>%@`":
        return json.dumps(s, ensure_ascii=False)
    return s


def emit(data, fmt: str):
    if fmt == "json":
        print(json.dumps(data, ensure_ascii=False, indent=2))
    else:
        print(yaml_dump(data))


# -------------------- 历史记录 --------------------

def build_time_clause(args, time_col: str = "last_visit_time"):
    conds = []
    params = []
    if args.since:
        conds.append(f"{time_col} >= ?")
        params.append(iso_to_chrome_time(args.since))
    if args.until:
        conds.append(f"{time_col} <= ?")
        params.append(iso_to_chrome_time(args.until, end_of_day=True))
    return conds, params


def cmd_history_list(args):
    db = copy_to_temp(profile_dir(args.profile) / "History")
    try:
        conn = sqlite3.connect(db)
        conds, params = build_time_clause(args)
        where = ("WHERE " + " AND ".join(conds)) if conds else ""
        sql = f"""
            SELECT url, title, visit_count, last_visit_time
            FROM urls
            {where}
            ORDER BY last_visit_time DESC
            LIMIT ?
        """
        params.append(args.limit)
        rows = conn.execute(sql, params).fetchall()
        conn.close()
    finally:
        _cleanup(db)

    items = [
        {
            "url": url,
            "title": title or url,
            "visit_count": visit_count,
            "last_visit": chrome_time_to_iso(lvt),
        }
        for url, title, visit_count, lvt in rows
    ]
    emit(items, args.format)


def cmd_history_search(args):
    db = copy_to_temp(profile_dir(args.profile) / "History")
    try:
        conn = sqlite3.connect(db)
        conds = ["(url LIKE ? OR title LIKE ?)"]
        like = f"%{args.query}%"
        params = [like, like]
        time_conds, time_params = build_time_clause(args)
        conds.extend(time_conds)
        params.extend(time_params)
        sql = f"""
            SELECT url, title, visit_count, last_visit_time
            FROM urls
            WHERE {" AND ".join(conds)}
            ORDER BY last_visit_time DESC
            LIMIT ?
        """
        params.append(args.limit)
        rows = conn.execute(sql, params).fetchall()
        conn.close()
    finally:
        _cleanup(db)

    items = [
        {
            "url": url,
            "title": title or url,
            "visit_count": visit_count,
            "last_visit": chrome_time_to_iso(lvt),
        }
        for url, title, visit_count, lvt in rows
    ]
    emit(items, args.format)


def cmd_history_top(args):
    db = copy_to_temp(profile_dir(args.profile) / "History")
    try:
        conn = sqlite3.connect(db)
        conds, params = build_time_clause(args)
        where = ("WHERE " + " AND ".join(conds)) if conds else ""
        sql = f"""
            SELECT url, title, visit_count, last_visit_time
            FROM urls
            {where}
            ORDER BY visit_count DESC
            LIMIT ?
        """
        params.append(args.limit)
        rows = conn.execute(sql, params).fetchall()
        conn.close()
    finally:
        _cleanup(db)

    items = [
        {
            "url": url,
            "title": title or url,
            "visit_count": visit_count,
            "last_visit": chrome_time_to_iso(lvt),
        }
        for url, title, visit_count, lvt in rows
    ]
    emit(items, args.format)


def cmd_history_domains(args):
    db = copy_to_temp(profile_dir(args.profile) / "History")
    try:
        conn = sqlite3.connect(db)
        conds, params = build_time_clause(args)
        where = ("WHERE " + " AND ".join(conds)) if conds else ""
        sql = f"""
            SELECT url, visit_count
            FROM urls
            {where}
        """
        rows = conn.execute(sql, params).fetchall()
        conn.close()
    finally:
        _cleanup(db)

    agg: dict[str, dict] = {}
    for url, visits in rows:
        host = urlparse(url).hostname or "(unknown)"
        d = agg.setdefault(host, {"domain": host, "visits": 0, "pages": 0})
        d["visits"] += visits
        d["pages"] += 1

    items = sorted(agg.values(), key=lambda x: x["visits"], reverse=True)[: args.limit]
    emit(items, args.format)


def _cleanup(tmp: Path):
    try:
        os.unlink(tmp)
    except OSError:
        pass
    for suffix in ("-journal", "-wal", "-shm"):
        sidecar = Path(str(tmp) + suffix)
        if sidecar.exists():
            try:
                os.unlink(sidecar)
            except OSError:
                pass


# -------------------- 书签 --------------------

def load_bookmarks(profile: str) -> dict:
    path = profile_dir(profile) / "Bookmarks"
    if not path.exists():
        sys.exit(f"错误：书签文件不存在：{path}")
    return json.loads(path.read_text(encoding="utf-8"))


def walk_bookmarks(node, folder_path: list[str]):
    """深度遍历，产出 {name, url, folder, added} 条目。"""
    ntype = node.get("type")
    name = node.get("name", "")
    if ntype == "url":
        yield {
            "name": name,
            "url": node.get("url", ""),
            "folder": "/".join(folder_path),
            "added": chrome_time_to_iso(int(node.get("date_added") or 0)),
        }
    elif ntype == "folder":
        sub = folder_path + ([name] if name else [])
        for child in node.get("children", []):
            yield from walk_bookmarks(child, sub)


def all_bookmarks(data) -> list[dict]:
    items = []
    roots = data.get("roots", {})
    root_labels = {
        "bookmark_bar": "书签栏",
        "other": "其他书签",
        "synced": "移动书签",
    }
    for key, node in roots.items():
        if not isinstance(node, dict):
            continue
        label = root_labels.get(key, key)
        items.extend(walk_bookmarks(node, [label]))
    return items


def cmd_bookmarks_list(args):
    data = load_bookmarks(args.profile)
    items = all_bookmarks(data)
    items.sort(key=lambda x: x.get("added") or "", reverse=True)
    emit(items[: args.limit], args.format)


def cmd_bookmarks_search(args):
    data = load_bookmarks(args.profile)
    q = args.query.lower()
    items = [
        b for b in all_bookmarks(data)
        if q in b["name"].lower() or q in b["url"].lower()
    ]
    items.sort(key=lambda x: x.get("added") or "", reverse=True)
    emit(items[: args.limit], args.format)


def cmd_bookmarks_folder(args):
    data = load_bookmarks(args.profile)
    q = args.name.lower()
    items = [b for b in all_bookmarks(data) if q in b["folder"].lower()]
    items.sort(key=lambda x: x.get("folder", ""))
    emit(items[: args.limit], args.format)


def cmd_bookmarks_tree(args):
    data = load_bookmarks(args.profile)
    root_labels = {
        "bookmark_bar": "书签栏",
        "other": "其他书签",
        "synced": "移动书签",
    }
    lines = []

    def render(node, depth: int):
        ntype = node.get("type")
        name = node.get("name", "")
        pad = "  " * depth
        if ntype == "folder":
            count = sum(1 for _ in walk_bookmarks(node, []))
            lines.append(f"{pad}[{name}] ({count})")
            for child in node.get("children", []):
                render(child, depth + 1)
        elif ntype == "url":
            lines.append(f"{pad}- {name}  {node.get('url', '')}")

    for key, node in data.get("roots", {}).items():
        if not isinstance(node, dict):
            continue
        label = root_labels.get(key, key)
        lines.append(f"[{label}]")
        for child in node.get("children", []):
            render(child, 1)
    print("\n".join(lines))


def cmd_profiles(args):
    emit(list_profiles(), args.format)


# -------------------- argparse --------------------

def add_common(sp: argparse.ArgumentParser, with_query: bool = False, with_time: bool = True):
    sp.add_argument("--profile", default="Default", help="Chrome profile 目录名（默认 Default）")
    sp.add_argument("--format", choices=["yaml", "json"], default="yaml", help="输出格式（默认 yaml）")
    sp.add_argument("-n", "--limit", type=int, default=50, help="返回条数（默认 50）")
    if with_time:
        sp.add_argument("--since", help="起始日期 YYYY-MM-DD")
        sp.add_argument("--until", help="结束日期 YYYY-MM-DD")


def main():
    parser = argparse.ArgumentParser(prog="chrome-cli", description="读取本地 Chrome 历史记录与书签")
    sub = parser.add_subparsers(dest="cmd", required=True)

    # profiles
    sp = sub.add_parser("profiles", help="列出所有 profile")
    sp.add_argument("--format", choices=["yaml", "json"], default="yaml")
    sp.set_defaults(func=cmd_profiles)

    # history
    p_hist = sub.add_parser("history", help="历史记录")
    hist_sub = p_hist.add_subparsers(dest="action", required=True)

    sp = hist_sub.add_parser("list", help="最近访问（按时间倒序）")
    add_common(sp)
    sp.set_defaults(func=cmd_history_list)

    sp = hist_sub.add_parser("search", help="搜索 URL / 标题")
    sp.add_argument("query", help="关键词")
    add_common(sp)
    sp.set_defaults(func=cmd_history_search)

    sp = hist_sub.add_parser("top", help="访问次数最多的 URL")
    add_common(sp)
    sp.set_defaults(func=cmd_history_top)

    sp = hist_sub.add_parser("domains", help="按域名聚合统计")
    add_common(sp)
    sp.set_defaults(func=cmd_history_domains)

    # bookmarks
    p_bm = sub.add_parser("bookmarks", help="书签")
    bm_sub = p_bm.add_subparsers(dest="action", required=True)

    sp = bm_sub.add_parser("list", help="所有书签（按添加时间倒序）")
    add_common(sp, with_time=False)
    sp.set_defaults(func=cmd_bookmarks_list)

    sp = bm_sub.add_parser("search", help="搜索书签")
    sp.add_argument("query", help="关键词")
    add_common(sp, with_time=False)
    sp.set_defaults(func=cmd_bookmarks_search)

    sp = bm_sub.add_parser("folder", help="列出某文件夹下的书签（模糊匹配）")
    sp.add_argument("name", help="文件夹名或路径片段")
    add_common(sp, with_time=False)
    sp.set_defaults(func=cmd_bookmarks_folder)

    sp = bm_sub.add_parser("tree", help="树形展示书签结构")
    sp.add_argument("--profile", default="Default")
    sp.set_defaults(func=cmd_bookmarks_tree)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(130)
