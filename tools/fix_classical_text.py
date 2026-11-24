"""修復古文語料：把 OpenCC 在《易經》原文上造成的用字破壞修回來。

《易經》經文用的是「于」「征」「丑」等古字，OpenCC `s2twp` 誤轉成
「於」「徵」「醜」；另外「蠱」被誤成「盎」。這些都在 `s2twp` 的
「同義異形」對照表裡，屬不可接受的原文改動。

修正規則（僅套用於古文語料檔）：

| 誤 | 正 | 說明 |
|---|---|---|
| 徵 | **征** | 「王用出征」；僅在「出征／征伐／征戰」語境，避開「徵兆」「徵求」 |
| 於 | **于** | 《易經》經文一律用「于」（鴻漸于干、至于八月有凶） |
| 醜 | **丑** | 「獲匪其醜」之「醜」＝類眾，經文作「丑」 |
| 盎 | **蠱** | 「幹父之蠱」之誤（OCR／字形混淆，非 OpenCC 所為） |

適用檔案：`data/zhouyi.json`。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

#: 古文語料檔（相對路徑）
CORPUS_FILES = [
    "data/zhouyi.json",
]

#: 必須保護、不可改的詞（現代詞或另有其義）
KEEP = [
    "徵兆", "徵求", "徵集", "徵信", "徵稅", "徵收", "徵召", "特徵", "象徵",
    "表徵", "徵狀", "病徵", "徵候", "應徵", "徵文", "徵才",
]

#: 詞組級修正（先做，較精確）
PHRASE_FIXES = [
    ("王用出徵", "王用出征"),
    ("出徵", "出征"),
    ("征伐", "征伐"),
    ("獲匪其醜", "獲匪其丑"),
    ("匪其醜", "匪其丑"),
    ("幹父之盎", "幹父之蠱"),
    ("幹母之盎", "幹母之蠱"),
    ("父之盎", "父之蠱"),
    ("母之盎", "母之蠱"),
]

#: 單字修正（在保護詞之後）
CHAR_FIXES = [
    ("於", "于"),
    ("徵", "征"),
    ("醜", "丑"),
]


def _protect(text: str, phrases: list[str]) -> tuple[str, dict[str, str]]:
    table: dict[str, str] = {}
    for i, phrase in enumerate(phrases):
        if phrase in text:
            token = f"\x02Q{i:02d}\x02"
            table[token] = phrase
            text = text.replace(phrase, token)
    return text, table


def _restore(text: str, table: dict[str, str]) -> str:
    for token, phrase in table.items():
        text = text.replace(token, phrase)
    return text


def fix_corpus_text(text: str) -> tuple[str, dict[str, int]]:
    """修正古文語料用字；回傳 (新文字, {修正項: 次數})。"""
    counts: dict[str, int] = {}

    # 1) 詞組級（最精確）
    for old, new in PHRASE_FIXES:
        if old in text and old != new:
            n = text.count(old)
            text = text.replace(old, new)
            counts[f"{old}→{new}"] = counts.get(f"{old}→{new}", 0) + n

    # 2) 單字級（保護現代詞）
    for old, new in CHAR_FIXES:
        if old not in text:
            continue
        text, table = _protect(text, KEEP)
        n = text.count(old)
        if n:
            text = text.replace(old, new)
            counts[f"{old}→{new}"] = counts.get(f"{old}→{new}", 0) + n
        text = _restore(text, table)

    return text, counts


def main() -> int:
    dry = "--dry-run" in sys.argv
    total: dict[str, int] = {}
    for rel in CORPUS_FILES:
        p = ROOT / rel
        if not p.exists():
            print(f"略過（不存在）：{rel}")
            continue
        original = p.read_text(encoding="utf-8")
        fixed, counts = fix_corpus_text(original)
        if fixed == original:
            print(f"無需修正：{rel}")
            continue
        for k, v in counts.items():
            total[k] = total.get(k, 0) + v
        if not dry:
            # JSON 檔要驗證仍是合法 JSON
            if p.suffix == ".json":
                json.loads(fixed)
            p.write_text(fixed, encoding="utf-8")
        print(f"{'[dry-run] ' if dry else ''}已修正：{rel}")

    print()
    for k, v in sorted(total.items(), key=lambda t: -t[1]):
        print(f"  {v:5d}  {k}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
