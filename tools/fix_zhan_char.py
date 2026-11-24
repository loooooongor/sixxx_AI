"""修正 OpenCC 過度轉換：把占卜義的「佔」改回「占」。

OpenCC 的 s2twp 會把「占」一律轉成「佔」，但台灣標準中：

* 占卜、占問、占事、占時、占得、占卦、男占女 → 用「占」
* 佔用、佔據、佔地、獨佔、佔便宜             → 才用「佔」

本工具只保留真正「佔用義」的「佔」，其餘一律改回「占」。
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

#: 必須保留「佔」的詞（佔用義）
KEEP_ZHAN4 = [
    "佔用", "佔據", "佔地", "獨佔", "佔便宜", "佔位", "佔空間", "佔時間",
    "佔一行", "不佔", "只佔", "佔去", "佔有", "佔滿", "佔上風", "佔優勢",
]

TEXT_EXTS = {".py", ".md", ".json", ".html", ".txt", ".toml", ".js", ".css"}
SKIP_DIRS = {".git", ".venv", ".tmp", "__pycache__", ".pytest_cache",
             "node_modules", "backup_simplified", "outputs"}
#: 跳過本工具自己（避免自我改寫）
SKIP_FILES = {"fix_zhan_char.py", "localize_zh_tw.py"}


def fix_text(text: str) -> tuple[str, int]:
    """把占卜義的「佔」改回「占」；回傳 (新文字, 改動次數)。"""
    # 先以佔位符保護「佔用義」的詞
    protected: dict[str, str] = {}
    for i, word in enumerate(KEEP_ZHAN4):
        if word in text:
            token = f"\x00ZHAN4_{i}\x00"
            protected[token] = word
            text = text.replace(word, token)
    count = text.count("佔")
    text = text.replace("佔", "占")
    for token, word in protected.items():
        text = text.replace(token, word)
    return text, count


def _iter_files(root: Path):
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


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    dry = "--dry-run" in sys.argv
    root = Path(args[0] if args else ".").resolve()

    total = 0
    touched: list[tuple[Path, int]] = []

    for p in _iter_files(root):
        try:
            original = p.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        if "佔" not in original:
            continue
        fixed, n = fix_text(original)
        if fixed != original:
            touched.append((p, n))
            total += n
            if not dry:
                p.write_text(fixed, encoding="utf-8")

    print(f"{'[dry-run] ' if dry else ''}修正 {total} 處，涉及 {len(touched)} 個檔案")
    for p, n in touched:
        print(f"  {n:4d}  {p.relative_to(root)}")

    if not dry and total:
        suspicious = 0
        for p in _iter_files(root):
            try:
                t = p.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            if "佔" not in t:
                continue
            for m in re.finditer(".{0,3}佔.{0,3}", t):
                if not any(w in m.group(0) for w in KEEP_ZHAN4):
                    print(f"  !! 仍有可疑「佔」：{p.relative_to(root)} → {m.group(0)!r}")
                    suspicious += 1
        print(f"殘留可疑「佔」：{suspicious} 處（0 為理想）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
