"""知識庫：把 references 的 12 冊技法文檔切成小節、建立索引，依占問與卦象擷取。

設計原則（沿用原專案哲學）：
* **機械層**（排盤、旺衰、空亡、暗動…）交給引擎算，不讓 LLM 猜。
* **推理層**才需要知識庫：把「怎麼判」的方法論餵給 LLM，讓它有依據。
* 依卦盤出現的象（暗動、月破、化退、三合、入墓…）**動態挑選**相關章節，
  避免把 90KB 全塞進 prompt（省 token、也更聚焦）。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
REFERENCES_DIR = ROOT / "references"
SKILL_PATH = ROOT / "skill" / "liuyao-divination" / "SKILL.md"


@dataclass
class Section:
    """一個可擷取的知識小節。"""

    doc: str            # 檔名（不含 .md）
    title: str          # 小節標題
    text: str           # 正文
    order: int          # 全書順序（供排序）
    keywords: set[str] = field(default_factory=set)

    def preview(self, n: int = 120) -> str:
        t = re.sub(r"\s+", " ", self.text).strip()
        return t[:n] + ("…" if len(t) > n else "")


#: 各冊的主題關鍵詞（供檢索加權）
DOC_TOPICS: dict[str, str] = {
    "01": "裝卦 排盤 納甲 六親 世應 六神 宮位 定盤",
    "02": "用神 取用 六親 占事 父母 兄弟 子孫 妻財 官鬼",
    "03": "旺衰 月建 日辰 當令 旺相休囚死 十二長生 有根",
    "04": "動靜 暗動 月破 日破 空亡 旬空 沖 靜爻",
    "05": "化進 化退 進神 退神 回頭生 回頭克 變爻 變卦",
    "06": "三合 六合 六沖 合局 虛合 實局 填實 入局從化",
    "07": "墓庫 入墓 空墓 出墓 沖墓 木墓未 火墓戌 金墓丑 水墓辰",
    "08": "步驟 流程 八步 綜合 定性 走查 案例",
    "09": "元神 忌神 仇神 四神 有力 無力 見生不生 雖動不克",
    "10": "卦變 反吟 伏吟 生克 墓絕 反覆",
    "12": "應期 應驗 時間窗 值日 填實 沖墓 當令 多通道 分層",
    "13": "象意 取象 同象異讀 七層象源 象核 六神 爻位",
}

#: 卦盤象 → 應該載入的冊別（依判定結果動態組 prompt 用）
SIGN_TO_DOCS: dict[str, list[str]] = {
    "暗動": ["04", "09"],
    "日破": ["04"],
    "月破": ["04"],
    "空亡": ["04", "07"],
    "真空": ["04"],
    "化進神": ["05"],
    "化退神": ["05"],
    "化回頭生": ["05", "09"],
    "化回頭克": ["05", "09"],
    "入墓": ["07"],
    "空墓": ["07"],
    "三合": ["06"],
    "六合": ["06"],
    "六沖": ["06"],
    "反吟": ["10"],
    "伏吟": ["10"],
    "卦變": ["10"],
    "應期": ["12"],
    "象意": ["13"],
    "用神": ["02"],
    "元神": ["09"],
    "忌神": ["09"],
}


# ────────────────────────────── 切分 ──────────────────────────────

_HEADING_RE = re.compile(r"^(#{1,4})\s+(.*)$")


def split_markdown(text: str, doc: str) -> list[Section]:
    """把一篇 markdown 依標題切成小節（保留標題行）。"""
    lines = text.splitlines()
    sections: list[Section] = []
    cur_title = "（前言）"
    cur_lines: list[str] = []
    order = 0

    def flush():
        nonlocal cur_lines, order
        body = "\n".join(cur_lines).strip()
        if body:
            sections.append(Section(doc=doc, title=cur_title, text=body, order=order))
            order += 1
        cur_lines = []

    for line in lines:
        m = _HEADING_RE.match(line)
        if m:
            flush()
            cur_title = m.group(2).strip()
            cur_lines = [line]
        else:
            cur_lines.append(line)
    flush()
    return sections


def _tokenize(text: str) -> set[str]:
    """中文斷詞：以 2-4 字滑窗 + 英文詞彙，用於寬鬆比對。"""
    text = re.sub(r"[^\w\u4e00-\u9fff]+", " ", text)
    toks: set[str] = set()
    for chunk in text.split():
        if re.fullmatch(r"[a-zA-Z0-9]+", chunk):
            toks.add(chunk.lower())
            continue
        for n in (2, 3, 4):
            for i in range(len(chunk) - n + 1):
                toks.add(chunk[i:i + n])
    return toks


# ────────────────────────────── 索引 ──────────────────────────────

class KnowledgeBase:
    """12 冊技法的檢索器。"""

    def __init__(self, refs_dir: Path = REFERENCES_DIR,
                 skill_path: Path = SKILL_PATH) -> None:
        self.refs_dir = refs_dir
        self.skill_path = skill_path
        self.sections: list[Section] = []
        self.doc_texts: dict[str, str] = {}
        self._load()

    def _load(self) -> None:
        for p in sorted(self.refs_dir.glob("*.md")):
            doc = p.stem
            text = p.read_text(encoding="utf-8")
            self.doc_texts[doc] = text
            for sec in split_markdown(text, doc):
                # 標題也算關鍵詞來源
                sec.keywords = _tokenize(sec.title + " " + sec.text)
                self.sections.append(sec)

    # —— 對外查詢 ——

    def doc(self, prefix: str) -> str:
        """取整冊原文（prefix 可為 '08' 或 '08-斷卦步驟'）。"""
        for name, text in self.doc_texts.items():
            if name.startswith(prefix):
                return text
        return ""

    def skill(self) -> str:
        """取 SKILL.md 全文（斷卦方法論主文）。"""
        try:
            return self.skill_path.read_text(encoding="utf-8")
        except OSError:
            return ""

    def search(self, query: str, top_k: int = 5,
               doc_filter: list[str] | None = None) -> list[Section]:
        """依關鍵詞檢索最相關的小節。"""
        q_tokens = _tokenize(query)
        if not q_tokens:
            return []
        scored: list[tuple[float, Section]] = []
        for sec in self.sections:
            if doc_filter and not any(sec.doc.startswith(d) for d in doc_filter):
                continue
            overlap = len(q_tokens & sec.keywords)
            if overlap == 0:
                continue
            # 短節點稍微降權，避免只命中一兩字就排前面
            length_penalty = 1.0 + min(len(sec.text), 4000) / 8000.0
            # 標題命中加重
            title_bonus = 3.0 * len(_tokenize(sec.title) & q_tokens)
            score = (overlap + title_bonus) / length_penalty
            scored.append((score, sec))
        scored.sort(key=lambda t: t[0], reverse=True)
        return [s for _, s in scored[:top_k]]

    def sections_for_board(self, board: dict, question: str,
                           max_docs: int = 4) -> list[str]:
        """依卦盤出現的象 + 占問，挑出最相關的幾冊。

        作法：每冊給一個「基礎優先度」，再依卦盤實際出現的象加分，
        取分數最高者；同時保證「用神(02)」與「動靜暗破(04)」兩冊入選
        （因為任何一卦都要取用神、都要看動靜空破）。
        """
        # 基礎優先度：愈核心愈高
        base = {
            "02": 6.0,   # 用神取用：每卦必用
            "04": 5.0,   # 動靜暗破：每卦必查
            "03": 4.0,   # 旺衰月日：每卦必看
            "09": 3.5,   # 四神有力無力
            "05": 2.0,   # 化進退
            "06": 2.0,   # 三合六合
            "07": 2.0,   # 墓庫
            "10": 1.5,   # 卦變反伏
            "12": 2.5,   # 應期
            "13": 2.0,   # 象意
            "08": 1.0,   # 步驟（精華已在 SKILL）
        }
        score = dict(base)

        # 依卦盤的象加分
        tags: set[str] = set()
        for ln in board.get("lines", []):
            tags.update(ln.get("tags", []))
            if ln.get("jin_tui"):
                tags.add(ln["jin_tui"])
            if ln.get("role") in ("元神", "忌神"):
                tags.add(ln["role"])
        if board.get("sanhe"):
            tags.add("三合")
        if board.get("is_liuhe_gua") or board.get("changed_is_liuhe"):
            tags.add("六合")
        if board.get("is_liuchong_gua") or board.get("changed_is_liuchong"):
            tags.add("六沖")
        if board.get("fan_yin"):
            tags.add("反吟")
        if board.get("fu_yin"):
            tags.add("伏吟")
        if board.get("changed_hexagram"):
            tags.add("卦變")

        for tag in tags:
            for doc in SIGN_TO_DOCS.get(tag, []):
                score[doc] = score.get(doc, 0.0) + 2.5

        # 應期與象意是解讀收尾必備，給保底分數
        score["12"] = max(score.get("12", 0), 2.5)
        score["13"] = max(score.get("13", 0), 2.0)

        ranked = sorted(
            (d for d in score if d in self._doc_prefixes()),
            key=lambda d: score[d], reverse=True,
        )

        chosen: list[str] = []
        # 保證核心兩冊
        for must in ("02", "04"):
            if must in ranked and must not in chosen:
                chosen.append(must)
        for d in ranked:
            if len(chosen) >= max_docs:
                break
            if d not in chosen:
                chosen.append(d)
        # 依冊號排序，閱讀順序較自然
        chosen.sort()
        return chosen

    def _doc_prefixes(self) -> set[str]:
        return {name.split("-")[0] for name in self.doc_texts}

    def build_context(self, board: dict, question: str,
                      per_doc_chars: int = 3000,
                      max_docs: int = 4) -> str:
        """組出給 LLM 的知識庫上下文（含 SKILL 方法論摘要 + 相關章節）。"""
        parts: list[str] = []

        # 1. 方法論主文：八步流程 + 關鍵辨析
        skill = self.skill()
        if skill:
            core = _extract_skill_core(skill)
            parts.append("## 斷卦方法論（摘自本專案 SKILL.md）\n\n" + core)

        # 2. 依象擷取相關技法章節
        docs = self.sections_for_board(board, question, max_docs=max_docs)
        for doc in docs:
            text = self.doc(doc)
            if not text:
                continue
            body = _trim_doc(text, per_doc_chars)
            parts.append(f"## 技法參考：{doc}\n\n{body}")

        return "\n\n---\n\n".join(parts)


def _extract_skill_core(skill: str) -> str:
    """從 SKILL.md 抽出「解讀流程」與「關鍵辨析」兩段（最核心、最省 token）。"""
    out: list[str] = []
    # 抓「Interpretation Workflow」到「Quick Reference」之間
    m = re.search(r"## Interpretation Workflow.*?(?=## Quick Reference)", skill, re.S)
    if m:
        out.append(m.group(0).strip())
    m = re.search(r"## Critical Distinctions.*?(?=## Quick Reference)", skill, re.S)
    if m:
        out.append(m.group(0).strip())
    if not out:                      # 結構不同的話退回全文前 6000 字
        return skill[:6000]
    return "\n\n".join(out)


def _trim_doc(text: str, limit: int) -> str:
    """整冊太長時，保留開頭與標題骨架，避免爆 token。"""
    if len(text) <= limit:
        return text
    # 保留所有標題行 + 前段正文
    heads = [ln for ln in text.splitlines() if ln.startswith("#")]
    head_block = "\n".join(heads[:60])
    return text[:limit] + "\n\n…（後略）\n\n【本冊標題索引】\n" + head_block


# ────────────────────────────── 單例 ──────────────────────────────

@lru_cache(maxsize=1)
def get_kb() -> KnowledgeBase:
    return KnowledgeBase()


# ────────────────────────────── 術語表 ──────────────────────────────

@lru_cache(maxsize=1)
def get_glossary() -> dict[str, str]:
    """術語解釋表（給前端點擊彈窗用）。"""
    import json

    path = ROOT / "data" / "glossary.json"
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
