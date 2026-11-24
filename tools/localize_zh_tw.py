"""繁體化工具：把 repo 內的簡體中文轉成臺灣正體（繁體）。

使用 OpenCC 的 ``s2twp`` 設定（簡體 → 臺灣正體，並轉換臺灣慣用詞，
例如 程式→程式、網路→網路、影片→影片）。

用法::

    python tools/localize_zh_tw.py --dry-run     # 只列出會改動的檔案
    python tools/localize_zh_tw.py               # 實際轉換（含檔名）
    python tools/localize_zh_tw.py --no-rename   # 只轉內容，不改檔名

轉換範圍：``.py`` / ``.md`` / ``.json`` / ``.html`` / ``.txt`` / ``.toml``；
略過 ``.git``、``.venv``、圖片、快取與本工具自身輸出的備份目錄。
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

try:
    import opencc
except ImportError:  # pragma: no cover
    print("需要 opencc-python-reimplemented：pip install opencc", file=sys.stderr)
    raise

#: 要轉換的副檔名
TEXT_EXTS = {".py", ".md", ".json", ".html", ".txt", ".toml"}

#: 略過的目錄名
SKIP_DIRS = {".git", ".venv", ".tmp", "__pycache__", ".pytest_cache",
             "node_modules", "backup_simplified"}

#: 略過的檔案（授權條款等不該改動者）
SKIP_FILES = {"LICENSE"}


def iter_text_files(root: Path):
    """走訪 root，產出需要轉換的文字檔。"""
    for p in sorted(root.rglob("*")):
        if not p.is_file():
            continue
        if any(part in SKIP_DIRS for part in p.parts):
            continue
        if p.name in SKIP_FILES:
            continue
        if p.suffix.lower() not in TEXT_EXTS:
            continue
        yield p


def convert_text(text: str, cc) -> str:
    """轉換內文；保留原檔的換行風格。"""
    return cc.convert(text)


def convert_filename(name: str, cc) -> str:
    """把檔名中的簡體字轉成繁體（不動副檔名）。"""
    stem = Path(name).stem
    suffix = Path(name).suffix
    return cc.convert(stem) + suffix


def localize(root: Path, dry_run: bool = False, rename: bool = True) -> int:
    cc = opencc.OpenCC("s2twp")
    changed: list[Path] = []
    renamed: list[tuple[Path, Path]] = []

    for p in iter_text_files(root):
        try:
            original = p.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        converted = convert_text(original, cc)
        if converted != original:
            changed.append(p)
            if not dry_run:
                p.write_text(converted, encoding="utf-8")

    # 檔名繁體化（由深到淺，避免路徑中途改名）
    if rename:
        for p in sorted(iter_text_files(root), key=lambda x: len(x.parts), reverse=True):
            new_name = convert_filename(p.name, cc)
            if new_name != p.name:
                target = p.with_name(new_name)
                renamed.append((p, target))
                if not dry_run:
                    if target.exists():
                        print(f"  !! 目標已存在，略過：{target.name}", file=sys.stderr)
                        continue
                    p.rename(target)

    print(f"{'[dry-run] ' if dry_run else ''}內容轉換：{len(changed)} 個檔案")
    for p in changed[:40]:
        print(f"  - {p.relative_to(root)}")
    if len(changed) > 40:
        print(f"  …其餘 {len(changed) - 40} 個")
    if rename:
        print(f"檔名轉換：{len(renamed)} 個")
        for a, b in renamed:
            print(f"  {a.name}  →  {b.name}")
    return len(changed)


def main() -> int:
    ap = argparse.ArgumentParser(description="把 repo 中文簡體轉為臺灣正體")
    ap.add_argument("root", nargs="?", default=".", help="專案根目錄")
    ap.add_argument("--dry-run", action="store_true", help="只列出，不寫入")
    ap.add_argument("--no-rename", action="store_true", help="不改檔名")
    ap.add_argument("--backup", action="store_true",
                    help="先把整個專案複製到 backup_simplified/（僅第一次）")
    args = ap.parse_args()

    root = Path(args.root).resolve()
    if not (root / "src" / "liuyao").exists():
        print(f"警告：{root} 看起來不像 liuyao-divination 專案根目錄", file=sys.stderr)

    if args.backup and not args.dry_run:
        backup = root / "backup_simplified"
        if backup.exists():
            print(f"備份已存在，略過：{backup}")
        else:
            def _ignore(directory, names):
                skip = set()
                for n in names:
                    if n in SKIP_DIRS or n.startswith("pytest-cache-files-"):
                        skip.add(n)
                return skip

            print(f"備份到 {backup} …")
            shutil.copytree(root, backup, ignore=_ignore, dirs_exist_ok=True)

    n = localize(root, dry_run=args.dry_run, rename=not args.no_rename)
    return 0 if n >= 0 else 1


if __name__ == "__main__":
    sys.exit(main())
