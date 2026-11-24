"""領域字回修：修正 OpenCC `s2twp` 對六爻／干支領域字的過度轉換。

`s2twp` 會把字一律轉成「更常見的繁體形」，但在本領域造成反效果，甚至讓程式壞掉：

| 被轉成 | 應為 | 原因 | 例 |
|---|---|---|---|
| 醜 | **丑** | 十二地支（會讓 `DIZHI` 鍵錯，CLI 打「丑」直接 KeyError） | 子丑寅卯、丑未沖 |
| 幹 | **干** | 天干、年干、月干、納干 | 五虎遁由年干推月干 |
| 兇 | **凶** | 吉凶 | 變克主（凶）、凶應 |
| 佔 | **占** | 占卜 | 占問、占事、所占 |
| 視窗 | **時間窗** | 時間語境 | 最佳時間窗 |
| 物件 | **對象** | 感情語境指人 | 家人介紹的對象 |
| 求測者 | **問卦者** | 大陸用語 | 代表問卦者處境 |

**關鍵**：`s2twp` 不是 idempotent。每跑一次 `localize_zh_tw.py`，修好的字會全部再壞一次。
故本工具必須**接在** `localize_zh_tw.py` 之後執行：
`localize_zh_tw.py → fix_zhan_char.py → fix_domain_chars.py`。

易經原文與既有正確用法一律保護，不會被改動。
"""

from __future__ import annotations

import sys
from pathlib import Path

TEXT_EXTS = {".py", ".md", ".json", ".html", ".txt", ".toml", ".js", ".css"}
SKIP_DIRS = {".git", ".venv", ".tmp", "__pycache__", ".pytest_cache",
             "node_modules", "backup_simplified", "outputs"}
SKIP_FILES = {"fix_domain_chars.py", "localize_zh_tw.py", "fix_zhan_char.py"}

# ── 必須保留原字的詞 ────────────────────────────────────────────

#: 「醜」保留（易經原文：離卦上九「獲匪其醜」）
KEEP_CHOU = ["獲匪其醜", "匪其醜"]

#: 「幹」保留（易經原文「幹父之蠱」；一般詞「幹部」「能幹」等）
KEEP_GAN = [
    "幹父之蠱", "幹母之蠱", "幹父", "幹母",
    "幹部", "幹事", "幹活", "能幹", "才幹", "骨幹", "主幹", "幹練",
    "幹勁", "樹幹", "軀幹", "幹線",
]

#: 「兇」保留（真正的兇惡義）
KEEP_XIONG = ["兇險", "兇傷", "兇狠", "兇惡", "兇手", "兇器",
              "行兇", "逞兇", "兇殘", "兇猛"]

#: 「衝」保留（真正的衝擊義；六爻術語一律用「沖」）
KEEP_CHONG = [
    "衝突", "衝擊", "衝動", "衝破", "衝刺", "衝鋒", "衝勁", "衝撞", "衝力",
    "衝上", "衝進", "衝出", "衝去", "衝來", "衝向", "衝到",
    "怒氣衝衝", "首當其衝", "幹勁衝天",
]

#: 「物件」保留（真正的「物件」義：程式碼、泛指事物）
KEEP_WUJIAN = [
    "物件導向", "物件模型", "物件陣列", "物件屬性", "物件參考", "建立物件",
    "無特定物件", "所測的物件", "物件或事", "物件是無生命", "一個物件",
    "回傳物件", "Board 物件", "dict 物件", "物件。", "物件自我",
]

#: 「占」保留為「佔」（佔用義）
KEEP_ZHAN4 = [
    "佔用", "佔據", "佔地", "獨佔", "佔便宜", "佔位", "佔空間", "佔時間",
    "佔一行", "不佔", "只佔", "佔去", "佔有", "佔滿", "佔上風", "佔優勢",
    "未占有孚",
]

#: 一律保留、不參與任何替換的片段
KEEP_LITERAL = ["可程式設計"]  # 由上層詞組規則處理


def _protect(text: str, phrases: list[str]) -> tuple[str, dict[str, str]]:
    table: dict[str, str] = {}
    for i, phrase in enumerate(phrases):
        if phrase in text:
            token = f"\x01P{i:02d}\x01"
            table[token] = phrase
            text = text.replace(phrase, token)
    return text, table


def _restore(text: str, table: dict[str, str]) -> str:
    for token, phrase in table.items():
        text = text.replace(token, phrase)
    return text


#: 詞組修正：(舊, 新)。先做長詞再做短詞，避免半途截斷。
WORD_RULES: list[tuple[str, str]] = [
    # 時間語境
    ("視窗期", "時間窗"),
    ("最佳視窗", "最佳時間窗"),
    ("時間視窗", "時間窗"),
    ("視窗", "時間窗"),
    # 感情語境（只改指人的用法）
    ("介紹的物件", "介紹的對象"),
    ("戀愛物件", "戀愛對象"),
    ("物件本身好", "對象本身好"),
    ("物件不差", "對象不差"),
    ("物件條件", "對象條件"),
    ("物件分量", "對象分量"),
    # 大陸用語 → 台灣用語
    ("求測者", "問卦者"),
    ("腳手架", "鷹架"),
    ("回血", "生扶"),
    ("託底", "保底"),
    ("閉環", "循環"),
    ("落地", "落實"),
    ("賬目", "帳目"),
    ("賬面", "帳面"),
    ("對賬", "對帳"),
    ("賬", "帳"),
    ("可程式設計", "可程式化"),
    ("軟鏈", "軟連結"),
    ("智慧體", "智慧代理"),
    ("文件名", "檔名"),
]

#: 單字修正：(說明, 保護詞, 舊字, 新字)
CHAR_RULES: list[tuple[str, list[str], str, str]] = [
    ("地支「丑」", KEEP_CHOU, "醜", "丑"),
    ("天干「干」", KEEP_GAN, "幹", "干"),
    ("吉凶「凶」", KEEP_XIONG, "兇", "凶"),
    ("占卜「占」", KEEP_ZHAN4, "佔", "占"),
    ("相沖「沖」", KEEP_CHONG, "衝", "沖"),
]


def fix_text(text: str) -> tuple[str, dict[str, int]]:
    """套用全部修正；回傳 (新文字, {修正項: 次數})。"""
    counts: dict[str, int] = {}

    # 1) 詞組（長詞優先，故先全部保護一次再逐一替換）
    for old, new in sorted(WORD_RULES, key=lambda t: -len(t[0])):
        if old not in text:
            continue
        # 「物件」類詞組需避免誤傷程式碼語境
        if old.startswith("物件"):
            text, table = _protect(text, KEEP_WUJIAN)
            n = text.count(old)
            if n:
                text = text.replace(old, new)
                counts[f"{old}→{new}"] = counts.get(f"{old}→{new}", 0) + n
            text = _restore(text, table)
        else:
            n = text.count(old)
            text = text.replace(old, new)
            counts[f"{old}→{new}"] = counts.get(f"{old}→{new}", 0) + n

    # 2) 單字（保護詞優先）
    for _label, keep, old, new in CHAR_RULES:
        if old not in text:
            continue
        text, table = _protect(text, keep)
        n = text.count(old)
        if n:
            text = text.replace(old, new)
            counts[f"{old}→{new}"] = counts.get(f"{old}→{new}", 0) + n
        text = _restore(text, table)

    return text, counts


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

    totals: dict[str, int] = {}
    touched = 0
    for p in _iter_files(root):
        try:
            original = p.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        fixed, counts = fix_text(original)
        if fixed == original:
            continue
        touched += 1
        for k, v in counts.items():
            totals[k] = totals.get(k, 0) + v
        if not dry:
            p.write_text(fixed, encoding="utf-8")

    print(f"{'[dry-run] ' if dry else ''}修正 {touched} 個檔案")
    for k, v in sorted(totals.items(), key=lambda t: -t[1]):
        print(f"  {v:5d}  {k}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
